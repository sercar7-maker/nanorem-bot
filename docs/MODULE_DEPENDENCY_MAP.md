# NANOREM MLM — Module Dependency Map

Этот документ показывает зависимости между модулями системы.

---

# Общая архитектура

Telegram Bot
↓
Handlers
↓
Services
↓
Core MLM Engine
↓
Database

---

# Telegram слой

main.py
↓
tg_handlers/bot.py
↓
tg_handlers/handlers.py
↓
tg_handlers/start.py
tg_handlers/balance.py

Handlers используют:

database
core
services

---

# Core MLM Engine

core/network.py
core/commission.py

Эти модули отвечают за:

* построение сети партнёров
* расчёт комиссий

Используются в:

web/order_handler.py

---

# Services слой

services/commission_service.py

Используется для:

* обработки комиссий
* записи в базу

---

# Web слой

web/app.py
↓
web/webhook.py
↓
web/order_handler.py

Этот слой получает:

Webhook от nanorvs

---

# Поток заказа

nanorvs
↓
webhook
↓
OrderHandler
↓
NetworkManager
↓
CommissionCalculator
↓
CommissionService
↓
Database

---

# Database слой

database/db.py
database/models.py

Используется всеми модулями:

Telegram
Web
Core

---

# Scheduler

scheduler.py

Зависит от:

database
services

---

# Уведомления

tg_notify/notifications.py

Зависит от:

Telegram Bot
Database

---

# Полная схема зависимостей

main.py
│
├── tg_handlers/
│   ├── bot.py
│   ├── handlers.py
│   ├── start.py
│   └── balance.py
│
├── core/
│   ├── commission.py
│   └── network.py
│
├── services/
│   └── commission_service.py
│
├── web/
│   ├── app.py
│   ├── webhook.py
│   └── order_handler.py
│
├── database/
│   ├── db.py
│   └── models.py
│
├── tg_notify/
│   └── notifications.py
│
└── scheduler.py

---

# Принцип архитектуры

Telegram и Web — это интерфейсы.

Core — бизнес логика.

Database — хранение данных.

Services — обработка операций.
