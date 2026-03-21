import logging
from telegram.ext import MessageHandler, CommandHandler, filters

from services.partner_service import PartnerService
from services.rank_service import RankService

from database.db import SessionLocal
from database.models import Partner

logger = logging.getLogger(__name__)


# -------------------------------------------------
# TEST ORDER
# -------------------------------------------------
async def test_order(update, context):
    print("TEST ORDER CALLED")

    session = SessionLocal()
    telegram_id = str(update.effective_user.id)

    try:
        partner = (
            session.query(Partner)
            .filter(Partner.telegram_id == telegram_id)
            .first()
        )

        if not partner:
            await update.message.reply_text("Вы не зарегистрированы")
            return

        from web.order_handler import OrderHandler
        from web.api_client import NanorvsAPIClient
        from core.commission import CommissionCalculator

        api_client = NanorvsAPIClient()
        calculator = CommissionCalculator(session, context.bot)
        handler = OrderHandler(api_client, calculator)

        order_data = {
            "id": "TEST123",
            "partner_id": partner.id,
            "total_amount": 1000
        }

        success = await handler.process_order(order_data)

        if success:
            await update.message.reply_text(
                "🎉 Новый человек успешно подписался и тестовый заказ обработан"
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при обработке тестового заказа"
            )

    finally:
        session.close()


# -------------------------------------------------
# BUTTON HANDLER
# -------------------------------------------------
async def button_handler(update, context):
    text = update.message.text
    telegram_id = str(update.effective_user.id)

    partner_service = PartnerService()
    session = SessionLocal()

    partner = partner_service.get_partner_by_telegram_id(telegram_id)

    if not partner:
        await update.message.reply_text(
            "Вы не зарегистрированы как партнёр."
        )
        session.close()
        return

    if text == "💰 Баланс":
        balance = partner_service.get_partner_balance(partner.id)

        await update.message.reply_text(
            f"Ваш баланс: {balance:.2f} ₽"
        )

    elif text == "👤 Профиль":
        rank_service = RankService(session)
        rank = rank_service.calculate_rank(partner.id)

        await update.message.reply_text(
            f"Партнёр ID: {partner.id}\n"
            f"Дата регистрации: {partner.registration_date}\n"
            f"Ранг: {rank}"
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
        link_code = partner.telegram_link_code

        message = (
            "🔗 Ваша реферальная ссылка:\n\n"
            f"https://nanorvs.ru/register?ref={link_code}\n\n"
            "Приглашайте партнёров и зарабатывайте 💰"
        )

        await update.message.reply_text(message)

    elif text == "📊 Статистика":
        stats = partner_service.get_partner_stats(partner.id)
        balance = partner_service.get_partner_balance(partner.id)

        message = (
            "📊 Ваша статистика\n\n"
            f"Партнёров в сети: {stats['partners']}\n"
            f"Всего комиссий: {stats['commission']:.2f} ₽\n"
            f"Ваш баланс: {balance:.2f} ₽\n\n"
            f"Личный оборот за месяц: {stats['personal_turnover']:.2f} ₽\n"
            f"Оборот сети за месяц: {stats['network_turnover']:.2f} ₽"
        )

        await update.message.reply_text(message)

    elif text == "🌐 Сайт":
        await update.message.reply_text("https://nanorvs.ru")

    session.close()


# -------------------------------------------------
# SETUP
# -------------------------------------------------
def setup_handlers(application):
    logger.info("Registering Telegram handlers")

    from tg_handlers.start import get_handler as start_handler
    from tg_handlers.balance import get_handler as balance_handler

    application.add_handler(start_handler())
    application.add_handler(balance_handler())

    application.add_handler(CommandHandler("test_order", test_order))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler)
    )