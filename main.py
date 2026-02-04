#!/usr/bin/env python3
"""NANOREM MLM System - Main Application Entry Point."""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import BOT_TOKEN, DEBUG, APP_NAME, APP_VERSION, DATABASE_URL
from telegram.bot import TelegramBot
from database.db import DatabaseManager

logger = logging.getLogger(__name__)


async def main():
    """Main application entry point."""
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Initialize database
    db = DatabaseManager(DATABASE_URL)
    if not db.check_connection():
        logger.error("Failed to connect to database!")
        return
    
    # Initialize bot
    bot = TelegramBot()
    bot.setup()
    
    try:
        logger.info("Bot is running. Press Ctrl+C to stop.")
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping bot...")
        await bot.stop()
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
        await bot.stop()
    finally:
        db.close()
        logger.info(f"{APP_NAME} stopped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - MLM Management System")
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize database schema",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in debug mode (overrides config)",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    if args.debug or DEBUG:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger = logging.getLogger(__name__)
    
    # Initialize database if requested
    if args.init_db:
        logger.info("Initializing database...")
        db = DatabaseManager(DATABASE_URL)
        db.init_db()
        logger.info("Database initialized successfully")
        sys.exit(0)
    
    # Run main app
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
