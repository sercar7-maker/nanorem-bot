import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from web import app as web_app
from web.webhook import WebhookHandler


def test_legacy_webhook_handler_fails_closed_without_secret():
    handler = WebhookHandler(order_handler=None)

    assert handler.verify_signature("payload", "signature") is False


def test_woocommerce_webhook_rejects_missing_and_invalid_signature(
    monkeypatch,
):
    monkeypatch.setattr(web_app, "WOOCOMMERCE_WEBHOOK_SECRET", "pytest-secret")
    client = TestClient(web_app.app)
    body = b'{"id": 123, "status": "completed"}'

    missing = client.post("/webhook", content=body)
    invalid = client.post(
        "/webhook",
        content=body,
        headers={"X-WC-Webhook-Signature": "invalid"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_woocommerce_webhook_accepts_valid_signature_without_external_calls(
    monkeypatch,
):
    secret = "pytest-webhook-secret"
    monkeypatch.setattr(web_app, "WOOCOMMERCE_WEBHOOK_SECRET", secret)
    processor = AsyncMock(return_value=True)
    monkeypatch.setattr(web_app.order_processor, "process_webhook", processor)

    body = json.dumps(
        {"id": 456, "status": "completed"},
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    response = TestClient(web_app.app).post(
        "/webhook",
        content=body,
        headers={"X-WC-Webhook-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    processor.assert_awaited_once_with(
        {"id": 456, "status": "completed"}
    )


def test_woocommerce_webhook_failure_returns_server_error_for_retry(
    monkeypatch,
):
    secret = "pytest-webhook-secret"
    monkeypatch.setattr(web_app, "WOOCOMMERCE_WEBHOOK_SECRET", secret)
    processor = AsyncMock(return_value=False)
    monkeypatch.setattr(web_app.order_processor, "process_webhook", processor)

    body = json.dumps(
        {"id": 457, "status": "completed"},
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    response = TestClient(web_app.app).post(
        "/webhook",
        content=body,
        headers={"X-WC-Webhook-Signature": signature},
    )

    assert response.status_code == 500
    processor.assert_awaited_once()


def test_woocommerce_webhook_exception_returns_server_error_for_retry(
    monkeypatch,
):
    secret = "pytest-webhook-secret"
    monkeypatch.setattr(web_app, "WOOCOMMERCE_WEBHOOK_SECRET", secret)
    processor = AsyncMock(side_effect=RuntimeError("processing failure"))
    monkeypatch.setattr(web_app.order_processor, "process_webhook", processor)

    body = json.dumps(
        {"id": 458, "status": "completed"},
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    response = TestClient(web_app.app).post(
        "/webhook",
        content=body,
        headers={"X-WC-Webhook-Signature": signature},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Webhook processing failed"
    processor.assert_awaited_once()


def test_telegram_webhook_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(web_app, "TELEGRAM_WEBHOOK_SECRET", "pytest-secret")

    response = TestClient(web_app.app).post(
        "/telegram-webhook",
        json={},
        headers={"X-Telegram-Bot-Api-Secret-Token": "invalid"},
    )

    assert response.status_code == 401
