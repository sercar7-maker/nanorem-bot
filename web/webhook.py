"""Webhook handler for nanorvs.ru notifications."""

import logging
import hmac
import hashlib
from typing import Dict, Any, Optional
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
    
    def handle_webhook(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Handle webhook event."""
        try:
            logger.info(f"Processing webhook: {event_type}")
            
            if event_type == 'order.created':
                return self._handle_order_created(data)
            elif event_type == 'order.completed':
                return self._handle_order_completed(data)
            elif event_type == 'product.updated':
                return self._handle_product_updated(data)
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return False
                
        except Exception as e:
            logger.error(f"Webhook handling failed: {e}")
            return False
    
    def _handle_order_created(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling order creation")
        return self.order_handler.process_order(data)
    
    def _handle_order_completed(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling order completion")
        return self.order_handler.process_order(data)
    
    def _handle_product_updated(self, data: Dict[str, Any]) -> bool:
        logger.info("Handling product update")
        # TODO: Trigger catalog sync
        return True
