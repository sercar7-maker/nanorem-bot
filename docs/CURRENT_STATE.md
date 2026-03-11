# NANOREM MLM — Current State

Дата: 11 марта 2026

---

# Что уже работает

## Telegram Bot

Работает Telegram кабинет партнёра.

Меню из 6 кнопок:

👤 Профиль
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
🌐 Сайт

Команды:

```
/start
/balance
```

---

# Telegram функции

Работают:

👤 Профиль — показывает ID и дату регистрации партнёра

💰 Баланс — считается из таблицы Commission

👥 Моя сеть — показывает структуру сети до 5 уровней + общее количество партнёров

🔗 Реферальная ссылка — формируется из telegram_link_code

📊 Статистика — показывает:

* количество партнёров в сети
* общую сумму комиссий
* текущий баланс

🌐 Сайт — ссылка на https://nanorvs.ru

---

# MLM Engine

Работает:

```
core/network.py
core/commission.py
```

Маркетинг план:

```
1 уровень — 20%
2 уровень — 10%
3 уровень — 5%
4 уровень — 5%
5 уровень — 5%
```

Комиссии создаются через:

```
Webhook
↓
OrderHandler
↓
CommissionCalculator
↓
CommissionService
↓
Database
```

---

# Database

Используется:

```
SQLite
SQLAlchemy
```

Основные таблицы:

```
Partner
Purchase
Commission
Balance
Withdrawal
```

Поле `lineage` хранит цепочку аплайнов партнёра.

Пример:

```
Partner 10
lineage [2,5]

Это означает:

2 → 5 → 10
```

---

# Структура сети

Сейчас реализовано:

```
1 уровень
2 уровень
3 уровень
4 уровень
5 уровень
```

Telegram показывает:

```
👥 Ваша сеть

1 уровень — X партнёров
2 уровень — X партнёров
3 уровень — X партнёров
4 уровень — X партнёров
5 уровень — X партнёров

Всего партнёров — X
```

---

# Git стабильные версии

```
MLM_ENGINE_WORKING
MLM_FINANCE_WORKING
TELEGRAM_MENU_WORKING
PARTNER_STATS_WORKING
TELEGRAM_PARTNER_CABINET_WORKING
NETWO
```
