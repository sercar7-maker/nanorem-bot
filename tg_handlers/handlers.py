import logging
import time
from telegram.ext import MessageHandler, CommandHandler, filters

from services.partner_service import PartnerService
from services.rank_service import RankService

from database.db import SessionLocal
from database.models import Partner

logger = logging.getLogger(__name__)

# 🔒 ЗАЩИТА ОТ ДВОЙНЫХ НАЖАТИЙ
_last_message_time = {}  # telegram_id -> timestamp
DEBOUNCE_SECONDS = 1.0   # минимальный интервал между обработками


def _should_skip(telegram_id: str) -> bool:
    """Проверяет, не пришло ли сообщение слишком быстро после предыдущего"""
    now = time.time()
    last = _last_message_time.get(telegram_id, 0)
    if now - last < DEBOUNCE_SECONDS:
        return True
    _last_message_time[telegram_id] = now
    return False


# -------------------------------------------------
# TEST ORDER
# -------------------------------------------------
async def test_order(update, context):
    print("TEST ORDER CALLED")

    telegram_id = str(update.effective_user.id)
    
    # Защита от двойных нажатий
    if _should_skip(telegram_id):
        print(f"⏭️ Skipped duplicate from {telegram_id}")
        return

    session = SessionLocal()

    try:
        # 👉 находим ТЕБЯ
        you = (
            session.query(Partner)
            .filter(Partner.telegram_id == telegram_id)
            .first()
        )

        if not you:
            await update.message.reply_text("Вы не зарегистрированы")
            return

        # 👉 находим любого партнёра ПОД ТОБОЙ
        partner = (
            session.query(Partner)
            .filter(Partner.upline_id == you.id)
            .first()
        )

        if not partner:
            await update.message.reply_text(
                "❌ Нет партнёров под вами для теста"
            )
            return

        from web.order_handler import OrderHandler
        from web.api_client import NanorvsAPIClient
        from core.commission import CommissionCalculator

        api_client = NanorvsAPIClient()
        calculator = CommissionCalculator(session, context.bot)
        handler = OrderHandler(api_client, calculator)

        order_data = {
            "id": "TEST123",
            "partner_id": partner.id,  # 🔥 ВАЖНО: НЕ ты
            "total_amount": 1000
        }

        success = await handler.process_order(order_data)

        if success:
            await update.message.reply_text(
                "🎉 Заказ от нижнего партнёра обработан"
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

    # 🔒 Защита от двойных нажатий
    if _should_skip(telegram_id):
        print(f"⏭️ Skipped duplicate button from {telegram_id}")
        return

    if text == "🌐 Сайт":
        await update.message.reply_text(
            "🌐 Перейдите для регистрации:\nhttps://nanorvs.ru/register"
        )
        return

    partner_service = PartnerService()
    session = SessionLocal()

    try:
        partner = partner_service.get_partner_by_telegram_id(telegram_id)

        if not partner:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы.\n\n"
                "Перейдите на сайт для регистрации:\n"
                "https://nanorvs.ru/register"
            )
            return

        if text == "💰 Баланс":
            balance = partner_service.get_partner_balance(partner.id)
            await update.message.reply_text(
                f"💰 Ваш баланс:\n\n{balance:.2f} ₽"
            )

        elif text == "👤 Профиль":
            rank_service = RankService(session)
            rank = rank_service.calculate_rank(partner.id)
            await update.message.reply_text(
                f"👤 Профиль\n\n"
                f"ID: {partner.id}\n"
                f"Дата регистрации: {partner.registration_date}\n"
                f"Ранг: {rank}"
            )

        elif text == "👥 Моя сеть":
            levels = partner_service.get_network_levels(partner.id)
            message = (
                "👥 Ваша сеть\n\n"
                f"1 уровень — {levels[1]}\n"
                f"2 уровень — {levels[2]}\n"
                f"3 уровень — {levels[3]}\n"
                f"4 уровень — {levels[4]}\n"
                f"5 уровень — {levels[5]}\n\n"
                f"Всего партнёров — {levels['total']}"
            )
            await update.message.reply_text(message)

        elif text == "🔗 Реферальная ссылка":
            link_code = partner.telegram_link_code
            message = (
                "🔗 Ваша ссылка\n\n"
                f"https://nanorvs.ru/register?ref={link_code}\n\n"
                "Приглашайте партнёров и зарабатывайте 💰"
            )
            await update.message.reply_text(message)

        elif text == "📊 Статистика":
            stats = partner_service.get_partner_stats(partner.id)
            balance = partner_service.get_partner_balance(partner.id)
            message = (
                "📊 Ваша статистика\n\n"
                "👥 Сеть\n"
                f"Партнёров: {stats['partners']}\n\n"
                "💰 Финансы\n"
                f"Комиссия: {stats['commission']:.2f} ₽\n"
                f"Баланс: {balance:.2f} ₽\n\n"
                "📦 Оборот\n"
                f"Личный: {stats['personal_turnover']:.2f} ₽\n"
                f"Сеть: {stats['network_turnover']:.2f} ₽"
            )
            await update.message.reply_text(message)

    finally:
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