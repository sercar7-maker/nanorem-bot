import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.db import SessionLocal
from database.models import Commission

logger = logging.getLogger(__name__)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    session = SessionLocal()

    commissions = session.query(Commission).filter_by(partner_id=user_id).all()

    balance = sum(c.amount for c in commissions)

    count = len(commissions)

    session.close()

    text = (
        f"💰 Ваш баланс: {balance}\n"
        f"📊 Всего комиссий: {count}"
    )

    await update.message.reply_text(text)


def get_handler():
    return CommandHandler("balance", balance_command)