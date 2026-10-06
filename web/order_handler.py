from decimal import Decimal
import hmac

from fastapi import APIRouter, Depends, HTTPException, Header

from sqlalchemy.orm import Session

from config import ADMIN_API_SECRET, DEBUG
from database.db import get_db
from database.models import (
    Purchase,
    OrderStatus,
)
from database.models_balance import Balance, BalanceTransaction

from core.commission import CommissionCalculator
from services.partner_service import PartnerService
from services.withdrawal_service import WithdrawalService

router = APIRouter()

BASE_URL = "https://nanorvs.ru"


def require_admin_secret(
    x_admin_secret: str | None = Header(default=None),
) -> None:
    """
    Защита технических/административных endpoints.

    Endpoint разрешён только в DEBUG-режиме и
    только при наличии правильного секрета.
    """
    if not DEBUG:
        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    if not ADMIN_API_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Admin API secret is not configured",
        )

    if not x_admin_secret or not hmac.compare_digest(
        x_admin_secret,
        ADMIN_API_SECRET,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin secret",
        )


@router.get("/ping")
def ping():
    return {"status": "ok"}


@router.post(
    "/create-partner",
    dependencies=[Depends(require_admin_secret)],
)
def create_partner(
    telegram_id: str,
    ref: int = None,
):
    service = PartnerService()

    partner = service.create_partner(
        telegram_id=telegram_id,
        upline_id=ref
    )

    return {
        "id": partner.id,
        "lineage": partner.lineage,
        "upline_id": partner.upline_id
    }


@router.get(
    "/referral-link",
    dependencies=[Depends(require_admin_secret)],
)
def get_referral_link(partner_id: int):
    return {
        "partner_id": partner_id,
        "referral_link": f"{BASE_URL}/register?ref={partner_id}"
    }


@router.get(
    "/balance",
    dependencies=[Depends(require_admin_secret)],
)
def get_balance(
    partner_id: int,
    db: Session = Depends(get_db)
):
    transactions = db.query(BalanceTransaction).filter(
        BalanceTransaction.partner_id == partner_id
    ).all()

    balance = db.query(Balance.amount).filter(
        Balance.partner_id == partner_id
    ).scalar()

    if balance is None:
        balance = sum(t.amount for t in transactions)

    return {
        "partner_id": partner_id,
        "balance": float(balance),
        "transactions": len(transactions)
    }


@router.get(
    "/transactions",
    dependencies=[Depends(require_admin_secret)],
)
def get_transactions(
    partner_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    transactions = db.query(BalanceTransaction).filter(
        BalanceTransaction.partner_id == partner_id
    ).order_by(
        BalanceTransaction.created_at.asc()
    ).all()

    result = []
    running_balance = 0

    for t in transactions:
        amount = float(t.amount)
        running_balance += amount

        direction = (
            "income" if amount > 0
            else "expense" if amount < 0
            else "settlement"
        )

        result.append({
            "id": t.id,
            "amount": amount,
            "direction": direction,
            "type": t.type.value,
            "description": t.description,
            "created_at": (
                t.created_at.isoformat()
                if t.created_at
                else None
            ),
            "balance_after": running_balance
        })

    paginated = result[offset: offset + limit]

    return {
        "partner_id": partner_id,
        "count": len(paginated),
        "items": paginated
    }


@router.post(
    "/withdraw",
    dependencies=[Depends(require_admin_secret)],
)
def withdraw(
    partner_id: int,
    amount: float,
    db: Session = Depends(get_db)
):
    try:
        service = WithdrawalService(db)

        withdrawal = service.create_pending(
            partner_id=partner_id,
            amount=Decimal(str(amount)),
            method="manual",
            details={"info": "web withdrawal"},
        )

        db.commit()
        db.refresh(withdrawal)

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Withdrawal processing error"
        )

    return {
        "status": withdrawal.status.value,
        "withdrawal_id": withdrawal.id,
        "amount": amount
    }


@router.post(
    "/test-order",
    include_in_schema=False,
    dependencies=[Depends(require_admin_secret)],
)
async def test_order(
    partner_id: int,
    amount: float,
    db: Session = Depends(get_db)
):
    existing = db.query(Purchase).filter(
        Purchase.partner_id == partner_id,
        Purchase.amount == amount
    ).first()

    if existing:
        return {
            "status": "already exists",
            "purchase_id": existing.id
        }

    purchase = Purchase(
        purchase_number=f"TEST-{partner_id}-{amount}",
        partner_id=partner_id,
        amount=amount,
        status=OrderStatus.PAID,
    )

    db.add(purchase)
    db.flush()

    calculator = CommissionCalculator(db, bot=None)
    await calculator.process_purchase(purchase)
    db.commit()
    db.refresh(purchase)

    return {
        "status": "ok",
        "purchase_id": purchase.id
    }