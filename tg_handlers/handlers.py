import logging
from telegram.ext import MessageHandler, CommandHandler, filters

from services.partner_service import PartnerService
from services.rank_service import RankService
from services.stats_service import StatsService
from core.commission import CommissionCalculator

from database.db import SessionLocal
from database.models import Partner, Purchase

logger = logging.getLogger(__name__)


# -------------------------------------------------
# TEST ORDER (🔥 главный тест системы)
# -------------------------------------------------

async def test_order(update, context):

    print("TEST ORDER CALLED")

    await update.message.reply_text("⏳ Обрабатываю заказ...")

    session = SessionLocal()
    telegram_id = str(update.effective_user.id)

    partner = (
        session.query(Partner)
        .filter(Partner.telegram_id == telegram_id)
        .first()
    )

    if not partner:
        print("PARTNER NOT FOUND")
        await update.message.reply_text("❌ Вы не зарегистрированы")
        session.close()
        return

    try:
        # создаём тестовый заказ
        purchase = Purchase(
            purchase_number="TEST123",
            partner_id=partner.id,
            amount=1000,
            status="paid",
            ext_ref="TEST123"
        )

        session.add(purchase)
        session.commit()
        session.refresh(purchase)

        # комиссии
        calculator = CommissionCalculator(session)
        await calculator.process_purchase(purchase)

        # статистика
        stats_service = StatsService(session)
        stats_service.process_purchase(partner.id, 1000)

        # ранги
        rank_service = RankService(session)
        await rank_service.process_rank(partner)

        await update.message.reply_text("✅ Тестовый заказ обработан")

    except Exception as e:
        print(f"TEST ORDER ERROR: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
            f"Дата регистрации: {partner.registration_date}\n"
            f"Ранг: {partner.rank}"
        )

    # -------------------------------------------------
    # Сеть
    # -------------------------------------------------
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

        message = (
            "📊 Ваша статистика\n\n"
            f"Партнёров в сети: {stats['partners']}\n"
            f"Всего комиссий: {stats['commission']:.2f} ₽\n"
            f"Ваш баланс: {balance:.2f} ₽\n\n"
            f"Личный оборот за месяц: {stats['personal_turnover']:.2f} ₽\n"
            f"Оборот сети за месяц: {stats['network_turnover']:.2f} ₽"
        )

        await update.message.reply_text(message)

    # -------------------------------------------------
    # Сайт
    # -------------------------------------------------
    elif text == "🌐 Сайт":

        await update.message.reply_text(
            "https://nanorvs.ru"
        )

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