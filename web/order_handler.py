import logging

from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from core.network import NetworkManager

from database.db import SessionLocal
from database.models import Commission, Purchase, Partner
from services.commission_service import CommissionService
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
            # OLD RANK
            # -------------------------------------------------

            rank_service = RankService(session)
            old_rank = rank_service.calculate_rank(partner_id)

            # -------------------------------------------------
            # PROCESS COMMISSIONS (НОВАЯ ЛОГИКА)
            # -------------------------------------------------

            await self.commission_calculator.process_purchase(purchase)

            # -------------------------------------------------
            # Stats update
            # -------------------------------------------------

            stats_service = StatsService(session)

            stats_service.process_purchase(
                partner_id=partner_id,
                amount=amount
            )

            session.commit()

            # -------------------------------------------------
            # NEW RANK
            # -------------------------------------------------

            new_rank = rank_service.calculate_rank(partner_id)

            # -------------------------------------------------
            # Notify if upgraded (FIX ASYNC)
            # -------------------------------------------------

            if new_rank != old_rank:

                logger.info(f"Partner {partner_id} rank upgraded: {old_rank} → {new_rank}")

                partner = session.query(Partner).filter(Partner.id == partner_id).first()

                if partner and partner.telegram_id:
                    try:
                        await self.bot.send_message(
                            chat_id=partner.telegram_id,
                            text=(
                                "🎉 Поздравляем!\n\n"
                                f"Вы достигли ранга: {new_rank}\n\n"
                                "Продолжайте развитие сети 🚀"
                            )
                        )
                    except Exception as e:
                        logger.error(f"Telegram notify error: {e}")

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