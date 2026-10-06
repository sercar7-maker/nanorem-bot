import pytest
from fastapi.testclient import TestClient

from main import app
from web import order_handler


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/create-partner?telegram_id=123"),
        ("get", "/referral-link?partner_id=1"),
        ("get", "/balance?partner_id=1"),
        ("get", "/transactions?partner_id=1"),
        ("post", "/withdraw?partner_id=1&amount=1"),
        ("post", "/test-order?partner_id=1&amount=1"),
    ],
)
def test_sensitive_routes_reject_missing_admin_secret(
    monkeypatch,
    method,
    path,
):
    monkeypatch.setattr(order_handler, "DEBUG", True)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", "test-secret")

    response = getattr(TestClient(app), method)(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/create-partner?telegram_id=123"),
        ("get", "/referral-link?partner_id=1"),
        ("get", "/balance?partner_id=1"),
        ("get", "/transactions?partner_id=1"),
        ("post", "/withdraw?partner_id=1&amount=1"),
        ("post", "/test-order?partner_id=1&amount=1"),
    ],
)
def test_sensitive_routes_reject_invalid_admin_secret(
    monkeypatch,
    method,
    path,
):
    monkeypatch.setattr(order_handler, "DEBUG", True)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", "test-secret")

    response = getattr(TestClient(app), method)(
        path,
        headers={"X-Admin-Secret": "invalid-secret"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/create-partner?telegram_id=123"),
        ("get", "/referral-link?partner_id=1"),
        ("get", "/balance?partner_id=1"),
        ("get", "/transactions?partner_id=1"),
        ("post", "/withdraw?partner_id=1&amount=1"),
        ("post", "/test-order?partner_id=1&amount=1"),
    ],
)
def test_sensitive_routes_are_unavailable_outside_debug(
    monkeypatch,
    method,
    path,
):
    monkeypatch.setattr(order_handler, "DEBUG", False)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", "test-secret")

    response = getattr(TestClient(app), method)(path)

    assert response.status_code == 404


def test_sensitive_routes_are_unavailable_without_configured_secret(
    monkeypatch,
):
    monkeypatch.setattr(order_handler, "DEBUG", True)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", None)

    response = TestClient(app).get("/balance?partner_id=1")

    assert response.status_code == 503
