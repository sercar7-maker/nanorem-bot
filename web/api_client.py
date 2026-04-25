"""
API Client for nanorvs.ru WooCommerce integration.
Uses query string authentication (consumer_key & consumer_secret in URL).
"""
import logging
import requests
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from config import WC_CONSUMER_KEY, WC_CONSUMER_SECRET, WC_API_BASE_URL

logger = logging.getLogger(__name__)


class NanorvsAPIClient:
    """Client for interacting with nanorvs.ru WooCommerce API."""

    def __init__(
        self,
        base_url: str = WC_API_BASE_URL,
        consumer_key: Optional[str] = WC_CONSUMER_KEY,
        consumer_secret: Optional[str] = WC_CONSUMER_SECRET,
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL for WooCommerce REST API (e.g., https://nanorvs.ru/wp-json/wc/v3)
            consumer_key: WooCommerce Consumer Key
            consumer_secret: WooCommerce Consumer Secret
        """
        self.base_url = base_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.session = requests.Session()
        # Добавляем заголовки, имитирующие браузер
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
        })
        logger.info(f"Initialized NanorvsAPIClient for {base_url} (using query auth)")

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Internal method to perform authenticated requests."""
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))

        if params is None:
            params = {}

        # Добавляем ключи в параметры URL
        if self.consumer_key and self.consumer_secret:
            params["consumer_key"] = self.consumer_key
            params["consumer_secret"] = self.consumer_secret

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=15)
            else:
                response = self.session.request(
                    method=method, url=url, params=params, json=data, timeout=15
                )

            response.raise_for_status()

            if response.status_code == 204:
                return {"success": True}

            # Убираем BOM (Byte Order Mark), если он есть
            text = response.text
            if text.startswith('\ufeff'):
                text = text[1:]
            return json.loads(text)

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error calling {endpoint}: {e}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error calling {endpoint}: {e}")
            return None

    # ----------------------------------------------------------------------
    # Customers (Partners)
    # ----------------------------------------------------------------------
    def get_customers(self, **filters) -> List[Dict[str, Any]]:
        """Get list of customers (partners) with optional filters."""
        params = {"per_page": 100, **filters}
        return self._request("GET", "customers", params=params) or []

    def get_customer(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Get single customer by ID."""
        return self._request("GET", f"customers/{customer_id}")

    def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find customer by email."""
        customers = self.get_customers(email=email)
        return customers[0] if customers else None

    # ----------------------------------------------------------------------
    # Orders
    # ----------------------------------------------------------------------
    def get_orders(self, **filters) -> List[Dict[str, Any]]:
        """Get list of orders with optional filters."""
        params = {"per_page": 100, **filters}
        return self._request("GET", "orders", params=params) or []

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Get single order by ID."""
        return self._request("GET", f"orders/{order_id}")

    def get_order_by_number(self, order_number: str) -> Optional[Dict[str, Any]]:
        """Get order by order number (e.g., '#1234')."""
        clean_number = order_number.lstrip("#")
        orders = self.get_orders(number=clean_number)
        return orders[0] if orders else None

    # ----------------------------------------------------------------------
    # Products
    # ----------------------------------------------------------------------
    def get_products(self, **filters) -> List[Dict[str, Any]]:
        """Get product catalog."""
        params = {"per_page": 100, **filters}
        return self._request("GET", "products", params=params) or []

    def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Get single product by ID."""
        return self._request("GET", f"products/{product_id}")

    # ----------------------------------------------------------------------
    # Utility
    # ----------------------------------------------------------------------
    def check_connection(self) -> bool:
        """Check connection to WooCommerce API."""
        try:
            response = self._request("GET", "system_status")
            return response is not None
        except Exception:
            return False