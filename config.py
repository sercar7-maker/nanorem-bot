import os
import logging
from decimal import Decimal, InvalidOperation
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
# SMTP CONFIGURATION
# ====================================

SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "false").lower() == "true"
SMTP_HOST: str = os.getenv("SMTP_HOST", "mail.nanorvs.ru")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL: str | None = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "NANOREM")
SMTP_TIMEOUT: int = int(os.getenv("SMTP_TIMEOUT", "15"))

# ====================================
# MLM CONFIGURATION
# ====================================

def parse_purchase_amount(setting_name: str, raw: str) -> Decimal:
    """Parse a ruble threshold: finite, positive, no fraction of a kopeck."""
    try:
        amount = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        raise RuntimeError(
            f"{setting_name}: нужно конечное положительное число рублей "
            f"без долей копейки, получено {raw!r}"
        ) from None
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(
        Decimal("0.01")
    ):
        raise RuntimeError(
            f"{setting_name}: нужно конечное положительное число рублей "
            f"без долей копейки, получено {raw!r}"
        )
    return amount.quantize(Decimal("0.01"))


def load_activity_thresholds(
    monthly_raw: str,
    annual_raw: str,
) -> tuple[Decimal, Decimal]:
    monthly = parse_purchase_amount("MONTHLY_PURCHASE_AMOUNT", monthly_raw)
    annual = parse_purchase_amount("ANNUAL_PURCHASE_AMOUNT", annual_raw)
    if annual <= monthly:
        raise RuntimeError(
            "ANNUAL_PURCHASE_AMOUNT должен быть больше "
            "MONTHLY_PURCHASE_AMOUNT: "
            f"год {annual}, месяц {monthly}"
        )
    return monthly, annual


def configured_activity_thresholds() -> tuple[Decimal, Decimal]:
    return load_activity_thresholds(
        os.getenv("MONTHLY_PURCHASE_AMOUNT", "3000.00"),
        os.getenv("ANNUAL_PURCHASE_AMOUNT", "10000.00"),
    )


MONTHLY_PURCHASE_AMOUNT, ANNUAL_PURCHASE_AMOUNT = (
    configured_activity_thresholds()
)

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
    database_scheme = DATABASE_URL.split(":", maxsplit=1)[0]
    print(f"  DATABASE: configured ({database_scheme})")
    print(f"  BOT_TOKEN: {'SET' if BOT_TOKEN else 'NOT SET'}")
    print(
        "  WEBHOOK: configured"
        if WEBHOOK_URL
        else "  WEBHOOK: not configured (using polling)"
    )
    print(
        f"  SECURITY: "
        f"WooCommerce={'SET' if WOOCOMMERCE_WEBHOOK_SECRET else 'NOT SET'}, "
        f"Telegram={'SET' if TELEGRAM_WEBHOOK_SECRET else 'NOT SET'}, "
        f"Admin={'SET' if ADMIN_API_SECRET else 'NOT SET'}"
    )
    print()
