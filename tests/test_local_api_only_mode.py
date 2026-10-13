"""Regression tests for the explicit LOCAL_API_ONLY mode of web.app.

LOCAL_API_ONLY=true must skip database initialization, the Telegram client,
webhook management and the scheduler. With the flag disabled (default) the
lifecycle must stay unchanged.
No test here talks to Telegram or uses a real token.
"""

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
import telegram
import telegram.ext
from fastapi.testclient import TestClient

import config
from web import app as standard_app_module


APP_PATH = Path(standard_app_module.__file__)
FAKE_TOKEN = "123456:LOCAL_TEST_TOKEN_NOT_REAL"


@pytest.fixture
def telegram_calls(monkeypatch):
    """Replace Telegram network entry points with recorders."""
    calls = []

    def recorder(name):
        async def _record(*args, **kwargs):
            calls.append(name)
            return None

        return _record

    for cls in (telegram.Bot, telegram.ext.ExtBot):
        for method in (
            "initialize",
            "get_me",
            "set_webhook",
            "delete_webhook",
            "send_message",
            "shutdown",
        ):
            monkeypatch.setattr(cls, method, recorder(f"{cls.__name__}.{method}"))

    for method in ("initialize", "shutdown", "start", "stop"):
        monkeypatch.setattr(
            telegram.ext.Application,
            method,
            recorder(f"Application.{method}"),
        )

    return calls


def _load_app_module(monkeypatch, *, local_flag, bot_token):
    """Import a fresh, private copy of web/app.py with the given settings."""
    if local_flag is None:
        monkeypatch.delenv("LOCAL_API_ONLY", raising=False)
    else:
        monkeypatch.setenv("LOCAL_API_ONLY", local_flag)

    monkeypatch.setattr(config, "BOT_TOKEN", bot_token)

    name = f"web._app_local_mode_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _record_lifecycle(monkeypatch, module, events):
    monkeypatch.setattr(module, "init_db", lambda: events.append("init_db"))
    monkeypatch.setattr(
        module, "start_scheduler", lambda: events.append("start_scheduler")
    )
    monkeypatch.setattr(
        module, "stop_scheduler", lambda: events.append("stop_scheduler")
    )


# ---------------------------------------------------------------------------
# LOCAL_API_ONLY=true
# ---------------------------------------------------------------------------


def test_local_mode_imports_without_bot_token(monkeypatch, telegram_calls):
    module = _load_app_module(monkeypatch, local_flag="true", bot_token=None)

    assert module.LOCAL_API_ONLY is True
    assert module.telegram_app is None
    assert isinstance(module.web_bot, module._LocalApiOnlyBot)
    assert telegram_calls == []


def test_local_mode_startup_and_shutdown_skip_telegram_webhook_and_scheduler(
    monkeypatch,
    telegram_calls,
):
    module = _load_app_module(monkeypatch, local_flag="true", bot_token=None)
    # Even with webhook settings present, local mode must not touch them.
    monkeypatch.setattr(module, "WEBHOOK_URL", "https://example.invalid")
    monkeypatch.setattr(module, "TELEGRAM_WEBHOOK_SECRET", "test-secret")
    events = []
    _record_lifecycle(monkeypatch, module, events)

    asyncio.run(module.on_startup())
    asyncio.run(module.on_shutdown())

    assert events == []
    assert "start_scheduler" not in events
    assert telegram_calls == []


def test_local_mode_notifications_do_not_contact_telegram(
    monkeypatch,
    telegram_calls,
):
    module = _load_app_module(monkeypatch, local_flag="true", bot_token=None)

    asyncio.run(
        module.notification_service.notify_new_referral(
            telegram_id=123456789,
            partner_name="Local Test",
        )
    )

    assert telegram_calls == []


def test_local_mode_keeps_routes_and_webhook_security(
    monkeypatch,
    telegram_calls,
):
    module = _load_app_module(monkeypatch, local_flag="true", bot_token=None)
    client = TestClient(module.app)

    assert client.get("/login").status_code == 200

    monkeypatch.setattr(module, "TELEGRAM_WEBHOOK_SECRET", None)
    response = client.post("/telegram-webhook", json={"update_id": 1})
    assert response.status_code == 503

    monkeypatch.setattr(module, "TELEGRAM_WEBHOOK_SECRET", "test-secret")
    response = client.post("/telegram-webhook", json={"update_id": 1})
    assert response.status_code == 401
    response = client.post(
        "/telegram-webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 401

    assert telegram_calls == []


@pytest.mark.parametrize("flag", [None, "", "false", "0", "no", "off"])
def test_flag_is_disabled_by_default_and_for_false_values(
    monkeypatch,
    telegram_calls,
    flag,
):
    module = _load_app_module(monkeypatch, local_flag=flag, bot_token=FAKE_TOKEN)

    assert module.LOCAL_API_ONLY is False
    assert isinstance(module.telegram_app, telegram.ext.Application)
    assert isinstance(module.web_bot, telegram.Bot)
    assert telegram_calls == []


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_flag_accepts_explicit_true_values(monkeypatch, telegram_calls, flag):
    module = _load_app_module(monkeypatch, local_flag=flag, bot_token=None)

    assert module.LOCAL_API_ONLY is True
    assert module.telegram_app is None


# ---------------------------------------------------------------------------
# Standard mode (flag disabled): lifecycle unchanged
# ---------------------------------------------------------------------------


class _FakeTelegramBot:
    def __init__(self, events):
        self.events = events

    async def set_webhook(self, **kwargs):
        self.events.append(("set_webhook", kwargs))

    async def delete_webhook(self, **kwargs):
        self.events.append("delete_webhook")


class _FakeTelegramApp:
    def __init__(self, events):
        self.events = events
        self.bot = _FakeTelegramBot(events)

    async def initialize(self):
        self.events.append("initialize")

    async def shutdown(self):
        self.events.append("shutdown")


def test_standard_module_is_not_in_local_mode():
    assert standard_app_module.LOCAL_API_ONLY is False
    assert isinstance(standard_app_module.telegram_app, telegram.ext.Application)
    assert isinstance(standard_app_module.web_bot, telegram.Bot)


def test_standard_lifecycle_with_webhook_is_unchanged(monkeypatch):
    module = standard_app_module
    events = []
    _record_lifecycle(monkeypatch, module, events)
    monkeypatch.setattr(module, "telegram_app", _FakeTelegramApp(events))
    monkeypatch.setattr(module, "WEBHOOK_URL", "https://example.invalid")
    monkeypatch.setattr(module, "TELEGRAM_WEBHOOK_SECRET", "test-secret")

    asyncio.run(module.on_startup())
    assert events == [
        "init_db",
        "initialize",
        (
            "set_webhook",
            {
                "url": "https://example.invalid/telegram-webhook",
                "secret_token": "test-secret",
            },
        ),
        "start_scheduler",
    ]

    events.clear()
    asyncio.run(module.on_shutdown())
    assert events == ["delete_webhook", "shutdown", "stop_scheduler"]


def test_standard_lifecycle_without_webhook_url_is_unchanged(monkeypatch):
    module = standard_app_module
    events = []
    _record_lifecycle(monkeypatch, module, events)
    monkeypatch.setattr(module, "telegram_app", _FakeTelegramApp(events))
    monkeypatch.setattr(module, "WEBHOOK_URL", None)

    asyncio.run(module.on_startup())
    assert events == ["init_db", "initialize", "start_scheduler"]

    events.clear()
    asyncio.run(module.on_shutdown())
    assert events == ["delete_webhook", "shutdown", "stop_scheduler"]


def test_standard_lifecycle_still_requires_webhook_secret(monkeypatch):
    module = standard_app_module
    events = []
    _record_lifecycle(monkeypatch, module, events)
    monkeypatch.setattr(module, "telegram_app", _FakeTelegramApp(events))
    monkeypatch.setattr(module, "WEBHOOK_URL", "https://example.invalid")
    monkeypatch.setattr(module, "TELEGRAM_WEBHOOK_SECRET", None)

    with pytest.raises(RuntimeError, match="TELEGRAM_WEBHOOK_SECRET"):
        asyncio.run(module.on_startup())

    assert "start_scheduler" not in events
