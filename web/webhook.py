"""Webhook handler for nanorvs.ru notifications."""

import logging
import hmac
import hashlib
from typing import Dict, Any, Optional

from database.db import SessionLocal
from database.models import Purchase

from .order_handler import OrderHandler

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Handle webhook notifications from nanorvs.ru."""
    
    def __init__(self, order_handler: OrderHandler, webhook_secret: Optional[str] = None):
        self.order_handler = order_handler
        self.webhook_secret = webhook_secret
        logger.info("Initialized WebhookHandler")
    
    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature."""
        if not self.webhook_secret:
            return True
        
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    async def handle_webhook(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Handle webhook event."""
        try:
            logger.info(f"Processing webhook: {event_type}")
            
            # -------------------------------------------------
            # 🔒 GLOBAL DEDUPLICATION
            # -------------------------------------------------

            order_id = str(data.get("id"))

            session = SessionLocal()

            existing = session.query(Purchase).filter_by(ext_ref=order_id).first()

            if existing and existing.is_commission_processed:
                logger.warning(f"Webhook duplicate ignored: order {order_id}")
                session.close()
                return True

            session.close()

            # -------------------------------------------------

            if event_type == 'order.created':
                return await self._handle_order_created(data)
            elif event_type == 'order.completed':
                return await self._handle_order_completed(data)
            elif event_type == 'product.updated':
                return self._handle_product_updated(data)
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return False
                
        except Exception as e:
            logger.error(f"Webhook handling failed: {e}")
            return False
    
    async def _handle_order_created(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling order creation")
        return await self.order_handler.process_order(data)
    
    async def _handle_order_completed(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling order completion")
        return await self.order_handler.process_order(data)
    
    def _handle_product_updated(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling product update")
        return True