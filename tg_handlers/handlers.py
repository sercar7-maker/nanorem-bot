import logging

from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from core.network import NetworkManager

from database.db import SessionLocal
from database.models import Commission
from services.commission_service import CommissionService

logger = logging.getLogger(__name__)


class OrderHandler:

    def __init__(self, api_client: NanorvsAPIClient, commission_calculator: CommissionCalculator):
        self.api_client = api_client
        self.commission_calculator = commission_calculator
        self.network_manager = NetworkManager()

        logger.info("Initialized OrderHandler")

    def process_order(self, order_data: dict):

        try:

            order_id = order_data["id"]
            partner_id = order_data["partner_id"]
            amount = order_data["total_amount"]

            session = SessionLocal()

            # защита от двойного webhook
            existing = session.query(Commission).filter_by(purchase_id=order_id).first()
            if existing:
                logger.warning(f"Order {order_id} already processed")
                session.close()
                return True

            logger.info(f"Processing order {order_id} for partner {partner_id}")
            logger.info(f"Order data received: {order_data}")

            # Build upline chain
            upline_chain = self.network_manager.get_upline_chain(partner_id)

            # Calculate commissions
            commissions = self.commission_calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner_id,
                upline_chain=upline_chain
            )

            logger.info(f"Calculated {len(commissions)} commissions for purchase by {partner_id}")

            # Save commissions
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

            session.commit()
            session.close()

            # Report sale to external API
            self.api_client.update_partner_sales(
                partner_id,
                {
                    "order_id": order_id,
                    "amount": float(amount),
                    "commissions": [
                        {
                            "partner_id": c.partner_id,
                            "level": c.level,
                            "rate": float(c.rate),
                            "amount": float(c.amount)
                        }
                        for c in commissions
                    ]
                }
            )

            logger.info(f"Successfully processed order {order_id}")

            return True

        except Exception as e:

            logger.error(f"Failed to process order: {e}")

            return False


def setup_handlers(application):

    from tg_handlers.balance import get_handler

    logger.info("Registering Telegram handlers")

    application.add_handler(get_handler())