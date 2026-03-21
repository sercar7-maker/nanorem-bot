"""Telegram notification helpers for NANOREM MLM Bot."""

import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self, bot: Bot):
        self.bot = bot

    # ----------------------------------------
    # 💰 Комиссия
    # ----------------------------------------
    async def notify_commission(
        self,
        telegram_id: int,
        amount: float,
        level: int,
        buyer_name: str
    ):
        if not telegram_id:
            return

        text = (
            f"💰 Новое начисление!\n\n"
            f"Сумма: +{amount:.2f} ₽\n"
            f"Уровень: {level}\n"
            f"От: {buyer_name}\n\n"
            f"Продолжайте развивать сеть 🚀"
        )

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text
            )
        except TelegramError as e:
            logger.error(f"Commission notify error: {e}")

    # ----------------------------------------
    # 👥 Новый партнёр
    # ----------------------------------------
    async def notify_new_referral(
        self,
        telegram_id: int,
        partner_name: str
    ):
        if not telegram_id:
            return

        text = (
            f"🎉 Новый партнёр!\n\n"
            f"{partner_name}"
        )

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text
            )
        except TelegramError as e:
            logger.error(f"Referral notify error: {e}")