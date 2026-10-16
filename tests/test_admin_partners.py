import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from database.models import AuthSession, Partner, PartnerStatus
from web import auth_api
from web.app import app


def _partner(
    session_factory,
    *,
    first_name: str,
    role: str = "partner",
    root: bool = False,
    upline_id: int | None = None,
    email: str | None = None,
) -> int:
    session = session_factory()
    partner = Partner(
        first_name=first_name,
        last_name="List",
        email=email or f"{first_name}@example.test",
        phone="+15550002001",
        upline_id=upline_id,
        lineage=[] if upline_id is None else [upline_id],
        role=role,
        status=PartnerStatus.ACTIVE,
    )
    session.add(partner)
    session.flush()
    if root:
        partner.root_id = partner.id
        partner.upline_id = None
    elif upline_id is not None:
        partner.root_id = upline_id
    session.commit()
    partner_id = partner.id
    session.close()
    return partner_id


def _session_token(session_factory, partner_id: int) -> str:
    token = f"admin-list-token-{partner_id}"
    now = datetime.now(timezone.utc)
    session = session_factory()
    session.add(
        AuthSession(
            partner_id=partner_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=now + timedelta(days=1),
        )
    )
    session.commit()
    session.close()
    return token


@pytest.fixture
def client(isolated_database, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    test_client = TestClient(app)
    try:
        yield test_client, isolated_database
    finally:
        test_client.close()


def _as_admin(client, session_factory) -> int:
    partner_id = _partner(
        session_factory,
        first_name="AdminViewer",
        role="admin",
        email="admin-viewer@example.test",
    )
    client.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        _session_token(session_factory, partner_id),
    )
    return partner_id


def test_admin_partners_requires_session(client):
    test_client, _ = client
    response = test_client.get("/admin/partners")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_admin_partners_rejects_regular_partner(client):
    test_client, session_factory = client
    partner_id = _partner(
        session_factory,
        first_name="Regular",
        email="regular-list@example.test",
    )
    test_client.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        _session_token(session_factory, partner_id),
    )

    response = test_client.get("/admin/partners")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_partners_rejects_root_without_admin_role(client):
    test_client, session_factory = client
    partner_id = _partner(
        session_factory,
        first_name="RootPartner",
        root=True,
        email="root-list@example.test",
    )
    test_client.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        _session_token(session_factory, partner_id),
    )

    response = test_client.get("/admin/partners")

    assert response.status_code == 403


def test_admin_receives_limited_partner_fields(client):
    test_client, session_factory = client
    root_id = _partner(
        session_factory,
        first_name="ListedRoot",
        root=True,
        email="listed-root@example.test",
    )
    _partner(
        session_factory,
        first_name="ListedChild",
        upline_id=root_id,
        email="listed-child@example.test",
    )
    admin_id = _as_admin(test_client, session_factory)

    response = test_client.get("/admin/partners")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert [item["id"] for item in payload["items"]] == sorted(
        item["id"] for item in payload["items"]
    )
    allowed = {
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "role",
        "status",
        "root_id",
        "upline_id",
        "is_permanent_root",
        "is_active",
    }
    by_id = {item["id"]: item for item in payload["items"]}
    assert root_id in by_id
    assert admin_id in by_id
    assert len(by_id) == 3
    for item in payload["items"]:
        assert set(item) == allowed
        assert "telegram_link_code" not in item
        assert "referral_code" not in item
    root = by_id[root_id]
    assert root["is_permanent_root"] is True
    assert root["is_active"] is True
    assert root["status"] == "active"
    assert root["role"] == "partner"
    child = next(item for item in payload["items"] if item["upline_id"] == root_id)
    assert child["is_permanent_root"] is False
    assert child["is_active"] is False
    assert by_id[admin_id]["role"] == "admin"


def test_admin_partners_pagination_reports_total(client):
    test_client, session_factory = client
    ids = [
        _partner(
            session_factory,
            first_name=f"Page{index}",
            email=f"page{index}@example.test",
        )
        for index in range(3)
    ]
    _as_admin(test_client, session_factory)

    response = test_client.get("/admin/partners?limit=1&offset=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == sorted(ids)[1]


def test_admin_partners_rejects_invalid_paging(client):
    test_client, session_factory = client
    _as_admin(test_client, session_factory)

    assert test_client.get("/admin/partners?limit=0").status_code == 422
    assert test_client.get("/admin/partners?limit=101").status_code == 422
    assert test_client.get("/admin/partners?offset=-1").status_code == 422


def test_admin_partners_route_is_on_web_app():
    from web.admin_api import router as admin_router

    included = [
        route
        for route in app.routes
        if type(route).__name__ == "_IncludedRouter"
        and route.original_router is admin_router
    ]
    declared = {getattr(route, "path", None) for route in admin_router.routes}

    assert included
    assert "/admin/partners" in declared
    assert TestClient(app).get("/admin/partners").status_code == 401
