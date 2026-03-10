import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

from database.db import SessionLocal
from database.models import Partner, PartnerStatus

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    telegram_id = user.id
    username = user.username or ""

    # код из /start CODE
    code = None
    if context.args:
        code = context.args[0]

    session = SessionLocal()

    # если код есть — пытаемся привязать Telegram
    if code:

        partner = session.query(Partner).filter_by(telegram_link_code=code).first()

        if partner:

            partner.telegram_id = telegram_id
            partner.username = username
            partner.status = PartnerStatus.ACTIVE

            session.commit()

            text = "✅ Telegram успешно привязан к вашему аккаунту!"

        else:

            text = "❌ Неверный код привязки."

    else:

        # пользователь просто написал /start
        partner = session.query(Partner).filter_by(telegram_id=telegram_id).first()

        if partner:

            text = "👋 Добро пожаловать в NANOREM MLM"

        else:

            text = "Вы не зарегистрированы. Зарегистрируйтесь на сайте."

    session.close()

    # КНОПКИ МЕНЮ
    keyboard = [
        ["💰 Баланс", "👥 Моя сеть"],
        ["🔗 Реферальная ссылка", "📊 Статистика"]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(text, reply_markup=reply_markup)


def get_handler():
    return CommandHandler("start", start_command)