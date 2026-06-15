from sqlalchemy.orm import Session
from database.models import Partner, Purchase, Commission
from compression_engine import get_active_uplines

# Проценты комиссий для уровней 1-5
LEVEL_RATES = [20.0, 10.0, 5.0, 5.0, 5.0]


def process_mlm_commissions(session: Session, purchase: Purchase) -> None:

    # Проверяем статус покупки
    if purchase.status != "PAID":
        return

    # Проверяем сумму
    if purchase.amount <= 0:
        return

    # Проверяем, не начисляли ли уже комиссии
    existing_commission = session.query(Commission).filter(
        Commission.purchase_id == purchase.id
    ).first()

    if existing_commission:
        return

    # Получаем покупателя
    buyer = session.get(Partner, purchase.partner_id)

    if not buyer:
        return

    # Получаем активных аплайнов
    active_uplines = get_active_uplines(session, buyer, max_levels=5)

    for level, upline in enumerate(active_uplines, start=1):

        rate = LEVEL_RATES[level - 1]
        amount = round(purchase.amount * rate / 100, 2)

        commission = Commission(
            partner_id=upline.id,
            purchase_id=purchase.id,
            level=level,
            rate=rate,
            amount=amount,
            status="PENDING"
        )

        session.add(commission)