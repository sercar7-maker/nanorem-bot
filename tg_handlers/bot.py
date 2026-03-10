"""Main Telegram Bot class for NANOREM MLM System."""

import logging

from telegram.ext import Application
from config import BOT_TOKEN
from .handlers import setup_handlers
from database.db import init_db
from scheduler import setup_scheduler

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for NANOREM MLM Telegram Bot."""

    def __init__(self) -> None:

        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set in configuration!")

        # создаём Telegram Application без использования системного прокси
        self.application = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

    def run(self) -> None:
        """Run the bot using polling."""

        print(">>> TELEGRAM BOT STARTED <<<")

        logger.info("Initializing database...")
        init_db()

        logger.info("Registering handlers...")
        setup_handlers(self.application)

        logger.info("Starting scheduler...")
        self._scheduler = setup_scheduler()

        logger.info("Starting polling...")
        self.application.run_polling(drop_pending_updates=True)