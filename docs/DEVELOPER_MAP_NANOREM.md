# NANOREM MLM — Developer Map

Этот файл описывает **структуру проекта и зависимости модулей**, чтобы разработчик мог быстро ориентироваться в системе.

---

# Общая структура проекта

```
nanorem-bot/
```

Основные директории:

```
core/
database/
services/
tg_handlers/
tg_notify/
web/
docs/
```

---

# Telegram Bot

Файлы:

```
tg_handlers/

bot.py
handlers.py
start.py
balance.py
notifications.py
```

Роли файлов:

### bot.py

Запускает Telegram Application.

```
Application.builder()
run_polling()
```

Инициализирует:

```
database
scheduler
handlers
```

---

### handlers.py

Главный обработчик кнопок Telegram.

Обрабатывает:

```
👤 Профиль
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
🌐 Сайт
```

Использует:

```
PartnerService
```

---

### start.py

Обработчик команды:

```
/start
```

Функции:

```
привязка Telegram ID
обработка start CODE
показ меню
```

---

# Services Layer

```
services/
```

### partner_service.py

Основной сервис партнёров.

Функции:

```
get_partner_by_telegram_id
get_partner_balance
get_network_levels
get_partner_stats
```

Работает напрямую с:

```
Partner
Commission
```

---

### commission_service.py

Обработка комиссий.

Используется в:

```
OrderHandler
```

---

# MLM Engine

```
core/
```

### network.py

Управляет структурой сети партнёров.

Функции:

```
get_upline_chain
get_downline
get_active_partner_ids
```

---

### commission.py

Рассчитывает комиссии MLM.

Использует маркетинг план:

```
20%
10%
5%
5%
5%
```

---

# Web Integration

```
web/
```

### webhook.py

Принимает webhook от сайта.

События:

```
order.created
order.completed
product.updated
```

---

### order_handler.py

Главный обработчик заказов.

Flow:

```
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
↓
External API
```

---

### api_client.py

Клиент API сайта:

```
https://nanorvs.ru
```

Функции:

```
get_products
create_order
get_order_status
update_partner_sales
get_partner_stats
```

---

# Database

```
database/
```

### db.py

Создаёт соединение с БД:

```
SessionLocal
```

---

### models.py

Основные модели:

```
Partner
Purchase
Commission
Withdrawal
Balance
```

---

# MLM Data Structure

Ключевое поле:

```
Partner.lineage
```

Тип:

```
JSON
```

Хранит цепочку аплайнов.

Пример:

```
Partner 10
lineage [2,5]
```

Это означает:

```
2 → 5 → 10
```

---

# Telegram Data Flow

```
Telegram User
↓
Telegram Bot
↓
handlers.py
↓
PartnerService
↓
Database
```

---

# Commission Flow

```
Purchase
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
Commission
```

---

# Git Stable Versions

Стабильные checkpoints:

```
MLM_ENGINE_WORKING
MLM_FINANCE_WORKING
TELEGRAM_MENU_WORKING
PARTNER_STATS_WORKING
TELEGRAM_PARTNER_CABINET_WORKING
NETWORK_LEVELS_WORKING
```

---

# Recovery

Если проект ломается:

```
git reset --hard NETWORK_LEVELS_WORKING
```

---

# Следующий этап разработки

Следующий модуль:

```
Network Turnover
```

Будет считать:

```
оборот сети
доход сети
MLM аналитику
```

Использует:

```
Purchase
Partner.lineage
Commission
```
