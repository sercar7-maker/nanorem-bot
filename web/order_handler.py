import logging

from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from core.network import NetworkManager

from database.db import SessionLocal
from database.models import Commission
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

    def process_order(self, order_data: dict):

        try:

            order_id = order_data["id"]
            partner_id = order_data["partner_id"]
            amount = order_data["total_amount"]

            session = SessionLocal()

            # -------------------------------------------------
            # OLD RANK
            # -------------------------------------------------

            rank_service = RankService(session)
            old_rank = rank_service.calculate_rank(partner_id)

            # -------------------------------------------------

            existing = session.query(Commission).filter_by(purchase_id=order_id).first()
            if existing:
                logger.warning(f"Order {order_id} already processed")
                session.close()
                return True

            logger.info(f"Processing order {order_id} for partner {partner_id}")

            # -------------------------------------------------
            # Upline
            # -------------------------------------------------

            upline_chain = self.network_manager.get_upline_chain(partner_id)

            # -------------------------------------------------
            # Commissions
            # -------------------------------------------------

            commissions = self.commission_calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner_id,
                upline_chain=upline_chain
            )

            commission_service = CommissionService(session)

            for c in commissions:

                commission = Commission(
                    partner_id=c.partner_id,
                    purchase_id=order_id,
                    source_partner_id=partner_id,
                    level=c.level,
                    rate=c.rate,
                    base_amount=amount,
                    amount=c.amount
                )

                session.add(commission)
                commission_service.approve_commission(commission)

            # -------------------------------------------------
            # Stats update
            # -------------------------------------------------

            stats_service = StatsService(session)

            stats_service.process_purchase(
                partner_id=partner_id,
                amount=float(amount)
            )

            session.commit()

            # -------------------------------------------------
            # NEW RANK
            # -------------------------------------------------

            new_rank = rank_service.calculate_rank(partner_id)

            # -------------------------------------------------
            # Notify if upgraded
            # -------------------------------------------------

            if new_rank != old_rank:

                logger.info(f"Partner {partner_id} rank upgraded: {old_rank} → {new_rank}")

                from database.models import Partner

                partner = session.query(Partner).filter(Partner.id == partner_id).first()

                if partner and partner.telegram_id:

                    try:
                        self.bot.send_message(
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
                    "amount": float(amount),
                }
            )

            logger.info(f"Successfully processed order {order_id}")

            return True

        except Exception as e:

            logger.error(f"Failed to process order: {e}")

            return False