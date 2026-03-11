# NANOREM MLM — PROJECT CONTEXT

Проект: Telegram + Web система MLM для платформы NANOREM.

Разработчик: Sergey Tsarik
Стек: Python 3.11, FastAPI, python-telegram-bot, SQLAlchemy, SQLite

---

# Архитектура проекта

nanorem-bot/

main.py — запуск Telegram бота
config.py — конфигурация

database/

* db.py — подключение БД
* models.py — модели

core/

* commission.py — расчёт комиссий MLM
* network.py — структура сети

services/

* commission_service.py — обработка комиссий

web/

* app.py — FastAPI сайт
* webhook.py — обработка webhook заказов
* order_handler.py — обработчик заказов

tg_handlers/

* bot.py — запуск Telegram Application
* handlers.py — регистрация handlers
* start.py — команда /start и меню
* balance.py — баланс партнёра

tg_notify/

* notifications.py — уведомления Telegram

scheduler.py — фоновые задачи APScheduler

---

# MLM логика

Маркетинг план:

1 уровень — 20%
2 уровень — 10%
3 уровень — 5%
4 уровень — 5%
5 уровень — 5%

Комиссии рассчитываются в:

core/commission.py

Сохранение комиссий:

services/commission_service.py

---

# Поток обработки заказа

Webhook
↓
OrderHandler
↓
проверка дубля заказа
↓
NetworkManager (поиск аплайна)
↓
CommissionCalculator
↓
запись комиссий в БД
↓
External API (nanorvs)

---

# Telegram Bot

Используется библиотека:

python-telegram-bot v20+

Polling режим.

Запуск:

python main.py

---

# Telegram меню

/start показывает клавиатуру:

👤 Профиль
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
🌐 Сайт

---

# Реализованные команды

/start — меню партнёра

/balance — баланс партнёра

Баланс считается из таблицы:

Commission
---
# Логика кнопок

Кнопки отправляют текст.

Обрабатываются в:

tg_handlers/handlers.py

Через:

MessageHandler(filters.TEXT)

---

# Регистрация партнёра

Регистрация происходит **только на сайте**.

Сайт создаёт:

Partner
telegram_link_code

Пользователь нажимает:

https://t.me/nanorem_bot?start=CODE

Бот привязывает Telegram ID к партнёру.

---

# Уведомления

tg_notify/notifications.py

Отправляются:

* начисление комиссии
* новый партнёр

---

# Scheduler

APScheduler задачи:

expire_statuses — каждый час
daily_summary — ежедневно

---

# Стабильные Git checkpoints

MLM_ENGINE_WORKING
MLM_FINANCE_WORKING
TELEGRAM_MENU_WORKING

---

# Восстановление проекта

Если что-то ломается:

git reset --hard TELEGRAM_MENU_WORKING

---

# Текущее состояние системы

Telegram bot — работает
Меню — работает
Кнопки — работают
Баланс — работает
MLM engine — работает
Webhook — работает

Система готова к подключению реальных данных:

* профиль партнёра
* сеть MLM
* реферальная ссылка
* статистика
