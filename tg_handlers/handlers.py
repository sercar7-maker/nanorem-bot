import logging
import uuid

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from sqlalchemy import func

from database.db import get_session
from database.models import Partner, Commission, Purchase, PartnerStatus

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    args = context.args

    with get_session() as session:

        # Проверяем существует ли партнёр
        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()

        # Если партнёра нет — создаём
        if not partner:

            upline_id = None

            # если есть реферальный параметр
            if args:
                try:
                    upline_id = int(args[0])
                except:
                    upline_id = None

            partner = Partner(
                telegram_id=str(user.id),
                first_name=user.first_name or "",
                username=user.username,
                upline_id=upline_id,
                status=PartnerStatus.ACTIVE
            )

            session.add(partner)
            session.commit()

        msg = (
            f"Привет, {user.first_name}!\n\n"
            "Добро пожаловать в систему NANOREM.\n\n"
            "Выберите действие из меню."
        )

    keyboard = [
        ["👤 Профиль", "💰 Баланс"],
        ["🛒 Закупка", "🌐 Сеть"],
        ["👥 Пригласить партнёра"]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(msg, reply_markup=reply_markup)


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        user = update.effective_user

        with get_session() as session:

            partner = session.query(Partner).filter(
                Partner.telegram_id == str(user.id)
            ).first()

            if not partner:
                await update.message.reply_text("Вы не зарегистрированы.")
                return

            partner_id = partner.id

            total_earned = (
                session.query(func.sum(Commission.amount))
                .filter(Commission.partner_id == partner_id)
                .scalar() or 0
            )

            personal_volume = (
                session.query(func.sum(Purchase.amount))
                .filter(Purchase.partner_id == partner_id)
                .scalar() or 0
            )

            status = "Активен" if partner.status == PartnerStatus.ACTIVE else "Неактивен"

        msg = (
            f"👤 Ваш профиль\n\n"
            f"🆔 ID: {user.id}\n"
            f"📊 Статус: {status}\n\n"
            f"💰 Баланс: {total_earned:.2f} руб\n"
            f"💰 Всего заработано: {total_earned:.2f} руб\n"
            f"🛒 Личный оборот: {personal_volume:.2f} руб\n\n"
            f"🔗 Ваша реферальная ссылка:\n"
            f"https://t.me/nanorem_bot?start={partner_id}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        logger.exception("Ошибка в profile_handler")
        await update.message.reply_text(f"Ошибка профиля: {e}")


async def purchase_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not context.args:
        await update.message.reply_text("Использование: /purchase 1000")
        return

    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Введите число.")
        return

    with get_session() as session:

        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()

        if not partner:
            await update.message.reply_text("Вы не зарегистрированы.")
            return

        purchase = Purchase(
            purchase_number=f"PUR-{uuid.uuid4().hex[:8]}",
            partner_id=partner.id,
            amount=amount,
            currency="RUB",
            status="PENDING"
        )

        session.add(purchase)
        session.commit()

    await update.message.reply_text(
        f"Закупка зарегистрирована: {amount:.2f} руб"
    )


async def network_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    with get_session() as session:

        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()

        if not partner:
            await update.message.reply_text("Вы не зарегистрированы.")
            return

        # 1 линия
        line1_ids = session.query(Partner.id).filter(
            Partner.upline_id == partner.id
        ).all()
        line1_count = len(line1_ids)

        # 2 линия
        line1_list = [p[0] for p in line1_ids]
        line2_ids = []

        if line1_list:
            line2_ids = session.query(Partner.id).filter(
                Partner.upline_id.in_(line1_list)
            ).all()

        line2_count = len(line2_ids)

        # 3 линия
        line2_list = [p[0] for p in line2_ids]
        line3_count = 0

        if line2_list:
            line3_count = session.query(Partner).filter(
                Partner.upline_id.in_(line2_list)
            ).count()

        total = line1_count + line2_count + line3_count

    msg = (
        f"🌐 Ваша сеть\n\n"
        f"👥 1 линия: {line1_count}\n"
        f"👥 2 линия: {line2_count}\n"
        f"👥 3 линия: {line3_count}\n\n"
        f"📊 Всего партнёров: {total}"
    )

    await update.message.reply_text(msg)


async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    with get_session() as session:

        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()

        if not partner:
            await update.message.reply_text("Вы не зарегистрированы.")
            return

        total_earned = (
            session.query(func.sum(Commission.amount))
            .filter(Commission.partner_id == partner.id)
            .scalar() or 0
        )

    msg = (
        f"💰 Ваш баланс\n\n"
        f"💵 Доступный баланс: {total_earned:.2f} руб"
    )

    await update.message.reply_text(msg)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.debug(f"button_handler received text: '{text}'")

    # Normalize whitespace and case
    if not text:
        await update.message.reply_text("Пустой текст получен.")
        return

    normalized = text.strip()

    if normalized == "👤 Профиль":
        await profile_handler(update, context)
    elif normalized == "💰 Баланс":
        await balance_handler(update, context)
    elif normalized == "🛒 Закупка":
        await update.message.reply_text("Используйте команду: /purchase [сумма]")
    elif normalized == "🌐 Сеть":
        await network_handler(update, context)
    elif normalized == "👥 Пригласить партнёра":
        user = update.effective_user

        with get_session() as session:
            partner = session.query(Partner).filter(
                Partner.telegram_id == str(user.id)
            ).first()

            if not partner:
                await update.message.reply_text("Вы не зарегистрированы.")
                return

            link = f"https://t.me/nanorem_bot?start={partner.id}"

        invite_msg = (
            "👥 Приглашение партнёров\n\n"
            "Ваша реферальная ссылка:\n"
            f"{link}\n\n"
            "Отправьте её партнёру для регистрации."
        )

        await update.message.reply_text(invite_msg)

    else:
        return


def setup_handlers(app: Application):

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("profile", profile_handler))
    app.add_handler(CommandHandler("purchase", purchase_handler))
    app.add_handler(CommandHandler("network", network_handler))
    app.add_handler(CommandHandler("balance", balance_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    
    logger.info("Handlers registered")