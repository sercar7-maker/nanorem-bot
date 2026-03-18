import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

from database.db import SessionLocal
from database.models import Partner, PartnerStatus

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    telegram_id = str(user.id)
    username = user.username
    first_name = user.first_name

    code = context.args[0] if context.args else None

    session = SessionLocal()

    # -------------------------------------------------
    # ПРОВЕРЯЕМ: УЖЕ ПРИВЯЗАН?
    # -------------------------------------------------

    partner = session.query(Partner).filter(
        Partner.telegram_id == telegram_id
    ).first()

    if partner:
        text = "👋 Добро пожаловать обратно!"

    else:
        # -------------------------------------------------
        # ПРИВЯЗКА ПО КОДУ (ТОЛЬКО САЙТ СОЗДАЁТ ПАРТНЁРА)
        # -------------------------------------------------

        if code:
            partner = session.query(Partner).filter(
                Partner.telegram_link_code == code
            ).first()

            if partner:
                partner.telegram_id = telegram_id
                partner.username = username
                partner.first_name = first_name
                partner.status = PartnerStatus.ACTIVE

                session.commit()

                text = "✅ Telegram успешно привязан!"

            else:
                text = "❌ Неверный код. Зарегистрируйтесь на сайте."

        else:
            text = "❌ Вы не зарегистрированы. Пройдите регистрацию на сайте."

    session.close()

    # -------------------------------------------------
    # КНОПКИ
    # -------------------------------------------------

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
        f"""👋 Привет, {first_name}!

{text}

Выберите действие:""",
        reply_markup=reply_markup
    )


def get_handler():
    return CommandHandler("start", start_handler)