# NANOREM MLM SYSTEM — CHAT START PROMPT

Этот файл используется для восстановления полного контекста проекта в новом чате.

После вставки этого текста ChatGPT должен работать как **Senior Python Developer и системный архитектор** проекта.

---

# PROJECT

Проект: **NANOREM MLM System**

Тип системы:

Telegram MLM бот + Web API + автоматическое начисление комиссий.

Система интегрирована с сайтом:

https://nanorvs.ru

---

# ОСНОВНАЯ АРХИТЕКТУРА

Система состоит из 5 основных модулей.

### Telegram Bot

Файлы:

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

Маркетинг-план:

```
20% / 10% / 5% / 5% / 5%
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

* получение заказов
* webhook от nanorvs
* обработка продаж
* начисление комиссий

---

### Database

```
database/
db.py
models.py
```

Используется:

```
SQLite (nanorem.db)
SQLAlchemy
```

Таблицы:

```
Partner
Purchase
Commission
```

---

### Scheduler

```
scheduler.py
```

Используется:

```
APScheduler
```

Задачи:

```
expire_statuses
daily_summary
```

---

# TELEGRAM MENU

В Telegram используются **6 кнопок**:

```
👤 Профиль
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
🌐 Сайт
```

---

# РЕГИСТРАЦИЯ ПАРТНЁРА

Регистрация происходит **только на сайте**.

Флоу:

```
Website registration
↓
Partner создаётся в БД
↓
генерируется telegram_link_code
↓
пользователь нажимает кнопку
↓
Telegram /start CODE
↓
активация партнёра
```
