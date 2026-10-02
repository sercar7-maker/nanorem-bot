from decimal import Decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)

logger = logging.getLogger(__name__)


class BalanceService:
    """
    Управление балансами партнёров.

    Balance.amount — текущий доступный баланс.
    Balance.hold — заблокированная сумма.
    BalanceTransaction — журнал финансовых операций.

    Все финансовые суммы внутри сервиса обрабатываются через Decimal.
    """

    def __init__(self, session: Session):
        self.session = session

    def _validate_amount(self, amount: Decimal) -> None:
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

    def _validate_balance_state(self, balance: Balance) -> None:
        if balance.amount < 0:
            raise RuntimeError(
                f"Отрицательный баланс ({balance.amount}) "
                f"у партнёра {balance.partner_id}"
            )

        if balance.hold < 0:
            raise RuntimeError(
                f"Отрицательный hold ({balance.hold}) "
                f"у партнёра {balance.partner_id}"
            )

    def _get_balance(self, partner_id: int) -> Balance:
        balance = self.session.execute(
            select(Balance).where(Balance.partner_id == partner_id)
        ).scalar_one_or_none()

        if not balance:
            balance = Balance(
                partner_id=partner_id,
                amount=Decimal("0.00"),
                hold=Decimal("0.00"),
            )

            self.session.add(balance)
            self.session.flush()

            logger.info(
                "Создан новый баланс для партнёра %s",
                partner_id,
            )

        return balance

    def _find_existing_transaction(
        self,
        partner_id: int,
        tx_type: BalanceTransactionType,
        reference_id: int | None = None,
        external_id: str | None = None,
    ) -> BalanceTransaction | None:
        """
        Ищет уже созданную финансовую операцию.

        Для комиссии используется:
            partner_id + type + reference_id

        Для внешних операций дополнительно можно использовать:
            partner_id + type + external_id
        """

        if reference_id is not None:
            transaction = self.session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.partner_id == partner_id,
                    BalanceTransaction.type == tx_type,
                    BalanceTransaction.reference_id == reference_id,
                )
            ).scalar_one_or_none()

            if transaction:
                return transaction

        if external_id is not None:
            transaction = self.session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.partner_id == partner_id,
                    BalanceTransaction.type == tx_type,
                    BalanceTransaction.external_id == external_id,
                )
            ).scalar_one_or_none()

            if transaction:
                return transaction

        return None

    def add_funds(
        self,
        partner_id: int,
        amount: Decimal,
        tx_type: BalanceTransactionType,
        reference_id: int | None = None,
        external_id: str | None = None,
    ) -> Balance:
        """
        Начисляет средства на баланс.

        Если операция с таким reference_id/external_id уже существует,
        повторное начисление не выполняется.
        """

        self._validate_amount(amount)

        existing_transaction = self._find_existing_transaction(
            partner_id=partner_id,
            tx_type=tx_type,
            reference_id=reference_id,
            external_id=external_id,
        )

        if existing_transaction:
            logger.warning(
                "Повторное начисление пропущено: "
                "partner_id=%s, type=%s, reference_id=%s, external_id=%s",
                partner_id,
                tx_type.value,
                reference_id,
                external_id,
            )

            return self._get_balance(partner_id)

        balance = self._get_balance(partner_id)
        balance.amount += amount

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=amount,
            type=tx_type,
            reference_id=reference_id,
            external_id=external_id,
        )

        self.session.add(transaction)
        self.session.flush()

        self._validate_balance_state(balance)

        logger.info(
            "Начисление средств: partner_id=%s, amount=%s, "
            "balance_after=%s, type=%s, reference_id=%s",
            partner_id,
            amount,
            balance.amount,
            tx_type.value,
            reference_id,
        )

        return balance

    def hold_funds(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str | None = None,
    ) -> Balance:
        """
        Блокирует средства под вывод.
        """

        self._validate_amount(amount)

        balance = self._get_balance(partner_id)

        if balance.amount < amount:
            raise ValueError("Недостаточно средств")

        balance.amount -= amount
        balance.hold += amount

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=-amount,
            type=BalanceTransactionType.WITHDRAWAL,
            reference_id=reference_id,
            external_id=external_id,
        )

        self.session.add(transaction)
        self.session.flush()

        self._validate_balance_state(balance)

        logger.info(
            "Средства заблокированы: partner_id=%s, amount=%s, "
            "balance_after=%s, hold_after=%s, reference_id=%s",
            partner_id,
            amount,
            balance.amount,
            balance.hold,
            reference_id,
        )

        return balance

    def release_hold(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str | None = None,
    ) -> Balance:
        """
        Возвращает заблокированные средства на доступный баланс.
        """

        self._validate_amount(amount)

        balance = self._get_balance(partner_id)

        if balance.hold < amount:
            raise ValueError("Недостаточно средств в hold")

        balance.hold -= amount
        balance.amount += amount

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=amount,
            type=BalanceTransactionType.WITHDRAWAL,
            reference_id=reference_id,
            external_id=external_id,
        )

        self.session.add(transaction)
        self.session.flush()

        self._validate_balance_state(balance)

        logger.info(
            "Средства возвращены из hold: partner_id=%s, amount=%s, "
            "balance_after=%s, hold_after=%s, reference_id=%s",
            partner_id,
            amount,
            balance.amount,
            balance.hold,
            reference_id,
        )

        return balance

    def confirm_hold_spent(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str | None = None,
    ) -> Balance:
        """
        Окончательно списывает средства из hold после успешной выплаты.
        """

        self._validate_amount(amount)

        balance = self._get_balance(partner_id)

        if balance.hold < amount:
            raise ValueError("Недостаточно средств в hold")

        balance.hold -= amount

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=-amount,
            type=BalanceTransactionType.WITHDRAWAL,
            reference_id=reference_id,
            external_id=external_id,
        )

        self.session.add(transaction)
        self.session.flush()

        self._validate_balance_state(balance)

        logger.info(
            "Выплата подтверждена: partner_id=%s, amount=%s, "
            "hold_after=%s, reference_id=%s",
            partner_id,
            amount,
            balance.hold,
            reference_id,
        )

        return balance