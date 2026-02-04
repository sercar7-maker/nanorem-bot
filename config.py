"""Configuration settings for NANOREM MLM System"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging

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

# Telegram bot token (REQUIRED)
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN is not set!\n"
        "Please add BOT_TOKEN to your .env file.\n"
        "Get it from BotFather in Telegram."
    )

# ====================================
# DATABASE CONFIGURATION
# ====================================

# Database URL (SQLite by default, PostgreSQL for production)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'nanorem.db'}"
)

# ====================================
# APPLICATION SETTINGS
# ====================================

# Application metadata
APP_NAME = os.getenv("APP_NAME", "NANOREM MLM System")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

# Debug mode
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ====================================
# WEBHOOK CONFIGURATION (optional)
# ====================================

# For deploying bot on a server with webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8443))

# ====================================
# EXPORT CONFIGURATION SUMMARY
# ====================================

if DEBUG:
    print(f"\nConfiguration Loaded:")
    print(f"  APP: {APP_NAME} v{APP_VERSION}")
    print(f"  DEBUG: {DEBUG}")
    print(f"  LOG_LEVEL: {LOG_LEVEL}")
    print(f"  DATABASE: {DATABASE_URL}")
    print(f"  WEBHOOK: {WEBHOOK_URL if WEBHOOK_URL else 'Not configured'}")
    print()
