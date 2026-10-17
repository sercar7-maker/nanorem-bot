from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.models import AuthSession, Base, Partner
from database.models_cabinet import CabinetOwner, CabinetPosition
from database.models_cabinet_contacts import CabinetContact
from database.cabinet_migration import backfill_cabinet_owners
from database.cabinet_contacts_migration import (
    CabinetContactMigrationError,
    backfill_cabinet_contacts,
    create_cabinet_contacts_schema,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            Partner.__table__,
            AuthSession.__table__,
            CabinetOwner.__table__,
            CabinetPosition.__table__,
            CabinetContact.__table__,
        ],
    )

    try:
        with sessionmaker(bind=engine)() as session:
            yield session, engine
    finally:
        engine.dispose()


def add_partner(session, **values):
    partner = Partner(first_name="Existing partner", **values)
    session.add(partner)
    session.flush()
    return partner


def link_secondary(session, primary, secondary):
    primary_owner = session.get(CabinetPosition, primary.id).owner_id
    secondary_owner = session.query(CabinetOwner).filter_by(
        primary_partner_id=secondary.id
    ).one()

    session.get(CabinetPosition, secondary.id).owner_id = primary_owner
    session.flush()
    session.delete(secondary_owner)
    session.flush()


def test_schema_is_repeatable(db):
    _, engine = db
    create_cabinet_contacts_schema(engine)
    create_cabinet_contacts_schema(engine)
    assert "cabinet_contacts" in inspect(engine).get_table_names()


def test_schema_requires_ownership_tables():
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(RuntimeError, match="Required table"):
            create_cabinet_contacts_schema(engine)
    finally:
        engine.dispose()


def test_normalization_unverified_and_repeatable(db):
    session, _ = db
    add_partner(
        session,
        email=" Owner@Example.com ",
        phone="+7 (999) 123-45-67",
    )
    backfill_cabinet_owners(session)

    assert backfill_cabinet_contacts(session) == 2
    assert backfill_cabinet_contacts(session) == 0

    contacts = session.query(CabinetContact).all()
    assert {
        (contact.channel, contact.normalized_value)
        for contact in contacts
    } == {
        ("email", "owner@example.com"),
        ("phone", "+79991234567"),
    }
    assert all(contact.verified_at is None for contact in contacts)


def test_empty_contacts_are_skipped(db):
    session, _ = db
    add_partner(session, email=" ", phone=None)
    backfill_cabinet_owners(session)
    assert backfill_cabinet_contacts(session) == 0


@pytest.mark.parametrize(
    "channel,first,second",
    [
        ("email", "Owner@example.com", " owner@example.com "),
        ("phone", "+7 (999) 123-45-67", "+79991234567"),
    ],
)
def test_cross_owner_conflict_is_atomic(db, channel, first, second):
    session, _ = db
    add_partner(session, email="unique@example.com")
    add_partner(session, **{channel: first})
    add_partner(session, **{channel: second})
    backfill_cabinet_owners(session)

    with pytest.raises(CabinetContactMigrationError, match="Conflicting"):
        backfill_cabinet_contacts(session)

    assert session.query(CabinetContact).count() == 0


def test_secondary_contacts_are_not_imported(db):
    session, _ = db
    primary = add_partner(session, email="primary@example.com")
    secondary = add_partner(session, email="secondary@example.com")
    backfill_cabinet_owners(session)
    link_secondary(session, primary, secondary)

    assert backfill_cabinet_contacts(session) == 1
    assert session.query(CabinetContact).one().normalized_value == (
        "primary@example.com"
    )


def test_equal_contacts_within_one_owner_are_allowed(db):
    session, _ = db
    primary = add_partner(session, phone="+79991234567")
    secondary = add_partner(session, phone="+7 (999) 123-45-67")
    backfill_cabinet_owners(session)
    link_secondary(session, primary, secondary)

    assert backfill_cabinet_contacts(session) == 1
    assert session.query(CabinetContact).count() == 1


def test_secondary_contact_can_block_another_owner(db):
    session, _ = db
    primary = add_partner(session)
    secondary = add_partner(session, phone="+79991234567")
    add_partner(session, phone="+7 (999) 123-45-67")
    backfill_cabinet_owners(session)
    link_secondary(session, primary, secondary)

    with pytest.raises(CabinetContactMigrationError, match="Conflicting"):
        backfill_cabinet_contacts(session)

    assert session.query(CabinetContact).count() == 0


def test_invalid_contact_blocks_import(db):
    session, _ = db
    add_partner(session, email="valid@example.com")
    add_partner(session, phone="not-a-phone")
    backfill_cabinet_owners(session)

    with pytest.raises(CabinetContactMigrationError, match="Invalid phone"):
        backfill_cabinet_contacts(session)

    assert session.query(CabinetContact).count() == 0


def test_missing_ownership_blocks_import(db):
    session, _ = db
    add_partner(session, email="owner@example.com")

    with pytest.raises(
        CabinetContactMigrationError,
        match="Missing ownership",
    ):
        backfill_cabinet_contacts(session)


def test_invalid_primary_position_blocks_import(db):
    session, _ = db
    first = add_partner(session)
    second = add_partner(session)
    backfill_cabinet_owners(session)

    first_owner = session.get(CabinetPosition, first.id).owner_id
    session.get(CabinetPosition, second.id).owner_id = first_owner
    session.flush()

    with pytest.raises(
        CabinetContactMigrationError,
        match="Invalid primary position",
    ):
        backfill_cabinet_contacts(session)


def test_existing_contact_of_another_owner_blocks_import(db):
    session, _ = db
    first = add_partner(session, email="owner@example.com")
    second = add_partner(session)
    backfill_cabinet_owners(session)

    session.add(
        CabinetContact(
            owner_id=session.get(CabinetPosition, second.id).owner_id,
            channel="email",
            normalized_value=first.email,
        )
    )
    session.flush()

    with pytest.raises(
        CabinetContactMigrationError,
        match="Existing email",
    ):
        backfill_cabinet_contacts(session)

    assert session.query(CabinetContact).count() == 1


def test_verification_partner_and_session_are_preserved(db):
    session, _ = db
    partner = add_partner(
        session,
        email="owner@example.com",
        role="admin",
    )
    auth = AuthSession(
        partner_id=partner.id,
        token_hash="unchanged",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(auth)
    backfill_cabinet_owners(session)
    assert backfill_cabinet_contacts(session) == 1

    contact = session.query(CabinetContact).one()
    verified_at = datetime(2026, 1, 1)
    contact.verified_at = verified_at
    session.flush()

    assert backfill_cabinet_contacts(session) == 0
    session.refresh(contact)
    session.refresh(partner)
    session.refresh(auth)

    assert contact.verified_at == verified_at
    assert (partner.email, partner.role) == ("owner@example.com", "admin")
    assert auth.partner_id == partner.id
    assert auth.token_hash == "unchanged"
    assert auth.revoked_at is None
    assert auth.is_active


def test_database_constraints(db):
    session, _ = db
    partner = add_partner(session)
    backfill_cabinet_owners(session)
    owner_id = session.get(CabinetPosition, partner.id).owner_id

    session.add(
        CabinetContact(
            owner_id=owner_id,
            channel="email",
            normalized_value="owner@example.com",
        )
    )
    session.flush()

    invalid_contacts = [
        {
            "owner_id": owner_id,
            "channel": "email",
            "normalized_value": "owner@example.com",
        },
        {
            "owner_id": 999999,
            "channel": "email",
            "normalized_value": "other@example.com",
        },
        {
            "owner_id": owner_id,
            "channel": "fax",
            "normalized_value": "123",
        },
    ]

    for values in invalid_contacts:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(CabinetContact(**values))
                session.flush()


def test_backfill_can_be_rolled_back(db):
    session, _ = db
    add_partner(session, email="owner@example.com")
    backfill_cabinet_owners(session)
    session.commit()

    session.begin()
    session.connection().exec_driver_sql("BEGIN")
    assert backfill_cabinet_contacts(session) == 1

    session.rollback()
    assert session.query(CabinetContact).count() == 0
    assert session.query(CabinetOwner).count() == 1