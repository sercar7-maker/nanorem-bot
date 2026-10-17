from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.balance_service import BalanceService
from database.models import Withdrawal, WithdrawalStatus


class WithdrawalService:
    """Withdrawal lifecycle; caller owns commit, each operation uses a savepoint."""

    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    @staticmethod
    def _money(amount: Decimal) -> Decimal:
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("Invalid withdrawal amount") from None
        if not value.is_finite() or value <= 0:
            raise ValueError("Withdrawal amount must be finite and positive")
        if value > Decimal("9999999999999999.99"):
            raise ValueError("Withdrawal amount is too large")
        if value != value.quantize(Decimal("0.01")):
            raise ValueError("Withdrawal amount must have at most two decimals")
        return value

    def create_pending(
        self,
        partner_id: int,
        amount: Decimal,
        method: str = "manual",
        details: dict | None = None,
    ) -> Withdrawal:
        amount = self._money(amount)
        with self.session.begin_nested():
            withdrawal = Withdrawal(
                partner_id=partner_id,
                amount=amount,
                method=method,
                details=details or {},
                status=WithdrawalStatus.PENDING,
            )
            self.session.add(withdrawal)
            self.session.flush()
            self.balance_service.hold_funds(
                partner_id=partner_id,
                amount=amount,
                reference_id=withdrawal.id,
            )
            self.session.flush()
        return withdrawal

    def complete(self, withdrawal_id: int) -> Withdrawal:
        with self.session.begin_nested():
            result = self.session.execute(
                update(Withdrawal)
                .where(
                    Withdrawal.id == withdrawal_id,
                    Withdrawal.status == WithdrawalStatus.PENDING,
                )
                .values(
                    status=WithdrawalStatus.COMPLETED,
                    processed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            if result.rowcount != 1:
                raise ValueError("Only a PENDING withdrawal can be completed")
            withdrawal = self._get_withdrawal(withdrawal_id)
            self.balance_service.confirm_hold_spent(
                partner_id=withdrawal.partner_id,
                amount=Decimal(str(withdrawal.amount)),
                reference_id=withdrawal.id,
            )
            self.session.flush()
        return withdrawal

    def reject(
        self,
        withdrawal_id: int,
        admin_comment: str | None = None,
    ) -> Withdrawal:
        with self.session.begin_nested():
            result = self.session.execute(
                update(Withdrawal)
                .where(
                    Withdrawal.id == withdrawal_id,
                    Withdrawal.status == WithdrawalStatus.PENDING,
                )
                .values(
                    status=WithdrawalStatus.REJECTED,
                    processed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    admin_comment=admin_comment,
                )
            )
            if result.rowcount != 1:
                raise ValueError("Only a PENDING withdrawal can be rejected")
            withdrawal = self._get_withdrawal(withdrawal_id)
            self.balance_service.release_hold(
                partner_id=withdrawal.partner_id,
                amount=Decimal(str(withdrawal.amount)),
                reference_id=withdrawal.id,
            )
            self.session.flush()
        return withdrawal

    def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal:
        withdrawal = self.session.get(Withdrawal, withdrawal_id)
        if withdrawal is None:
            raise ValueError("Withdrawal not found")
        return withdrawal
