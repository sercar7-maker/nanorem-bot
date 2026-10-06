import os
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NOT_A_REAL_TOKEN"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEBUG"] = "false"
os.environ["WEBHOOK_URL"] = ""
os.environ["WOOCOMMERCE_WEBHOOK_SECRET"] = "pytest-only-secret"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "pytest-only-secret"
os.environ["ADMIN_API_SECRET"] = "pytest-only-secret"
os.environ["WC_CONSUMER_KEY"] = "pytest-only-key"
os.environ["WC_CONSUMER_SECRET"] = "pytest-only-secret"


def pytest_sessionstart(session):
    from database.db import init_db

    init_db()


@pytest.fixture
def isolated_database(monkeypatch):
    from database.base import Base
    from services import partner_service
    from tg_handlers import start
    from web import app as web_app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)

    monkeypatch.setattr(partner_service, "SessionLocal", test_session)
    monkeypatch.setattr(start, "SessionLocal", test_session)

    @contextmanager
    def get_test_session():
        session = test_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(web_app, "get_session", get_test_session)

    try:
        yield test_session
    finally:
        engine.dispose()
