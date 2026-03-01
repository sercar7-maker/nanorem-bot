"""Main Telegram Bot class for NANOREM MLM System."""
import logging
import sys
import os

# Ensure the system telegram library is used, not the local folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import Application
from config import BOT_TOKEN
from .handlers import setup_handlers
from database.db import init_db
from scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for NANOREM MLM Telegram Bot."""

    def __init__(self) -> None:
        """Initialize bot application with token."""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set in configuration!")
        self.application: Application = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )
        self._scheduler = None
        logger.info("TelegramBot initialized successfully.")

    def setup(self) -> None:
        """Register all handlers, initialize database, and set up scheduler."""
        # Initialize database tables
        init_db()
        logger.info("Database initialized.")

        # Register command handlers
        setup_handlers(self.application)
        logger.info("Handlers registered.")

        # Set up background scheduler for status expiration
        self._scheduler = start_scheduler()
        logger.info("Background scheduler started.")

    def run(self) -> None:
        """Run the bot using long polling until stopped."""
        self.setup()
        logger.info("Starting NANOREM MLM bot via polling...")
        try:
            self.application.run_polling(drop_pending_updates=True)
        finally:
            stop_scheduler()
            logger.info("Bot stopped.")
