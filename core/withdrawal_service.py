from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import Withdrawal, WithdrawalStatus
from core.balance_service import BalanceService

import logging

logger = logging.getLogger(__name__)


class WithdrawalService:
    """
    Сервис для управления выводами средств партнёров.
    """

    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    def request_withdrawal(
        self,
        partner_id: int,
        amount: Decimal,
        method: str,
        details: dict
    ) -> Withdrawal:
        """
        Создание заявки на вывод средств.
        """

        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        withdrawal = Withdrawal(
            partner_id=partner_id,
            amount=amount,
            method=method,
            details=details,
            status=WithdrawalStatus.PENDING.value
        )

        self.session.add(withdrawal)
        self.session.flush()

        # блокируем средства
        self.balance_service.hold_funds(
            partner_id,
            amount,
            withdrawal.id
        )

        logger.info(
            "Создана заявка на вывод",
            extra={
                "withdrawal_id": withdrawal.id,
                "partner_id": partner_id,
                "amount": str(amount)
            }
        )

        return withdrawal

    def approve_withdrawal(
        self,
        withdrawal_id: int,
        admin_comment: str | None = None
    ) -> Withdrawal:
        """
        Подтверждение вывода средств.
        """

        withdrawal = self.session.get(Withdrawal, withdrawal_id)

        if not withdrawal:
            raise ValueError("Заявка не найдена")

        if withdrawal.status != WithdrawalStatus.PENDING.value:
            raise ValueError("Заявка уже обработана")

        # окончательно списываем средства из холда
        self.balance_service.confirm_hold_spent(
            withdrawal.partner_id,
            withdrawal.amount,
            withdrawal.id
        )

        withdrawal.status = WithdrawalStatus.COMPLETED.value
        withdrawal.processed_at = datetime.utcnow()
        withdrawal.admin_comment = admin_comment

        self.session.flush()

        logger.info(
            "Заявка на вывод одобрена",
            extra={
                "withdrawal_id": withdrawal.id,
                "partner_id": withdrawal.partner_id,
                "amount": str(withdrawal.amount)
            }
        )

        return withdrawal

    def reject_withdrawal(
        self,
        withdrawal_id: int,
        admin_comment: str | None = None
    ) -> Withdrawal:
        """
        Отклонение заявки на вывод.
        """

        withdrawal = self.session.get(Withdrawal, withdrawal_id)

        if not withdrawal:
            raise ValueError("Заявка не найдена")

        if withdrawal.status != WithdrawalStatus.PENDING.value:
            raise ValueError("Заявка уже обработана")

        # возвращаем средства из холда
        self.balance_service.release_hold(
            withdrawal.partner_id,
            withdrawal.amount,
            withdrawal.id
        )

        withdrawal.status = WithdrawalStatus.REJECTED.value
        withdrawal.processed_at = datetime.utcnow()
        withdrawal.admin_comment = admin_comment

        self.session.flush()

        logger.info(
            "Заявка на вывод отклонена",
            extra={
                "withdrawal_id": withdrawal.id,
                "partner_id": withdrawal.partner_id,
                "amount": str(withdrawal.amount)
            }
        )

        return withdrawal

    def get_withdrawals(
        self,
        partner_id: int | None = None,
        status: str | None = None
    ):
        """
        Получение списка заявок на вывод.
        """

        query = select(Withdrawal)

        if partner_id:
            query = query.where(Withdrawal.partner_id == partner_id)

        if status:
            query = query.where(Withdrawal.status == status)

        query = query.order_by(Withdrawal.created_at.desc())

        return self.session.execute(query).scalars().all()