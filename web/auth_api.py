
import ipaddress
import os
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.db import SessionLocal
from services.auth_service import (
    AUTH_SESSION_TTL,
    AuthCodeDelivery,
    AuthService,
    DeferredAuthCodeDelivery,
    InvalidAuthCodeError,
    normalize_identifier,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE_NAME = "nanorem_session"
SESSION_COOKIE_PATH = "/"
GENERIC_REQUEST_RESPONSE = {
    "message": "If the account exists, a code has been sent."
}

LOCAL_API_ONLY = os.getenv("LOCAL_API_ONLY", "").strip().lower() == "true"

_local_auth_codes: dict[tuple[str, str], str] = {}
_local_auth_codes_lock = Lock()


class RequestCodeBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    channel: Literal["email", "phone"]


class VerifyCodeBody(RequestCodeBody):
    code: str = Field(pattern=r"^[0-9]{6}$")


class LocalAuthCodeDelivery:
    """In-memory OTP delivery adapter for explicit local testing only."""

    def send_code(
        self,
        *,
        channel: str,
        destination: str,
        code: str,
    ) -> None:
        with _local_auth_codes_lock:
            _local_auth_codes[(channel, destination)] = code


def _is_loopback_request(request: Request) -> bool:
    if request.client is None:
        return False

    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _require_local_code_access(request: Request) -> None:
    if not LOCAL_API_ONLY or not _is_loopback_request(request):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


def get_auth_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_auth_code_delivery() -> AuthCodeDelivery:
    if LOCAL_API_ONLY:
        return LocalAuthCodeDelivery()

    from config import (
        SMTP_ENABLED,
        SMTP_FROM_EMAIL,
        SMTP_PASSWORD,
        SMTP_USERNAME,
    )

    if not SMTP_ENABLED:
        return DeferredAuthCodeDelivery()

    missing_settings = [
        setting
        for setting, value in (
            ("SMTP_USERNAME", SMTP_USERNAME),
            ("SMTP_PASSWORD", SMTP_PASSWORD),
            ("SMTP_FROM_EMAIL", SMTP_FROM_EMAIL),
        )
        if not value
    ]
    if missing_settings:
        missing = ", ".join(missing_settings)
        raise RuntimeError(
            f"SMTP is enabled but required configuration is missing: {missing}"
        )

    from services.smtp_delivery import SmtpAuthCodeDelivery

    return SmtpAuthCodeDelivery()


@router.post("/request-code", status_code=status.HTTP_202_ACCEPTED)
def request_code(
    body: RequestCodeBody,
    session: Session = Depends(get_auth_db),
    delivery: AuthCodeDelivery = Depends(get_auth_code_delivery),
):
    try:
        AuthService(session, delivery).request_code(
            body.identifier,
            body.channel,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return GENERIC_REQUEST_RESPONSE


@router.get("/local-code")
def get_local_auth_code(
    request: Request,
    identifier: str,
    channel: Literal["email", "phone"] = "phone",
):
    _require_local_code_access(request)

    if not identifier.strip() or len(identifier) > 320:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid identifier",
        )

    try:
        destination = normalize_identifier(identifier, channel)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    key = (channel, destination)
    with _local_auth_codes_lock:
        code = _local_auth_codes.pop(key, None)

    if code is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No local code available",
        )

    return {"code": code}


@router.post("/verify-code")
def verify_code(
    body: VerifyCodeBody,
    response: Response,
    session: Session = Depends(get_auth_db),
    delivery: AuthCodeDelivery = Depends(get_auth_code_delivery),
):
    try:
        token, _ = AuthService(session, delivery).verify_code(
            body.identifier,
            body.channel,
            body.code,
        )
    except InvalidAuthCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(AUTH_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=not LOCAL_API_ONLY,
        samesite="strict",
        path=SESSION_COOKIE_PATH,
    )
    return {"authenticated": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    session: Session = Depends(get_auth_db),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    AuthService(session, DeferredAuthCodeDelivery()).logout(token)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        secure=not LOCAL_API_ONLY,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me")
def get_current_partner(
    request: Request,
    session: Session = Depends(get_auth_db),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = AuthService(
        session,
        DeferredAuthCodeDelivery(),
    ).authenticate_session(token)

    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    _, partner = authenticated
    return {
        "id": partner.id,
        "email": partner.email,
        "phone": partner.phone,
        "telegram_id": partner.telegram_id,
        "referral_code": partner.referral_code,
        "root_id": partner.root_id,
        "status": (
            partner.status.value
            if hasattr(partner.status, "value")
            else partner.status
        ),
    }
