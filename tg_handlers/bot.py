import logging

from telegram.ext import Application

from config import BOT_TOKEN
from database.db import init_db
from scheduler import setup_scheduler
from tg_handlers.handlers import setup_handlers

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for NANOREM MLM Telegram Bot."""

    def __init__(self):

        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set in configuration!")

        self.application = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

    def run(self):

        print(">>> TELEGRAM BOT STARTED <<<")

        logger.info("Initializing database...")
        init_db()

        logger.info("Registering handlers...")
        setup_handlers(self.application)

        logger.info("Starting scheduler...")
        self.scheduler = setup_scheduler()

        logger.info("Starting polling...")
        self.application.run_polling(drop_pending_updates=True)