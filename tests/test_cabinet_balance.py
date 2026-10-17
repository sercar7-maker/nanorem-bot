import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from database.models import AuthSession, Partner
from database.models_balance import Balance, BalanceTransaction
from web import auth_api
from web.app import app


@pytest.fixture
def balance_client(isolated_database, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    client = TestClient(app, base_url="https://testserver")
    try:
        yield client
    finally:
        client.close()


def seed(factory, *, role="partner", amount=None, hold="0.00",
         expired=False, revoked=False):
    with factory() as session:
        partner = Partner(first_name="Balance test", role=role)
        session.add(partner)
        session.flush()
        partner_id = partner.id
        token = f"balance-test-{partner_id}"
        now = datetime.now(timezone.utc)
        session.add(AuthSession(
            partner_id=partner_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now + timedelta(days=-1 if expired else 1),
            revoked_at=now if revoked else None,
        ))
        if amount is not None:
            session.add(Balance(partner_id=partner_id,
                                amount=Decimal(amount), hold=Decimal(hold)))
        session.commit()
    return partner_id, token


@pytest.mark.parametrize("kind", ["missing", "invalid", "expired", "revoked"])
def test_balance_requires_valid_session(balance_client, isolated_database, kind):
    if kind in {"expired", "revoked"}:
        _, token = seed(isolated_database, expired=kind == "expired",
                        revoked=kind == "revoked")
        balance_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)
    elif kind == "invalid":
        balance_client.cookies.set(auth_api.SESSION_COOKIE_NAME, "invalid")
    assert balance_client.get("/auth/me/balance").status_code == 401


@pytest.mark.parametrize("role", ["partner", "admin"])
def test_balance_is_bound_to_session(balance_client, isolated_database, role):
    own_id, token = seed(isolated_database, role=role,
                         amount="1234.56", hold="100.01")
    other_id, _ = seed(isolated_database, amount="99999.99", hold="500.00")
    balance_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)
    expected = {"available": "1234.56", "reserved": "100.01",
                "total": "1334.57", "currency": "RUB"}
    for path in ("/auth/me/balance",
                 f"/auth/me/balance?partner_id={other_id}&owner_id={other_id}"):
        response = balance_client.get(path)
        assert response.status_code == 200
        assert response.json() == expected
        assert response.headers["cache-control"] == "no-store"
    assert balance_client.get(f"/auth/me/balance/{other_id}").status_code == 404
    with isolated_database() as session:
        assert session.get(Balance, own_id).amount == Decimal("1234.56")
        assert session.get(Balance, own_id).hold == Decimal("100.01")
        assert session.get(Balance, other_id).amount == Decimal("99999.99")
        assert session.query(BalanceTransaction).count() == 0


def test_missing_balance_returns_zero_without_creating_rows(
    balance_client, isolated_database,
):
    _, token = seed(isolated_database)
    balance_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)
    for _ in range(2):
        response = balance_client.get("/auth/me/balance")
        assert response.status_code == 200
        assert response.json() == {"available": "0.00", "reserved": "0.00",
                                   "total": "0.00", "currency": "RUB"}
    with isolated_database() as session:
        assert session.query(Balance).count() == 0
        assert session.query(BalanceTransaction).count() == 0


def test_large_balance_keeps_decimal_precision(balance_client, isolated_database):
    _, token = seed(isolated_database, amount="1234567.01", hold="0.02")
    balance_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)
    response = balance_client.get("/auth/me/balance")
    assert response.status_code == 200
    assert response.json()["available"] == "1234567.01"
    assert response.json()["total"] == "1234567.03"


def test_balance_ui_is_connected(balance_client):
    page = balance_client.get("/dashboard")
    assert page.status_code == 200
    for marker in ("balance-available", "balance-reserved", "balance-total",
                   "balance-refresh", "/static/balance.js?v=1"):
        assert marker in page.text
    script = balance_client.get("/static/balance.js")
    assert script.status_code == 200
    assert "/auth/me/balance" in script.text
    assert "textContent" in script.text
