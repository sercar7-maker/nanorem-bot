from database.db import get_session
from database.models import Partner, Purchase, Commission
import uuid
import random

with get_session() as session:

    # найти тебя
    me = session.query(Partner).filter(
        Partner.telegram_id == "899738024"
    ).first()

    # случайный telegram_id
    random_id = str(random.randint(100000000, 999999999))

    # создаём тестового партнёра
    test_partner = Partner(
        telegram_id=random_id,
        first_name="TestPartner",
        upline_id=me.id
    )

    session.add(test_partner)
    session.commit()

    # создаём закупку
    purchase = Purchase(
        purchase_number=f"TEST-{uuid.uuid4().hex[:6]}",
        partner_id=test_partner.id,
        amount=1000,
        currency="RUB",
        status="PAID"
    )

    session.add(purchase)
    session.commit()

    # создаём комиссию
    commission = Commission(
        partner_id=me.id,
        purchase_id=purchase.id,
        source_partner_id=test_partner.id,
        level=1,
        rate=0.20,
        base_amount=1000,
        amount=200,
        status="PENDING"
    )

    session.add(commission)
    session.commit()

print("MLM TEST CREATED SUCCESSFULLY")