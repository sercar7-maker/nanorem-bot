"""Main Telegram Bot class for NANOREM MLM System."""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN
from database.db import DatabaseManager
from core.partner_manager import PartnerManager
from core.commission import CommissionCalculator
from integrations.cash_register import CashRegister

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class for handling Telegram interactions."""
    
    def __init__(self):
        """Initialize bot with database and business logic components."""
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.db_manager = DatabaseManager()
        self.partner_manager = PartnerManager(self.db_manager)
        self.commission_calculator = CommissionCalculator()
        self.cash_register = CashRegister()
        logger.info("TelegramBot initialized")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        await update.message.reply_text(
            f"Добро пожаловать, {user.first_name}!\n\n"
            "Это система управления MLM бизнесом NANOREM.\n"
            "Используйте /help для списка доступных команд."
        )
        logger.info(f"User {user.id} started bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "Доступные команды:\n\n"
            "/start - Начать работу\n"
            "/help - Показать эту справку\n"
            "/register - Регистрация партнёра\n"
            "/profile - Мой профиль\n"
            "/network - Моя структура\n"
            "/sales - Продажи и комиссии\n"
            "/receipt - Создать чек"
        )
        await update.message.reply_text(help_text)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in bot."""
        logger.error(f"Update {update} caused error {context.error}")
        if update and update.message:
            await update.message.reply_text(
                "Произошла ошибка. Пожалуйста, попробуйте позже."
            )
    
    def run(self):
        """Start the bot."""
        logger.info("Starting bot...")
        self.app.run_polling()
        logger.info("Bot stopped")
