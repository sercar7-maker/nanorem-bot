import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError

from core.security_tokens import is_telegram_binding_token_valid
from database.db import SessionLocal
from database.models import Partner

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

    try:
        if code:
            if not is_telegram_binding_token_valid(code):
                session.query(Partner).filter(
                    Partner.telegram_link_code == code,
                ).update(
                    {Partner.telegram_link_code: None},
                    synchronize_session=False,
                )
                session.commit()
                text = "❌ Срок действия кода истёк. Запросите новую ссылку."
            else:
                existing_binding = session.query(Partner).filter(
                    Partner.telegram_id == telegram_id,
                ).first()

                if existing_binding:
                    text = "❌ Этот Telegram уже привязан к аккаунту."
                else:
                    result = session.execute(
                        sql_update(Partner)
                        .where(
                            Partner.telegram_link_code == code,
                            Partner.telegram_id.is_(None),
                        )
                        .values(
                            telegram_id=telegram_id,
                            telegram_link_code=None,
                            username=username,
                            first_name=first_name,
                        )
                    )

                    if result.rowcount != 1:
                        session.rollback()
                        text = "❌ Код неверный, истёк или уже использован."
                    else:
                        try:
                            session.commit()
                            text = "✅ Telegram успешно привязан!"
                        except IntegrityError:
                            session.rollback()
                            text = "❌ Этот Telegram уже привязан к аккаунту."
        else:
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
    finally:
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