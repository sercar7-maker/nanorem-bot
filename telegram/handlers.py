"""Command handlers setup for NANOREM MLM Telegram Bot."""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    message = (
        f"Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в NANOREM MLM систему.\n\n"
        f"Команды:\n"
        f"/help - справка\n"
        f"/profile - мой профиль\n"
        f"/register - зарегистрироваться партнёром"
    )
    await update.message.reply_text(message)
    logger.info(f"User {user.id} started bot")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    message = (
        "Доступные команды:\n\n"
        "/start - начало\n"
        "/help - справка\n"
        "/profile - мой профиль\n"
        "/register - зарегистрироваться партнёром\n\n"
        "Для помощи свяжитесь с поддержкой."
    )
    await update.message.reply_text(message)


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile command."""
    user = update.effective_user
    message = (
        f"Ваш профиль:\n\n"
        f"ID: {user.id}\n"
        f"Имя: {user.first_name} {user.last_name or ''}\n"
        f"Username: @{user.username or 'не указан'}\n"
        f"\nДополнительная информация скоро..."
    )
    await update.message.reply_text(message)


def setup_handlers(app: Application) -> None:
    """Setup all command and message handlers."""
    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("profile", profile_handler))
    
    logger.info("Handlers registered successfully")
