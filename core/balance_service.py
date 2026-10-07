from datetime import datetime
from decimal import Decimal
import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from database.models_balance import (
    Balance,
    BalanceOrderReservation,
    BalanceOrderReservationStatus,
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
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Сумма должна быть положительной")

    def _get_purchase_balance(self, partner_id: int) -> Balance:
        dialect_name = self.session.get_bind().dialect.name
        insert = {
            "sqlite": sqlite_insert,
            "postgresql": postgresql_insert,
        }.get(dialect_name)
        if insert is None:
            raise RuntimeError(
                "Purchase balance reservations support only "
                "SQLite and PostgreSQL"
            )

        self.session.execute(
            insert(Balance.__table__)
            .values(
                partner_id=partner_id,
                amount=Decimal("0.00"),
                hold=Decimal("0.00"),
            )
            .on_conflict_do_nothing(
                index_elements=[Balance.partner_id]
            )
        )

        return self.session.execute(
            select(Balance).where(Balance.partner_id == partner_id)
        ).scalar_one()

    def _get_purchase_reservation(
        self,
        order_id: str,
    ) -> BalanceOrderReservation:
        reservation = self.session.execute(
            select(BalanceOrderReservation).where(
                BalanceOrderReservation.order_id == order_id
            )
        ).scalar_one_or_none()
        if reservation is None:
            raise ValueError(
                f"Balance reservation for WooCommerce order "
                f"{order_id} was not found"
            )
        return reservation

    @staticmethod
    def _purchase_event_id(order_id: str, action: str) -> str:
        return f"wc-order:{order_id}:{action}"

    def reserve_purchase(
        self,
        partner_id: int,
        order_id: str | int,
        order_total: Decimal,
    ) -> BalanceOrderReservation:
        """Atomically reserve up to the balance available for this order."""
        self._validate_amount(order_total)
        if order_total != order_total.quantize(Decimal("0.01")):
            raise ValueError(
                "WooCommerce order total must have at most 2 decimals"
            )

        order_key = str(order_id).strip()
        if not order_key or len(order_key) > 100:
            raise ValueError("WooCommerce order id must be 1-100 characters")

        dialect_name = self.session.get_bind().dialect.name
        insert = {
            "sqlite": sqlite_insert,
            "postgresql": postgresql_insert,
        }.get(dialect_name)
        if insert is None:
            raise RuntimeError(
                "Purchase balance reservations support only "
                "SQLite and PostgreSQL"
            )

        result = self.session.execute(
            insert(BalanceOrderReservation.__table__)
            .values(
                order_id=order_key,
                partner_id=partner_id,
                order_total=order_total,
                amount=Decimal("0.00"),
                status=BalanceOrderReservationStatus.PENDING,
            )
            .on_conflict_do_nothing(
                index_elements=[BalanceOrderReservation.order_id]
            )
        )
        reservation = self._get_purchase_reservation(order_key)

        if result.rowcount == 0:
            if (
                reservation.partner_id != partner_id
                or Decimal(str(reservation.order_total)) != order_total
            ):
                raise ValueError(
                    "WooCommerce order id is already reserved for a "
                    "different partner or order total"
                )
            return reservation

        balance = self._get_purchase_balance(partner_id)
        reserved_amount = Decimal("0.00")

        # The conditional UPDATE serializes deductions on the balance row.
        for _ in range(10):
            self.session.refresh(balance)
            available = Decimal(str(balance.amount))
            reserved_amount = min(max(available, Decimal("0.00")), order_total)

            if reserved_amount == 0:
                break

            updated = self.session.execute(
                update(Balance)
                .where(
                    Balance.partner_id == partner_id,
                    Balance.amount >= reserved_amount,
                )
                .values(
                    amount=Balance.amount - reserved_amount,
                    hold=Balance.hold + reserved_amount,
                )
                .execution_options(synchronize_session=False)
            )
            if updated.rowcount == 1:
                break
        else:
            raise RuntimeError(
                "Could not reserve purchase balance after concurrent updates"
            )

        reservation.amount = reserved_amount
        self.session.add(
            BalanceTransaction(
                partner_id=partner_id,
                amount=-reserved_amount,
                type=BalanceTransactionType.PURCHASE_PAYMENT,
                reference_id=reservation.id,
                external_id=self._purchase_event_id(order_key, "reserve"),
                description=f"Balance reserved for WooCommerce order {order_key}",
            )
        )
        self.session.flush()
        self.session.refresh(balance)
        self._validate_balance_state(balance)
        return reservation

    def confirm_purchase(
        self,
        order_id: str | int,
    ) -> BalanceOrderReservation:
        """Finalize a pending purchase reservation; repeating is a no-op."""
        order_key = str(order_id).strip()
        reservation = self._get_purchase_reservation(order_key)

        if reservation.status == BalanceOrderReservationStatus.CONFIRMED:
            return reservation
        if reservation.status == BalanceOrderReservationStatus.RELEASED:
            raise ValueError(
                f"Balance reservation for WooCommerce order "
                f"{order_key} has already been released"
            )

        changed = self.session.execute(
            update(BalanceOrderReservation)
            .where(
                BalanceOrderReservation.id == reservation.id,
                BalanceOrderReservation.status
                == BalanceOrderReservationStatus.PENDING,
            )
            .values(
                status=BalanceOrderReservationStatus.CONFIRMED,
                processed_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            self.session.refresh(reservation)
            if reservation.status == BalanceOrderReservationStatus.CONFIRMED:
                return reservation
            raise ValueError(
                f"Balance reservation for WooCommerce order "
                f"{order_key} is no longer pending"
            )

        reserved_amount = Decimal(str(reservation.amount))
        balance = self._get_purchase_balance(reservation.partner_id)
        if reserved_amount > 0:
            spent = self.session.execute(
                update(Balance)
                .where(
                    Balance.partner_id == reservation.partner_id,
                    Balance.hold >= reserved_amount,
                )
                .values(hold=Balance.hold - reserved_amount)
                .execution_options(synchronize_session=False)
            )
            if spent.rowcount != 1:
                raise RuntimeError(
                    "Reserved balance is missing while confirming "
                    f"WooCommerce order {order_key}"
                )

        self.session.add(
            BalanceTransaction(
                partner_id=reservation.partner_id,
                amount=Decimal("0.00"),
                type=BalanceTransactionType.PURCHASE_PAYMENT,
                reference_id=reservation.id,
                external_id=self._purchase_event_id(order_key, "confirm"),
                description=f"Balance payment confirmed for WooCommerce order {order_key}",
            )
        )
        self.session.flush()
        self.session.refresh(balance)
        self.session.refresh(reservation)
        self._validate_balance_state(balance)
        return reservation

    def release_purchase(
        self,
        order_id: str | int,
    ) -> BalanceOrderReservation:
        """Release a pending purchase reservation; repeating is a no-op."""
        order_key = str(order_id).strip()
        reservation = self._get_purchase_reservation(order_key)

        if reservation.status == BalanceOrderReservationStatus.RELEASED:
            return reservation
        if reservation.status == BalanceOrderReservationStatus.CONFIRMED:
            raise ValueError(
                f"Balance reservation for WooCommerce order "
                f"{order_key} has already been confirmed"
            )

        changed = self.session.execute(
            update(BalanceOrderReservation)
            .where(
                BalanceOrderReservation.id == reservation.id,
                BalanceOrderReservation.status
                == BalanceOrderReservationStatus.PENDING,
            )
            .values(
                status=BalanceOrderReservationStatus.RELEASED,
                processed_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            self.session.refresh(reservation)
            if reservation.status == BalanceOrderReservationStatus.RELEASED:
                return reservation
            raise ValueError(
                f"Balance reservation for WooCommerce order "
                f"{order_key} is no longer pending"
            )

        reserved_amount = Decimal(str(reservation.amount))
        balance = self._get_purchase_balance(reservation.partner_id)
        if reserved_amount > 0:
            released = self.session.execute(
                update(Balance)
                .where(
                    Balance.partner_id == reservation.partner_id,
                    Balance.hold >= reserved_amount,
                )
                .values(
                    hold=Balance.hold - reserved_amount,
                    amount=Balance.amount + reserved_amount,
                )
                .execution_options(synchronize_session=False)
            )
            if released.rowcount != 1:
                raise RuntimeError(
                    "Reserved balance is missing while releasing "
                    f"WooCommerce order {order_key}"
                )

        self.session.add(
            BalanceTransaction(
                partner_id=reservation.partner_id,
                amount=reserved_amount,
                type=BalanceTransactionType.PURCHASE_PAYMENT,
                reference_id=reservation.id,
                external_id=self._purchase_event_id(order_key, "release"),
                description=f"Balance reservation released for WooCommerce order {order_key}",
            )
        )
        self.session.flush()
        self.session.refresh(balance)
        self.session.refresh(reservation)
        self._validate_balance_state(balance)
        return reservation

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
        self.session.execute(
            update(Balance)
            .where(Balance.partner_id == partner_id)
            .values(amount=Balance.amount + amount)
        )
        self.session.refresh(balance)

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

        result = self.session.execute(
            update(Balance)
            .where(
                Balance.partner_id == partner_id,
                Balance.amount >= amount,
            )
            .values(
                amount=Balance.amount - amount,
                hold=Balance.hold + amount,
            )
        )

        if result.rowcount != 1:
            raise ValueError("Недостаточно средств")

        self.session.refresh(balance)

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

        result = self.session.execute(
            update(Balance)
            .where(
                Balance.partner_id == partner_id,
                Balance.hold >= amount,
            )
            .values(
                hold=Balance.hold - amount,
                amount=Balance.amount + amount,
            )
        )

        if result.rowcount != 1:
            raise ValueError("Недостаточно средств в hold")

        self.session.refresh(balance)

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

        result = self.session.execute(
            update(Balance)
            .where(
                Balance.partner_id == partner_id,
                Balance.hold >= amount,
            )
            .values(hold=Balance.hold - amount)
        )

        if result.rowcount != 1:
            raise ValueError("Недостаточно средств в hold")

        self.session.refresh(balance)

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=Decimal("0.00"),
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