from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from database.models import Partner, Withdrawal, WithdrawalStatus
from web.auth_api import (
    get_auth_db,
    require_authenticated_partner,
    require_withdrawal_processor,
)

router = APIRouter(prefix="/auth", tags=["withdrawals"])

_OWN_FIELDS = (
    "withdrawal_id",
    "amount",
    "status",
    "method",
    "created_at",
    "processed_at",
)
_QUEUE_FIELDS = _OWN_FIELDS + (
    "partner_id",
    "first_name",
    "last_name",
)


def _money(amount) -> str:
    return format(Decimal(str(amount)), ".2f")


def _timestamp(value):
    if value is None:
        return None
    return value.isoformat()


def _status_name(value) -> str:
    if isinstance(value, WithdrawalStatus):
        return value.value
    return str(value)


def _own_item(row) -> dict:
    item = {
        "withdrawal_id": row.id,
        "amount": _money(row.amount),
        "status": _status_name(row.status),
        "method": row.method,
        "created_at": _timestamp(row.created_at),
        "processed_at": _timestamp(row.processed_at),
    }
    if set(item) != set(_OWN_FIELDS):
        raise RuntimeError("Own withdrawal fields drifted from the allowed set")
    return item


def _queue_item(row) -> dict:
    item = _own_item(row)
    item["partner_id"] = row.partner_id
    item["first_name"] = row.first_name
    item["last_name"] = row.last_name
    if set(item) != set(_QUEUE_FIELDS):
        raise RuntimeError("Withdrawal queue fields drifted from the allowed set")
    return item


def _ordered(query):
    return query.order_by(
        Withdrawal.created_at.desc(),
        Withdrawal.id.desc(),
    )


def _apply_status(query, status: WithdrawalStatus | None):
    if status is None:
        return query
    return query.filter(Withdrawal.status == status)


@router.get("/me/withdrawals")
def list_my_withdrawals(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: WithdrawalStatus | None = Query(default=None),
    partner: Partner = Depends(require_authenticated_partner),
    session: Session = Depends(get_auth_db),
):
    """Return only the signed-in partner's withdrawals."""
    rows = (
        _ordered(
            _apply_status(
                session.query(
                    Withdrawal.id,
                    Withdrawal.amount,
                    Withdrawal.status,
                    Withdrawal.method,
                    Withdrawal.created_at,
                    Withdrawal.processed_at,
                ).filter(Withdrawal.partner_id == partner.id),
                status,
            )
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [_own_item(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/withdrawals/queue")
def list_withdrawal_queue(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: WithdrawalStatus | None = Query(default=None),
    _: Partner = Depends(require_withdrawal_processor),
    session: Session = Depends(get_auth_db),
):
    """Return the processing queue for a partner who currently has permission."""
    selected_status = WithdrawalStatus.PENDING if status is None else status
    rows = (
        _ordered(
            session.query(
                Withdrawal.id,
                Withdrawal.amount,
                Withdrawal.status,
                Withdrawal.method,
                Withdrawal.created_at,
                Withdrawal.processed_at,
                Withdrawal.partner_id,
                Partner.first_name,
                Partner.last_name,
            )
            .join(Partner, Partner.id == Withdrawal.partner_id)
            .filter(Withdrawal.status == selected_status)
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [_queue_item(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }
