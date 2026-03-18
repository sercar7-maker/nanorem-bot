import logging

from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from core.network import NetworkManager

from database.db import SessionLocal
from database.models import Purchase, Partner
from services.stats_service import StatsService
from services.rank_service import RankService

from telegram import Bot
from config import BOT_TOKEN

logger = logging.getLogger(__name__)


class OrderHandler:

    def __init__(self, api_client: NanorvsAPIClient, commission_calculator: CommissionCalculator):
        self.api_client = api_client
        self.commission_calculator = commission_calculator
        self.network_manager = NetworkManager()
        self.bot = Bot(token=BOT_TOKEN)

        logger.info("Initialized OrderHandler")

    async def process_order(self, order_data: dict):

        try:

            order_id = order_data["id"]
            partner_id = order_data["partner_id"]
            amount = float(order_data["total_amount"])

            session = SessionLocal()

            # -------------------------------------------------
            # CREATE OR GET PURCHASE
            # -------------------------------------------------

            purchase = session.query(Purchase).filter_by(ext_ref=str(order_id)).first()

            if not purchase:
                purchase = Purchase(
                    purchase_number=str(order_id),
                    partner_id=partner_id,
                    amount=amount,
                    status="paid",
                    ext_ref=str(order_id)
                )
                session.add(purchase)
                session.commit()
                session.refresh(purchase)

            # -------------------------------------------------
            # PROCESS COMMISSIONS
            # -------------------------------------------------

            await self.commission_calculator.process_purchase(purchase)

            # -------------------------------------------------
            # STATS UPDATE
            # -------------------------------------------------

            stats_service = StatsService(session)

            stats_service.process_purchase(
                partner_id=partner_id,
                amount=amount
            )

            # -------------------------------------------------
            # RANK UPDATE (НОВАЯ ЛОГИКА)
            # -------------------------------------------------

            partner = session.query(Partner).filter(Partner.id == partner_id).first()

            if partner:
                rank_service = RankService(session)
                await rank_service.process_rank(partner)

            session.close()

            # -------------------------------------------------
            # External API
            # -------------------------------------------------

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

            return False