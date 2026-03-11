# NANOREM MLM — Failure Scenarios

Этот документ описывает действия при типичных сбоях системы.

---

# 1. Telegram бот не запускается

Признаки:

* бот не отвечает
* ошибка при запуске `python main.py`

Проверить:

1. BOT_TOKEN в config.py
2. интернет соединение
3. зависимости Python

Запуск:

```
python main.py
```

Если сломались handlers:

```
git reset --hard TELEGRAM_MENU_WORKING
```

---

# 2. Telegram кнопки не работают

Признаки:
