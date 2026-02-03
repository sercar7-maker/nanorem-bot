"""Order handling module for nanorvs.ru integration."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from .api_client import NanorvsAPIClient
from core.partner_manager import PartnerManager
from core.commission import CommissionCalculator

logger = logging.getLogger(__name__)


class OrderHandler:
    """Handle orders from nanorvs.ru and process MLM commissions."""
    
    def __init__(self, api_client: NanorvsAPIClient, 
                 partner_manager: PartnerManager,
                 commission_calculator: CommissionCalculator):
        self.api_client = api_client
        self.partner_manager = partner_manager
        self.commission_calculator = commission_calculator
        logger.info("Initialized OrderHandler")
    
    def process_order(self, order_data: Dict[str, Any]) -> bool:
        """Process order and calculate MLM commissions."""
        try:
            order_id = order_data.get('id')
            partner_id = order_data.get('partner_id')
            amount = order_data.get('total_amount', 0)
            
            logger.info(f"Processing order {order_id} for partner {partner_id}")
            
            # Calculate commissions
            commissions = self.commission_calculator.calculate(
                partner_id=partner_id,
                sale_amount=amount
            )
            
            # Update partner sales
            self.api_client.update_partner_sales(partner_id, {
                'order_id': order_id,
                'amount': amount,
                'commissions': commissions
            })
            
            logger.info(f"Successfully processed order {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process order: {e}")
            return False
