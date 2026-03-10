# NANOREM MLM – Project Context

Дата создания контекста: 10.03.2026
Проект: Telegram + Web MLM система NANOREM

---

# Общая архитектура

Система состоит из 3 основных частей:

1. **Web сайт (FastAPI)**
2. **Telegram бот**
3. **MLM Engine (комиссии и сеть)**

Рабочий поток:

Site registration
↓
Partner created in DB
↓
telegram_link_code generated
↓
User clicks link
↓
/start CODE in Telegram
↓
Telegram ID привязывается к Partner
↓
Bot показывает кабинет

---

# Структура проекта

```
nanorem-bot/

core/
    commission.py
    network.py

database/
    db.py
    models.py

services/
    commission_service.py

tg_handlers/
    bot.py
    handlers.py
    start.py
    balance.py

tg_notify/
    notifications.py

web/
    app.py
    order_handler.py
    webhook.py
    api_client.py

main.py
scheduler.py
config.py
```

---

# MLM логика

Маркетинг план:

Level 1 — 20%
Level 2 — 10%
Level 3 — 5%
Level 4 — 5%
Level 5 — 5%

Комиссии создаются через:

```
core/commission.py
```

Записываются в таблицу:

```
Commission
```

---

# Обработка заказов

Webhook →
webhook_handler →
OrderHandler →
NetworkManager →
CommissionCalculator →
CommissionService →
DB commit →
Telegram notification

---

# Регистрация партнёра

Регистрация происходит **только на сайте**.

Файл:

```
web/app.py
```

При регистрации:

```
telegram_link_code = random 6 digits
```

Создаётся Partner:

```
telegram_id = None
telegram_link_code = code
status = INACTIVE
```

После регистрации пользователь получает ссылку:

```
https://t.me/nanorem_bot?start=CODE
```

---

# Привязка Telegram

Файл:

```
tg_handlers/start.py
```

Логика:

```
/start CODE
↓
find Partner.telegram_link_code
↓
partner.telegram_id = telegram_id
↓
status = ACTIVE
```

---

# Telegram команды

Работают сейчас:

```
/start
/balance
```

---

# Telegram меню (кнопки)

Кнопки:

```
💰 Баланс
👥 Моя сеть
🔗 Реферальная ссылка
📊 Статистика
```

Кнопки — обычные текстовые сообщения.

Их должен обрабатывать:

```
MessageHandler(filters.TEXT)
```

---

# Что уже работает

✔ Telegram бот запускается
✔ Polling работает
✔ Webhook работает
✔ MLM сеть работает
✔ CommissionCalculator считает комиссии
✔ Комиссии пишутся в БД
✔ Защита от двойного webhook работает
✔ Telegram уведомления о комиссиях работают
✔ Команда /balance работает
✔ Привязка Telegram через link_code работает

---

# Что ещё нужно сделать

1. Полностью восстановить обработчики кнопок
2. Кнопка "Баланс" должна вызывать баланс
3. Кнопка "Моя сеть"
4. Кнопка "Реферальная ссылка"
5. Кнопка "Статистика"
6. Админ уведомления
7. Кабинет партнёра

---

# Важные правила проекта

1. Регистрация только на сайте
2. Telegram используется как кабинет
3. Partner.id ≠ Telegram ID
4. Telegram ID хранится в:

```
Partner.telegram_id
```

---

# Как продолжать проект в новом чате

В начале нового чата писать:

```
Продолжаем проект NANOREM MLM
Контекст проекта ниже
```

и вставлять этот файл.

После этого можно сразу продолжать разработку.
