"""
Order Processor for NANOREM MLM System.
Handles new orders from WooCommerce and calculates partner commissions.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import Partner, Purchase, OrderStatus
from database.models_balance import (
    BalanceOrderReservation,
    BalanceOrderReservationStatus,
)
from web.api_client import NanorvsAPIClient
from core.balance_service import BalanceService
from core.commission import CommissionCalculator
from services.distribution_service import DistributionService
from services.stats_service import StatsService
from services.rank_service import RankService
from services.root_allocation_lock import acquire_root_allocation_lock
from services.subscription_service import SubscriptionService
from services.structural_compression_service import (
    StructuralCompressionService,
)

logger = logging.getLogger(__name__)


class RootPairNotReadyError(RuntimeError):
    """Raised when WooCommerce processing requires unavailable Root partners."""


class OrderProcessor:
    def __init__(self, api_client: Optional[NanorvsAPIClient] = None):
        self.api_client = api_client or NanorvsAPIClient()

    def process_order_by_id(self, order_id: int) -> bool:
        """
        Синхронный метод для старых внутренних вызовов.
        FastAPI webhook использует async-метод process_webhook().
        """
        logger.info(f"Обработка заказа #{order_id}")

        order_data = self.api_client.get_order(order_id)

        if not order_data:
            logger.error(
                f"Не удалось получить заказ #{order_id}"
            )
            return False

        import asyncio

        return asyncio.run(
            self.process_order_data(order_data)
        )

    async def process_order_data(
        self,
        order_data: Dict[str, Any]
    ) -> bool:
        """
        Полностью обрабатывает WooCommerce-заказ.

        Purchase и комиссии находятся в одной транзакции:
        если начисление комиссии падает, Purchase также откатывается.
        """

        order_id = order_data.get("id")
        customer_id = order_data.get("customer_id")
        status = order_data.get("status", "")

        if status in {"cancelled", "failed"}:
            return self._release_cancelled_purchase(order_id)

        total_amount = Decimal(
            str(order_data.get("total", "0"))
        )

        logger.info(
            f"Заказ #{order_id}: "
            f"клиент={customer_id}, "
            f"сумма={total_amount}, "
            f"статус={status}"
        )

        if status != "completed":
            logger.warning(
                f"Заказ #{order_id}: статус '{status}'. "
                f"Требуется 'completed'"
            )
            return False

        if total_amount <= 0:
            logger.warning(
                f"Заказ #{order_id}: сумма заказа <= 0"
            )
            return False

        customer_email = (
            order_data.get("billing", {}).get("email")
        )

        if not customer_email:
            logger.error(
                f"Заказ #{order_id}: "
                f"не указан email клиента"
            )
            return False

        session = SessionLocal()

        try:
            acquire_root_allocation_lock(session)
            self._require_root_pair(session)

            # -------------------------------------------------
            # 1. Проверяем существующий заказ
            # -------------------------------------------------

            existing_purchase = (
                session.query(Purchase)
                .filter(
                    Purchase.ext_ref == str(order_id)
                )
                .first()
            )

            if existing_purchase:
                logger.warning(
                    f"Заказ #{order_id} уже существует "
                    f"(Purchase ID={existing_purchase.id}). "
                    f"Повторный webhook игнорируется."
                )
                return True

            # -------------------------------------------------
            # 2. Находим или создаём партнёра
            # -------------------------------------------------

            partner = self._find_or_create_partner(
                session=session,
                woo_customer_id=customer_id,
                email=customer_email,
                order_data=order_data,
            )

            if not partner:
                logger.error(
                    f"Заказ #{order_id}: "
                    f"не удалось найти или создать партнёра"
                )
                session.rollback()
                return False

            reservation = (
                session.query(BalanceOrderReservation)
                .filter(
                    BalanceOrderReservation.order_id == str(order_id)
                )
                .one_or_none()
            )
            if reservation:
                if reservation.partner_id != partner.id:
                    raise ValueError(
                        "WooCommerce order balance reservation belongs "
                        "to a different partner"
                    )
                if Decimal(str(reservation.order_total)) != total_amount:
                    raise ValueError(
                        "WooCommerce order total does not match its "
                        "balance reservation"
                    )
                BalanceService(session).confirm_purchase(order_id)

            # -------------------------------------------------
            # 3. Создаём Purchase
            # -------------------------------------------------

            purchase = Purchase(
                purchase_number=f"WC-{order_id}",
                partner_id=partner.id,
                amount=total_amount,
                status=OrderStatus.PAID,
                ext_ref=str(order_id),
                paid_at=self._purchase_paid_at(order_data),
            )

            session.add(purchase)

            # flush получает purchase.id, но НЕ делает commit.
            session.flush()

            compression_service = StructuralCompressionService(session)
            compression_service.compress_if_due_before_purchase(
                partner,
                purchase.paid_at or datetime.now(timezone.utc),
            )
            SubscriptionService(session).apply_purchase(purchase)
            compression_service.process_paid_purchase(partner, purchase)

            stats = StatsService(session).process_purchase(
                partner_id=partner.id,
                amount=total_amount,
            )
            partner.rank = RankService(session).calculate_rank(
                stats.personal_turnover
            )

            logger.info(
                f"Создана Purchase ID={purchase.id} "
                f"для партнёра ID={partner.id}"
            )

            # -------------------------------------------------
            # 4. Начисляем MLM-комиссии
            # -------------------------------------------------

            calculator = CommissionCalculator(
                session,
                bot=None,
            )

            await calculator.process_purchase(purchase)
            session.commit()

            logger.info(
                f"Заказ #{order_id} "
                f"успешно обработан вместе с комиссиями"
            )

            return True

        except RootPairNotReadyError:
            session.rollback()
            raise

        except Exception as e:
            logger.exception(
                f"Ошибка при обработке заказа "
                f"#{order_id}: {e}"
            )

            session.rollback()

            return False

        finally:
            session.close()

    @staticmethod
    def _purchase_paid_at(order_data: Dict[str, Any]) -> datetime:
        for field in ("date_paid_gmt", "date_paid"):
            value = order_data.get(field)
            if not value:
                continue

            try:
                parsed = datetime.fromisoformat(
                    str(value).replace("Z", "+00:00")
                )
            except ValueError:
                logger.warning(
                    "Ignoring invalid WooCommerce %s value",
                    field,
                )
                continue

            if parsed.tzinfo is None:
                if field != "date_paid_gmt":
                    continue
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc).replace(tzinfo=None)

        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _release_cancelled_purchase(
        self,
        order_id: int | str | None,
    ) -> bool:
        if order_id is None:
            logger.error("Cancelled WooCommerce order has no order id")
            return False

        session = SessionLocal()
        try:
            reservation = (
                session.query(BalanceOrderReservation)
                .filter(
                    BalanceOrderReservation.order_id == str(order_id)
                )
                .one_or_none()
            )
            if reservation is None:
                return True

            if reservation.status == BalanceOrderReservationStatus.PENDING:
                BalanceService(session).release_purchase(order_id)
                session.commit()

            return True
        except Exception:
            logger.exception(
                "Failed to release balance reservation for "
                "cancelled WooCommerce order #%s",
                order_id,
            )
            session.rollback()
            return False
        finally:
            session.close()

    def _find_or_create_partner(
        self,
        session: Session,
        woo_customer_id: int,
        email: str,
        order_data: Dict[str, Any],
    ) -> Optional[Partner]:
        """
        Находит партнёра по email или создаёт нового.

        ВАЖНО:
        здесь больше нет session.commit().
        Транзакцией управляет process_order_data().
        """

        normalized_email = email.strip().lower()
        partner = (
            session.query(Partner)
            .filter(func.lower(Partner.email) == normalized_email)
            .first()
        )

        if partner:
            logger.info(
                f"Партнёр найден по email: "
                f"{email}, ID={partner.id}"
            )
            return partner

        billing = order_data.get("billing", {})

        first_name = billing.get(
            "first_name",
            "",
        )

        last_name = billing.get(
            "last_name",
            "",
        )

        phone = billing.get(
            "phone",
            "",
        )

        logger.info(
            f"Создаём нового партнёра: {email}"
        )

        upline_id = self._choose_root_for_new_partner(
            session
        )

        lineage = []

        if upline_id:
            upline = (
                session.query(Partner)
                .filter(
                    Partner.id == upline_id
                )
                .first()
            )

            if upline and upline.lineage:
                lineage = list(upline.lineage)

            lineage.insert(0, upline_id)

        new_partner = Partner(
            telegram_id=None,
            first_name=first_name,
            last_name=last_name,
            email=normalized_email,
            phone=phone,
            upline_id=upline_id,
            lineage=lineage,
            status="ACTIVE",
            role="partner",
            rank="Partner",
        )

        session.add(new_partner)

        # Только flush.
        # Commit будет выполнен после успешной обработки комиссии.
        session.flush()
        StructuralCompressionService(
            session
        ).ensure_root_affiliation(new_partner)
        session.flush()

        logger.info(
            f"Создан новый партнёр "
            f"ID={new_partner.id}, "
            f"upline={upline_id}"
        )

        return new_partner

    def _choose_root_for_new_partner(
        self,
        session: Session,
    ) -> Optional[int]:
        """
        Выбирает корневого партнёра для свободной регистрации.

        Используется единый DistributionService.
        """

        self._require_root_pair(session)
        return (
            DistributionService()
            .get_upline_for_new_partner(session)
        )

    @staticmethod
    def _require_root_pair(session: Session) -> None:
        root_count = session.query(Partner).filter(
            Partner.upline_id.is_(None),
            or_(
                Partner.root_id.is_(None),
                Partner.root_id == Partner.id,
            ),
        ).count()
        if root_count != 2:
            raise RootPairNotReadyError(
                "System is not ready for registration: exactly two "
                "Root partners must be created by an administrator"
            )

    async def process_webhook(
        self,
        webhook_data: Dict[str, Any],
    ) -> bool:
        """
        Асинхронный вход для FastAPI WooCommerce webhook.
        """

        return await self.process_order_data(
            webhook_data
        )


def process_woocommerce_order(
    order_id: int,
) -> bool:
    """
    Старый синхронный интерфейс.

    Использовать только из синхронного кода.
    В FastAPI использовать await processor.process_webhook().
    """

    processor = OrderProcessor()

    return processor.process_order_by_id(
        order_id
    )