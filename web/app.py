from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import random
import string
import asyncio

from telegram import Bot

from config import BOT_TOKEN
from database.db import get_session, SessionLocal
from database.models import Partner, PartnerStatus

# MLM imports
from web.api_client import NanorvsAPIClient
from core.commission import CommissionCalculator
from web.order_handler import OrderHandler
from web.webhook import WebhookHandler

# уведомления
from services.notifications import NotificationService


app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
    ref: int | None = Form(None)
):
    link_code = generate_link_code()

    with get_session() as session:
        partner = Partner(
            telegram_id=None,
            telegram_link_code=link_code,
            first_name=first_name,
            last_name=last_name,
            username=None,
            email=email,
            phone=phone,
            upline_id=ref,
            status=PartnerStatus.INACTIVE
        )

        session.add(partner)
        session.commit()
        session.refresh(partner)

        if ref:
            upline = session.query(Partner).filter(Partner.id == ref).first()

            if upline and upline.telegram_id:
                full_name = f"{first_name} {last_name}"

                try:
                    asyncio.create_task(
                        notify_new_referral(
                            upline_telegram_id=int(upline.telegram_id),
                            new_partner_name=full_name
                        )
                    )
                except Exception as e:
                    print(f"Notify error: {e}")

    return HTMLResponse(f"""
    <html>
    <head>
        <title>Р РµРіРёСЃС‚СЂР°С†РёСЏ Р·Р°РІРµСЂС€РµРЅР°</title>
    </head>

    <body style="font-family:Arial;text-align:center;margin-top:60px;">

        <h2>Р РµРіРёСЃС‚СЂР°С†РёСЏ Р·Р°РІРµСЂС€РµРЅР°</h2>

        <p>Р’Р°С€ Р°РєРєР°СѓРЅС‚ СЃРѕР·РґР°РЅ.</p>

        <p><b>РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ С‡С‚РѕР±С‹ РїСЂРёРІСЏР·Р°С‚СЊ Telegram:</b></p>

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
                РћС‚РєСЂС‹С‚СЊ Telegram Рё Р°РєС‚РёРІРёСЂРѕРІР°С‚СЊ
            </button>
        </a>

        <br><br>

        <p>Р•СЃР»Рё РєРЅРѕРїРєР° РЅРµ СЂР°Р±РѕС‚Р°РµС‚:</p>

        <pre>https://t.me/nanorem_bot?start={link_code}</pre>

    </body>
    </html>
    """)


api_client = NanorvsAPIClient()
web_db = SessionLocal()
web_bot = Bot(token=BOT_TOKEN)
calculator = CommissionCalculator(web_db, web_bot)
order_handler = OrderHandler(api_client, calculator)
webhook_handler = WebhookHandler(order_handler)


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    payload = await request.json()

    event_type = payload.get("event_type")
    data = payload.get("data")

    result = await webhook_handler.handle_webhook(event_type, data)

    return {"success": result}