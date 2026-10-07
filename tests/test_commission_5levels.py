from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock

from database.db import SessionLocal
from database.models import Partner, Purchase, PartnerStatus
from core.commission import CommissionCalculator


def test_commission_5_levels():
    session = SessionLocal()
    active_until = datetime.utcnow() + timedelta(days=365)

    try:
        # Создаем цепочку:
        # Root -> A -> B -> C -> D -> E -> Buyer
        root = Partner(
            first_name="Test Root",
            username="test_root",
            subscription_end_date=active_until,
        )

        partner_a = Partner(
            first_name="Test A",
            username="test_a",
            subscription_end_date=active_until,
        )

        partner_b = Partner(
            first_name="Test B",
            username="test_b",
            subscription_end_date=active_until,
        )

        partner_c = Partner(
            first_name="Test C",
            username="test_c",
            subscription_end_date=active_until,
        )

        partner_d = Partner(
            first_name="Test D",
            username="test_d",
            subscription_end_date=active_until,
        )

        partner_e = Partner(
            first_name="Test E",
            username="test_e",
            subscription_end_date=active_until,
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
            lineage=[partner_e.id, partner_d.id, partner_c.id, partner_b.id, partner_a.id, root.id],
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

def test_commission_compression_skips_inactive_partners():
    session = SessionLocal()

    try:
        active_1 = Partner(first_name="Active 1", username="compression_active_1")
        inactive_1 = Partner(first_name="Inactive 1", username="compression_inactive_1")
        active_2 = Partner(first_name="Active 2", username="compression_active_2")
        inactive_2 = Partner(first_name="Inactive 2", username="compression_inactive_2")
        active_3 = Partner(first_name="Active 3", username="compression_active_3")
        buyer = Partner(first_name="Compression Buyer", username="compression_buyer")

        session.add_all([
            active_1,
            inactive_1,
            active_2,
            inactive_2,
            active_3,
            buyer,
        ])
        session.flush()

        for active_partner in (active_1, active_2, active_3):
            active_partner.subscription_end_date = (
                datetime.utcnow() + timedelta(days=365)
            )
        inactive_1.status = PartnerStatus.INACTIVE
        inactive_2.status = PartnerStatus.INACTIVE
        session.flush()

        calculator = CommissionCalculator(session, Mock())

        results = calculator.calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            lineage=[
                active_1.id,
                inactive_1.id,
                active_2.id,
                inactive_2.id,
                active_3.id,
            ],
        )

        assert [result.partner_id for result in results] == [
            active_1.id,
            active_2.id,
            active_3.id,
        ]

        assert [result.level for result in results] == [1, 2, 3]

        assert [result.amount for result in results] == [
            Decimal("200.00"),
            Decimal("100.00"),
            Decimal("50.00"),
        ]

        assert results[0].compressed is False
        assert results[1].compressed is True
        assert results[2].compressed is True

    finally:
        session.rollback()
        session.close()


def test_commission_chain_never_pays_the_buying_partner():
    session = SessionLocal()

    try:
        buyer = Partner(
            first_name="Self Commission Buyer",
            username="self_commission_buyer",
        )
        upline = Partner(
            first_name="Self Commission Upline",
            username="self_commission_upline",
            subscription_end_date=(
                datetime.utcnow() + timedelta(days=365)
            ),
        )
        session.add_all([buyer, upline])
        session.flush()

        results = CommissionCalculator(
            session,
            Mock(),
        ).calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            lineage=[buyer.id, upline.id],
        )

        assert [result.partner_id for result in results] == [upline.id]
        assert [result.level for result in results] == [1]
        assert results[0].amount == Decimal("200.00")
    finally:
        session.rollback()
        session.close()


def test_compression_assigns_nearest_active_ancestors_to_payout_levels():
    session = SessionLocal()

    try:
        active_until = datetime.utcnow() + timedelta(days=365)
        root = Partner(
            first_name="Compression Scenario Root",
            subscription_end_date=active_until,
        )
        active_a = Partner(
            first_name="Compression Scenario A",
            subscription_end_date=active_until,
        )
        inactive_b = Partner(
            first_name="Compression Scenario B",
            status=PartnerStatus.INACTIVE,
        )
        active_c = Partner(
            first_name="Compression Scenario C",
            subscription_end_date=active_until,
        )
        buyer_d = Partner(first_name="Compression Scenario D")
        session.add_all([root, active_a, inactive_b, active_c, buyer_d])
        session.flush()

        results = CommissionCalculator(
            session,
            Mock(),
        ).calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer_d.id,
            lineage=[active_c.id, inactive_b.id, active_a.id, root.id],
        )

        assert [
            (result.partner_id, result.level, result.amount)
            for result in results
        ] == [
            (active_c.id, 1, Decimal("200.00")),
            (active_a.id, 2, Decimal("100.00")),
            (root.id, 3, Decimal("50.00")),
        ]
        assert results[1].compressed is True
    finally:
        session.rollback()
        session.close()
