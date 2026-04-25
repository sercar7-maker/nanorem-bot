"""
Order Processor for NANOREM MLM System.
Handles new orders from WooCommerce and calculates partner commissions.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import Partner, Purchase, OrderStatus
from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator

logger = logging.getLogger(__name__)


class OrderProcessor:
    """
    Обрабатывает заказы из WooCommerce и начисляет MLM-комиссии.
    """

    def __init__(self, api_client: Optional[NanorvsAPIClient] = None):
        """
        Args:
            api_client: Клиент для WooCommerce API. Если не передан, создаётся новый.
        """
        self.api_client = api_client or NanorvsAPIClient()

    def process_order_by_id(self, order_id: int) -> bool:
        """
        Обработать заказ по его ID в WooCommerce.
        
        Returns:
            True если заказ успешно обработан, False в случае ошибки.
        """
        logger.info(f"Обработка заказа #{order_id}")

        # 1. Получаем заказ из WooCommerce
        order_data = self.api_client.get_order(order_id)
        if not order_data:
            logger.error(f"Не удалось получить заказ #{order_id} из WooCommerce")
            return False

        return self.process_order_data(order_data)

    def process_order_data(self, order_data: Dict[str, Any]) -> bool:
        """
        Обработать заказ по данным, полученным из WooCommerce.
        
        Args:
            order_data: JSON-данные заказа от WooCommerce API.
            
        Returns:
            True если успешно, False в случае ошибки.
        """
        order_id = order_data.get('id')
        customer_id = order_data.get('customer_id')
        total_amount = Decimal(str(order_data.get('total', '0')))
        status = order_data.get('status', '')

        logger.info(f"Заказ #{order_id}: клиент={customer_id}, сумма={total_amount}, статус={status}")

        # Проверяем статус заказа
        if status != 'completed':
            logger.warning(f"Заказ #{order_id} не обработан: статус '{status}' (требуется 'completed')")
            return False

        if total_amount <= 0:
            logger.warning(f"Заказ #{order_id}: сумма заказа равна 0")
            return False

        # Создаём сессию БД
        session = SessionLocal()
        try:
            # 2. Находим партнёра по customer_id из WooCommerce
            customer_email = order_data.get('billing', {}).get('email')
            if not customer_email:
                logger.error(f"Заказ #{order_id}: не указан email клиента")
                return False

            partner = self._find_or_create_partner(session, customer_id, customer_email, order_data)

            if not partner:
                logger.error(f"Заказ #{order_id}: не удалось найти или создать партнёра")
                return False

            # 3. Проверяем, не обработан ли уже этот заказ
            existing_purchase = session.query(Purchase).filter(
                Purchase.ext_ref == str(order_id)
            ).first()
            if existing_purchase:
                logger.warning(f"Заказ #{order_id} уже обработан (Purchase ID: {existing_purchase.id})")
                return True  # Не ошибка, просто уже обработан

            # 4. Создаём запись о покупке
            purchase = Purchase(
                purchase_number=f"WC-{order_id}",
                partner_id=partner.id,
                amount=float(total_amount),
                status=OrderStatus.PAID,
                ext_ref=str(order_id)
            )
            session.add(purchase)
            session.commit()
            session.refresh(purchase)
            logger.info(f"Создана покупка ID={purchase.id} для партнёра ID={partner.id}")

            # 5. Запускаем расчёт комиссий
            calculator = CommissionCalculator(session, bot=None)
            import asyncio
            asyncio.run(calculator.process_purchase(purchase))

            logger.info(f"Заказ #{order_id} успешно обработан. Комиссии начислены.")
            return True

        except Exception as e:
            logger.exception(f"Ошибка при обработке заказа #{order_id}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _find_or_create_partner(
        self, 
        session: Session, 
        woo_customer_id: int, 
        email: str,
        order_data: Dict[str, Any]
    ) -> Optional[Partner]:
        """
        Находит существующего партнёра по woo_customer_id или email,
        либо создаёт нового на основе данных заказа.
        """
        # 1. Ищем по email (если партнёр уже регистрировался)
        partner = session.query(Partner).filter(Partner.email == email).first()
        if partner:
            logger.info(f"Партнёр найден по email: {email}, ID={partner.id}")
            return partner

        # 2. Если не нашли — создаём нового партнёра с авто-распределением
        billing = order_data.get('billing', {})
        first_name = billing.get('first_name', '')
        last_name = billing.get('last_name', '')
        phone = billing.get('phone', '')

        logger.info(f"Создаём нового партнёра: {email}")

        # Определяем upline_id через авто-распределение (свободная регистрация)
        # Используем ту же логику, что и в PartnerService.choose_root
        upline_id = self._choose_root_for_new_partner(session)

        # Формируем lineage
        lineage = []
        if upline_id:
            upline = session.query(Partner).filter(Partner.id == upline_id).first()
            if upline and upline.lineage:
                lineage = list(upline.lineage)
            lineage.insert(0, upline_id)

        new_partner = Partner(
            telegram_id=None,
            telegram_link_code=None,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            upline_id=upline_id,
            lineage=lineage,
            status="ACTIVE",
            role="partner",
            rank="Partner"
        )

        session.add(new_partner)
        session.commit()
        session.refresh(new_partner)

        logger.info(f"Создан новый партнёр ID={new_partner.id}, upline={upline_id}")
        return new_partner

    def _choose_root_for_new_partner(self, session: Session) -> Optional[int]:
        """
        Выбирает корневого партнёра (root) для свободной регистрации.
        Логика: у кого меньше людей в ноге, к тому и прикрепляем.
        """
        roots = session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).order_by(Partner.id).all()

        if len(roots) < 2:
            return roots[0].id if roots else None

        root1, root2 = roots[0], roots[1]

        # Считаем количество людей в каждой ноге
        count1 = session.query(Partner).filter(
            Partner.lineage.contains([root1.id])
        ).count()
        count2 = session.query(Partner).filter(
            Partner.lineage.contains([root2.id])
        ).count()

        logger.info(f"Авто-распределение: root1={root1.id} ({count1} чел.), root2={root2.id} ({count2} чел.)")

        return root1.id if count1 <= count2 else root2.id

    def process_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Обработать данные, полученные от вебхука WooCommerce.
        """
        return self.process_order_data(webhook_data)


def process_woocommerce_order(order_id: int) -> bool:
    """
    Быстрая функция для обработки заказа по ID.
    """
    processor = OrderProcessor()
    return processor.process_order_by_id(order_id)