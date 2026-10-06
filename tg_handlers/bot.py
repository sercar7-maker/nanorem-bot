import sys
import os

# добавляем корень проекта
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import logging
from dotenv import load_dotenv
from telegram.ext import Application

# загрузка .env
load_dotenv()

from config import BOT_TOKEN
from database.db import init_db
from scheduler import start_scheduler, stop_scheduler
from tg_handlers.handlers import setup_handlers


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required to run the Telegram bot")

    # создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # подключаем handlers
    setup_handlers(application)

    init_db()
    start_scheduler()

    logger.info("Бот запущен...")

    # ВАЖНО: без asyncio.run
    try:
        application.run_polling()
    finally:
        stop_scheduler()


if __name__ == "__main__":
    main()