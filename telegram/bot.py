"""Main Telegram Bot class for NANOREM MLM System."""

import logging
from telegram.ext import Application
from config import BOT_TOKEN
from .handlers import setup_handlers
from database.db import init_db

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
        logger.info("TelegramBot initialized successfully.")

    def setup(self) -> None:
        """Register all handlers and prepare the bot."""
        # Initialize database tables
        init_db()
        logger.info("Database initialized.")

        # Register command handlers
        setup_handlers(self.application)
        logger.info("Handlers registered.")

    def run(self) -> None:
        """Run the bot using long-polling until stopped."""
        self.setup()
        logger.info("Starting NANOREM MLM bot via polling...")
        self.application.run_polling(drop_pending_updates=True)
        logger.info("Bot stopped.")
