import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.balance_service import BalanceService
from database.models import Withdrawal, WithdrawalStatus


class WithdrawalRequestConflict(Exception):
    """Same partner request_id already belongs to different withdrawal data."""


_REQUEST_KEY_CONSTRAINT = "uq_withdrawals_partner_request_id"


class WithdrawalService:
    """Withdrawal lifecycle; caller owns commit, each operation uses a savepoint."""

    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    @contextmanager
    def _operation(self):
        connection = self.session.connection()
        if connection.dialect.name == "sqlite":
            driver = connection.connection.driver_connection
            if not driver.in_transaction:
                connection.exec_driver_sql("BEGIN")
        with self.session.begin_nested():
            yield

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
        *,
        request_id: str | uuid.UUID | None = None,
    ) -> Withdrawal:
        canonical_request_id = self._canonical_request_id(request_id)
        amount = self._money(amount)
        stored_details = details or {}

        if canonical_request_id is not None:
            existing = self._find_by_request_id(
                partner_id,
                canonical_request_id,
            )
            if existing is not None:
                self._require_same_request(
                    existing,
                    amount,
                    method,
                    stored_details,
                )
                return existing

        try:
            with self._operation():
                withdrawal = Withdrawal(
                    partner_id=partner_id,
                    amount=amount,
                    method=method,
                    details=stored_details,
                    status=WithdrawalStatus.PENDING,
                    request_id=canonical_request_id,
                )
                self.session.add(withdrawal)
                self.session.flush()
                self.balance_service.hold_funds(
                    partner_id=partner_id,
                    amount=amount,
                    reference_id=withdrawal.id,
                )
                self.session.flush()
        except IntegrityError as exc:
            if (
                canonical_request_id is None
                or not self._is_request_key_violation(exc)
            ):
                raise
            existing = self._find_by_request_id(
                partner_id,
                canonical_request_id,
            )
            if existing is None:
                raise
            self._require_same_request(
                existing,
                amount,
                method,
                stored_details,
            )
            return existing
        return withdrawal

    @staticmethod
    def _canonical_request_id(
        request_id: str | uuid.UUID | None,
    ) -> str | None:
        if request_id is None:
            return None
        if isinstance(request_id, uuid.UUID):
            parsed = request_id
        elif isinstance(request_id, str):
            text_value = request_id.strip()
            if not text_value:
                raise ValueError(
                    "Withdrawal request_id must be a UUIDv4"
                )
            try:
                parsed = uuid.UUID(text_value)
            except ValueError:
                raise ValueError(
                    "Withdrawal request_id must be a UUIDv4"
                ) from None
        else:
            raise ValueError("Withdrawal request_id must be a UUIDv4")
        if parsed.version != 4:
            raise ValueError("Withdrawal request_id must be a UUIDv4")
        return str(parsed)

    @staticmethod
    def _canonical_details(details: dict | None) -> str:
        return json.dumps(
            details or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def _require_same_request(
        self,
        existing: Withdrawal,
        amount: Decimal,
        method: str,
        details: dict,
    ) -> None:
        same_amount = Decimal(str(existing.amount)) == amount
        same_details = (
            self._canonical_details(existing.details)
            == self._canonical_details(details)
        )
        if same_amount and existing.method == method and same_details:
            return
        raise WithdrawalRequestConflict(
            "Withdrawal request_id is already used with different data"
        )

    def _find_by_request_id(
        self,
        partner_id: int,
        request_id: str,
    ) -> Withdrawal | None:
        return self.session.execute(
            select(Withdrawal).where(
                Withdrawal.partner_id == partner_id,
                Withdrawal.request_id == request_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _is_request_key_violation(exc: IntegrityError) -> bool:
        orig = getattr(exc, "orig", None)
        if orig is None:
            return False
        diag = getattr(orig, "diag", None)
        constraint_name = (
            getattr(diag, "constraint_name", None) if diag else None
        )
        if constraint_name == _REQUEST_KEY_CONSTRAINT:
            return True
        message = str(orig).lower()
        if _REQUEST_KEY_CONSTRAINT in message:
            return True
        return (
            "unique constraint failed" in message
            and "withdrawals.partner_id" in message
            and "withdrawals.request_id" in message
        )

    def complete(self, withdrawal_id: int) -> Withdrawal:
        with self._operation():
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
        with self._operation():
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
        self.session.refresh(withdrawal)
        return withdrawal
