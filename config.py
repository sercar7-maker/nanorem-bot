import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ====================================
# ENVIRONMENT SETUP
# ====================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ====================================
# TELEGRAM BOT CONFIGURATION
# ====================================

BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")

# ====================================
# DATABASE CONFIGURATION
# ====================================

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'nanorem.db'}"
)

# ====================================
# APPLICATION SETTINGS
# ====================================

APP_NAME: str = os.getenv("APP_NAME", "NANOREM MLM System")
APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ====================================
# WEBHOOK CONFIGURATION
# ====================================

WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

# ====================================
# SECURITY
# ====================================

WOOCOMMERCE_WEBHOOK_SECRET: str | None = os.getenv(
    "WOOCOMMERCE_WEBHOOK_SECRET"
)

TELEGRAM_WEBHOOK_SECRET: str | None = os.getenv(
    "TELEGRAM_WEBHOOK_SECRET"
)

ADMIN_API_SECRET: str | None = os.getenv(
    "ADMIN_API_SECRET"
)

# ====================================
# WOOCOMMERCE API CONFIGURATION
# ====================================

WC_CONSUMER_KEY: str | None = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET: str | None = os.getenv("WC_CONSUMER_SECRET")

WC_API_BASE_URL: str = os.getenv(
    "WC_API_BASE_URL",
    "https://nanorvs.ru/wp-json/wc/v3"
)

# ====================================
# MLM CONFIGURATION
# ====================================

COMMISSION_RATES: dict[int, float] = {
    1: 20.0,
    2: 10.0,
    3: 5.0,
    4: 5.0,
    5: 5.0,
}

MAX_REFERRAL_DEPTH: int = 5

# ====================================
# STARTUP INFO
# ====================================

if DEBUG:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

    print("\nConfiguration Loaded:")
    print(f"  APP: {APP_NAME} v{APP_VERSION}")
    print(f"  DEBUG: {DEBUG}")
    print(f"  LOG_LEVEL: {LOG_LEVEL}")
    print(f"  DATABASE: {DATABASE_URL}")
    print(f"  BOT_TOKEN: {'SET' if BOT_TOKEN else 'NOT SET'}")
    print(
        f"  WEBHOOK: "
        f"{WEBHOOK_URL if WEBHOOK_URL else 'Not configured (using polling)'}"
    )
    print(
        f"  SECURITY: "
        f"WooCommerce={'SET' if WOOCOMMERCE_WEBHOOK_SECRET else 'NOT SET'}, "
        f"Telegram={'SET' if TELEGRAM_WEBHOOK_SECRET else 'NOT SET'}, "
        f"Admin={'SET' if ADMIN_API_SECRET else 'NOT SET'}"
    )
    print()
