from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, current_thread
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from database.base import Base
from database.migrations import upgrade_schema
from database.models import Partner
from database.models import RootAllocationLock
from services import partner_service as partner_service_module
from services.distribution_service import DistributionService
from services.partner_service import PartnerService
from services.root_allocation_lock import acquire_root_allocation_lock
from web import order_handler


def _registration_request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/register",
            "raw_path": b"/register",
            "query_string": b"",
            "headers": [],
            "client": ("test", 123),
            "server": ("test", 80),
        }
    )


def create_partner(*, name, upline_id=None, telegram_id=None):
    if upline_id is None:
        raise ValueError("Tests must pass an explicit referral/upline")
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
    session.flush()
    for root in roots:
        root.root_id = root.id
    session.commit()
    root_ids = [root.id for root in roots]
    session.close()
    return root_ids


def test_regular_registration_requires_existing_roots_and_referral(
    isolated_database,
):
    service = PartnerService()
    with pytest.raises(ValueError, match="System is not ready"):
        service.create_partner(
            telegram_id=None,
            first_name="Cannot bootstrap Root",
        )

    session = isolated_database()
    try:
        assert session.query(Partner).count() == 0
    finally:
        session.close()

    root_ids = seed_root_pair(isolated_database)
    with pytest.raises(ValueError, match="referral link is required"):
        service.create_partner(
            telegram_id=None,
            first_name="Missing referral",
        )

    partner_id = create_partner(
        name="Referred partner",
        upline_id=root_ids[0],
    )
    session = isolated_database()
    try:
        partner = session.get(Partner, partner_id)
        assert partner.upline_id == root_ids[0]
        assert partner.root_id == root_ids[0]
        assert partner.root_id != partner.id
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
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


def test_registration_with_referral_fails_until_both_roots_exist(
    isolated_database,
):
    session = isolated_database()
    first_root = Partner(first_name="Only root")
    session.add(first_root)
    session.flush()
    first_root.root_id = first_root.id
    session.commit()
    first_root_id = first_root.id
    session.close()

    with pytest.raises(ValueError, match="System is not ready"):
        create_partner(
            name="Registration before Root two",
            upline_id=first_root_id,
        )
    session = isolated_database()
    try:
        assert session.query(Partner).count() == 1
    finally:
        session.close()


def test_public_registration_without_ref_does_not_create_root(
    isolated_database,
    monkeypatch,
):
    from web import app as public_app

    seed_root_pair(isolated_database)
    monkeypatch.setattr(
        partner_service_module,
        "SessionLocal",
        isolated_database,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            public_app.register_user(
                _registration_request(),
                first_name="Public",
                last_name="Registrant",
                email="public-no-ref@example.test",
                phone="",
                ref=None,
                consent="on",
            )
        )

    assert error.value.status_code == 400
    assert "referral link is required" in error.value.detail
    session = isolated_database()
    try:
        assert session.query(Partner).count() == 2
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
    finally:
        session.close()


def test_public_registration_without_root_pair_reports_system_not_ready(
    isolated_database,
    monkeypatch,
):
    from web import app as public_app

    monkeypatch.setattr(
        partner_service_module,
        "SessionLocal",
        isolated_database,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            public_app.register_user(
                _registration_request(),
                first_name="Public",
                last_name="Registrant",
                email="public-before-roots@example.test",
                phone="",
                ref=None,
                consent="on",
            )
        )

    assert error.value.status_code == 400
    assert "System is not ready" in error.value.detail
    session = isolated_database()
    try:
        assert session.query(Partner).count() == 0
    finally:
        session.close()


def test_public_registration_with_two_roots_creates_regular_partner(
    isolated_database,
    monkeypatch,
):
    from web import app as public_app

    root_ids = seed_root_pair(isolated_database)
    session = isolated_database()
    referral_code = session.get(Partner, root_ids[0]).referral_code
    session.close()
    monkeypatch.setattr(
        partner_service_module,
        "SessionLocal",
        isolated_database,
    )

    @contextmanager
    def test_session():
        session = isolated_database()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(public_app, "get_session", test_session)
    response = asyncio.run(
        public_app.register_user(
            _registration_request(),
            first_name="Public",
            last_name="Registrant",
            email="public-referred@example.test",
            phone="",
            ref=referral_code,
            consent="on",
        )
    )

    assert response.status_code == 200
    session = isolated_database()
    try:
        partner = session.query(Partner).filter_by(
            email="public-referred@example.test"
        ).one()
        assert partner.upline_id == root_ids[0]
        assert partner.root_id == root_ids[0]
        assert partner.root_id != partner.id
        assert session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).count() == 2
    finally:
        session.close()


def test_admin_endpoint_creates_only_two_roots(
    isolated_database,
    monkeypatch,
):
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr(
        partner_service_module,
        "SessionLocal",
        isolated_database,
    )
    monkeypatch.setattr(order_handler, "DEBUG", True)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", "test-secret")

    client = TestClient(app)
    assert client.post("/create-root").status_code == 401
    headers = {"X-Admin-Secret": "test-secret"}
    first = client.post(
        "/create-root",
        params={"first_name": "Admin Root 1"},
        headers=headers,
    )
    second = client.post(
        "/create-root",
        params={"first_name": "Admin Root 2"},
        headers=headers,
    )
    third = client.post(
        "/create-root",
        params={"first_name": "Forbidden Root 3"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["root_id"] == first.json()["id"]
    assert second.json()["root_id"] == second.json()["id"]
    assert third.status_code == 400

    session = isolated_database()
    try:
        roots = session.query(Partner).filter(
            Partner.upline_id.is_(None),
            Partner.root_id == Partner.id,
        ).all()
        assert len(roots) == 2
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

    session = isolated_database()
    first_expected_root = DistributionService().get_upline_for_new_partner(
        session
    )
    session.close()
    first_free_id = create_partner(
        name="Free registrant one",
        upline_id=first_expected_root,
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
            upline_id=expected_root,
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
    session = isolated_database()
    referral_id = DistributionService().get_upline_for_new_partner(session)
    session.close()
    create_partner(
        name="Existing telegram",
        upline_id=referral_id,
        telegram_id="root-lock-duplicate",
    )

    with pytest.raises(IntegrityError):
        create_partner(
            name="Failed registration",
            upline_id=referral_id,
            telegram_id="root-lock-duplicate",
        )

    session = isolated_database()
    next_referral_id = DistributionService().get_upline_for_new_partner(
        session
    )
    session.close()
    next_id = create_partner(
        name="Registration after rollback",
        upline_id=next_referral_id,
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


def test_concurrent_registrations_serialize_after_root_bootstrap(
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
    root_ids = seed_root_pair(session_factory)

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
        return create_partner(
            name=f"{name} partner",
            upline_id=root_ids[0],
        )

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
        assert session.query(Partner).count() == 4
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
