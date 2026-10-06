from decimal import Decimal

from database.db import SessionLocal
from database.models import Partner, WithdrawalStatus
from database.models_balance import (
    BalanceTransaction,
    BalanceTransactionType,
)
from core.balance_service import BalanceService
from services.withdrawal_service import WithdrawalService


def test_withdrawal_complete():
    session = SessionLocal()

    try:
        partner = Partner(
            first_name="Withdrawal Complete Test",
            username="withdrawal_complete_test",
        )
        session.add(partner)
        session.flush()

        balance_service = BalanceService(session)
        balance = balance_service._get_balance(partner.id)

        balance.amount = Decimal("0.00")
        balance.hold = Decimal("0.00")
        session.flush()

        balance_service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=910001,
        )

        withdrawal_service = WithdrawalService(session)

        withdrawal = withdrawal_service.create_pending(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            method="manual",
            details={"test": True},
        )

        assert withdrawal.status == WithdrawalStatus.PENDING
        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        withdrawal_service.complete(withdrawal.id)

        assert withdrawal.status == WithdrawalStatus.COMPLETED
        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("0.00")
        assert withdrawal.processed_at is not None
        assert sum(
            tx.amount
            for tx in session.query(BalanceTransaction).filter_by(
                partner_id=partner.id
            )
        ) == balance.amount

        try:
            withdrawal_service.complete(withdrawal.id)
        except ValueError:
            pass
        else:
            raise AssertionError("A completed withdrawal must not complete twice")

    finally:
        session.rollback()
        session.close()


def test_withdrawal_reject():
    session = SessionLocal()

    try:
        partner = Partner(
            first_name="Withdrawal Reject Test",
            username="withdrawal_reject_test",
        )
        session.add(partner)
        session.flush()

        balance_service = BalanceService(session)
        balance = balance_service._get_balance(partner.id)

        balance.amount = Decimal("0.00")
        balance.hold = Decimal("0.00")
        session.flush()

        balance_service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=910002,
        )

        withdrawal_service = WithdrawalService(session)

        withdrawal = withdrawal_service.create_pending(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            method="manual",
            details={"test": True},
        )

        assert withdrawal.status == WithdrawalStatus.PENDING
        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        withdrawal_service.reject(
            withdrawal.id,
            admin_comment="Test rejection",
        )

        assert withdrawal.status == WithdrawalStatus.REJECTED
        assert balance.amount == Decimal("1000.00")
        assert balance.hold == Decimal("0.00")
        assert withdrawal.processed_at is not None
        assert withdrawal.admin_comment == "Test rejection"
        assert sum(
            tx.amount
            for tx in session.query(BalanceTransaction).filter_by(
                partner_id=partner.id
            )
        ) == balance.amount

    finally:
        session.rollback()
        session.close()
