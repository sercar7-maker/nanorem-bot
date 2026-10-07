import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

from database.db import SessionLocal
from database.models import Commission, Partner, Purchase
from database.models_balance import Balance, BalanceTransaction, BalanceTransactionType
from core.commission import CommissionCalculator


def test_process_purchase_creates_five_commissions_and_is_idempotent():
    session = SessionLocal()
    session.commit = Mock(
        side_effect=AssertionError(
            "CommissionCalculator must not commit the caller's transaction"
        )
    )

    suffix = uuid4().hex[:8]

    try:
        active_until = datetime.utcnow() + timedelta(days=365)

        root = Partner(
            first_name="Integration Root",
            username=f"integration_root_{suffix}",
            subscription_end_date=active_until,
        )
        partner_a = Partner(
            first_name="Integration A",
            username=f"integration_a_{suffix}",
            subscription_end_date=active_until,
        )
        partner_b = Partner(
            first_name="Integration B",
            username=f"integration_b_{suffix}",
            subscription_end_date=active_until,
        )
        partner_c = Partner(
            first_name="Integration C",
            username=f"integration_c_{suffix}",
            subscription_end_date=active_until,
        )
        partner_d = Partner(
            first_name="Integration D",
            username=f"integration_d_{suffix}",
            subscription_end_date=active_until,
        )
        partner_e = Partner(
            first_name="Integration E",
            username=f"integration_e_{suffix}",
            subscription_end_date=active_until,
        )
        buyer = Partner(
            first_name="Integration Buyer",
            username=f"integration_buyer_{suffix}",
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

        partner_a.upline_id = root.id
        partner_a.lineage = [root.id]

        partner_b.upline_id = partner_a.id
        partner_b.lineage = [partner_a.id, root.id]

        partner_c.upline_id = partner_b.id
        partner_c.lineage = [
            partner_b.id,
            partner_a.id,
            root.id,
        ]

        partner_d.upline_id = partner_c.id
        partner_d.lineage = [
            partner_c.id,
            partner_b.id,
            partner_a.id,
            root.id,
        ]

        partner_e.upline_id = partner_d.id
        partner_e.lineage = [
            partner_d.id,
            partner_c.id,
            partner_b.id,
            partner_a.id,
            root.id,
        ]

        buyer.upline_id = partner_e.id
        buyer.lineage = [
            partner_e.id,
            partner_d.id,
            partner_c.id,
            partner_b.id,
            partner_a.id,
            root.id,
        ]

        session.flush()

        recipient_ids = [
            partner_e.id,
            partner_d.id,
            partner_c.id,
            partner_b.id,
            partner_a.id,
        ]

        balances_before = {}

        for partner_id in recipient_ids:
            balance = (
                session.query(Balance)
                .filter(Balance.partner_id == partner_id)
                .one_or_none()
            )

            balances_before[partner_id] = (
                balance.amount if balance else Decimal("0.00")
            )

        purchase = Purchase(
            purchase_number=f"TEST-PROCESS-PURCHASE-{suffix}",
            partner_id=buyer.id,
            amount=1000.0,
            currency="RUB",
        )
        session.add(purchase)
        session.flush()

        calculator = CommissionCalculator(session, Mock())

        asyncio.run(calculator.process_purchase(purchase))
        session.commit.assert_not_called()

        commissions = (
            session.query(Commission)
            .filter(Commission.purchase_id == purchase.id)
            .order_by(Commission.level)
            .all()
        )

        assert purchase.is_commission_processed is True
        assert len(commissions) == 5

        expected = [
            (partner_e.id, 1, Decimal("0.20"), Decimal("200.00")),
            (partner_d.id, 2, Decimal("0.10"), Decimal("100.00")),
            (partner_c.id, 3, Decimal("0.05"), Decimal("50.00")),
            (partner_b.id, 4, Decimal("0.05"), Decimal("50.00")),
            (partner_a.id, 5, Decimal("0.05"), Decimal("50.00")),
        ]

        for commission, (partner_id, level, rate, amount) in zip(
            commissions,
            expected,
        ):
            assert commission.partner_id == partner_id
            assert commission.level == level
            assert Decimal(str(commission.rate)) == rate
            assert Decimal(str(commission.amount)) == amount
            assert commission.status.value == "approved"

        # Шестой предок ничего не получает.
        assert (
            session.query(Commission)
            .filter(
                Commission.purchase_id == purchase.id,
                Commission.partner_id == root.id,
            )
            .count()
            == 0
        )

        expected_amounts = {
            partner_e.id: Decimal("200.00"),
            partner_d.id: Decimal("100.00"),
            partner_c.id: Decimal("50.00"),
            partner_b.id: Decimal("50.00"),
            partner_a.id: Decimal("50.00"),
        }

        balances_after_first = {}

        for partner_id, commission_amount in expected_amounts.items():
            balance = (
                session.query(Balance)
                .filter(Balance.partner_id == partner_id)
                .one()
            )

            expected_balance = (
                balances_before[partner_id] + commission_amount
            )

            assert balance.amount == expected_balance
            assert balance.hold == Decimal("0.00")

            balances_after_first[partner_id] = balance.amount

        transactions_after_first = (
            session.query(BalanceTransaction)
            .filter(
                BalanceTransaction.type == BalanceTransactionType.COMMISSION,
                BalanceTransaction.partner_id.in_(recipient_ids),
            )
            .count()
        )

        assert transactions_after_first == 5

        # Повторная обработка той же покупки ничего не должна начислить.
        asyncio.run(calculator.process_purchase(purchase))
        session.commit.assert_not_called()

        assert (
            session.query(Commission)
            .filter(Commission.purchase_id == purchase.id)
            .count()
            == 5
        )

        transactions_after_second = (
            session.query(BalanceTransaction)
            .filter(
                BalanceTransaction.type == BalanceTransactionType.COMMISSION,
                BalanceTransaction.partner_id.in_(recipient_ids),
            )
            .count()
        )

        assert transactions_after_second == transactions_after_first

        for partner_id, expected_balance in balances_after_first.items():
            balance = (
                session.query(Balance)
                .filter(Balance.partner_id == partner_id)
                .one()
            )

            assert balance.amount == expected_balance

    finally:
        session.rollback()
        session.close()