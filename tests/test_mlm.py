
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import get_session
from database.models import Partner, Purchase, Commission, OrderStatus, CommissionStatus
import uuid
import random
with get_session() as session:
    me = session.query(Partner).filter(
        Partner.telegram_id == "899738024"
    ).first()

    random_id = str(random.randint(100000000, 999999999))

    test_partner = Partner(
        telegram_id=random_id,
        first_name="TestPartner",
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

print("MLM TEST CREATED SUCCESSFULLY")