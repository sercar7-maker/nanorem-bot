from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models_balance import Balance, BalanceTransaction, BalanceTransactionType
import logging

logger = logging.getLogger(__name__)


class BalanceService:
    """
    Сервис для управления балансами партнёров.
    Все операции используют Decimal и проходят проверку состояния.
    """

    def __init__(self, session: Session):
        self.session = session

    def _validate_amount(self, amount: Decimal) -> None:
        """Сумма должна быть положительной"""
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

    def _validate_balance_state(self, balance: Balance) -> None:
        """Проверка корректности состояния баланса"""
        if balance.amount < 0:
            raise RuntimeError(
                f"Отрицательный баланс ({balance.amount}) у партнёра {balance.partner_id}"
            )

        if balance.hold < 0:
            raise RuntimeError(
                f"Отрицательный холд ({balance.hold}) у партнёра {balance.partner_id}"
            )

    def _get_balance(self, partner_id: int) -> Balance:
        """Получить или создать баланс партнёра"""

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

            logger.info(f"Создан новый баланс для партнёра {partner_id}")

        return balance

    def add_funds(
        self,
        partner_id: int,
        amount: Decimal,
        tx_type: BalanceTransactionType,
        reference_id: int = None,
        external_id: str = None,
    ) -> Balance:
        """
        Начисление средств на баланс
        """

        self._validate_amount(amount)

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
            "Начисление средств",
            extra={
                "partner_id": partner_id,
                "amount": str(amount),
                "balance_after": str(balance.amount),
                "type": tx_type.value,
                "reference_id": reference_id,
            },
        )

        return balance

    def hold_funds(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str = None,
    ) -> Balance:
        """
        Блокировка средств под вывод
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
            "Средства заблокированы (hold)",
            extra={
                "partner_id": partner_id,
                "amount": str(amount),
                "balance_after": str(balance.amount),
                "hold_after": str(balance.hold),
                "reference_id": reference_id,
            },
        )

        return balance

    def release_hold(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str = None,
    ) -> Balance:
        """
        Возврат средств из холда обратно на баланс
        """

        self._validate_amount(amount)

        balance = self._get_balance(partner_id)

        if balance.hold < amount:
            raise ValueError("Недостаточно средств в холде")

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
            "Средства возвращены из холда",
            extra={
                "partner_id": partner_id,
                "amount": str(amount),
                "balance_after": str(balance.amount),
                "hold_after": str(balance.hold),
                "reference_id": reference_id,
            },
        )

        return balance

    def confirm_hold_spent(
        self,
        partner_id: int,
        amount: Decimal,
        reference_id: int,
        external_id: str = None,
    ) -> Balance:
        """
        Финальное списание средств после успешной выплаты
        """

        self._validate_amount(amount)

        balance = self._get_balance(partner_id)

        if balance.hold < amount:
            raise ValueError("Недостаточно средств в холде")

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
            "Выплата подтверждена",
            extra={
                "partner_id": partner_id,
                "amount": str(amount),
                "hold_after": str(balance.hold),
                "reference_id": reference_id,
            },
        )

        return balance