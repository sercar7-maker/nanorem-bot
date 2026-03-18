import logging
import os

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

        # ❌ убираем прокси
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

        self.application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connection_pool_size(5)   # меньше = стабильнее
            .pool_timeout(5)
            .build()
        )

    def run(self):

        print(">>> BOT START <<<")

        init_db()
        setup_handlers(self.application)
        setup_scheduler()

        # 🔥 КЛЮЧЕВОЙ ФИКС
        self.application.run_polling(
            drop_pending_updates=True,
            close_loop=False,   # 💥 фикс зависаний
        )