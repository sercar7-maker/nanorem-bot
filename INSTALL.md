# Инструкция по установке NANOREM MLM System

## Требования

- Python 3.9 или выше
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
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost/nanorem_mlm
# Для разработки можно использовать SQLite:
# DATABASE_URL=sqlite:///nanorem_mlm.db

# Application Settings
APP_NAME=NANOREM MLM System
APP_VERSION=1.0.0
DEBUG_MODE=False
LOG_LEVEL=INFO

# Cash Register Integration (optional)
CASH_REGISTER_API_URL=https://api.example.com
CASH_REGISTER_API_KEY=your_api_key
CASH_REGISTER_SHOP_ID=your_shop_id
```

## Шаг 5: Инициализация базы данных

```bash
# Создайте базу данных PostgreSQL
createdb nanorem_mlm

# Или используйте SQLite (файл будет создан автоматически)
```

## Шаг 6: Запуск приложения

### Запуск Telegram бота

```bash
python main.py --mode telegram
```

### Запуск в режиме отладки

```bash
python main.py --mode telegram --debug
```

### Запуск в фоновом режиме (Linux)

```bash
nohup python main.py --mode telegram > bot.log 2>&1 &
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
ExecStart=/path/to/nanorem-bot/venv/bin/python main.py --mode telegram
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

- Проверьте правильность TELEGRAM_BOT_TOKEN
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
