from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.base import Base
from database.migrations import upgrade_schema
from database.models import AuthChallenge, AuthSession, Partner


def _new_partner(session, *, name: str = "Auth test partner") -> Partner:
    partner = Partner(
        first_name=name,
        referral_code=f"nr_auth_{name.lower().replace(' ', '_')}",
    )
    session.add(partner)
    session.flush()
    return partner


def test_auth_challenge_is_partner_linked_and_expires_or_is_consumed(
    isolated_database,
):
    session = isolated_database()
    partner = _new_partner(session)
    now = datetime.now(timezone.utc)
    challenge = AuthChallenge(
        partner_id=partner.id,
        channel="email",
        purpose="login",
        destination="member@example.test",
        code_hash="sha256:opaque-hash",
        expires_at=now + timedelta(minutes=5),
        attempts=0,
        max_attempts=5,
    )
    session.add(challenge)
    session.flush()

    assert challenge.partner_id == partner.id
    assert session.get(Partner, challenge.partner_id) is partner
    assert challenge.code_hash == "sha256:opaque-hash"
    assert not hasattr(challenge, "code")
    assert challenge.is_valid is True
    assert challenge.used_at is None
    assert challenge.created_at is not None

    challenge.used_at = now
    assert challenge.is_valid is False
    challenge.used_at = None
    challenge.expires_at = now - timedelta(seconds=1)
    assert challenge.is_valid is False
    session.close()


def test_auth_challenge_attempt_count_is_bounded(isolated_database):
    session = isolated_database()
    partner = _new_partner(session)
    challenge = AuthChallenge(
        partner_id=partner.id,
        channel="phone",
        purpose="recovery",
        destination="+15551234567",
        code_hash="opaque-code-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        attempts=5,
        max_attempts=5,
    )
    session.add(challenge)
    session.flush()

    assert challenge.is_valid is False
    challenge.attempts = 6
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()


def test_auth_session_is_partner_linked_and_token_hash_is_unique(
    isolated_database,
):
    session = isolated_database()
    partner = _new_partner(session)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    auth_session = AuthSession(
        partner_id=partner.id,
        token_hash="session-hash-unique",
        expires_at=expires_at,
    )
    session.add(auth_session)
    session.flush()

    assert session.get(Partner, auth_session.partner_id) is partner
    assert auth_session.is_active is True
    assert auth_session.revoked_at is None
    assert auth_session.last_seen_at is None
    assert auth_session.created_at is not None

    auth_session.revoked_at = datetime.now(timezone.utc)
    assert auth_session.is_active is False
    auth_session.revoked_at = None
    auth_session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert auth_session.is_active is False

    session.add(
        AuthSession(
            partner_id=partner.id,
            token_hash="session-hash-unique",
            expires_at=expires_at,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()


def test_auth_tables_are_created_additively_without_changing_partner_rows():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    try:
        auth_table_names = {"auth_challenges", "auth_sessions"}
        Base.metadata.create_all(
            engine,
            tables=[
                table
                for table in Base.metadata.sorted_tables
                if table.name not in auth_table_names
            ],
        )
        with engine.begin() as connection:
            connection.execute(
                Partner.__table__.insert().values(
                    first_name="Existing Root",
                    referral_code="nr_existing_root",
                    upline_id=None,
                    root_id=None,
                    lineage=[],
                    subscription_end_date=None,
                    annual_activity_until=None,
                    telegram_link_code="telegram-binding-code",
                )
            )
            root_id = connection.exec_driver_sql(
                "SELECT id FROM partners"
            ).scalar_one()
            connection.execute(
                Partner.__table__.update()
                .where(Partner.id == root_id)
                .values(root_id=root_id)
            )

        upgrade_schema(engine)

        inspector = inspect(engine)
        assert inspector.has_table("auth_challenges")
        assert inspector.has_table("auth_sessions")
        assert inspector.get_foreign_keys("auth_challenges")[0][
            "referred_table"
        ] == "partners"
        assert inspector.get_foreign_keys("auth_sessions")[0][
            "referred_table"
        ] == "partners"
        with engine.connect() as connection:
            root = connection.execute(
                Partner.__table__.select().where(Partner.id == root_id)
            ).mappings().one()
        assert root["root_id"] == root_id
        assert root["referral_code"] == "nr_existing_root"
        assert root["telegram_link_code"] == "telegram-binding-code"
    finally:
        engine.dispose()
