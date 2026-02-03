"""Configuration settings for NANOREM MLM System"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'your-bot-token-here')
TELEGRAM_ADMIN_ID = int(os.getenv('TELEGRAM_ADMIN_ID', '0'))

# Database Configuration
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'sqlite:///nanorem_mlm.db'
)

# Application Settings
APP_NAME = 'NANOREM MLM System'
APP_VERSION = '1.0.0'
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'

# MLM System Configuration
class MLMConfig:
    """MLM system business rules and settings"""
    
    # Commission rates by level (percentage)
    COMMISSION_RATES = {
        'level_1': 15.0,      # Direct partners
        'level_2': 8.0,       # Second-level partners
        'level_3': 5.0,       # Third-level partners
        'level_4': 3.0,       # Fourth-level partners
    }
    
    # Partner status levels
    PARTNER_STATUSES = {
        'ACTIVE': 'active',
        'INACTIVE': 'inactive',
        'SUSPENDED': 'suspended',
        'TERMINATED': 'terminated',
    }
    
    # Minimum order amounts
    MIN_ORDER_AMOUNT = 50.0  # Minimum order value in currency units
    MIN_MONTHLY_TARGET = 500.0  # Minimum monthly sales target
    
    # Bonus rates
    TEAM_BONUS_RATE = 2.0  # Team bonus percentage
    PERFORMANCE_BONUS = 100.0  # Fixed performance bonus
    
    # Network configuration
    MAX_DIRECT_PARTNERS = None  # Unlimited, or set a number
    ACTIVATION_BONUS = 50.0  # Bonus for new partner activation

# Product Configuration
class ProductConfig:
    """NANOREM product pricing and settings"""
    
    # Currency settings
    CURRENCY = 'EUR'
    CURRENCY_SYMBOL = '€'
    
    # Product categories
    CATEGORIES = [
        'exterior_care',
        'interior_care',
        'protection',
        'tools',
        'bundles',
    ]
    
    # Default product markup for partners
    DEFAULT_PARTNER_MARKUP = 20.0  # 20% markup

# API Configuration
class APIConfig:
    """API and integration settings"""
    
    # Request timeout
    REQUEST_TIMEOUT = 30
    
    # Rate limiting
    RATE_LIMIT_REQUESTS = 100
    RATE_LIMIT_PERIOD = 60  # seconds
    
    # Webhook settings
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'secret-key')
    WEBHOOK_TIMEOUT = 10

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'nanorem_mlm.log')

# Email Configuration (for notifications)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'noreply@nanorem.com')

# Timezone
TIMEZONE = os.getenv('TIMEZONE', 'Europe/Riga')
