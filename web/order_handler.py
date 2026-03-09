"""Order handling module for nanorvs.ru integration."""

import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import Commission
from core.network import NetworkManager
from core.commission import CommissionCalculator
from .api_client import NanorvsAPIClient

logger = logging.getLogger(__name__)


class OrderHandler:
    """Handle orders from nanorvs.ru and process MLM commissions."""

    def __init__(
        self,
        api_client: NanorvsAPIClient,
        commission_calculator: CommissionCalculator,
    ):
        self.api_client = api_client
        self.commission_calculator = commission_calculator
        logger.info("Initialized OrderHandler")

    def process_order(self, order_data: Dict[str, Any]) -> bool:
        """Process order and calculate MLM commissions."""

        session: Session = SessionLocal()

        try:
            order_id = order_data.get("id")
            partner_id = order_data.get("partner_id")
            amount = order_data.get("total_amount", 0)

            logger.info(f"Processing order {order_id} for partner {partner_id}")
            logger.info(f"Order data received: {order_data}")

            # ---------- NETWORK ----------
            network = NetworkManager()
            upline_chain = network.get_upline_chain(partner_id)

            # ---------- CALCULATE COMMISSIONS ----------
            commissions = self.commission_calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner_id,
                upline_chain=upline_chain
            )

            logger.info(f"Calculated {len(commissions)} commissions for purchase by {partner_id}")

            # ---------- SAVE COMMISSIONS ----------
            for c in commissions:

                db_commission = Commission(
                    partner_id=c.partner_id,
                    source_partner_id=partner_id,
                    purchase_id=order_id,
                    level=c.level,
                    rate=c.rate,
                    base_amount=c.base_amount,
                    amount=c.amount,
                    status="PENDING",
                    is_compressed=c.compressed
                )

                session.add(db_commission)

            session.commit()

            # ---------- REPORT SALE ----------
            self.api_client.update_partner_sales(
                partner_id,
                {
                    "order_id": order_id,
                    "amount": amount,
                    "commissions": [
                        {
                            "partner_id": c.partner_id,
                            "level": c.level,
                            "rate": c.rate,
                            "amount": c.amount,
                        }
                        for c in commissions
                    ],
                },
            )

            logger.info(f"Successfully processed order {order_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to process order: {e}")
            return False

        finally:
            session.close()