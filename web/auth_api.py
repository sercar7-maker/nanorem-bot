from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import Partner
from services.auth_service import (
    AUTH_SESSION_TTL,
    AuthCodeDelivery,
    AuthService,
    DeferredAuthCodeDelivery,
    InvalidAuthCodeError,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE_NAME = "nanorem_session"
SESSION_COOKIE_PATH = "/"
GENERIC_REQUEST_RESPONSE = {
    "message": "If the account exists, a code has been sent."
}


class RequestCodeBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    channel: Literal["email", "phone"]


class VerifyCodeBody(RequestCodeBody):
    code: str = Field(pattern=r"^[0-9]{6}$")


def get_auth_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_auth_code_delivery() -> AuthCodeDelivery:
    return DeferredAuthCodeDelivery()


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
        secure=True,
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
        secure=True,
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
