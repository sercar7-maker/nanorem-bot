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
from tg_handlers.handlers import setup_handlers


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # подключаем handlers
    setup_handlers(application)

    logger.info("Бот запущен...")

    # ВАЖНО: без asyncio.run
    application.run_polling()


if __name__ == "__main__":
    main()