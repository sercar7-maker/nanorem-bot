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
from scheduler import setup_scheduler

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for NANOREM MLM Telegram Bot."""

    def __init__(self) -> None:
        """Initialize bot application with token."""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set in configuration!")

        self._scheduler = None

        self.application: Application = (
            Application.builder()
            .token(BOT_TOKEN)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )

        logger.info("TelegramBot initialized successfully.")

    async def _post_init(self, application: Application) -> None:
        """Called after application is initialized - start scheduler here."""
        init_db()
        setup_handlers(application)

        self._scheduler = setup_scheduler()
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("[Scheduler] Started inside event loop successfully")

    async def _post_shutdown(self, application: Application) -> None:
        """Called on shutdown - stop scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[Scheduler] Stopped")

    def run(self) -> None:
        """Run the bot using polling."""
        logger.info("Starting NANOREM MLM Bot polling...")
        self.application.run_polling(drop_pending_updates=True)
