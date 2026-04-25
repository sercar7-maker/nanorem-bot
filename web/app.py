from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import random
import string
import asyncio
import logging
from datetime import datetime

from telegram import Bot, Update
from telegram.ext import Application

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT
from database.db import get_session, SessionLocal
from database.models import Partner, PartnerStatus

# MLM imports
from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator

# уведомления
from services.notifications import NotificationService

# Telegram handlers
from tg_handlers.handlers import setup_handlers

# Роутер для заказов (старый, пока оставлен для совместимости)
from web import order_handler as order_router

# Обработчик заказов WooCommerce
from services.order_processor import OrderProcessor

logger = logging.getLogger(__name__)

app = FastAPI()

# Подключаем роутер из order_handler (старые API-эндпоинты)
app.include_router(order_router.router)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Инициализация Telegram бота
telegram_app = Application.builder().token(BOT_TOKEN).build()
setup_handlers(telegram_app)


def generate_link_code():
    return "".join(random.choices(string.digits, k=6))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "ref": None}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, ref: int | None = None):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "ref": ref}
    )


@app.post("/register", response_class=HTMLResponse)
async def register_user(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    ref: str | None = Form(None),
    consent: str | None = Form(None)
):
    link_code = generate_link_code()

    # Проверяем, что согласие дано
    consent_given = consent is not None and consent.lower() == "on"

    # Правильно обрабатываем ref: если пустой или "None", то upline_id = None
    upline_id = None
    if ref and ref != "None" and ref.strip():
        try:
            upline_id = int(ref)
        except ValueError:
            pass  # Оставляем None, если не число

    # Используем PartnerService для создания с учётом авто-распределения
    from services.partner_service import PartnerService
    partner_service = PartnerService()
    
    new_partner = partner_service.create_partner(
        telegram_id=None,  # будет привязан позже
        upline_id=upline_id  # None → сработает авто-распределение
    )

    # Обновляем данные партнёра
    with get_session() as session:
        partner = session.query(Partner).filter(Partner.id == new_partner.id).first()
        if partner:
            partner.telegram_link_code = link_code
            partner.first_name = first_name
            partner.last_name = last_name
            partner.email = email
            partner.phone = phone
            partner.consent_given = consent_given
            partner.consent_version = "v.1.0 21.04.2026"
            partner.consent_date = datetime.utcnow() if consent_given else None
            session.commit()
            session.refresh(partner)

            # Уведомление рефереру
            if upline_id:
                upline = session.query(Partner).filter(Partner.id == upline_id).first()
                if upline and upline.telegram_id:
                    full_name = f"{first_name} {last_name}"
                    try:
                        asyncio.create_task(
                            notification_service.notify_new_referral(
                                telegram_id=int(upline.telegram_id),
                                partner_name=full_name
                            )
                        )
                    except Exception as e:
                        print(f"Notify error: {e}")

    return HTMLResponse(f"""
    <html>
    <head>
        <title>Регистрация завершена</title>
    </head>

    <body style="font-family:Arial;text-align:center;margin-top:60px;">

        <h2>Регистрация завершена</h2>

        <p>Ваш аккаунт создан.</p>

        <p><b>Нажмите кнопку чтобы привязать Telegram:</b></p>

        <br>

        <a href="https://t.me/nanorem_bot?start={link_code}">
            <button style="
                font-size:20px;
                padding:15px 30px;
                background:#2AABEE;
                color:white;
                border:none;
                border-radius:8px;
                cursor:pointer;
            ">
                Открыть Telegram и активировать
            </button>
        </a>

        <br><br>

        <p>Если кнопка не работает:</p>

        <pre>https://t.me/nanorem_bot?start={link_code}</pre>

    </body>
    </html>
    """)


# Инициализация клиентов
api_client = NanorvsAPIClient()
web_db = SessionLocal()
web_bot = Bot(token=BOT_TOKEN)
notification_service = NotificationService(web_bot)
calculator = CommissionCalculator(web_db, web_bot)
order_processor = OrderProcessor(api_client)


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    """Webhook для приёма заказов от WooCommerce (nanorvs.ru)."""
    try:
        payload = await request.json()
        logger.info(f"Received WooCommerce webhook: event={payload.get('event', 'unknown')}")

        # Обрабатываем заказ через OrderProcessor
        success = order_processor.process_webhook(payload)

        if success:
            return {"success": True, "message": "Order processed successfully"}
        else:
            logger.error("Failed to process webhook order")
            return {"success": False, "message": "Order processing failed"}

    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return {"success": False, "error": str(e)}


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Webhook для Telegram Bot API"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, telegram_app.bot)
        
        await telegram_app.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"status": "error", "detail": str(e)}


@app.on_event("startup")
async def on_startup():
    """Устанавливаем вебхук при запуске сервера"""
    await telegram_app.initialize()
    
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        await telegram_app.bot.set_webhook(url=webhook_url)
        logger.info(f"Telegram webhook set to: {webhook_url}")
    else:
        logger.warning("WEBHOOK_URL not set, Telegram webhook not configured")


@app.on_event("shutdown")
async def on_shutdown():
    """Удаляем вебхук при остановке"""
    await telegram_app.bot.delete_webhook()
    await telegram_app.shutdown()
    web_db.close()