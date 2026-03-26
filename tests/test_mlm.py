import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from database.db import SessionLocal
from database.models import Partner, Purchase, OrderStatus
from core.commission import CommissionCalculator


class FakeBot:
    async def send_message(self, *args, **kwargs):
        print("📩 FAKE MESSAGE SENT")


def main():
    session = SessionLocal()

    # 1. найти тебя
    you = session.query(Partner).filter_by(telegram_id="899738024").first()

    # 2. найти партнёра под тобой
    user = session.query(Partner).filter_by(upline_id=you.id).first()

    if not user:
        print("❌ нет партнёра под тобой")
        return

    print(f"👤 Ты: {you.id}")
    print(f"👤 Нижний партнёр: {user.id}")

    # 3. создаём заказ
    purchase = Purchase(
        purchase_number="TEST_LOCAL",
        partner_id=user.id,
        amount=1000,
        status=OrderStatus.PAID,
        ext_ref="TEST_LOCAL",
    )

    session.add(purchase)
    session.commit()
    session.refresh(purchase)

    print(f"📦 Purchase ID: {purchase.id}")

    # 4. считаем комиссию напрямую
    calculator = CommissionCalculator(session, FakeBot())

    import asyncio
    asyncio.run(calculator.process_purchase(purchase))

    # 5. проверяем комиссии
    from database.models import Commission

    commissions = session.query(Commission).all()

    print("\n=== КОМИССИИ ===")

    for c in commissions:
        print(
            f"partner_id={c.partner_id}, amount={c.amount}, level={c.level}"
        )

    session.close()


if __name__ == "__main__":
    main()