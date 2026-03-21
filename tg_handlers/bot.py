import logging

from telegram.ext import ApplicationBuilder

from config import BOT_TOKEN
from database.db import init_db, SessionLocal
from scheduler import setup_scheduler
from tg_handlers.handlers import setup_handlers
from core.commission import CommissionCalculator

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set!")

        self.application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(30)
            .build()
        )

        self.bot = self.application.bot

        self.db = SessionLocal()
        self.commission_calculator = CommissionCalculator(
            db=self.db,
            bot=self.bot
        )

    def run(self):
        print(">>> BOT START <<<")

        init_db()
        setup_handlers(self.application)
        self.scheduler = setup_scheduler()

        self.application.run_polling(
            drop_pending_updates=True,
            close_loop=False
        )