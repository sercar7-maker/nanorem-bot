import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.db import SessionLocal
from database.models import Partner

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    telegram_id = user.id
    username = user.username or ""

    session = SessionLocal()

    partner = session.query(Partner).filter_by(id=telegram_id).first()

    if not partner:

        partner = Partner(
            id=telegram_id,
            username=username
        )

        session.add(partner)
        session.commit()

        text = "✅ Вы зарегистрированы в системе NANOREM MLM"

    else:

        text = "👋 С возвращением!"

    session.close()

    await update.message.reply_text(text)


def get_handler():
    return CommandHandler("start", start_command)