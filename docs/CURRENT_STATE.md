# NANOREM MLM — Current State

Дата: 22 марта 2026

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

/start  
/balance  

---

# Telegram функции

Работают:

👤 Профиль  
- показывает ID  
- дату регистрации  
- текущий ранг

💰 Баланс  
- считается из таблицы `Commission`

👥 Моя сеть  
- показывает структуру сети до 5 уровней
- считает прямых и следующих партнёров по `upline_id`
- общее количество партнёров выводится корректно

🔗 Реферальная ссылка  
- формируется из `telegram_link_code`

📊 Статистика  
показывает:

- количество партнёров в сети
- сумму комиссий
- текущий баланс
- личный оборот за месяц
- оборот сети за месяц

🌐 Сайт  
- ссылка на `https://nanorvs.ru`

---

# Что уже исправлено

## PartnerService

Файл: `services/partner_service.py`

Исправлено:

- восстановлен файл после проблем с отступами
- `get_network_levels()` работает как метод класса
- уровни сети считаются по `upline_id`
- статистика перестала падать из-за ошибок структуры файла

Результат:

- кнопка **Моя сеть** показывает корректно:
  - 1 уровень — 1 партнёр
  - всего партнёров — 1

- кнопка **Статистика** показывает корректно:
  - партнёров в сети — 1
  - всего комиссий — 200.00 ₽
  - баланс — 200.00 ₽
  - личный оборот — 3000.00 ₽

---

## Чистка тестов

Удалены мусорные и временные файлы:

### Из папки `tests`
- `tests/test_generate_network.py`
- `tests/test_telegram.py`
- `tests/test_order.py`

### Из корня проекта
- `test_httpx.py`
- `test_ptb.py`
- `test_ptb_no_proxy.py`
- `test_ptb_selector.py`
- `test_requests_verify_false.py`
- `test_telebot.py`

Оставлен основной живой тест:

- `tests/test_mlm.py`

---

## Webhook / уведомления

Файл: `web/app.py`

Исправлено:

- раньше было:
  - `CommissionCalculator(None, None)`

- теперь создаётся нормально:
  - отдельная DB session
  - `Bot(token=BOT_TOKEN)`
  - `CommissionCalculator(web_db, web_bot)`

Результат:

- `web.app` импортируется без ошибок логики
- `OrderHandler` и `WebhookHandler` создаются нормально
- webhook-часть больше не стартует с пустыми `db=None` и `bot=None`

---

# Уведомления: текущее состояние

Сейчас в проекте оставлен **один механизм уведомлений**:

1. `services/notifications.py`

Что сделано:

- удалён `tg_handlers/notifications.py`
- удалён `tg_notify/notifications.py`
- `web/app.py` переведён на `NotificationService`
- `core/commission.py` использует `NotificationService`
- в `services/notifications.py` используется класс `NotificationService`
- bot передаётся в сервис извне, отдельный `Bot(token=BOT_TOKEN)` внутри `services/notifications.py` больше не создаётся

## Что используется сейчас

### Комиссии
Файл: `core/commission.py`

Использует:

- `NotificationService`
- импорт из `services/notifications.py`

### Новый партнёр
Файл: `web/app.py`

Использует:

- `NotificationService`
- импорт из `services/notifications.py`

Итог:

- система уведомлений **унифицирована**
- дубли удалены
- правило **один Bot instance на всё приложение** соблюдается на уровне архитектуры уведомлений

---

# Проверка уведомлений

## Тестовый файл

Основной тест сейчас:

- `tests/test_mlm.py`

Текущая версия теста:

- создаёт тестового партнёра
- создаёт тестовую покупку
- создаёт тестовую комиссию
- создаёт bot напрямую через `Bot(token=BOT_TOKEN)`
- вызывает `NotificationService(bot)`
- пытается отправить уведомление о комиссии

Это было сделано специально для диагностики, чтобы убрать влияние `ApplicationBuilder` и проверить прямой вызов Telegram Bot API.

## Результат последней проверки

Код доходит до вызова:

- `notify_commission()`
- `bot.send_message(...)`

Но фактическая отправка не проходит.

Последний результат Python-теста:

- `connect_tcp` проходит успешно
- ошибка возникает на шаге TLS
- `start_tls.failed`
- `ConnectTimeout(TimeoutError())`

Это значит:

- логика Python-кода уже доходит до отправки
- проблема сейчас не в `NotificationService`
- проблема не в `web/app.py`
- проблема не в `core/commission.py`
- проблема в сетевом TLS/HTTPS-соединении Python → Telegram API

---

# Сетевые наблюдения

Проверено:

- proxy-переменные в PowerShell не видны
- `Test-NetConnection api.telegram.org -Port 443` = успешно
- TCP до Telegram есть

Дополнительные проверки:

## curl
Команда:

`curl.exe -v https://api.telegram.org`

Результат:

- TLS handshake не проходит
- ошибка:
  - `Connection was reset`
  - `schannel: failed to receive handshake, SSL/TLS connection failed`

## PowerShell
Команда:

`Invoke-WebRequest https://api.telegram.org`

Результат:

- `200 OK`

## requests
Команда:

`python -c "import requests; print(requests.get('https://api.telegram.org', timeout=10).status_code)"`

Результат на одном из запусков:

- `200`

Позже проверка стала нестабильной:

- без `verify=False` запросы начали иногда падать
- после временного отключения `Hiddify` запрос к `api.telegram.org` завершился `ReadTimeout`
- с `verify=False` запрос к `api.telegram.org` завершался `UNEXPECTED_EOF_WHILE_READING`

## requests / другие сайты

### Google
Команда:

`python -c "import requests; print(requests.get('https://www.google.com', timeout=10).status_code)"`

Результат на одном из запусков:

- `200`

Позже поведение стало нестабильным:

- запрос к `www.google.com` начал падать с `UNEXPECTED_EOF_WHILE_READING`

### example.com
Команда:

`python -c "import requests; print(requests.get('https://example.com', timeout=10).status_code)"`

Результат:

- `SSLError`
- `UNEXPECTED_EOF_WHILE_READING`

Команда:

`python -c "import requests; print(requests.get('https://example.com', timeout=10, verify=False).status_code)"`

Результат:

- ошибка остаётся
- `UNEXPECTED_EOF_WHILE_READING`

Вывод по `requests`:

- поведение нестабильное
- часть HTTPS-запросов иногда проходит
- часть падает по SSL/TLS
- проблема не сводится только к проверке сертификата

## httpx
Команда:

`python -c "import httpx; r=httpx.get('https://api.telegram.org', timeout=10); print(r.status_code)"`

Результат:

- ошибка TLS handshake
- `httpx.ConnectTimeout: _ssl.c:989: The handshake operation timed out`

## httpx без окружения
Команда:

`python -c "import httpx; r=httpx.get('https://api.telegram.org', timeout=10, trust_env=False); print(r.status_code)"`

Результат:

- ошибка остаётся
- `httpx.ConnectTimeout: _ssl.c:989: The handshake operation timed out`

## httpx с явным HTTP/1.1
Команда:

`python -c "import httpx; c=httpx.Client(http2=False, trust_env=False, timeout=10); r=c.get('https://api.telegram.org'); print(r.status_code); c.close()"`

Результат:

- ошибка остаётся
- `httpx.ConnectTimeout: _ssl.c:989: The handshake operation timed out`

## httpx / другие сайты
Команда:

`python -c "import httpx; r=httpx.get('https://example.com', timeout=10, trust_env=False); print(r.status_code)"`

Результат:

- `httpx.ConnectError`
- `CERTIFICATE_VERIFY_FAILED`

Команда:

`python -c "import httpx, certifi; r=httpx.get('https://example.com', timeout=10, trust_env=False, verify=certifi.where()); print(r.status_code)"`

Результат:

- ошибка остаётся
- `CERTIFICATE_VERIFY_FAILED`

Вывод по `httpx`:

- проблема не только на Telegram
- `trust_env=False` не помогает
- `http2=False` не помогает
- явный `certifi.where()` не помогает

## WinHTTP proxy
Команда:

`netsh winhttp show proxy`

Результат:

- `Прямой доступ (без прокси-сервера)`

## Python / Telegram
Тест через `python-telegram-bot` и прямой `Bot(...)` показывает:

- TCP соединение открывается
- TLS handshake завершается ошибкой
- ошибка доходит до:
  - `ConnectError(BrokenResourceError())`
  - или `ConnectTimeout(TimeoutError())`

## Среда Windows / VPN
На ПК установлены два VPN:

- `Hiddify`
- `Outline`

Что дополнительно выяснено:

- `Outline` ранее был отключён, но не удалён
- при попытке вернуть `Hiddify` в рабочее состояние он тоже начал показывать timeout
- даже при временном отключении `Hiddify` проблема с HTTPS/TLS не исчезла

Это усиливает вывод, что проблема зависит не от кода проекта, а от состояния сетевой среды Windows / VPN / маршрутов / TLS-стека.

## Зафиксированные версии среды

- `Python = 3.11.7`
- `OpenSSL = 3.0.11`
- `python-telegram-bot = 22.6`
- `httpx = 0.27.2`
- `httpcore = 1.0.5`
- `requests = 2.32.5`
- `certifi = 2026.2.25`

Вывод на текущий момент:

- проблема не в бизнес-логике MLM
- проблема не в расчёте комиссий
- проблема не в `PartnerService`
- проблема не в `config.py`
- проблема не в `ApplicationBuilder`
- проблема не в самом `NotificationService`
- проблема не в proxy-переменных окружения
- проблема не снимается через `trust_env=False`
- проблема не снимается через `http2=False`
- проблема не снимается через явный `certifi.where()`
- проблема уже выглядит не как ошибка только `httpx`, а как нестабильная внешняя TLS/HTTPS-проблема среды Windows/VPN/маршрутов

---

# Orders / Оборот

Работает частично:

- можно вручную создавать тестовые покупки
- можно вручную создавать тестовые комиссии
- личный оборот считается
- сетевой оборот пока не доведён до конца

---

# Database

Используется:

- SQLite
- SQLAlchemy

Основные таблицы:

- `Partner`
- `Purchase`
- `Commission`
- `Balance`
- `Withdrawal`

Дополнительно используется:

- `PartnerStats`

---

# Структура сети

Реализовано:

- 1 уровень
- 2 уровень
- 3 уровень
- 4 уровень
- 5 уровень

Подход сейчас:

- структура для Telegram считается по `upline_id`
- это дало корректный результат в кабинете

---

# Scheduler

Работает APScheduler:

- `expire_statuses`
- `daily_summary`
- `monthly_reset_turnover`

---

# Установленные пакеты

Для корректного импорта `web/app.py` были установлены:

- `jinja2`
- `python-multipart`

---

# Важные файлы на текущий момент

## Основные рабочие файлы
- `services/partner_service.py`
- `services/notifications.py`
- `core/commission.py`
- `tg_handlers/bot.py`
- `web/app.py`
- `tests/test_mlm.py`

## Файлы, которые смотреть в первую очередь дальше
1. `tests/test_mlm.py`
2. `services/notifications.py`
3. `tg_handlers/bot.py`
4. `core/commission.py`
5. `web/app.py`

---

# Последний сохранённый Git статус

Ветка:

- `notifications_fix`

Рабочее дерево:

- clean

Последние важные commit'ы:

- `eaeb5c7` — `Убраны дубли уведомлений`
- `205898c` — `Web app переведён на NotificationService`
- `aa207fc` — `Тест MLM переведён на прямой Bot для диагностики TLS`
- `abf40f8` — `Обновлён CURRENT_STATE после унификации уведомлений`
- `d2217b4` — `Обновлён CURRENT_STATE по диагностике httpx TLS`

Также сохранён tag:

- `checkpoint_notifications_tls_diag`

Все изменения отправлены на GitHub.

---

# Что делать следующим шагом

Варианты следующей работы:

1. сначала стабилизировать сеть / VPN-среду Windows
2. затем повторить минимальные HTTPS-тесты `requests` и `httpx`
3. только после этого возвращаться к фактической отправке Telegram-уведомлений
4. бизнес-логика MLM сейчас не является блокером

---

# Итог

Проект рабочий.

Что точно работает:

- Telegram кабинет
- профиль
- баланс
- моя сеть
- статистика
- реферальная ссылка
- расчёт сети по уровням
- тестовая комиссия в базе
- webhook-инициализация без `None, None`
- единый механизм уведомлений через `services/notifications.py`

Что уже доведено до конца:

- удалены дубли уведомлений
- `web/app.py` переведён на `NotificationService`
- `core/commission.py` использует `NotificationService`
- диагностикой подтверждено, что код доходит до Telegram API
- диагностикой подтверждено, что текущий блокер находится вне бизнес-логики проекта

Что не добито до конца:

- фактическая отправка Telegram-уведомлений с этой машины
- стабилизация сети / VPN / TLS-среды Windows
- повторная проверка HTTPS после стабилизации сети
- стабильная интеграция с сайтом / webhook в боевом виде
- полный сетевой оборот

Следующая задача:

👉 сначала стабилизировать сетевую среду  
👉 потом повторить HTTPS-проверки  
👉 после этого снова тестировать полный цикл уведомлений  
👉 затем продолжить боевую интеграцию