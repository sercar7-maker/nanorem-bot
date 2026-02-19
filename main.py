#!/usr/bin/env python3
"""NANOREM MLM System - Main Application Entry Point."""

import sys
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from config import BOT_TOKEN, DEBUG
from telegram.bot import TelegramBot


def configure_logging(debug: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Main entry point for NANOREM MLM Bot."""
    configure_logging(debug=DEBUG)
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not configured. Set it in .env or config.py")
        sys.exit(1)

    logger.info("Initializing NANOREM MLM Telegram Bot...")
    bot = TelegramBot()
    bot.run()


if __name__ == "__main__":
    main()
