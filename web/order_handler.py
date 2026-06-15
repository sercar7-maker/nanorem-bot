from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import (
    Purchase, OrderStatus,
    Commission, CommissionStatus,
    Withdrawal, WithdrawalStatus
)
from database.models_balance import (
    BalanceTransaction,
    BalanceTransactionType
)

from core.commission import CommissionCalculator
from services.partner_service import PartnerService

router = APIRouter()

BASE_URL = "http://127.0.0.1:8000"


@router.get("/ping")
def ping():
    return {"status": "ok"}


# 🔥 ОБНОВЛЁННЫЙ ENDPOINT
@router.post("/create-partner")
def create_partner(
    telegram_id: str,
    ref: int = None  # 👈 НОВОЕ
):
    service = PartnerService()

    partner = service.create_partner(
        telegram_id=telegram_id,
        upline_id=ref  # 👈 передаём ref как upline
    )

    return {
        "id": partner.id,
        "lineage": partner.lineage,
        "upline_id": partner.upline_id
    }


@router.get("/referral-link")
def get_referral_link(partner_id: int):
    return {
        "partner_id": partner_id,
        "referral_link": f"{BASE_URL}/register?ref={partner_id}"
    }


@router.get("/balance")
def get_balance(
    partner_id: int,
    db: Session = Depends(get_db)
):
    transactions = db.query(BalanceTransaction).filter(
        BalanceTransaction.partner_id == partner_id
    ).all()

    balance = sum(t.amount for t in transactions)

    return {
        "partner_id": partner_id,
        "balance": float(balance),
        "transactions": len(transactions)
    }


@router.get("/transactions")
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

        direction = "income" if amount > 0 else "expense"

        result.append({
            "id": t.id,
            "amount": amount,
            "direction": direction,
            "type": t.type.value,
            "description": t.description,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "balance_after": running_balance
        })

    paginated = result[offset: offset + limit]

    return {
        "partner_id": partner_id,
        "count": len(paginated),
        "items": paginated
    }


@router.post("/withdraw")
def withdraw(
    partner_id: int,
    amount: float,
    db: Session = Depends(get_db)
):
    transactions = db.query(BalanceTransaction).filter(
        BalanceTransaction.partner_id == partner_id
    ).all()

    balance = sum(t.amount for t in transactions)

    if amount > balance:
        raise HTTPException(
            status_code=400,
            detail="Not enough balance"
        )

    withdrawal = Withdrawal(
        partner_id=partner_id,
        amount=amount,
        method="manual",
        details={"info": "test withdrawal"},
        status=WithdrawalStatus.COMPLETED
    )

    db.add(withdrawal)

    tx = BalanceTransaction(
        partner_id=partner_id,
        amount=-amount,
        type=BalanceTransactionType.WITHDRAWAL,
        description="Withdrawal"
    )

    db.add(tx)

    db.commit()
    db.refresh(withdrawal)

    return {
        "status": "paid",
        "withdrawal_id": withdrawal.id,
        "amount": amount
    }


@router.post("/test-order")
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
    db.commit()
    db.refresh(purchase)

    calculator = CommissionCalculator(db, bot=None)
    await calculator.process_purchase(purchase)

    commissions = db.query(Commission).filter(
        Commission.purchase_id == purchase.id,
        Commission.status == CommissionStatus.APPROVED
    ).all()

    for c in commissions:
        tx = BalanceTransaction(
            partner_id=c.partner_id,
            amount=c.amount,
            type=BalanceTransactionType.COMMISSION,
            description=f"Commission from purchase {purchase.id}"
        )
        db.add(tx)

    db.commit()

    return {
        "status": "ok",
        "purchase_id": purchase.id
    }