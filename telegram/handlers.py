"""Command handlers setup for NANOREM MLM Telegram Bot."""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from database.db import SessionLocal
from database.models import Partner, Commission, Purchase
from sqlalchemy import func

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with referral support."""
    user = update.effective_user
    args = context.args
    
    # Check for referral ID in command arguments
    ref_id = None
    if args and args[0].isdigit():
        ref_id = int(args[0])
        context.user_data['upline_id'] = ref_id
        logger.info(f"User {user.id} came from referral {ref_id}")

    message = (
        f"Привет, {user.first_name}!

"
        "Добро пожаловать в NANOREM MLM систему.

"
        "Используйте команды:
"
        "/register - зарегистрироваться в системе
"
        "/profile - мой личный кабинет
"
        "/info - условия начислений
"
        "/help - справка"
    )
    
    if ref_id:
        message += f"

Вы приглашены партнером ID: {ref_id}"
        
    await update.message.reply_text(message)

async def register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a new partner in the system."""
    user = update.effective_user
    upline_id = context.user_data.get('upline_id')
    
    with SessionLocal() as session:
        # Check if already registered
        partner = session.query(Partner).filter(Partner.telegram_id == user.id).first()
        if partner:
            await update.message.reply_text("Вы уже зарегистрированы в системе!")
            return
            
        # Create new partner
        new_partner = Partner(
            telegram_id=user.id,
            username=user.username,
            upline_id=upline_id,
            is_active=True # Default active for demo
        )
        session.add(new_partner)
        session.commit()
        
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        
        await update.message.reply_text(
            "🎉 Регистрация успешно завершена!

"
            f"Ваша реферальная ссылка для приглашений:
`{ref_link}`",
            parse_mode='Markdown'
        )
        logger.info(f"New partner registered: {user.id} (upline: {upline_id})")

async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show partner's profile and statistics."""
    user = update.effective_user
    
    with SessionLocal() as session:
        partner = session.query(Partner).filter(Partner.telegram_id == user.id).first()
        if not partner:
            await update.message.reply_text("Вы не зарегистрированы. Используйте /register")
            return
            
        # Aggregate statistics
        total_earned = session.query(func.sum(Commission.amount)).filter(Commission.partner_id == partner.id).scalar() or 0.0
        personal_volume = session.query(func.sum(Purchase.amount)).filter(Purchase.partner_id == partner.id).scalar() or 0.0
        direct_referrals = session.query(Partner).filter(Partner.upline_id == user.id).count()
        
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        
        status_emoji = "✅" if partner.is_active else "❌"
        
        msg = (
            f"👤 *Ваш профиль*

"
            f"🆔 Telegram ID: `{user.id}`
"
            f"📊 Статус: {status_emoji} {'Активен' if partner.is_active else 'Неактивен'}

"
            f"💰 Заработано комиссий: *{total_earned:.2f}* руб.
"
            f"🛒 Личный оборот: *{personal_volume:.2f}* руб.
"
            f"👥 Партнеров в 1 линии: *{direct_referrals}*

"
            f"🔗 Реферальная ссылка:
`{ref_link}`"
        )
        
        await update.message.reply_text(msg, parse_mode='Markdown')

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display marketing plan information."""
    msg = (
        "📊 *Маркетинг-план NANOREM*

"
        "Система начислений с 5 уровней:

"
        "1 уровень: *20%*
"
        "2 уровень: *10%*
"
        "3 уровень: *5%*
"
        "4 уровень: *5%*
"
        "5 уровень: *5%*

"
        "💰 *База начисления:* сумма закупки материалов.

"
        "⚡️ *Компрессия:* если ваш прямой аплайн не активен, "
        "его комиссия передается выше по ветке, чтобы цепочка не прерывалась."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

def setup_handlers(app: Application) -> None:
    """Register all command handlers with the application."""
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("register", register_handler))
    app.add_handler(CommandHandler("profile", profile_handler))
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(CommandHandler("help", start_handler))
    
    logger.info("Telegram handlers updated and registered.")
