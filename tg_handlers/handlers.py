import logging
from telegram.ext import MessageHandler, filters

from services.partner_service import PartnerService

logger = logging.getLogger(__name__)


async def button_handler(update, context):

    text = update.message.text
    telegram_id = str(update.effective_user.id)

    partner_service = PartnerService()

    partner = partner_service.get_partner_by_telegram_id(telegram_id)

    if not partner:
        await update.message.reply_text(
            "Вы не зарегистрированы как партнёр."
        )
        return

    if text == "💰 Баланс":

        balance = partner_service.get_partner_balance(partner.id)

        await update.message.reply_text(
            f"Ваш баланс: {balance:.2f} ₽"
        )

    elif text == "👤 Профиль":

        await update.message.reply_text(
            f"Партнёр ID: {partner.id}\n"
            f"Дата регистрации: {partner.registration_date}"
        )

    elif text == "👥 Моя сеть":

        levels = partner_service.get_network_levels(partner.id)

        message = (
            "👥 Ваша сеть\n\n"
            f"1 уровень — {levels[1]} партнёров\n"
            f"2 уровень — {levels[2]} партнёров\n"
            f"3 уровень — {levels[3]} партнёров\n"
            f"4 уровень — {levels[4]} партнёров\n"
            f"5 уровень — {levels[5]} партнёров\n\n"
            f"Всего партнёров — {levels['total']}"
        )

        await update.message.reply_text(message)

    elif text == "🔗 Реферальная ссылка":

        await update.message.reply_text(
            f"https://t.me/nanorem_bot?start={partner.telegram_link_code}"
        )

    elif text == "📊 Статистика":

        stats = partner_service.get_partner_stats(partner.id)
        balance = partner_service.get_partner_balance(partner.id)

        message = (
            "📊 Ваша статистика\n\n"
            f"Партнёров в сети: {stats['partners']}\n"
            f"Всего комиссий: {stats['commission']:.2f} ₽\n"
            f"Ваш баланс: {balance:.2f} ₽"
        )

        await update.message.reply_text(message)

    elif text == "🌐 Сайт":

        await update.message.reply_text(
            "https://nanorvs.ru"
        )


def setup_handlers(application):

    logger.info("Registering Telegram handlers")

    from tg_handlers.start import get_handler as start_handler
    from tg_handlers.balance import get_handler as balance_handler

    application.add_handler(start_handler())
    application.add_handler(balance_handler())

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler)
    )