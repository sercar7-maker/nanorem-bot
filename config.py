"""Configuration settings for NANOREM MLM System"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ====================================
# ENVIRONMENT SETUP
# ====================================

# Get the base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# ====================================
# TELEGRAM BOT CONFIGURATION
# ====================================

# Telegram bot token (REQUIRED) - set in .env file
# Returns None if not set; validation is handled by main.py and TelegramBot
BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")

# ====================================
# DATABASE CONFIGURATION
# ====================================

# Database URL (SQLite by default, PostgreSQL for production)
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'nanorem.db'}"
)

# ====================================
# APPLICATION SETTINGS
# ====================================

APP_NAME: str = os.getenv("APP_NAME", "NANOREM MLM System")
APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

# Debug mode (set DEBUG=true in .env to enable)
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# Logging level
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ====================================
# WEBHOOK CONFIGURATION (optional)
# ====================================

# For deploying bot on a server with webhook instead of polling
WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

# ====================================
# MLM CONFIGURATION
# ====================================

# Commission rates per referral level (1-5)
COMMISSION_RATES: dict[int, float] = {
    1: 20.0,  # 20% for level 1 (direct referrals)
    2: 10.0,  # 10% for level 2
    3: 5.0,   # 5% for level 3
    4: 5.0,   # 5% for level 4
    5: 5.0,   # 5% for level 5
}

# Maximum referral depth
MAX_REFERRAL_DEPTH: int = 5

# ====================================
# STARTUP INFO (DEBUG mode only)
# ====================================

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    print(f"\nConfiguration Loaded:")
    print(f"  APP: {APP_NAME} v{APP_VERSION}")
    print(f"  DEBUG: {DEBUG}")
    print(f"  LOG_LEVEL: {LOG_LEVEL}")
    print(f"  DATABASE: {DATABASE_URL}")
    print(f"  BOT_TOKEN: {'SET' if BOT_TOKEN else 'NOT SET - bot will not start'}")
    print(f"  WEBHOOK: {WEBHOOK_URL if WEBHOOK_URL else 'Not configured (using polling)'}")
    print()
