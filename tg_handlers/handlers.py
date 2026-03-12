import logging

from telegram.ext import MessageHandler, filters

from services.partner_service import PartnerService
from database.db import SessionLocal
from services.network_tree_service import NetworkTreeService
from services.network_turnover_service import NetworkTurnoverService

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

    # -------------------------------------------------
    # Баланс
    # -------------------------------------------------

    if text == "💰 Баланс":

        balance = partner_service.get_partner_balance(partner.id)

        await update.message.reply_text(
            f"Ваш баланс: {balance:.2f} ₽"
        )

    # -------------------------------------------------
    # Профиль
    # -------------------------------------------------

    elif text == "👤 Профиль":

        await update.message.reply_text(
            f"Партнёр ID: {partner.id}\n"
            f"Дата регистрации: {partner.registration_date}"
        )

    # -------------------------------------------------
    # Моя сеть
    # -------------------------------------------------

    elif text == "👥 Моя сеть":

        session = SessionLocal()

        tree_service = NetworkTreeService(session)

        partners = tree_service.get_direct_partners(partner.id)

        session.close()

        if not partners:

            await update.message.reply_text(
                "У вас пока нет партнёров."
            )
            return

        message = "👥 Ваши партнёры (1 уровень)\n\n"

        for p in partners:

            name = p["first_name"] or "Без имени"

            if p["username"]:
                name += f" (@{p['username']})"

            message += f"• {name}\n"

        await update.message.reply_text(message)

    # -------------------------------------------------
    # Реферальная ссылка
    # -------------------------------------------------

    elif text == "🔗 Реферальная ссылка":

        await update.message.reply_text(
            f"https://t.me/nanorem_bot?start={partner.telegram_link_code}"
        )

    # -------------------------------------------------
    # Статистика
    # -------------------------------------------------

    elif text == "📊 Статистика":

        stats = partner_service.get_partner_stats(partner.id)

        balance = partner_service.get_partner_balance(partner.id)

        session = SessionLocal()

        turnover_service = NetworkTurnoverService(session)

        monthly_personal = turnover_service.get_monthly_personal_turnover(partner.id)
        monthly_network = turnover_service.get_monthly_network_turnover(partner.id)

        session.close()

        message = (
            "📊 Ваша статистика\n\n"
            f"Партнёров в сети: {stats['partners']}\n"
            f"Всего комиссий: {stats['commission']:.2f} ₽\n"
            f"Ваш баланс: {balance:.2f} ₽\n\n"
            f"Личный оборот за месяц: {monthly_personal:.2f} ₽\n"
            f"Оборот сети за месяц: {monthly_network:.2f} ₽"
        )

        await update.message.reply_text(message)

    # -------------------------------------------------
    # Сайт
    # -------------------------------------------------

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