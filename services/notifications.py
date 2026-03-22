"""Telegram notification helpers for NANOREM MLM Bot."""

import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_commission(
        self,
        telegram_id: int,
        amount: float,
        level: int,
        buyer_name: str
    ) -> None:
        if not telegram_id:
            return

        msg = (
            f"💵 Новое начисление!\n\n"
            f"Уровень: {level}\n"
            f"Сумма: +{amount:.2f} руб.\n"
            f"От: {buyer_name}"
        )

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=msg
            )
            logger.info(f"Commission sent → {telegram_id}")
        except TelegramError as e:
            logger.warning(f"Notify error: {e}")

    async def notify_new_referral(
        self,
        telegram_id: int,
        partner_name: str
    ) -> None:
        if not telegram_id:
            return

        msg = (
            f"🎉 Новый партнёр!\n\n"
            f"{partner_name} зарегистрировался по вашей ссылке"
        )

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=msg
            )
            logger.info(f"Referral notify → {telegram_id}")
        except TelegramError as e:
            logger.warning(f"Notify error: {e}")

    async def notify_rank_up(
        self,
        telegram_id: int,
        new_rank: str
    ) -> None:
        if not telegram_id:
            return

        msg = (
            f"🎉 Поздравляем!\n\n"
            f"Ваш новый ранг: {new_rank}\n\n"
            f"Так держать 🚀"
        )

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=msg
            )
            logger.info(f"Rank notify → {telegram_id}")
        except TelegramError as e:
            logger.warning(f"Notify error: {e}")