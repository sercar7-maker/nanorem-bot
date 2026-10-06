from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.base import Base
from database.migrations import upgrade_schema
from database.models import Partner
from database.models import RootAllocationLock
from services import partner_service as partner_service_module
from services.distribution_service import DistributionService
from services.partner_service import PartnerService
from services.root_allocation_lock import acquire_root_allocation_lock


def create_partner(*, name, upline_id=None, telegram_id=None):
    service = PartnerService()
    partner = service.create_partner(
        telegram_id=telegram_id,
        first_name=name,
        upline_id=upline_id,
    )
    return partner.id


def seed_root_pair(session_factory):
    session = session_factory()
    roots = [
        Partner(first_name="Allocation root 1", lineage=[]),
        Partner(first_name="Allocation root 2", lineage=[]),
    ]
    session.add_all(roots)
    session.commit()
    root_ids = [root.id for root in roots]
    session.close()
    return root_ids


def test_first_two_registrations_create_roots_and_third_is_distributed(
    isolated_database,
):
    first_id = create_partner(
        name="First root",
        upline_id=999,
    )
    second_id = create_partner(
        name="Second root",
        upline_id=999,
    )
    third_id = create_partner(
        name="Third partner",
    )

    session = isolated_database()
    try:
        roots = session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).all()
        third = session.get(Partner, third_id)
        assert {root.id for root in roots} == {first_id, second_id}
        assert third.upline_id == second_id
        assert third.lineage == [second_id]
    finally:
        session.close()


def test_explicit_referral_is_preserved_after_root_bootstrap(
    isolated_database,
):
    root_ids = seed_root_pair(isolated_database)

    partner_id = create_partner(
        name="Explicit referral",
        upline_id=root_ids[0],
    )

    session = isolated_database()
    try:
        partner = session.get(Partner, partner_id)
        assert partner.upline_id == root_ids[0]
        assert partner.lineage == [root_ids[0]]
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
    finally:
        session.close()


def test_free_registration_selects_smaller_root_network_and_rebalances(
    isolated_database,
):
    root_ids = seed_root_pair(isolated_database)
    session = isolated_database()
    first_root_children = [
        Partner(
            first_name=f"Root one child {index}",
            upline_id=root_ids[0],
            lineage=[root_ids[0]],
        )
        for index in range(3)
    ]
    second_root_child = Partner(
        first_name="Root two child",
        upline_id=root_ids[1],
        lineage=[root_ids[1]],
    )
    session.add_all([*first_root_children, second_root_child])
    session.commit()
    session.close()

    first_free_id = create_partner(
        name="Free registrant one",
    )
    session = isolated_database()
    first_free = session.get(Partner, first_free_id)
    assert first_free.upline_id == root_ids[1]
    session.close()

    for index in range(5):
        session = isolated_database()
        expected_root = DistributionService().get_upline_for_new_partner(
            session
        )
        session.close()
        partner_id = create_partner(
            name=f"Free registrant {index + 2}",
        )
        session = isolated_database()
        try:
            assert session.get(Partner, partner_id).upline_id == expected_root
        finally:
            session.close()

    session = isolated_database()
    try:
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
    finally:
        session.close()


def test_failed_registration_rolls_back_and_releases_allocation_lock(
    isolated_database,
):
    root_ids = seed_root_pair(isolated_database)
    create_partner(
        name="Existing telegram",
        telegram_id="root-lock-duplicate",
    )

    with pytest.raises(IntegrityError):
        create_partner(
            name="Failed registration",
            telegram_id="root-lock-duplicate",
        )

    next_id = create_partner(
        name="Registration after rollback",
    )

    session = isolated_database()
    try:
        partner = session.get(Partner, next_id)
        assert partner.upline_id in root_ids
        assert session.query(Partner).filter_by(
            first_name="Failed registration"
        ).count() == 0
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
    finally:
        session.close()


def test_concurrent_bootstrap_registrations_serialize_before_root_count(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "concurrent-root-bootstrap.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    upgrade_schema(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(
        partner_service_module,
        "SessionLocal",
        session_factory,
    )

    first_has_lock = Event()
    allow_first_to_continue = Event()
    second_attempting_lock = Event()
    second_has_lock = Event()
    original_acquire = acquire_root_allocation_lock

    def observed_acquire(session):
        if current_thread().name == "second-registration":
            second_attempting_lock.set()

        original_acquire(session)

        if current_thread().name == "first-registration":
            first_has_lock.set()
            if not allow_first_to_continue.wait(timeout=10):
                raise TimeoutError("Timed out waiting to release root lock")
        elif current_thread().name == "second-registration":
            second_has_lock.set()

    def register_named(name):
        current_thread().name = name
        return create_partner(name=f"{name} partner")

    monkeypatch.setattr(
        partner_service_module,
        "acquire_root_allocation_lock",
        observed_acquire,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            register_named,
            "first-registration",
        )
        assert first_has_lock.wait(timeout=5)

        second = executor.submit(
            register_named,
            "second-registration",
        )
        assert second_attempting_lock.wait(timeout=5)

        # The second registration must not get past the singleton-row UPDATE
        # while the first transaction holds its write lock.
        assert not second_has_lock.wait(timeout=0.25)
        allow_first_to_continue.set()

        first.result(timeout=10)
        second.result(timeout=10)

    session = session_factory()
    try:
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
        assert session.query(Partner).count() == 2
    finally:
        session.close()
        engine.dispose()


def test_postgresql_root_lock_selects_singleton_for_update():
    statement = (
        select(RootAllocationLock.id)
        .where(RootAllocationLock.id == 1)
        .with_for_update()
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "FROM root_allocation_lock" in compiled
    assert "WHERE root_allocation_lock.id = %(id_1)s::INTEGER" in compiled
    assert compiled.endswith("FOR UPDATE")
