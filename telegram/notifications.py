"""Telegram notification helpers for NANOREM MLM Bot."""

import logging
from telegram import Bot
from telegram.error import TelegramError
from database.db import SessionLocal
from database.models import Partner, Commission
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

async def notify_commission(partner_telegram_id: int, amount: float, level: int, buyer_name: str) -> None:
    """Send a commission notification to a partner."""
    if not partner_telegram_id or not BOT_TOKEN:
        return
    
    msg = (
        f"💵 Новое начисление!

"
        f"Уровень: *{level}*
"
        f"Сумма: *+{amount:.2f}* руб.
"
        f"От: закупки партнёра {buyer_name}"
    )
    
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=partner_telegram_id,
            text=msg,
            parse_mode='Markdown'
        )
        logger.info(f"Commission notification sent to {partner_telegram_id}: +{amount:.2f} rub (level {level})")
    except TelegramError as e:
        logger.warning(f"Failed to notify {partner_telegram_id}: {e}")

async def notify_new_referral(upline_telegram_id: int, new_partner_name: str) -> None:
    """Notify an upline partner that a new partner registered via their link."""
    if not upline_telegram_id or not BOT_TOKEN:
        return
    
    msg = (
        f"🎉 Новый партнёр в вашей команде!

"
        f"По вашей реферальной ссылке зарегистрировался партнёр: *{new_partner_name}*"
    )
    
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=upline_telegram_id,
            text=msg,
            parse_mode='Markdown'
        )
        logger.info(f"New referral notification sent to {upline_telegram_id}")
    except TelegramError as e:
        logger.warning(f"Failed to notify upline {upline_telegram_id}: {e}")
