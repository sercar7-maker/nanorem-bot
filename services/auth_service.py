import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import case, func, update
from sqlalchemy.orm import Session

from config import BOT_TOKEN
from database.models import AuthChallenge, AuthSession, Partner


logger = logging.getLogger(__name__)

CHALLENGE_TTL = timedelta(minutes=10)
AUTH_SESSION_TTL = timedelta(days=30)
MAX_CHALLENGE_ATTEMPTS = 5


class AuthCodeDelivery(Protocol):
    def send_code(
        self,
        *,
        channel: str,
        destination: str,
        code: str,
    ) -> None: ...


class DeferredAuthCodeDelivery:
    """Placeholder adapter; a delivery provider can replace it later."""

    def send_code(
        self,
        *,
        channel: str,
        destination: str,
        code: str,
    ) -> None:
        return None


class InvalidAuthCodeError(ValueError):
    """The supplied authentication code is unavailable or invalid."""


def normalize_email(identifier: str) -> str:
    normalized = identifier.strip().lower()
    if (
        len(normalized) > 254
        or normalized.count("@") != 1
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Invalid email address")
    local, domain = normalized.split("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Invalid email address")
    return normalized


def normalize_phone(identifier: str) -> str:
    value = identifier.strip()
    if not value:
        raise ValueError("Invalid phone number")

    has_plus = value.startswith("+")
    if any(
        not character.isdigit() and character not in "+ ()-."
        for character in value
    ):
        raise ValueError("Invalid phone number")
    if (has_plus and "+" in value[1:]) or (
        not has_plus and "+" in value
    ):
        raise ValueError("Invalid phone number")
    digits = "".join(character for character in value if character.isdigit())
    if not digits.isascii() or not 7 <= len(digits) <= 15:
        raise ValueError("Invalid phone number")
    if digits.startswith("00"):
        digits = digits[2:]
    if not 7 <= len(digits) <= 15:
        raise ValueError("Invalid phone number")
    return f"+{digits}"


def normalize_identifier(identifier: str, channel: str) -> str:
    if channel == "email":
        return normalize_email(identifier)
    if channel == "phone":
        return normalize_phone(identifier)
    raise ValueError("Unsupported authentication channel")


class AuthService:
    def __init__(
        self,
        session: Session,
        delivery: AuthCodeDelivery,
        *,
        code_pepper: str | None = None,
    ):
        self.session = session
        self.delivery = delivery
        self._code_pepper = (
            code_pepper
            or os.getenv("AUTH_CODE_PEPPER")
            or BOT_TOKEN
        )
        if not self._code_pepper:
            raise RuntimeError("Authentication code pepper is not configured")

    def _find_partner(self, destination: str, channel: str) -> Partner | None:
        if channel == "email":
            return (
                self.session.query(Partner)
                .filter(func.lower(Partner.email) == destination)
                .one_or_none()
            )

        matching_partner_ids = [
            partner_id
            for partner_id, phone in self.session.query(
                Partner.id,
                Partner.phone,
            ).filter(Partner.phone.is_not(None))
            if self._normalized_stored_phone(phone) == destination
        ]
        if len(matching_partner_ids) != 1:
            return None
        return self.session.get(Partner, matching_partner_ids[0])

    @staticmethod
    def _normalized_stored_phone(phone: str) -> str | None:
        try:
            return normalize_phone(phone)
        except ValueError:
            return None

    def _hash_code(self, challenge_id: int, code: str) -> str:
        message = f"{challenge_id}:{code}".encode("utf-8")
        return hmac.new(
            self._code_pepper.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    def request_code(self, identifier: str, channel: str) -> None:
        destination = normalize_identifier(identifier, channel)
        partner = self._find_partner(destination, channel)
        if partner is None:
            return

        now = datetime.now(timezone.utc)
        previous_challenges = (
            self.session.query(AuthChallenge)
            .filter(
                AuthChallenge.partner_id == partner.id,
                AuthChallenge.channel == channel,
                AuthChallenge.purpose == "login",
                AuthChallenge.used_at.is_(None),
            )
            .all()
        )
        for challenge in previous_challenges:
            challenge.used_at = now

        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = AuthChallenge(
            partner_id=partner.id,
            channel=channel,
            purpose="login",
            destination=destination,
            code_hash="pending",
            expires_at=now + CHALLENGE_TTL,
            attempts=0,
            max_attempts=MAX_CHALLENGE_ATTEMPTS,
        )
        self.session.add(challenge)
        self.session.flush()
        challenge.code_hash = self._hash_code(challenge.id, code)
        self.session.commit()

        try:
            self.delivery.send_code(
                channel=channel,
                destination=destination,
                code=code,
            )
        except Exception:
            logger.warning("Authentication code delivery failed")

    def verify_code(
        self,
        identifier: str,
        channel: str,
        code: str,
    ) -> tuple[str, AuthSession]:
        destination = normalize_identifier(identifier, channel)
        partner = self._find_partner(destination, channel)
        now = datetime.now(timezone.utc)
        if partner is None:
            raise InvalidAuthCodeError("Invalid or expired code")

        challenge = (
            self.session.query(AuthChallenge)
            .filter(
                AuthChallenge.partner_id == partner.id,
                AuthChallenge.channel == channel,
                AuthChallenge.purpose == "login",
                AuthChallenge.destination == destination,
                AuthChallenge.used_at.is_(None),
            )
            .order_by(AuthChallenge.id.desc())
            .first()
        )
        if challenge is None or not challenge.is_valid:
            raise InvalidAuthCodeError("Invalid or expired code")

        expected_hash = self._hash_code(challenge.id, code)
        if not hmac.compare_digest(challenge.code_hash, expected_hash):
            next_attempt_count = challenge.attempts + 1
            update_result = self.session.execute(
                update(AuthChallenge)
                .where(
                    AuthChallenge.id == challenge.id,
                    AuthChallenge.used_at.is_(None),
                    AuthChallenge.attempts == challenge.attempts,
                    AuthChallenge.attempts < AuthChallenge.max_attempts,
                )
                .values(
                    attempts=AuthChallenge.attempts + 1,
                    used_at=case(
                        (
                            next_attempt_count >= challenge.max_attempts,
                            now,
                        ),
                        else_=AuthChallenge.used_at,
                    ),
                )
                .execution_options(synchronize_session=False)
            )
            self.session.commit()
            if update_result.rowcount != 1:
                raise InvalidAuthCodeError("Invalid or expired code")
            raise InvalidAuthCodeError("Invalid or expired code")

        consumed = self.session.execute(
            update(AuthChallenge)
            .where(
                AuthChallenge.id == challenge.id,
                AuthChallenge.used_at.is_(None),
                AuthChallenge.attempts < AuthChallenge.max_attempts,
                AuthChallenge.expires_at > now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            self.session.rollback()
            raise InvalidAuthCodeError("Invalid or expired code")

        token = secrets.token_urlsafe(32)
        auth_session = AuthSession(
            partner_id=partner.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=now + AUTH_SESSION_TTL,
        )
        self.session.add(auth_session)
        self.session.commit()
        self.session.refresh(auth_session)
        return token, auth_session

    def authenticate_session(self, token: str | None) -> tuple[AuthSession, Partner] | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        auth_session = (
            self.session.query(AuthSession)
            .filter(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
            .first()
        )
        if auth_session is None or not auth_session.is_active:
            return None

        partner = self.session.get(Partner, auth_session.partner_id)
        if partner is None:
            return None
        auth_session.last_seen_at = datetime.now(timezone.utc)
        self.session.commit()
        return auth_session, partner

    def logout(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        auth_session = (
            self.session.query(AuthSession)
            .filter(AuthSession.token_hash == token_hash)
            .first()
        )
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(timezone.utc)
            self.session.commit()
