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

        # 🔥 УБИВАЕМ ПРОКСИ ЖЁСТКО
        for key in [
            "HTTP_PROXY", "HTTPS_PROXY",
            "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy"
        ]:
            os.environ.pop(key, None)

        # 🔥 создаём приложение БЕЗ proxy
        self.application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connection_pool_size(5)
            .pool_timeout(5)
            .build()
        )

    def run(self):

        print(">>> BOT START <<<")

        init_db()
        setup_handlers(self.application)
        setup_scheduler()

        self.application.run_polling(
            drop_pending_updates=True,
            close_loop=False,
        )