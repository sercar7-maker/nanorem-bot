# NANOREM MLM — System Flow

Общая архитектура системы.

---

# Пользовательский поток

User
↓
Website registration
↓
Partner created in database
↓
Telegram linking via start CODE
↓
Telegram partner cabinet

---

# Telegram Flow

User
↓
/start
↓
Keyboard Menu

👤 Профиль
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
🌐 Сайт

↓
Handlers
↓
Database

---

# Order Processing Flow

nanorvs.ru
↓
Webhook
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

# Commission Flow

Purchase
↓
Calculate MLM levels
↓
Create Commission records
↓
Update partner balance
↓
Send Telegram notifications

---

# Scheduler Flow

APScheduler

expire_statuses — hourly
daily_summary — daily

---

# Core Components

Telegram Bot
FastAPI Web
MLM Engine
Database
Scheduler

---

# External Services

nanorvs.ru — product & order system
Telegram — partner interface
