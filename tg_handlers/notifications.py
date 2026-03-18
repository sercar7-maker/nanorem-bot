"""Telegram notification helpers for NANOREM MLM Bot."""

import logging
from telegram import Bot
from telegram.error import TelegramError

from database.db import get_session
from database.models import Partner
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

# 🔥 создаём ОДИН bot (важно!)
bot = Bot(token=BOT_TOKEN)


# -------------------------------------------------
# Комиссия
# -------------------------------------------------

async def notify_commission(partner_telegram_id: int, amount: float, level: int, buyer_name: str) -> None:

    if not partner_telegram_id:
        return

    msg = (
        f"💵 Новое начисление!\n\n"
        f"Уровень: {level}\n"
        f"Сумма: +{amount:.2f} руб.\n"
        f"От: {buyer_name}"
    )

    try:
        await bot.send_message(
            chat_id=partner_telegram_id,
            text=msg
        )
        logger.info(f"Commission sent → {partner_telegram_id}")

    except TelegramError as e:
        logger.warning(f"Notify error: {e}")


# -------------------------------------------------
# Новый партнёр
# -------------------------------------------------

async def notify_new_referral(upline_telegram_id: int, new_partner_name: str) -> None:

    if not upline_telegram_id:
        return

    msg = (
        f"🎉 Новый партнёр!\n\n"
        f"{new_partner_name} зарегистрировался по вашей ссылке"
    )

    try:
        await bot.send_message(
            chat_id=upline_telegram_id,
            text=msg
        )
        logger.info(f"Referral notify → {upline_telegram_id}")

    except TelegramError as e:
        logger.warning(f"Notify error: {e}")


# -------------------------------------------------
# Повышение ранга
# -------------------------------------------------

async def notify_rank_up(partner_telegram_id: int, new_rank: str) -> None:

    if not partner_telegram_id:
        return

    msg = (
        f"🎉 Поздравляем!\n\n"
        f"Ваш новый ранг: {new_rank}\n\n"
        f"Так держать 🚀"
    )

    try:
        await bot.send_message(
            chat_id=partner_telegram_id,
            text=msg
        )
        logger.info(f"Rank notify → {partner_telegram_id}")

    except TelegramError as e:
        logger.warning(f"Notify error: {e}")