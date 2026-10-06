from decimal import Decimal

from database.db import SessionLocal
from database.models import Partner
from database.models_balance import BalanceTransaction, BalanceTransactionType
from core.balance_service import BalanceService


def test_balance_hold_release_and_confirm():
    session = SessionLocal()

    try:
        partner = Partner(
            first_name="Balance Test",
            username="balance_test",
        )
        session.add(partner)
        session.flush()

        service = BalanceService(session)

        balance = service._get_balance(partner.id)
        balance.amount = Decimal("0.00")
        balance.hold = Decimal("0.00")
        session.flush()

        service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=900001,
        )
        service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=900001,
        )

        assert balance.amount == Decimal("1000.00")
        assert balance.hold == Decimal("0.00")
        assert (
            session.query(BalanceTransaction)
            .filter_by(
                partner_id=partner.id,
                reference_id=900001,
            )
            .count()
            == 1
        )

        service.hold_funds(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900002,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        service.release_hold(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900002,
        )

        assert balance.amount == Decimal("1000.00")
        assert balance.hold == Decimal("0.00")

        service.hold_funds(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900003,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        service.confirm_hold_spent(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900003,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("0.00")

    finally:
        session.rollback()
        session.close()


def test_confirm_hold_cannot_be_applied_twice():
    session = SessionLocal()

    try:
        partner = Partner(
            first_name="Balance Duplicate Test",
            username="balance_duplicate_test",
        )
        session.add(partner)
        session.flush()

        service = BalanceService(session)

        balance = service._get_balance(partner.id)
        balance.amount = Decimal("0.00")
        balance.hold = Decimal("0.00")
        session.flush()

        service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=900004,
        )

        service.hold_funds(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900005,
        )

        service.confirm_hold_spent(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900005,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("0.00")

        try:
            service.confirm_hold_spent(
                partner_id=partner.id,
                amount=Decimal("300.00"),
                reference_id=900005,
            )
        except ValueError:
            pass

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("0.00")

    finally:
        session.rollback()
        session.close()