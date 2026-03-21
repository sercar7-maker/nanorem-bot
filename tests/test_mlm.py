import os
import sys
from pathlib import Path
import uuid
import random
import asyncio

os.environ["NO_PROXY"] = "*"
for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy"
]:
    os.environ.pop(key, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Bot

from config import BOT_TOKEN
from database.db import get_session
from database.models import Partner, Purchase, Commission, OrderStatus, CommissionStatus
from services.notifications import NotificationService


async def main():
    with get_session() as session:
        me = session.query(Partner).filter(
            Partner.telegram_id == "899738024"
        ).first()

        if not me:
            print("MAIN PARTNER NOT FOUND")
            return

        random_id = str(random.randint(100000000, 999999999))

        test_partner = Partner(
            telegram_id=random_id,
            first_name="TestPartner",
            last_name="Demo",
            upline_id=me.id
        )

        session.add(test_partner)
        session.commit()
        session.refresh(test_partner)

        purchase = Purchase(
            purchase_number=f"TEST-{uuid.uuid4().hex[:6]}",
            partner_id=test_partner.id,
            amount=1000,
            currency="RUB",
            status=OrderStatus.PAID
        )

        session.add(purchase)
        session.commit()
        session.refresh(purchase)

        commission = Commission(
            partner_id=me.id,
            purchase_id=purchase.id,
            source_partner_id=test_partner.id,
            level=1,
            rate=0.20,
            base_amount=1000,
            amount=200,
            status=CommissionStatus.PENDING
        )

        session.add(commission)
        session.commit()

        if me.telegram_id:
            bot = Bot(token=BOT_TOKEN)
            notify = NotificationService(bot)

            await notify.notify_new_referral(
                telegram_id=int(me.telegram_id),
                partner_name=f"{test_partner.first_name} {test_partner.last_name}"
            )

    print("MLM TEST CREATED SUCCESSFULLY")


if __name__ == "__main__":
    asyncio.run(main())