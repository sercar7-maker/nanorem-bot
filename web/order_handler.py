import logging

from telegram import Bot

from config import BOT_TOKEN
from core.network import NetworkManager
from database.db import SessionLocal
from database.models import Partner, Purchase, OrderStatus
from services.rank_service import RankService
from services.stats_service import StatsService
from web.api_client import NanorvsAPIClient

logger = logging.getLogger(__name__)


class OrderHandler:
    def __init__(
        self,
        api_client: NanorvsAPIClient,
        commission_calculator
    ):
        self.api_client = api_client
        self.commission_calculator = commission_calculator
        self.network_manager = NetworkManager()
        self.bot = Bot(token=BOT_TOKEN)

        logger.info("Initialized OrderHandler")

    async def process_order(self, order_data: dict):
        session = SessionLocal()

        try:
            print("🚀 ORDER START")

            order_id = order_data["id"]
            partner_id = order_data["partner_id"]
            amount = float(order_data["total_amount"])

            purchase = session.query(Purchase).filter_by(ext_ref=str(order_id)).first()

            if not purchase:
                print("📦 creating purchase")

                purchase = Purchase(
                    purchase_number=str(order_id),
                    partner_id=partner_id,
                    amount=amount,
                    status=OrderStatus.PAID,
                    ext_ref=str(order_id),
                )
                session.add(purchase)
                session.commit()
                session.refresh(purchase)

            print(f"📦 PURCHASE ID: {purchase.id}")

            # 🔥 ВАЖНО
            print("👉 CALLING COMMISSION CALCULATOR")

            self.commission_calculator.session = session

            await self.commission_calculator.process_purchase(purchase)

            print("✅ COMMISSION CALCULATOR CALLED")

            session.commit()

            stats_service = StatsService(session)
            stats_service.process_purchase(
                partner_id=partner_id,
                amount=amount
            )

            partner = session.query(Partner).filter(Partner.id == partner_id).first()
            if partner:
                rank_service = RankService(session)
                await rank_service.process_rank(partner)

            self.api_client.update_partner_sales(
                partner_id,
                {
                    "order_id": order_id,
                    "amount": amount,
                }
            )

            logger.info(f"Successfully processed order {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to process order: {e}")
            print(f"❌ ERROR: {e}")
            return False

        finally:
            session.close()