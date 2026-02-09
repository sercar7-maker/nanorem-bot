"""Main Telegram Bot class for NANOREM MLM System."""

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN, DEBUG
from .handlers import setup_handlers

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for handling Telegram interactions."""

    def __init__(self):
        """Initialize bot with Telegram token and handlers."""
        self.application = None
        self.token = BOT_TOKEN
        logger.info("TelegramBot initialized")

    def setup(self):
        """Setup bot application and handlers."""
        if not self.token:
            raise ValueError("BOT_TOKEN is not set!")

        # Create application using token
        self.application = Application.builder().token(self.token).build()
        logger.info("Bot application created")

        # Import and setup handlers
        setup_handlers(self.application)
        logger.info("Handlers registered")

    async def start(self):
        """Start the bot polling for updates."""
        if not self.application:
            self.setup()

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Bot started polling for updates")

    async def stop(self):
        """Stop the bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        logger.info("Bot stopped")

    def get_application(self):
        """Get the application instance (for webhook mode)."""
        if not self.application:
            self.setup()
        return self.application
