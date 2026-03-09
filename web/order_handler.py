"""Order handling module for nanorvs.ru integration."""

import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

from .api_client import NanorvsAPIClient
from core.partner_manager import PartnerManager
from core.commission import CommissionCalculator

from database.models import Partner, PartnerStatus
from database.db import SessionLocal

logger = logging.getLogger(__name__)


class OrderHandler:
    """Handle orders from nanorvs.ru and process MLM commissions."""

    def __init__(
        self,
        api_client: NanorvsAPIClient,
        partner_manager: PartnerManager,
        commission_calculator: CommissionCalculator
    ):
        self.api_client = api_client
        self.partner_manager = partner_manager
        self.commission_calculator = commission_calculator

        logger.info("Initialized OrderHandler")

    def build_upline_chain(self, session: Session, partner_id: int):
        """
        Build MLM upline chain from database.

        Returns:
        [(partner_id, is_active)]
        """

        chain = []

        current_partner = session.query(Partner).filter(
            Partner.id == partner_id
        ).first()

        if not current_partner:
            return chain

        current_id = current_partner.upline_id

        level = 0

        while current_id and level < 10:

            partner = session.query(Partner).filter(
                Partner.id == current_id
            ).first()

            if not partner:
                break

            is_active = partner.status == PartnerStatus.ACTIVE

            chain.append((partner.id, is_active))

            current_id = partner.upline_id
            level += 1

        return chain

    def process_order(self, order_data: Dict[str, Any]) -> bool:
        """Process order and calculate MLM commissions."""

        session = SessionLocal()

        try:

            order_id = order_data.get("id")
            partner_id = order_data.get("partner_id")
            amount = order_data.get("total_amount", 0)

            logger.info(f"Processing order {order_id} for partner {partner_id}")
            logger.info(f"Order data received: {order_data}")

            # ------------------------------------------------
            # Build MLM chain
            # ------------------------------------------------

            upline_chain = self.build_upline_chain(session, partner_id)

            # ------------------------------------------------
            # Calculate commissions
            # ------------------------------------------------

            commissions = self.commission_calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner_id,
                upline_chain=upline_chain
            )

            logger.info(
                f"Calculated {len(commissions)} commissions for purchase by {partner_id}"
            )

            # ------------------------------------------------
            # Convert commissions to JSON
            # ------------------------------------------------

            commissions_data = [
                {
                    "partner_id": c.partner_id,
                    "level": c.level,
                    "rate": c.rate,
                    "amount": c.amount
                }
                for c in commissions
            ]

            # ------------------------------------------------
            # Send to API
            # ------------------------------------------------

            self.api_client.update_partner_sales(
                partner_id,
                {
                    "order_id": order_id,
                    "amount": amount,
                    "commissions": commissions_data
                }
            )

            logger.info(f"Successfully processed order {order_id}")

            return True

        except Exception as e:

            logger.error(f"Failed to process order: {e}")

            return False

        finally:
            session.close()