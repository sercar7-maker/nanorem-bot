import base64
import hashlib
import hmac
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError

from telegram import Bot, Update
from telegram.ext import Application

from config import (
    BOT_TOKEN,
    WEBHOOK_URL,
    WOOCOMMERCE_WEBHOOK_SECRET,
    TELEGRAM_WEBHOOK_SECRET,
)

from database.db import get_session, SessionLocal, init_db
from database.models import Partner

from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from core.security_tokens import create_telegram_binding_token
from services.notifications import NotificationService
from tg_handlers.handlers import setup_handlers
from services.order_processor import (
    OrderProcessor,
    RootPairNotReadyError,
)
from scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


app = FastAPI()


BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


# ---------------------------------------------------------
# Telegram
# ---------------------------------------------------------

telegram_app = (
    Application
    .builder()
    .token(BOT_TOKEN)
    .build()
)

setup_handlers(telegram_app)


# ---------------------------------------------------------
# Вспомогательные объекты
# ---------------------------------------------------------

api_client = NanorvsAPIClient()

web_bot = Bot(
    token=BOT_TOKEN
)

notification_service = NotificationService(
    web_bot
)

calculator = None

order_processor = OrderProcessor(
    api_client
)


# ---------------------------------------------------------
# Регистрация
# ---------------------------------------------------------

@app.get(
    "/",
    response_class=HTMLResponse,
)
async def home(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "request": request,
            "ref": None,
        },
    )


@app.get(
    "/register",
    response_class=HTMLResponse,
)
async def register_page(
    request: Request,
    ref: str | None = None,
):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "request": request,
            "ref": ref,
        },
    )


@app.post(
    "/register",
    response_class=HTMLResponse,
)
async def register_user(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    ref: str | None = Form(None),
    consent: str | None = Form(None),
):
    if consent is None or consent.lower() != "on":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent is required",
        )

    binding_token = create_telegram_binding_token()
    upline_id = None

    if ref and ref != "None" and ref.strip():
        with get_session() as session:
            upline_id = session.query(Partner.id).filter(
                Partner.referral_code == ref.strip()
            ).scalar()
            if upline_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Referral code not found",
                )

    from services.partner_service import PartnerService

    partner_service = PartnerService()

    try:
        partner_service.create_partner(
            telegram_id=None,
            upline_id=upline_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            telegram_link_code=binding_token,
            consent_given=True,
            consent_version="v.1.0 21.04.2026",
            consent_date=datetime.utcnow(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create partner",
        ) from exc

    if upline_id:
        with get_session() as session:
            upline = session.query(Partner).filter(
                Partner.id == upline_id
            ).first()
            upline_telegram_id = (
                upline.telegram_id if upline else None
            )

        if upline_telegram_id:
            full_name = f"{first_name} {last_name}"

            try:
                import asyncio

                asyncio.create_task(
                    notification_service.notify_new_referral(
                        telegram_id=int(upline_telegram_id),
                        partner_name=full_name,
                    )
                )
            except Exception:
                logger.exception("Failed to schedule referral notification")

    return HTMLResponse(
        f"""
        <html>
        <head>
            <title>Регистрация завершена</title>
        </head>

        <body style="
            font-family:Arial;
            text-align:center;
            margin-top:60px;
        ">

            <h2>Регистрация завершена</h2>

            <p>Ваш аккаунт создан.</p>

            <p>
                <b>
                    Нажмите кнопку чтобы привязать Telegram:
                </b>
            </p>

            <br>

            <a href="
                https://t.me/nanorem_bot?start={binding_token}
            ">
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

            <pre>
https://t.me/nanorem_bot?start={binding_token}
            </pre>

        </body>
        </html>
        """
    )


# ---------------------------------------------------------
# WooCommerce security
# ---------------------------------------------------------

def verify_woocommerce_signature(
    body: bytes,
    signature: str | None,
) -> bool:
    """
    Проверяет стандартную WooCommerce webhook подпись.

    WooCommerce использует:
    HMAC-SHA256 + Base64.
    """

    if not WOOCOMMERCE_WEBHOOK_SECRET:
        logger.error(
            "WOOCOMMERCE_WEBHOOK_SECRET is not configured"
        )
        return False

    if not signature:
        return False

    digest = hmac.new(
        WOOCOMMERCE_WEBHOOK_SECRET.encode(
            "utf-8"
        ),
        body,
        hashlib.sha256,
    ).digest()

    expected = base64.b64encode(
        digest
    ).decode("utf-8")

    return hmac.compare_digest(
        expected,
        signature,
    )


# ---------------------------------------------------------
# WooCommerce webhook
# ---------------------------------------------------------

@app.post("/webhook")
async def webhook_endpoint(
    request: Request,
    x_wc_webhook_signature: str | None = Header(
        default=None,
        alias="X-WC-Webhook-Signature",
    ),
):
    """
    Основной WooCommerce webhook.

    Важно:
    сначала читаем raw body,
    проверяем подпись,
    только потом разбираем JSON.
    """

    try:
        body = await request.body()

        if not verify_woocommerce_signature(
            body,
            x_wc_webhook_signature,
        ):
            logger.warning(
                "Rejected WooCommerce webhook: "
                "invalid signature"
            )

            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature",
            )

        payload = await request.json()

        logger.info(
            "Received WooCommerce webhook: "
            f"order={payload.get('id')}, "
            f"status={payload.get('status')}"
        )

        success = (
            await order_processor.process_webhook(
                payload
            )
        )

        if success:
            return {
                "success": True,
                "message": (
                    "Order processed successfully"
                ),
            }

        logger.error(
            "Failed to process webhook order"
        )

        raise HTTPException(
            status_code=500,
            detail="Order processing failed",
        )

    except HTTPException:
        raise

    except RootPairNotReadyError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as e:
        logger.exception(
            f"Error processing webhook: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        ) from e


# ---------------------------------------------------------
# Telegram webhook security
# ---------------------------------------------------------

@app.post("/telegram-webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
):
    """
    Webhook Telegram Bot API.

    Проверяем секретный заголовок Telegram.
    """

    if not TELEGRAM_WEBHOOK_SECRET:
        logger.error(
            "TELEGRAM_WEBHOOK_SECRET is not configured"
        )

        raise HTTPException(
            status_code=503,
            detail="Telegram webhook secret is not configured",
        )

    if not x_telegram_bot_api_secret_token:
        raise HTTPException(
            status_code=401,
            detail="Missing Telegram webhook secret",
        )

    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token,
        TELEGRAM_WEBHOOK_SECRET,
    ):
        logger.warning(
            "Rejected Telegram webhook: "
            "invalid secret"
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram webhook secret",
        )

    try:
        update_data = await request.json()

        update = Update.de_json(
            update_data,
            telegram_app.bot,
        )

        await telegram_app.process_update(
            update
        )

        return {
            "status": "ok"
        }

    except Exception as e:
        logger.exception(
            f"Telegram webhook error: {e}"
        )

        return {
            "status": "error",
            "detail": "Telegram update processing failed",
        }


# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    """
    Инициализация Telegram и установка webhook.
    """

    init_db()
    await telegram_app.initialize()

    if WEBHOOK_URL:
        if not TELEGRAM_WEBHOOK_SECRET:
            raise RuntimeError(
                "TELEGRAM_WEBHOOK_SECRET is required when WEBHOOK_URL is set"
            )

        webhook_url = (
            f"{WEBHOOK_URL}/telegram-webhook"
        )

        await telegram_app.bot.set_webhook(
            url=webhook_url,
            secret_token=TELEGRAM_WEBHOOK_SECRET,
        )

        logger.info("Telegram webhook configured")

    else:
        logger.warning(
            "WEBHOOK_URL not set, "
            "Telegram webhook not configured"
        )

    start_scheduler()


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------

@app.on_event("shutdown")
async def on_shutdown():
    """
    Корректное завершение Telegram.
    """

    await telegram_app.bot.delete_webhook()

    await telegram_app.shutdown()
    stop_scheduler()