import secrets
import time


TELEGRAM_BINDING_TOKEN_TTL_SECONDS = 24 * 60 * 60
_MAX_FUTURE_SKEW_SECONDS = 5 * 60


def create_telegram_binding_token(now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    return f"{issued_at:x}.{secrets.token_urlsafe(32)}"


def is_telegram_binding_token_valid(
    token: str,
    now: int | None = None,
) -> bool:
    try:
        issued_at_text, secret = token.split(".", maxsplit=1)
        issued_at = int(issued_at_text, 16)
    except (AttributeError, ValueError):
        return False

    if not secret:
        return False

    current_time = int(time.time()) if now is None else now
    age = current_time - issued_at
    return -_MAX_FUTURE_SKEW_SECONDS <= age <= TELEGRAM_BINDING_TOKEN_TTL_SECONDS
