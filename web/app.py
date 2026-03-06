from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import random
import string

from database.db import get_session
from database.models import Partner, PartnerStatus

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# -------------------------------
# Генерация кода Telegram
# -------------------------------

def generate_link_code():
    return "".join(random.choices(string.digits, k=6))


# -------------------------------
# Главная страница
# -------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "ref": None}
    )


# -------------------------------
# Страница регистрации
# -------------------------------

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, ref: int | None = None):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "ref": ref}
    )


# -------------------------------
# Обработка регистрации
# -------------------------------

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

    # Кнопка автопривязки Telegram
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