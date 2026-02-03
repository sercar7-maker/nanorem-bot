"""Cloud Cash Register Configuration Module

Configuration and credentials for cloud-based cash register systems.
To be filled in with actual provider details when available.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CashRegisterConfig:
    """
    Configuration for Cloud Cash Register API
    
    TODO: Update with actual values from manufacturer
    """
    
    # API Endpoint Configuration
    api_provider: str = os.getenv('CASH_REGISTER_PROVIDER', 'unknown')
    api_endpoint: str = os.getenv(
        'CASH_REGISTER_API_ENDPOINT',
        'https://api.cashregister.example.com/v1'
    )
    api_version: str = os.getenv('CASH_REGISTER_API_VERSION', '1.0')
    
    # Authentication
    auth_token: str = os.getenv('CASH_REGISTER_AUTH_TOKEN', '')
    auth_secret: Optional[str] = os.getenv('CASH_REGISTER_AUTH_SECRET', None)
    api_key: str = os.getenv('CASH_REGISTER_API_KEY', '')
    
    # Connection Settings
    timeout: int = int(os.getenv('CASH_REGISTER_TIMEOUT', '30'))
    max_retries: int = int(os.getenv('CASH_REGISTER_MAX_RETRIES', '3'))
    retry_delay: int = int(os.getenv('CASH_REGISTER_RETRY_DELAY', '5'))
    
    # Webhook Configuration
    webhook_secret: str = os.getenv('CASH_REGISTER_WEBHOOK_SECRET', '')
    webhook_url: str = os.getenv(
        'CASH_REGISTER_WEBHOOK_URL',
        'https://nanorem.example.com/webhooks/cash-register'
    )
    
    # Store/Register Information
    store_id: Optional[str] = os.getenv('CASH_REGISTER_STORE_ID', None)
    register_id: Optional[str] = os.getenv('CASH_REGISTER_REGISTER_ID', None)
    
    # Feature Flags
    enable_receipts: bool = os.getenv('CASH_REGISTER_ENABLE_RECEIPTS', 'true').lower() == 'true'
    enable_sync: bool = os.getenv('CASH_REGISTER_ENABLE_SYNC', 'true').lower() == 'true'
    enable_webhooks: bool = os.getenv('CASH_REGISTER_ENABLE_WEBHOOKS', 'true').lower() == 'true'
    
    # Sync Settings
    auto_sync_interval: int = int(os.getenv('CASH_REGISTER_AUTO_SYNC_INTERVAL', '3600'))
    sync_batch_size: int = int(os.getenv('CASH_REGISTER_SYNC_BATCH_SIZE', '100'))
    
    # Report Settings
    daily_report_enabled: bool = os.getenv('CASH_REGISTER_DAILY_REPORT', 'true').lower() == 'true'
    daily_report_time: str = os.getenv('CASH_REGISTER_DAILY_REPORT_TIME', '23:00')
    
    def is_configured(self) -> bool:
        """
        Check if cash register is properly configured.
        
        Returns:
            bool: True if minimum required configuration is present
        """
        return bool(
            self.api_endpoint != 'https://api.cashregister.example.com/v1' and
            self.api_key and
            self.auth_token
        )
    
    def get_headers(self) -> dict:
        """
        Get HTTP headers for API requests.
        
        Returns:
            Dictionary with authorization and other headers
        """
        return {
            'Authorization': f'Bearer {self.auth_token}',
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json',
            'User-Agent': 'NANOREM-MLM/1.0',
        }


# Default configuration instance
default_config = CashRegisterConfig()


class CashRegisterProviders:
    """
    Known cloud cash register providers
    
    TODO: Add support for multiple providers as needed
    """
    
    # Common providers (to be implemented)
    IIKO = 'iiko'          # Система управления рестораном
    ATOL = 'atol'          # Облачная касса АТОЛ
    TAXCOM = 'taxcom'      # TaxCom
    YANDEX_KASSA = 'yandex'  # Яндекс.Касса
    PAYKEEPER = 'paykeeper'  # PayKeeper
    CLOUDKASSA = 'cloudkassa'  # CloudKassa
    CUSTOM = 'custom'      # Custom/Generic provider
    
    SUPPORTED = [
        IIKO, ATOL, TAXCOM, YANDEX_KASSA, PAYKEEPER, CLOUDKASSA, CUSTOM
    ]


class ReceiptSettings:
    """
    Receipt generation and formatting settings
    
    TODO: Configure based on requirements
    """
    
    # Receipt format
    INCLUDE_QR_CODE = True
    INCLUDE_PARTNER_INFO = True
    INCLUDE_PRODUCT_DETAILS = True
    INCLUDE_COMMISSION_INFO = False  # For partner receipts
    
    # Email settings
    SEND_EMAIL_RECEIPT = True
    EMAIL_FORMAT = 'html'  # 'html' or 'pdf'
    
    # Print settings
    AUTO_PRINT = False
    PRINT_COPIES = 2
    
    # Storage
    STORE_RECEIPT_PDF = True
    STORE_RECEIPT_JSON = True
    RETENTION_DAYS = 365


print("""
╔════════════════════════════════════════════════════════════╗
║  Cloud Cash Register Integration - Configuration Status     ║
╠════════════════════════════════════════════════════════════╣
║  Status: WAITING FOR MANUFACTURER DETAILS                   ║
║  Expected: API endpoint, auth method, webhook format         ║
║                                                             ║
║  Once details are provided:                                 ║
║  1. Update .env file with credentials                        ║
║  2. Fill in webhook handler implementation                   ║
║  3. Test API connectivity                                    ║
║  4. Configure receipt sync schedule                          ║
╚════════════════════════════════════════════════════════════╝
""")
