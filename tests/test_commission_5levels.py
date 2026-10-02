from decimal import Decimal
from unittest.mock import Mock

from database.db import SessionLocal
from database.models import Partner, Purchase
from core.commission import CommissionCalculator


def test_commission_5_levels():
    session = SessionLocal()

    try:
        # Создаем цепочку:
        # Root -> A -> B -> C -> D -> E -> Buyer
        root = Partner(
            first_name="Test Root",
            username="test_root",
        )

        partner_a = Partner(
            first_name="Test A",
            username="test_a",
        )

        partner_b = Partner(
            first_name="Test B",
            username="test_b",
        )

        partner_c = Partner(
            first_name="Test C",
            username="test_c",
        )

        partner_d = Partner(
            first_name="Test D",
            username="test_d",
        )

        partner_e = Partner(
            first_name="Test E",
            username="test_e",
        )

        buyer = Partner(
            first_name="Test Buyer",
            username="test_buyer",
        )

        session.add_all(
            [
                root,
                partner_a,
                partner_b,
                partner_c,
                partner_d,
                partner_e,
                buyer,
            ]
        )
        session.flush()

        purchase = Purchase(
            purchase_number="TEST-5-LEVELS",
            partner_id=buyer.id,
            amount=1000.00,
            currency="RUB",
        )

        session.add(purchase)
        session.flush()

        calculator = CommissionCalculator(
            session,
            Mock(),
        )

        # Для покупателя ближайшие 5 предков:
        # E -> D -> C -> B -> A
        upline_chain = [
            (partner_e.id, True),
            (partner_d.id, True),
            (partner_c.id, True),
            (partner_b.id, True),
            (partner_a.id, True),
            (root.id, True),
        ]

        commissions = calculator.calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            upline_chain=upline_chain,
        )

        # Должно быть только 5 уровней.
        assert len(commissions) == 5

        rates = [Decimal(str(c.rate)) for c in commissions]
        amounts = [Decimal(str(c.amount)) for c in commissions]

        assert rates == [
            Decimal("0.20"),
            Decimal("0.10"),
            Decimal("0.05"),
            Decimal("0.05"),
            Decimal("0.05"),
        ]

        assert amounts == [
            Decimal("200.00"),
            Decimal("100.00"),
            Decimal("50.00"),
            Decimal("50.00"),
            Decimal("50.00"),
        ]

    finally:
        # Тест не должен менять реальную базу данных.
        session.rollback()
        session.close()