#!/usr/bin/env python3
"""NANOREM MLM System - Main Application Entry Point"""

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import configuration
try:
    from config import (
        TELEGRAM_BOT_TOKEN,
        DATABASE_URL,
        APP_NAME,
        APP_VERSION,
        DEBUG_MODE,
        LOG_LEVEL
    )
except ImportError as e:
    logger.error(f"Failed to import configuration: {e}")
    sys.exit(1)

# Import application modules
try:
    from telegram import TelegramBot
    from telegram.handlers import setup_handlers
    from database.db import DatabaseManager
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    sys.exit(1)


def main():
    """Main entry point for NANOREM MLM application."""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION}"
    )
    parser.add_argument(
        '--mode',
        choices=['telegram', 'web', 'all'],
        default='telegram',
        help='Run mode: telegram bot, web interface, or both'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    logger.info("Initializing database...")
    db_manager = DatabaseManager()
    
    try:
        # Check database connection
        if db_manager.check_connection():
            logger.info("Соединение с базой данных установлено")
        else:
            logger.error("Не удалось подключиться к базе данных")
            return 1
        
        # Run selected mode
        if args.mode in ['telegram', 'all']:
            logger.info("Запуск Telegram бота...")
            bot = TelegramBot()
            setup_handlers(bot.app, bot)
            
            logger.info(f"{APP_NAME} v{APP_VERSION} started")
            logger.info("Бот готов к работе!")
            
            bot.run()
        
        if args.mode == 'web':
            logger.info("Веб-интерфейс будет добавлен в следующей версии")
            # TODO: Implement web interface
            pass
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")
        return 0
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1
    finally:
        logger.info("Завершение работы...")


if __name__ == '__main__':
    sys.exit(main())
