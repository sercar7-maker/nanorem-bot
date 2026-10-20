import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from database.models import AuthChallenge, AuthSession, Partner, PartnerStatus
from services import auth_service
from web import auth_api
from web.app import app


class FakeAuthCodeDelivery:
    def __init__(self):
        self.deliveries: list[dict[str, str]] = []

    def send_code(
        self,
        *,
        channel: str,
        destination: str,
        code: str,
    ) -> None:
        self.deliveries.append(
            {
                "channel": channel,
                "destination": destination,
                "code": code,
            }
        )


@pytest.fixture
def auth_client(isolated_database, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    delivery = FakeAuthCodeDelivery()
    app.dependency_overrides[auth_api.get_auth_code_delivery] = (
        lambda: delivery
    )
    client = TestClient(app, base_url="https://testserver")
    try:
        yield client, delivery
    finally:
        app.dependency_overrides.pop(auth_api.get_auth_code_delivery, None)
        client.close()


def _create_partner(
    session_factory,
    *,
    email: str | None = None,
    phone: str | None = None,
    first_name: str = "OTP Partner",
    root: bool = False,
) -> int:
    session = session_factory()
    partner = Partner(
        first_name=first_name,
        email=email,
        phone=phone,
        telegram_id="998877" if root else None,
        status=PartnerStatus.ACTIVE,
        subscription_end_date=(
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
            if root
            else None
        ),
        annual_activity_until=(
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
            if root
            else None
        ),
        lineage=[],
    )
    session.add(partner)
    session.flush()
    if root:
        partner.root_id = partner.id
    session.commit()
    partner_id = partner.id
    session.close()
    return partner_id


def _request_code(client, identifier: str, channel: str):
    return client.post(
        "/auth/request-code",
        json={"identifier": identifier, "channel": channel},
    )


def _verify_code(client, identifier: str, channel: str, code: str):
    return client.post(
        "/auth/verify-code",
        json={
            "identifier": identifier,
            "channel": channel,
            "code": code,
        },
    )


@pytest.fixture
def auth_clock(monkeypatch):
    class MutableDateTime(datetime):
        current = datetime.now(timezone.utc)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls.current.replace(tzinfo=None)
            return cls.current.astimezone(tz)

        @classmethod
        def advance(cls, seconds: int) -> None:
            cls.current += timedelta(seconds=seconds)

    monkeypatch.setattr(auth_service, "datetime", MutableDateTime)
    return MutableDateTime.advance


def test_request_code_creates_email_challenge(auth_client, isolated_database):
    client, delivery = auth_client
    partner_id = _create_partner(
        isolated_database,
        email="Person@Example.Test",
    )

    response = _request_code(client, " PERSON@example.test ", "email")

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert len(delivery.deliveries) == 1
    assert delivery.deliveries[0]["channel"] == "email"
    assert delivery.deliveries[0]["destination"] == "person@example.test"

    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    assert challenge.partner_id == partner_id
    assert challenge.purpose == "login"
    assert challenge.destination == "person@example.test"
    assert challenge.attempts == 0
    session.close()


def test_request_code_within_cooldown_does_not_create_challenge(
    auth_client,
    isolated_database,
    auth_clock,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="cooldown@example.test")

    _request_code(client, "cooldown@example.test", "email")
    auth_clock(59)
    response = _request_code(client, "cooldown@example.test", "email")

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert len(delivery.deliveries) == 1
    session = isolated_database()
    assert session.query(AuthChallenge).count() == 1
    session.close()


def test_sequential_requests_with_existing_cooldown_create_one_challenge(
    auth_client,
    isolated_database,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="serialized@example.test")

    first_response = _request_code(client, "serialized@example.test", "email")
    second_response = _request_code(client, "serialized@example.test", "email")

    assert first_response.status_code == second_response.status_code == 202
    assert first_response.json() == second_response.json() == (
        auth_api.GENERIC_REQUEST_RESPONSE
    )
    assert len(delivery.deliveries) == 1
    session = isolated_database()
    assert session.query(AuthChallenge).count() == 1
    session.close()


def test_request_code_after_cooldown_is_allowed(
    auth_client,
    isolated_database,
    auth_clock,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="cooldown-expired@example.test")

    _request_code(client, "cooldown-expired@example.test", "email")
    auth_clock(60)
    response = _request_code(
        client,
        "cooldown-expired@example.test",
        "email",
    )

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert len(delivery.deliveries) == 2
    session = isolated_database()
    assert session.query(AuthChallenge).count() == 2
    session.close()


def test_sixth_request_within_window_is_limited(
    auth_client,
    isolated_database,
    auth_clock,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="window-limit@example.test")

    for _ in range(5):
        _request_code(client, "window-limit@example.test", "email")
        auth_clock(61)
    response = _request_code(client, "window-limit@example.test", "email")

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert len(delivery.deliveries) == 5
    session = isolated_database()
    assert session.query(AuthChallenge).count() == 5
    session.close()


def test_request_allowed_after_old_challenge_leaves_window(
    auth_client,
    isolated_database,
    auth_clock,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="window-expired@example.test")

    for _ in range(5):
        _request_code(client, "window-expired@example.test", "email")
        auth_clock(61)
    auth_clock(15 * 60 + 1 - 5 * 61)
    response = _request_code(client, "window-expired@example.test", "email")

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert len(delivery.deliveries) == 6
    session = isolated_database()
    assert session.query(AuthChallenge).count() == 6
    session.close()


def test_delivery_failure_invalidates_challenge_without_exposing_error(
    auth_client,
    isolated_database,
):
    client, _ = auth_client
    _create_partner(isolated_database, email="delivery-failure@example.test")

    class FailingAuthCodeDelivery(FakeAuthCodeDelivery):
        def send_code(
            self,
            *,
            channel: str,
            destination: str,
            code: str,
        ) -> None:
            raise RuntimeError("sensitive delivery failure")

    app.dependency_overrides[auth_api.get_auth_code_delivery] = (
        FailingAuthCodeDelivery
    )

    response = _request_code(
        client,
        "delivery-failure@example.test",
        "email",
    )

    assert response.status_code == 202
    assert response.json() == auth_api.GENERIC_REQUEST_RESPONSE
    assert "sensitive delivery failure" not in response.text

    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    assert challenge.used_at is not None
    assert challenge.is_valid is False
    assert session.query(AuthSession).count() == 0
    session.close()


def test_request_code_creates_phone_challenge(auth_client, isolated_database):
    client, delivery = auth_client
    partner_id = _create_partner(
        isolated_database,
        phone="+1 (555) 123-4567",
    )

    response = _request_code(client, "0015551234567", "phone")

    assert response.status_code == 202
    assert delivery.deliveries[0]["destination"] == "+15551234567"
    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    assert challenge.partner_id == partner_id
    assert challenge.channel == "phone"
    assert challenge.destination == "+15551234567"
    session.close()


def test_unknown_email_and_phone_have_same_external_response(auth_client):
    client, delivery = auth_client

    email_response = _request_code(
        client,
        "unknown@example.test",
        "email",
    )
    phone_response = _request_code(client, "+15551230000", "phone")

    assert email_response.status_code == phone_response.status_code == 202
    assert email_response.json() == phone_response.json()
    assert delivery.deliveries == []


def test_plaintext_otp_is_not_returned_or_stored(auth_client, isolated_database):
    client, delivery = auth_client
    _create_partner(isolated_database, email="otp@example.test")

    response = _request_code(client, "otp@example.test", "email")
    otp = delivery.deliveries[0]["code"]

    assert otp not in response.text
    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    assert challenge.code_hash != otp
    assert otp not in challenge.code_hash
    session.close()


def test_correct_code_creates_session_in_secure_cookie(
    auth_client,
    isolated_database,
):
    client, delivery = auth_client
    partner_id = _create_partner(
        isolated_database,
        email="login@example.test",
    )
    _request_code(client, "login@example.test", "email")
    otp = delivery.deliveries[0]["code"]

    response = _verify_code(client, "login@example.test", "email", otp)

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert otp not in response.text
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "secure" in cookie_header
    assert "samesite=strict" in cookie_header
    token = client.cookies.get(auth_api.SESSION_COOKIE_NAME)
    assert token

    session = isolated_database()
    auth_session = session.query(AuthSession).one()
    assert auth_session.partner_id == partner_id
    assert auth_session.token_hash == hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()
    assert auth_session.token_hash != token
    session.close()


def test_wrong_code_increments_attempts(auth_client, isolated_database):
    client, delivery = auth_client
    _create_partner(isolated_database, email="wrong-code@example.test")
    _request_code(client, "wrong-code@example.test", "email")
    actual_code = delivery.deliveries[0]["code"]
    wrong_code = "000000" if actual_code != "000000" else "000001"

    response = _verify_code(
        client,
        "wrong-code@example.test",
        "email",
        wrong_code,
    )

    assert response.status_code == 400
    session = isolated_database()
    assert session.query(AuthChallenge).one().attempts == 1
    session.close()


def test_challenge_is_invalid_after_max_attempts(auth_client, isolated_database):
    client, delivery = auth_client
    _create_partner(isolated_database, email="max-attempts@example.test")
    _request_code(client, "max-attempts@example.test", "email")
    actual_code = delivery.deliveries[0]["code"]
    wrong_code = "000000" if actual_code != "000000" else "000001"

    for _ in range(5):
        response = _verify_code(
            client,
            "max-attempts@example.test",
            "email",
            wrong_code,
        )
        assert response.status_code == 400

    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    assert challenge.attempts == challenge.max_attempts
    assert challenge.is_valid is False
    session.close()


def test_expired_challenge_is_rejected(auth_client, isolated_database):
    client, delivery = auth_client
    _create_partner(isolated_database, email="expired@example.test")
    _request_code(client, "expired@example.test", "email")
    otp = delivery.deliveries[0]["code"]
    session = isolated_database()
    challenge = session.query(AuthChallenge).one()
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    session.close()

    response = _verify_code(client, "expired@example.test", "email", otp)

    assert response.status_code == 400
    session = isolated_database()
    assert session.query(AuthSession).count() == 0
    session.close()


def test_challenge_cannot_be_reused(auth_client, isolated_database):
    client, delivery = auth_client
    _create_partner(isolated_database, email="replay@example.test")
    _request_code(client, "replay@example.test", "email")
    otp = delivery.deliveries[0]["code"]

    assert _verify_code(client, "replay@example.test", "email", otp).status_code == 200
    client.cookies.clear()
    replay = _verify_code(client, "replay@example.test", "email", otp)

    assert replay.status_code == 400
    session = isolated_database()
    assert session.query(AuthSession).count() == 1
    session.close()


def test_new_challenge_invalidates_previous_active_challenge(
    auth_client,
    isolated_database,
    auth_clock,
):
    client, delivery = auth_client
    _create_partner(isolated_database, email="replace@example.test")
    _request_code(client, "replace@example.test", "email")
    previous_code = delivery.deliveries[0]["code"]
    auth_clock(60)
    _request_code(client, "replace@example.test", "email")
    current_code = delivery.deliveries[1]["code"]

    assert previous_code != current_code
    assert _verify_code(
        client,
        "replace@example.test",
        "email",
        previous_code,
    ).status_code == 400
    client.cookies.clear()
    assert _verify_code(
        client,
        "replace@example.test",
        "email",
        current_code,
    ).status_code == 200


def test_me_returns_only_authenticated_partner_fields(
    auth_client,
    isolated_database,
):
    client, delivery = auth_client
    partner_id = _create_partner(
        isolated_database,
        email="me@example.test",
        phone="+15551230011",
    )
    _request_code(client, "me@example.test", "email")
    _verify_code(
        client,
        "me@example.test",
        "email",
        delivery.deliveries[0]["code"],
    )

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert set(response.json()) == {
        "id",
        "email",
        "phone",
        "telegram_id",
        "referral_code",
        "root_id",
        "status",
        "role",
        "can_process_withdrawals",
    }
    assert response.json()["id"] == partner_id
    assert response.json()["email"] == "me@example.test"
    assert response.json()["role"] == "partner"
    assert response.json()["can_process_withdrawals"] is False

    stored = isolated_database()
    stored.get(Partner, partner_id).role = "admin"
    stored.commit()
    stored.close()

    assert client.get("/auth/me").json()["role"] == "admin"


def test_logout_revokes_current_session(auth_client, isolated_database):
    client, delivery = auth_client
    partner_id = _create_partner(
        isolated_database,
        email="logout@example.test",
    )
    _request_code(client, "logout@example.test", "email")
    _verify_code(
        client,
        "logout@example.test",
        "email",
        delivery.deliveries[0]["code"],
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert client.get("/auth/me").status_code == 401
    session = isolated_database()
    auth_session = session.query(AuthSession).one()
    assert auth_session.partner_id == partner_id
    assert auth_session.revoked_at is not None
    session.close()


def _store_session(
    session_factory,
    partner_id: int,
    *,
    expired: bool = False,
    revoked: bool = False,
) -> str:
    token = f"probe-token-{partner_id}-{expired}-{revoked}"
    now = datetime.now(timezone.utc)
    session = session_factory()
    session.add(
        AuthSession(
            partner_id=partner_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=(
                now - timedelta(minutes=1)
                if expired
                else now + timedelta(days=1)
            ),
            revoked_at=now if revoked else None,
        )
    )
    session.commit()
    session.close()
    return token


@pytest.fixture
def admin_probe_client(isolated_database, monkeypatch):
    from fastapi import Depends, FastAPI

    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    probe = FastAPI()

    @probe.get("/admin-check")
    def admin_check(
        partner: Partner = Depends(auth_api.require_admin_partner),
    ):
        return {"id": partner.id, "role": partner.role}

    client = TestClient(probe)
    try:
        yield client
    finally:
        client.close()


def test_admin_check_without_session_is_rejected(admin_probe_client):
    response = admin_probe_client.get("/admin-check")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.parametrize(
    ("expired", "revoked", "cookie"),
    [
        (False, False, "not-a-valid-session"),
        (True, False, None),
        (False, True, None),
    ],
)
def test_admin_check_rejects_unusable_session(
    admin_probe_client,
    isolated_database,
    expired,
    revoked,
    cookie,
):
    partner_id = _create_partner(
        isolated_database,
        email=f"unusable-{expired}-{revoked}@example.test",
    )
    if cookie is None:
        cookie = _store_session(
            isolated_database,
            partner_id,
            expired=expired,
            revoked=revoked,
        )
    admin_probe_client.cookies.set(auth_api.SESSION_COOKIE_NAME, cookie)

    response = admin_probe_client.get("/admin-check")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_admin_check_rejects_regular_partner(
    admin_probe_client,
    isolated_database,
):
    partner_id = _create_partner(
        isolated_database,
        email="regular-admin-check@example.test",
    )
    token = _store_session(isolated_database, partner_id)
    admin_probe_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)

    response = admin_probe_client.get("/admin-check")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_check_rejects_root_without_admin_role(
    admin_probe_client,
    isolated_database,
):
    partner_id = _create_partner(
        isolated_database,
        email="root-not-admin@example.test",
        root=True,
    )
    token = _store_session(isolated_database, partner_id)
    admin_probe_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)

    response = admin_probe_client.get("/admin-check")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_check_allows_stored_admin_role(
    admin_probe_client,
    isolated_database,
):
    partner_id = _create_partner(
        isolated_database,
        email="stored-admin@example.test",
    )
    session = isolated_database()
    session.get(Partner, partner_id).role = "admin"
    session.commit()
    session.close()
    token = _store_session(isolated_database, partner_id)
    admin_probe_client.cookies.set(auth_api.SESSION_COOKIE_NAME, token)

    response = admin_probe_client.get("/admin-check")

    assert response.status_code == 200
    assert response.json() == {"id": partner_id, "role": "admin"}


def test_repeated_logout_is_safe(auth_client):
    client, _ = auth_client

    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout").status_code == 204


def test_root_can_authenticate_without_activity_or_identity_changes(
    auth_client,
    isolated_database,
):
    client, delivery = auth_client
    root_id = _create_partner(
        isolated_database,
        email="root@example.test",
        phone="+15551230099",
        first_name="Root partner",
        root=True,
    )
    session = isolated_database()
    root = session.get(Partner, root_id)
    original_status = root.status
    original_end = root.subscription_end_date
    original_annual_end = root.annual_activity_until
    original_referral_code = root.referral_code
    original_telegram_code = root.telegram_link_code
    session.close()

    _request_code(client, "root@example.test", "email")
    response = _verify_code(
        client,
        "root@example.test",
        "email",
        delivery.deliveries[0]["code"],
    )

    assert response.status_code == 200
    assert client.get("/auth/me").json()["id"] == root_id
    session = isolated_database()
    root = session.get(Partner, root_id)
    assert root.root_id == root.id
    assert root.status == original_status
    assert root.subscription_end_date == original_end
    assert root.annual_activity_until == original_annual_end
    assert root.referral_code == original_referral_code
    assert root.telegram_link_code == original_telegram_code
    session.close()
