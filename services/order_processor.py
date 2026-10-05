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
from services.distribution_service import DistributionService

logger = logging.getLogger(__name__)


class OrderProcessor:
    def __init__(self, api_client: Optional[NanorvsAPIClient] = None):
        self.api_client = api_client or NanorvsAPIClient()

    def process_order_by_id(self, order_id: int) -> bool:
        logger.info(f"РћР±СЂР°Р±РѕС‚РєР° Р·Р°РєР°Р·Р° #{order_id}")
        order_data = self.api_client.get_order(order_id)
        if not order_data:
            logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ Р·Р°РєР°Р· #{order_id}")
            return False
        return self.process_order_data(order_data)

    def process_order_data(self, order_data: Dict[str, Any]) -> bool:
        order_id = order_data.get('id')
        customer_id = order_data.get('customer_id')
        total_amount = Decimal(str(order_data.get('total', '0')))
        status = order_data.get('status', '')

        logger.info(f"Р—Р°РєР°Р· #{order_id}: РєР»РёРµРЅС‚={customer_id}, СЃСѓРјРјР°={total_amount}, СЃС‚Р°С‚СѓСЃ={status}")

        if status != 'completed':
            logger.warning(f"Р—Р°РєР°Р· #{order_id}: СЃС‚Р°С‚СѓСЃ '{status}' (С‚СЂРµР±СѓРµС‚СЃСЏ 'completed')")
            return False

        if total_amount <= 0:
            logger.warning(f"Р—Р°РєР°Р· #{order_id}: СЃСѓРјРјР° Р·Р°РєР°Р·Р° СЂР°РІРЅР° 0")
            return False

        session = SessionLocal()
        try:
            customer_email = order_data.get('billing', {}).get('email')
            if not customer_email:
                logger.error(f"Р—Р°РєР°Р· #{order_id}: РЅРµ СѓРєР°Р·Р°РЅ email РєР»РёРµРЅС‚Р°")
                return False

            partner = self._find_or_create_partner(session, customer_id, customer_email, order_data)
            if not partner:
                logger.error(f"Р—Р°РєР°Р· #{order_id}: РЅРµ СѓРґР°Р»РѕСЃСЊ РЅР°Р№С‚Рё РёР»Рё СЃРѕР·РґР°С‚СЊ РїР°СЂС‚РЅС‘СЂР°")
                return False

            existing_purchase = session.query(Purchase).filter(
                Purchase.ext_ref == str(order_id)
            ).first()
            if existing_purchase:
                logger.warning(f"Р—Р°РєР°Р· #{order_id} СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ")
                return True

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
            logger.info(f"РЎРѕР·РґР°РЅР° РїРѕРєСѓРїРєР° ID={purchase.id} РґР»СЏ РїР°СЂС‚РЅС‘СЂР° ID={partner.id}")

            calculator = CommissionCalculator(session, bot=None)
            import asyncio
            asyncio.run(calculator.process_purchase(purchase))

            logger.info(f"Р—Р°РєР°Р· #{order_id} СѓСЃРїРµС€РЅРѕ РѕР±СЂР°Р±РѕС‚Р°РЅ")
            return True

        except Exception as e:
            logger.exception(f"РћС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ Р·Р°РєР°Р·Р° #{order_id}: {e}")
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
        partner = session.query(Partner).filter(Partner.email == email).first()
        if partner:
            logger.info(f"РџР°СЂС‚РЅС‘СЂ РЅР°Р№РґРµРЅ РїРѕ email: {email}, ID={partner.id}")
            return partner

        billing = order_data.get('billing', {})
        first_name = billing.get('first_name', '')
        last_name = billing.get('last_name', '')
        phone = billing.get('phone', '')

        logger.info(f"РЎРѕР·РґР°С‘Рј РЅРѕРІРѕРіРѕ РїР°СЂС‚РЅС‘СЂР°: {email}")

        upline_id = self._choose_root_for_new_partner(session)

        lineage = []
        if upline_id:
            upline = session.query(Partner).filter(Partner.id == upline_id).first()
            if upline and upline.lineage:
                lineage = list(upline.lineage)
            lineage.insert(0, upline_id)

        new_partner = Partner(
            telegram_id=None,
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

        logger.info(f"РЎРѕР·РґР°РЅ РЅРѕРІС‹Р№ РїР°СЂС‚РЅС‘СЂ ID={new_partner.id}, upline={upline_id}")
        return new_partner

    def _choose_root_for_new_partner(self, session: Session) -> Optional[int]:
        """
        С‹Р±РёСЂР°РµС‚ РєРѕСЂРЅРµРІРѕРіРѕ РїР°СЂС‚РЅС‘СЂР° РґР»СЏ СЃРІРѕР±РѕРґРЅРѕР№ СЂРµРіРёСЃС‚СЂР°С†РёРё.
        СЃРїРѕР»СЊР·СѓРµС‚ РµРґРёРЅС‹Р№ DistributionService.
        """
        return DistributionService().get_upline_for_new_partner(session)

    def process_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        return self.process_order_data(webhook_data)


def process_woocommerce_order(order_id: int) -> bool:
    processor = OrderProcessor()
    return processor.process_order_by_id(order_id)
