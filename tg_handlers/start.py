import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

from database.db import SessionLocal
from database.models import Partner

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    telegram_id = str(user.id)
    first_name = user.first_name

    start_code = None

    if context.args:
        start_code = context.args[0]

    session = SessionLocal()

    partner = session.query(Partner).filter(
        Partner.telegram_id == telegram_id
    ).first()

    if not partner and start_code:

        partner = session.query(Partner).filter(
            Partner.telegram_link_code == start_code
        ).first()

        if partner:
            partner.telegram_id = telegram_id
            session.commit()

            logger.info(f"Telegram linked to partner {partner.id}")

    session.close()

    text = f"""👋 Привет, {first_name}!

Добро пожаловать в систему партнёров NANOREM.
Выберите действие:"""

    keyboard = [
        ["👤 Профиль", "💰 Баланс"],
        ["👥 Моя сеть", "🔗 Реферальная ссылка"],
        ["📊 Статистика", "🌐 Сайт"]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        text,
        reply_markup=reply_markup
    )


def get_handler():
    return CommandHandler("start", start_handler)