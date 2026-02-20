"""Command handlers setup for NANOREM MLM Telegram Bot."""
import logging
import io
import qrcode
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from database.db import get_session
from database.models import Partner, Commission, Purchase, PartnerStatus
from sqlalchemy import func
from core.commission import CommissionCalculator
from core.subscription_manager import subscription_manager
from .notifications import notify_new_referral

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with referral support."""
    user = update.effective_user
    args = context.args

    ref_id = None
    if args and args[0].isdigit():
        ref_id = int(args[0])
        context.user_data['upline_id'] = ref_id
        logger.info(f"User {user.id} came from referral {ref_id}")

    message = (
        f"Привет, {user.first_name}! "
        "Добро пожаловать в систему NANOREM MLM.\n"
        "Используйте команду:\n"
        "/register - зарегистрироваться в системе\n"
        "/profile - мой личный кабинет\n"
        "/network - команда моя\n"
        "/purchase [сумма] - закупка (тест)\n"
        "/info - условия начислений\n"
        "/help - справка"
    )
    if ref_id:
        message += f"\n Вы приглашены ID партнёра: {ref_id}"
    await update.message.reply_text(message)


async def register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a new partner in the system."""
    user = update.effective_user
    upline_id = context.user_data.get('upline_id')

    with get_session() as session:
        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()
        if partner:
            await update.message.reply_text("Вы уже зарегистрированы!")
            return

        new_partner = Partner(
            telegram_id=str(user.id),
            first_name=user.first_name or "",
            last_name=user.last_name,
            username=user.username,
            upline_id=upline_id,
        )
        session.add(new_partner)

        if upline_id:
            await notify_new_referral(upline_id, user.first_name or user.username)

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"

    await update.message.reply_text(
        "🎉 Регистрация успешно завершена!\n"
        f"Ваша реферальная ссылка: `{ref_link}`",
        parse_mode='Markdown'
    )


async def purchase_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perform a manual purchase for testing."""
    user = update.effective_user
    if not context.args or not context.args[0].replace('.', '', 1).isdigit():
        await update.message.reply_text("Использование: /purchase [сумма]")
        return

    amount = float(context.args[0])

    with get_session() as session:
        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()
        if not partner:
            await update.message.reply_text("Сначала зарегистрируйтесь: /register")
            return

        import time
        purchase = Purchase(
            purchase_number=f"TEST-{user.id}-{int(time.time())}",
            partner_id=partner.id,
            amount=amount,
            status="paid"
        )
        session.add(purchase)
        session.flush()

        calculator = CommissionCalculator()
        commissions = calculator.calculate_commissions(partner.id, amount)

        for comm_data in commissions:
            new_comm = Commission(
                partner_id=comm_data['partner_id'],
                purchase_id=purchase.id,
                source_partner_id=partner.id,
                level=comm_data['level'],
                rate=comm_data['rate'],
                base_amount=amount,
                amount=comm_data['commission_amount']
            )
            session.add(new_comm)

            beneficiary = session.query(Partner).get(comm_data['partner_id'])
            if beneficiary:
                beneficiary.total_commissions += comm_data['commission_amount']

    await update.message.reply_text(
        f"✅ Закупка на {amount} руб. внесена! Комиссии распределены."
    )


async def network_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's referral network structure."""
    user = update.effective_user
    with get_session() as session:
        partner = session.query(Partner).filter(
            Partner.telegram_id == str(user.id)
        ).first()
        if not partner:
            await update.message.reply_text("Сначала зарегистрируйтесь: /register")
            return

        level_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        current_level_ids = [partner.id]

        for level in range(1, 6):
            next_level_partners = session.query(Partner).filter(
                Partner.upline_id.in_(current_level_ids)
            ).all()
            if not next_level_partners:
                break
            level_counts[level] = len(next_level_partners)
            current_level_ids = [p.id for p in next_level_partners]

        total_team = sum(level_counts.values())
        msg = (
            f"👥 *Ваша команда*\n"
            f"Всего партнёров: *{total_team}*\n"
            f"1 линия: *{level_counts[1]}*\n"
            f"2 линия: *{level_counts[2]}*\n"
            f"3 линия: *{level_counts[3]}*\n"
            f"4 линия: *{level_counts[4]}*\n"
            f"5 линия: *{level_counts[5]}*"
        )
    await update.message.reply_text(msg, parse_mode='Markdown')


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show partner profile, stats, subscription status, and referral QR code."""
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
            .scalar() or 0.0
        )
        personal_volume = (
            session.query(func.sum(Purchase.amount))
            .filter(Purchase.partner_id == partner.id)
            .scalar() or 0.0
        )

        # Subscription status
        is_active = partner.status == PartnerStatus.ACTIVE
        status_icon = "✅" if is_active else "❌"
        status_text = "Активен" if is_active else "Неактивен"

        # Days until expiry
        expiry_text = ""
        if is_active and partner.subscription_end_date:
            days_left = (partner.subscription_end_date - datetime.utcnow()).days
            if days_left > 0:
                expiry_text = f"\n⏳ Статус действует ещё: *{days_left}* дн."
            elif days_left == 0:
                expiry_text = "\n⚠️ Статус истекает сегодня!"
            else:
                expiry_text = "\n🔴 Статус истёк, требуется продление."

        partner_id_val = partner.telegram_id
        subscription_end = partner.subscription_end_date

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(ref_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Save to bytes
    bio = io.BytesIO()
    bio.name = 'referral_qr.png'
    img.save(bio, 'PNG')
    bio.seek(0)

    msg = (
        f"👤 *Ваш профиль*\n"
        f"🆔 ID: `{user.id}`\n"
        f"📊 Статус: {status_icon} {status_text}{expiry_text}\n"
        f"💰 Заработано: *{total_earned:.2f}* руб.\n"
        f"🛒 Личный оборот: *{personal_volume:.2f}* руб.\n"
        f"🔗 Ссылка: `{ref_link}`"
    )

    await update.message.reply_photo(
        photo=bio,
        caption=msg,
        parse_mode='Markdown'
    )


async def activate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate partner status for 30 days (admin command or test)."""
    user = update.effective_user
    success = subscription_manager.activate_status(str(user.id))
    if success:
        days_left = subscription_manager.get_days_until_expiry(str(user.id))
        await update.message.reply_text(
            f"✅ Ваш статус активирован на {days_left} дней!"
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось активировать статус. Сначала зарегистрируйтесь: /register"
        )


async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display marketing plan information."""
    msg = (
        "📊 *Маркетинг-план NANOREM*\n"
        "1 линия: *20%*\n"
        "2 линия: *10%*\n"
        "3-5 линии: *5%*\n"
        "💰 Начисления от суммы закупки материалов.\n"
        "⚡️ Система компрессии вверх."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


def setup_handlers(app: Application) -> None:
    """Register all command handlers."""
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("register", register_handler))
    app.add_handler(CommandHandler("purchase", purchase_handler))
    app.add_handler(CommandHandler("network", network_handler))
    app.add_handler(CommandHandler("profile", profile_handler))
    app.add_handler(CommandHandler("activate", activate_handler))
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(CommandHandler("help", start_handler))
