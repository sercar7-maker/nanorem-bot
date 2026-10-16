from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.models import AuthSession, Base, Partner
from database.models_cabinet import CabinetOwner, CabinetPosition
from database.cabinet_migration import backfill_cabinet_owners, create_cabinet_schema


@pytest.fixture
def cabinet_db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [
        Partner.__table__, AuthSession.__table__,
        CabinetOwner.__table__, CabinetPosition.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as session:
            yield session, engine
    finally:
        engine.dispose()


def add_partner(session, **values):
    partner = Partner(first_name="Existing partner", **values)
    session.add(partner)
    session.flush()
    return partner


def test_schema_creation_is_repeatable(cabinet_db):
    _, engine = cabinet_db
    create_cabinet_schema(engine)
    create_cabinet_schema(engine)
    assert {"cabinet_owners", "cabinet_positions"}.issubset(
        inspect(engine).get_table_names()
    )


def test_schema_requires_partners_table():
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(RuntimeError, match="partners"):
            create_cabinet_schema(engine)
    finally:
        engine.dispose()


def test_backfill_does_not_merge_equal_phones(cabinet_db):
    session, _ = cabinet_db
    first = add_partner(session, phone="+79990000000")
    second = add_partner(session, phone="+79990000000")
    assert backfill_cabinet_owners(session) == 2
    assert session.get(CabinetPosition, first.id).owner_id != (
        session.get(CabinetPosition, second.id).owner_id
    )
    assert backfill_cabinet_owners(session) == 0
    assert session.query(CabinetOwner).count() == 2


def test_one_owner_can_have_multiple_positions(cabinet_db):
    session, _ = cabinet_db
    first = add_partner(session)
    second = add_partner(session)
    owner = CabinetOwner(primary_partner_id=first.id)
    session.add(owner)
    session.flush()
    session.add_all([
        CabinetPosition(partner_id=first.id, owner_id=owner.id),
        CabinetPosition(partner_id=second.id, owner_id=owner.id),
    ])
    session.flush()
    assert backfill_cabinet_owners(session) == 0
    assert session.query(CabinetPosition).filter_by(owner_id=owner.id).count() == 2


def test_position_cannot_have_two_owners(cabinet_db):
    session, _ = cabinet_db
    first = add_partner(session)
    second = add_partner(session)
    backfill_cabinet_owners(session)
    other_owner = session.get(CabinetPosition, second.id).owner_id
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(CabinetPosition(partner_id=first.id, owner_id=other_owner))
            session.flush()


def test_missing_owner_is_rejected(cabinet_db):
    session, _ = cabinet_db
    partner = add_partner(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(CabinetPosition(partner_id=partner.id, owner_id=999999))
            session.flush()


def test_backfill_preserves_partner_and_auth_session(cabinet_db):
    session, _ = cabinet_db
    partner = add_partner(session, email="owner@example.com", role="admin")
    partner.root_id = partner.id
    partner.lineage = []
    auth = AuthSession(
        partner_id=partner.id, token_hash="unchanged-session-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(auth)
    session.commit()
    before = (partner.id, partner.email, partner.role, partner.root_id,
              partner.upline_id, partner.lineage, partner.subscription_end_date)
    auth_id = auth.id
    assert backfill_cabinet_owners(session) == 1
    session.commit()
    session.expire_all()
    partner = session.get(Partner, before[0])
    assert before == (partner.id, partner.email, partner.role, partner.root_id,
                      partner.upline_id, partner.lineage, partner.subscription_end_date)
    auth = session.get(AuthSession, auth_id)
    assert auth.partner_id == partner.id
    assert auth.token_hash == "unchanged-session-hash"
    assert auth.revoked_at is None
    assert auth.is_active


def test_backfill_can_be_rolled_back(cabinet_db):
    session, _ = cabinet_db
    add_partner(session)
    session.commit()
    session.begin()
    session.connection().exec_driver_sql("BEGIN")
    assert backfill_cabinet_owners(session) == 1
    session.rollback()
    assert session.query(CabinetOwner).count() == 0
    assert session.query(CabinetPosition).count() == 0
    assert session.query(Partner).count() == 1
