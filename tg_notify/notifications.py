import logging

logger = logging.getLogger(__name__)


async def notify_commission(telegram_id: int, amount: float, level: int, buyer_name: str):
    """
    Temporary stub for commission notification.
    Later this will send a Telegram message.
    """

    logger.info(
        f"Commission notification: partner={telegram_id}, "
        f"amount={amount}, level={level}, buyer={buyer_name}"
    )