"""API Client for nanorvs.ru website integration."""

import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class NanorvsAPIClient:
    """Client for interacting with nanorvs.ru API."""
    
    def __init__(self, base_url: str = "https://nanorvs.ru", api_key: Optional[str] = None):
        """Initialize API client.
        
        Args:
            base_url: Base URL for nanorvs.ru
            api_key: API key for authentication (if required)
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        
        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            })
        
        logger.info(f"Initialized NanorvsAPIClient for {base_url}")
    
    def get_products(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get product catalog from nanorvs.ru.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of products with details
        """
        try:
            endpoint = f"{self.base_url}/api/products"
            params = {}
            if category:
                params['category'] = category
            
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            products = response.json()
            logger.info(f"Retrieved {len(products)} products from nanorvs.ru")
            return products
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get products: {e}")
            return []
    
    def get_product_details(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about specific product.
        
        Args:
            product_id: Product identifier
            
        Returns:
            Product details or None if not found
        """
        try:
            endpoint = f"{self.base_url}/api/products/{product_id}"
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            
            product = response.json()
            logger.info(f"Retrieved details for product {product_id}")
            return product
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get product {product_id}: {e}")
            return None
    
    def create_order(self, order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new order on nanorvs.ru.
        
        Args:
            order_data: Order information (items, customer, etc.)
            
        Returns:
            Created order details or None if failed
        """
        try:
            endpoint = f"{self.base_url}/api/orders"
            response = self.session.post(endpoint, json=order_data, timeout=10)
            response.raise_for_status()
            
            order = response.json()
            logger.info(f"Created order {order.get('id')}")
            return order
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create order: {e}")
            return None
    
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status from nanorvs.ru.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Order status information
        """
        try:
            endpoint = f"{self.base_url}/api/orders/{order_id}"
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            
            order = response.json()
            logger.info(f"Retrieved status for order {order_id}")
            return order
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def update_partner_sales(self, partner_id: str, sale_data: Dict[str, Any]) -> bool:
        """Report partner sale to nanorvs.ru system.
        
        Args:
            partner_id: Partner identifier
            sale_data: Sale information
            
        Returns:
            True if successful
        """
        try:
            endpoint = f"{self.base_url}/api/partners/{partner_id}/sales"
            response = self.session.post(endpoint, json=sale_data, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Reported sale for partner {partner_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to report sale: {e}")
            return False
    
    def get_partner_stats(self, partner_id: str) -> Optional[Dict[str, Any]]:
        """Get partner statistics from nanorvs.ru.
        
        Args:
            partner_id: Partner identifier
            
        Returns:
            Partner statistics
        """
        try:
            endpoint = f"{self.base_url}/api/partners/{partner_id}/stats"
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            
            stats = response.json()
            logger.info(f"Retrieved stats for partner {partner_id}")
            return stats
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get partner stats: {e}")
            return None
    
    def check_connection(self) -> bool:
        """Check connection to nanorvs.ru.
        
        Returns:
            True if connection successful
        """
        try:
            response = self.session.get(f"{self.base_url}/api/health", timeout=5)
            return response.status_code == 200
        except:
            return False
