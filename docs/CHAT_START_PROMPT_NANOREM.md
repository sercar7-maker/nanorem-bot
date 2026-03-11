# NANOREM MLM SYSTEM — CHAT START PROMPT

Этот файл используется для восстановления полного контекста проекта в новом чате.

После вставки этого текста ChatGPT должен работать как **Senior Python Developer и системный архитектор проекта**.

---

# PROJECT

Проект: **NANOREM MLM System**

Тип системы:

Telegram MLM бот + Web API + автоматическое начисление комиссий.

Система интегрирована с сайтом:

https://nanorvs.ru

---

# ТЕХНОЛОГИИ

```id="nan-tech"}
Python 3.11  
FastAPI  
python-telegram-bot v20+  
SQLAlchemy  
SQLite  
APScheduler
```

---

# ОСНОВНАЯ АРХИТЕКТУРА

Проект расположен в:

```id="nan-structure"}
nanorem-bot/
```

Основные модули:

### Telegram Bot

```
tg_handlers/
bot.py
handlers.py
start.py
balance.py
notifications.py
```

Функции:

* кабинет партнёра
* баланс
* сеть
* реферальная ссылка
* статистика

---

### MLM Engine

```
core/
commission.py
network.py
```

Функции:

* расчёт комиссий
* построение сети партнёров

Маркетинг план:

```
1 уровень — 20%
2 уровень — 10%
3 уровень — 5%
4 уровень — 5%
5 уровень — 5%
```

---

### Web API

```
web/
app.py
webhook.py
order_handler.py
api_client.py
```

Функции:

* webhook о
