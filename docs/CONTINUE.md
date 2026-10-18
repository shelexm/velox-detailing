# Как продолжить работу

Состояние: `docs/PROGRESS.md`. Этапы 1-6 готовы, следующий этап 7: Telegram-бот.

## Запуск и проверка (Windows, Git Bash)

```sh
docker compose -f compose.test.yaml up -d --wait db-test       # тестовая БД на 127.0.0.1:55432
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q     # ожидается 147 passed
C:/Users/arizo/.venvs/velox/Scripts/ruff.exe check app tests
docker compose up -d --build                                    # сайт: http://127.0.0.1:8010/ (API_PORT=8010 в .env)
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"   # пароль вводится интерактивно
```

Админка: `http://127.0.0.1:8010/admin` (описание: `docs/admin-panel.md`).

Подсказки по окружению: в Git Bash пути вида `/admin/...` в аргументах подменяются (ставить `MSYS_NO_PATHCONV=1`),
длинные файлы лучше писать инструментом записи, а не heredoc. `docker compose cp` меняет файлы только в текущем
контейнере, после `docker compose up` нужно `--build`.

## Этап 7: Telegram-бот (следующий шаг)

1. Бот на aiogram 3 в сервисе `bot` (`compose.yaml` уже есть, без токена сервис спокойно завершается).
   Код в `app/bot/`: обработчики, клавиатуры, вызовы только сервисов `app/services/` (бронирование через
   `booking.create_hold` / `complete_hold`, перенос и отмена через существующие функции).
2. Сценарий по `design-reference/5` (распаковано в `design-reference/extracted/bot-*.html`): /start с deep-link
   (`service_*`, `gift`, `booking_*`), выбор услуги и авто, дата и время кнопками с удержанием слота
   (`studio.hold_minutes`), имя, «Поделиться номером», подтверждение; «Мои записи», перенос, отмена, вопрос администратору.
3. Чат администраторов: привязка по одноразовому коду из «Настроек», кнопки Подтвердить / Перенести / Отклонить
   с проверкой членства в студии.
4. Outbox-воркер (`app/services/outbox.py`): `FOR UPDATE SKIP LOCKED`, повторы с паузой, статус dead после лимита;
   напоминания за 24 ч и 2 ч, отказ от напоминаний.
5. Мини-приложение `/tg/app` (календарь и контакты) с проверкой подписи `initData`; включается только при HTTPS
   `PUBLIC_BASE_URL` (после деплоя), бот обновляет кнопку меню при старте.
6. Тесты только с моками aiogram, реальные сообщения не отправляются.
7. Создание бота: через Telegram Web пользователя у @BotFather, токен сразу в `.env`, в чат и в Git не попадает.

## Потом

Этап 8 (полный прогон, Docker с нуля, бэкап и восстановление, поиск секретов, CI, тест моделей против миграций),
этап 9 (VPS: сначала спросить адрес и SSH-пользователя, разведка только на чтение, без изменений без согласования).
