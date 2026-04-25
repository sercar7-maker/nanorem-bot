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

    # Извлекаем код из текста сообщения напрямую
    code = None
    if update.message and update.message.text:
        parts = update.message.text.strip().split()
        if len(parts) > 1:
            code = parts[1]

    session = SessionLocal()
    partner = None

    # -------------------------------------------------
    # ШАГ 1: ПРИВЯЗКА ПО КОДУ (если код передан)
    # -------------------------------------------------
    if code:
        partner = session.query(Partner).filter(
            Partner.telegram_link_code == code
        ).first()

        if partner:
            # Проверяем, не привязан ли уже этот код к другому Telegram
            if partner.telegram_id and partner.telegram_id != telegram_id:
                text = "❌ Этот код уже привязан к другому Telegram."
                session.close()
                await update.message.reply_text(text)
                return

            # Привязываем Telegram к партнёру
            partner.telegram_id = telegram_id
            partner.username = username
            partner.first_name = first_name
            partner.status = PartnerStatus.ACTIVE
            session.commit()

            text = "✅ Telegram успешно привязан!"
        else:
            text = "❌ Неверный код. Зарегистрируйтесь на сайте."
            session.close()
            await update.message.reply_text(text)
            return

    # -------------------------------------------------
    # ШАГ 2: ПРОВЕРЯЕМ, УЖЕ ПРИВЯЗАН?
    # -------------------------------------------------
    if not partner:
        partner = session.query(Partner).filter(
            Partner.telegram_id == telegram_id
        ).first()

        if partner:
            text = "👋 Добро пожаловать обратно!"
        else:
            text = (
                "❌ Вы не зарегистрированы.\n\n"
                "Перейдите на сайт для регистрации:\n"
                "https://nanorvs.ru/register"
            )

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
        f"👋 Привет, {first_name}!\n\n"
        f"{text}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )


def get_handler():
    return CommandHandler("start", start_handler)