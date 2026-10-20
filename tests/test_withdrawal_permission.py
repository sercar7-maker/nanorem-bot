import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from database.migrations import upgrade_schema
from database.models import AuthSession, Partner, PartnerStatus
from web import auth_api
from web.app import app


def add_partner(
    factory,
    *,
    first_name="Permission partner",
    role="partner",
    root=False,
    allowed=False,
    email=None,
):
    session = factory()
    partner = Partner(
        first_name=first_name,
        email=email or f"{first_name}@example.test",
        phone="+15550003001",
        role=role,
        status=PartnerStatus.ACTIVE,
        lineage=[],
        can_process_withdrawals=allowed,
    )
    session.add(partner)
    session.flush()
    if root:
        partner.root_id = partner.id
        partner.upline_id = None
    session.commit()
    partner_id = partner.id
    session.close()
    return partner_id


def store_session(factory, partner_id, *, expired=False, revoked=False):
    token = f"withdrawal-permission-{partner_id}-{expired}-{revoked}"
    now = datetime.now(timezone.utc)
    session = factory()
    session.add(AuthSession(
        partner_id=partner_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(days=-1 if expired else 1),
        revoked_at=now if revoked else None,
    ))
    session.commit()
    session.close()
    return token


def set_permission(factory, partner_id, allowed):
    session = factory()
    session.get(Partner, partner_id).can_process_withdrawals = allowed
    session.commit()
    session.close()


@pytest.fixture
def permission_clients(isolated_database, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    probe = FastAPI()

    @probe.get("/withdrawal-processing-check")
    def withdrawal_processing_check(
        partner: Partner = Depends(auth_api.require_withdrawal_processor),
    ):
        return {
            "id": partner.id,
            "role": partner.role,
            "can_process_withdrawals": bool(
                partner.can_process_withdrawals
            ),
        }

    probe_client = TestClient(probe)
    cabinet = TestClient(app)
    try:
        yield probe_client, cabinet, isolated_database
    finally:
        probe_client.close()
        cabinet.close()


def test_new_partner_cannot_process_withdrawals(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="Default permission")
    session.add(partner)
    session.commit()
    assert partner.can_process_withdrawals is False
    assert partner.role == "partner"
    session.close()


def test_me_returns_current_permission(permission_clients):
    probe, cabinet, factory = permission_clients
    partner_id = add_partner(
        factory,
        first_name="Own permission",
        email="own-permission@example.test",
    )
    token = store_session(factory, partner_id)
    cabinet.cookies.set(auth_api.SESSION_COOKIE_NAME, token)

    denied = cabinet.get("/auth/me")
    assert denied.status_code == 200
    assert denied.json()["id"] == partner_id
    assert denied.json()["can_process_withdrawals"] is False
    assert denied.json()["role"] == "partner"

    set_permission(factory, partner_id, True)
    allowed = cabinet.get("/auth/me")
    assert allowed.json()["can_process_withdrawals"] is True
    assert allowed.json()["role"] == "partner"

    set_permission(factory, partner_id, False)
    assert cabinet.get("/auth/me").json()["can_process_withdrawals"] is False


def test_processing_check_requires_session(permission_clients):
    probe, _, _ = permission_clients
    response = probe.get("/withdrawal-processing-check")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.parametrize("kind", ["partner", "root", "admin"])
def test_authenticated_partner_without_permission_is_forbidden(
    permission_clients, kind,
):
    probe, _, factory = permission_clients
    partner_id = add_partner(
        factory,
        first_name=f"No permission {kind}",
        email=f"no-permission-{kind}@example.test",
        role="admin" if kind == "admin" else "partner",
        root=kind == "root",
        allowed=False,
    )
    probe.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        store_session(factory, partner_id),
    )

    response = probe.get("/withdrawal-processing-check")

    assert response.status_code == 403
    assert response.json()["detail"] == "Withdrawal processing is not allowed"


def test_partner_with_permission_is_allowed_without_admin_access(
    permission_clients,
):
    probe, cabinet, factory = permission_clients
    partner_id = add_partner(
        factory,
        first_name="Processor",
        email="processor@example.test",
        role="partner",
        allowed=True,
    )
    token = store_session(factory, partner_id)
    probe.cookies.set(auth_api.SESSION_COOKIE_NAME, token)
    cabinet.cookies.set(auth_api.SESSION_COOKIE_NAME, token)

    response = probe.get("/withdrawal-processing-check")
    assert response.status_code == 200
    assert response.json() == {
        "id": partner_id,
        "role": "partner",
        "can_process_withdrawals": True,
    }
    assert cabinet.get("/admin/partners").status_code == 403


def test_revoked_permission_blocks_the_existing_cookie(permission_clients):
    probe, _, factory = permission_clients
    partner_id = add_partner(
        factory,
        first_name="Revoked processor",
        email="revoked-processor@example.test",
        allowed=True,
    )
    probe.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        store_session(factory, partner_id),
    )
    assert probe.get("/withdrawal-processing-check").status_code == 200

    set_permission(factory, partner_id, False)

    response = probe.get("/withdrawal-processing-check")
    assert response.status_code == 403
    assert response.json()["detail"] == "Withdrawal processing is not allowed"


@pytest.mark.parametrize("expired", [True, False])
def test_unusable_session_is_rejected_even_with_permission(
    permission_clients, expired,
):
    probe, _, factory = permission_clients
    partner_id = add_partner(
        factory,
        first_name="Expired processor",
        email=f"unusable-{expired}@example.test",
        allowed=True,
    )
    probe.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        store_session(
            factory,
            partner_id,
            expired=expired,
            revoked=not expired,
        ),
    )

    response = probe.get("/withdrawal-processing-check")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def _rows(connection, sql):
    return [tuple(row) for row in connection.execute(text(sql))]


def test_legacy_partners_gain_false_permission_without_role_changes(tmp_path):
    database = tmp_path / "legacy-permissions.sqlite"
    assert database.name != "nanorem.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE partners ("
                "id INTEGER PRIMARY KEY, "
                "first_name VARCHAR, "
                "last_name VARCHAR, "
                "email VARCHAR, "
                "phone VARCHAR, "
                "role VARCHAR, "
                "referral_code VARCHAR(32), "
                "upline_id INTEGER, "
                "root_id INTEGER, "
                "placement_version INTEGER NOT NULL DEFAULT 0, "
                "consent_given BOOLEAN NOT NULL DEFAULT 0, "
                "consent_version VARCHAR(50), "
                "consent_date DATETIME, "
                "annual_activity_until DATETIME)"
            ))
            connection.execute(text(
                "INSERT INTO partners "
                "(id, first_name, last_name, email, phone, role, "
                "referral_code, upline_id, root_id, placement_version, "
                "consent_given) VALUES "
                "(1, 'Root', 'One', 'root-one@example.test', "
                "'+10000000001', 'admin', 'nr_legacy_root_one', "
                "NULL, 1, 0, 0), "
                "(2, 'Root', 'Two', 'root-two@example.test', "
                "'+10000000002', 'partner', 'nr_legacy_root_two', "
                "NULL, 2, 0, 0), "
                "(3, 'Member', 'Three', 'member@example.test', "
                "'+10000000003', 'partner', 'nr_legacy_member', "
                "1, 1, 0, 0)"
            ))

        original_sql = (
            "SELECT id, first_name, last_name, email, phone, role, "
            "referral_code, upline_id, root_id, placement_version, "
            "consent_given FROM partners ORDER BY id"
        )
        with engine.connect() as connection:
            before = _rows(connection, original_sql)

        upgrade_schema(engine)
        upgrade_schema(engine)

        with engine.connect() as connection:
            assert _rows(connection, original_sql) == before
            flags = _rows(
                connection,
                "SELECT id, role, can_process_withdrawals "
                "FROM partners ORDER BY id",
            )
        assert flags == [
            (1, "admin", 0),
            (2, "partner", 0),
            (3, "partner", 0),
        ]
        column = next(
            item for item in inspect(engine).get_columns("partners")
            if item["name"] == "can_process_withdrawals"
        )
        assert column["nullable"] is False

        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO partners "
                "(first_name, role, referral_code, root_id, "
                "placement_version, consent_given) "
                "VALUES ('Later', 'partner', 'nr_legacy_later', 1, 0, 0)"
            ))
            later = connection.execute(text(
                "SELECT role, can_process_withdrawals FROM partners "
                "WHERE first_name = 'Later'"
            )).one()
        assert tuple(later) == ("partner", 0)
    finally:
        engine.dispose()
