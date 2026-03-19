import logging

from telegram.ext import ApplicationBuilder

from config import BOT_TOKEN
from database.db import init_db
from scheduler import setup_scheduler
from tg_handlers.handlers import setup_handlers

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):

        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set!")

        # ✅ нормальные таймауты + стабильный polling
        self.application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connect_timeout(10)
            .read_timeout(10)
            .write_timeout(10)
            .pool_timeout(10)
            .build()
        )

    def run(self):

        print(">>> BOT START <<<")

        init_db()
        setup_handlers(self.application)
        self.scheduler = setup_scheduler()

        # ✅ уменьшаем лаги
        self.application.run_polling(
            drop_pending_updates=True,
            close_loop=False
        )