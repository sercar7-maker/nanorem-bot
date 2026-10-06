from datetime import datetime
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.balance_service import BalanceService
from database.models import Withdrawal, WithdrawalStatus


class WithdrawalService:
    """
    Управляет жизненным циклом заявки на вывод средств.

    Сценарий:

        create_pending()
            ↓
        PENDING
            ↓
        complete()  → COMPLETED

    или:

        PENDING
            ↓
        reject()    → REJECTED
    """

    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    def create_pending(
        self,
        partner_id: int,
        amount: Decimal,
        method: str = "manual",
        details: dict | None = None,
    ) -> Withdrawal:
        """
        Создаёт заявку на вывод и блокирует сумму в hold.
        """

        if amount <= 0:
            raise ValueError("Сумма вывода должна быть положительной")

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

        return withdrawal

    def complete(self, withdrawal_id: int) -> Withdrawal:
        """
        Завершает выплату.

        Деньги, которые были в hold, окончательно списываются.
        """

        processed_at = datetime.utcnow()
        result = self.session.execute(
            update(Withdrawal)
            .where(
                Withdrawal.id == withdrawal_id,
                Withdrawal.status == WithdrawalStatus.PENDING,
            )
            .values(
                status=WithdrawalStatus.COMPLETED,
                processed_at=processed_at,
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Завершить можно только заявку со статусом PENDING"
            )

        withdrawal = self._get_withdrawal(withdrawal_id)
        amount = Decimal(str(withdrawal.amount))

        self.balance_service.confirm_hold_spent(
            partner_id=withdrawal.partner_id,
            amount=amount,
            reference_id=withdrawal.id,
        )

        self.session.flush()

        return withdrawal

    def reject(
        self,
        withdrawal_id: int,
        admin_comment: str | None = None,
    ) -> Withdrawal:
        """
        Отклоняет выплату.

        Деньги из hold возвращаются на доступный баланс.
        """

        processed_at = datetime.utcnow()
        result = self.session.execute(
            update(Withdrawal)
            .where(
                Withdrawal.id == withdrawal_id,
                Withdrawal.status == WithdrawalStatus.PENDING,
            )
            .values(
                status=WithdrawalStatus.REJECTED,
                processed_at=processed_at,
                admin_comment=admin_comment,
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Отклонить можно только заявку со статусом PENDING"
            )

        withdrawal = self._get_withdrawal(withdrawal_id)
        amount = Decimal(str(withdrawal.amount))

        self.balance_service.release_hold(
            partner_id=withdrawal.partner_id,
            amount=amount,
            reference_id=withdrawal.id,
        )

        self.session.flush()

        return withdrawal

    def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal:
        withdrawal = (
            self.session.query(Withdrawal)
            .filter(Withdrawal.id == withdrawal_id)
            .first()
        )

        if not withdrawal:
            raise ValueError(
                f"Заявка на вывод {withdrawal_id} не найдена"
            )

        return withdrawal