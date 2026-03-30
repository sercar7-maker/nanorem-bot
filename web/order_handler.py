from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Purchase, OrderStatus
from core.commission import CommissionCalculator
from services.partner_service import PartnerService

router = APIRouter()


@router.get("/ping")
def ping():
    return {"status": "ok"}


@router.post("/create-partner")
def create_partner(
    telegram_id: str,
    upline_id: int = None
):
    service = PartnerService()

    partner = service.create_partner(
        telegram_id=telegram_id,
        upline_id=upline_id
    )

    return {
        "id": partner.id,
        "lineage": partner.lineage
    }


@router.post("/test-order")
async def test_order(
    partner_id: int,
    amount: float,
    db: Session = Depends(get_db)
):
    # 🔒 ищем любой заказ этого партнёра с такой суммой
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

    return {
        "status": "ok",
        "purchase_id": purchase.id
    }