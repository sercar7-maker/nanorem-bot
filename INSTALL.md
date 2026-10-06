# Инструкция по установке NANOREM MLM System

## Требования

- Python 3.10 или выше
- PostgreSQL 12 или выше (или SQLite для разработки)
- Git
- Telegram Bot Token (от @BotFather)

## Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/sercar7-maker/nanorem-bot.git
cd nanorem-bot
```

## Шаг 2: Создание виртуального окружения

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

## Шаг 3: Установка зависимостей

```bash
pip install -r requirements.txt
```

## Шаг 4: Настройка конфигурации

1. Скопируйте файл .env.example в .env:

```bash
cp .env.example .env
```

2. Откройте файл .env и заполните переменные:

```env
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_from_botfather

# Database Configuration
DATABASE_URL=sqlite:///nanorem.db
# Для разработки можно использовать SQLite:
# DATABASE_URL=sqlite:///nanorem_mlm.db

# Application Settings
APP_NAME=NANOREM MLM System
APP_VERSION=1.0.0
DEBUG=false
LOG_LEVEL=INFO

# WooCommerce webhook authentication
WOOCOMMERCE_WEBHOOK_SECRET=your_woocommerce_webhook_secret

# Set these only for Telegram webhook mode
# WEBHOOK_URL=https://yourdomain.com
# TELEGRAM_WEBHOOK_SECRET=your_telegram_webhook_secret

# Optional WooCommerce REST API access
# WC_API_BASE_URL=https://yourdomain.com/wp-json/wc/v3
# WC_CONSUMER_KEY=your_consumer_key
# WC_CONSUMER_SECRET=your_consumer_secret
```

## Шаг 5: Инициализация базы данных

```bash
# Создайте базу данных PostgreSQL
createdb nanorem_mlm

# Или используйте SQLite (файл будет создан автоматически)
python init_db.py
```

## Шаг 6: Запуск приложения

### Web-приложение и Telegram webhook

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

Для WooCommerce настройте webhook на `https://yourdomain.com/webhook` и задайте `WOOCOMMERCE_WEBHOOK_SECRET`. Для Telegram webhook укажите `WEBHOOK_URL=https://yourdomain.com` (без пути) и `TELEGRAM_WEBHOOK_SECRET`; маршрут `/telegram-webhook` будет добавлен автоматически.

### Альтернативный запуск Telegram polling

```bash
python -m tg_handlers.bot
```

Не запускайте одновременно polling- и webhook-режимы для одного Telegram-бота. Polling entry point инициализирует базу данных и scheduler. У обоих режимов должен быть один процесс/worker: приложение содержит in-process scheduler и Telegram client.

`main.py` — отдельное legacy FastAPI-приложение для технических routes, не entry point для регистрации или webhook.

### Запуск в фоновом режиме (Linux)

```bash
nohup uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1 > app.log 2>&1 &
```

## Шаг 7: Регистрация Telegram бота

1. Откройте Telegram и найдите @BotFather
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте токен и добавьте его в файл .env
5. Настройте команды бота через @BotFather:

```
start - Начать работу
help - Показать справку
register - Регистрация партнёра
profile - Мой профиль
network - Моя структура
sales - Продажи и комиссии
receipt - Создать чек
```

## Дополнительные настройки

### Настройка PostgreSQL

```sql
CREATE DATABASE nanorem_mlm;
CREATE USER nanorem_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE nanorem_mlm TO nanorem_user;
```

### Настройка systemd service (Linux)

Создайте файл `/etc/systemd/system/nanorem-bot.service`:

```ini
[Unit]
Description=NANOREM MLM Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/nanorem-bot
Environment="PATH=/path/to/nanorem-bot/venv/bin"
ExecStart=/path/to/nanorem-bot/venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nanorem-bot
sudo systemctl start nanorem-bot
sudo systemctl status nanorem-bot
```

## Решение проблем

### Ошибка: "Failed to import configuration"

- Убедитесь, что файл .env создан и заполнен
- Проверьте синтаксис в файле config.py

### Ошибка подключения к базе данных

- Проверьте правильность DATABASE_URL
- Убедитесь, что PostgreSQL запущен
- Проверьте права доступа пользователя к базе данных

### Бот не отвечает

- Проверьте правильность BOT_TOKEN
- Убедитесь, что бот запущен
- Проверьте логи: `tail -f bot.log`

## Обновление

```bash
git pull origin main
pip install -r requirements.txt --upgrade
sudo systemctl restart nanorem-bot
```

## Поддержка

При возникновении проблем создайте issue на GitHub:
https://github.com/sercar7-maker/nanorem-bot/issues
