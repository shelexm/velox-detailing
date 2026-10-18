# Как продолжить работу

Состояние: `docs/PROGRESS.md`. Этапы 1-6 готовы, следующий этап 7: Telegram-бот.

## Запуск и проверка (Windows, Git Bash)

```sh
docker compose -f compose.test.yaml up -d --wait db-test       # тестовая БД на 127.0.0.1:55432
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q     # ожидается 159 passed
C:/Users/arizo/.venvs/velox/Scripts/ruff.exe check app tests
docker compose up -d --build                                    # сайт: http://127.0.0.1:8010/ (API_PORT=8010 в .env)
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"   # пароль вводится интерактивно
```

Админка: `http://127.0.0.1:8010/admin` (описание: `docs/admin-panel.md`).

Подсказки по окружению: в Git Bash пути вида `/admin/...` в аргументах подменяются (ставить `MSYS_NO_PATHCONV=1`),
длинные файлы лучше писать инструментом записи, а не heredoc. `docker compose cp` меняет файлы только в текущем
контейнере, после `docker compose up` нужно `--build`.

## Этап 7: осталось

Код бота готов (`app/bot/`, `docs/telegram-bot.md`). Осталось: с согласия владельца создать бота у @BotFather
через его Telegram Web (имя, username, описание, команды /start /book /mine), токен сразу в `.env`
(`TELEGRAM_BOT_TOKEN`), username в «Настройках» панели, `docker compose up -d bot`, привязать чат
администраторов кодом из «Настроек» и пройти запись вживую.

## Потом

Этап 8 (полный прогон, Docker с нуля, бэкап и восстановление, поиск секретов, CI, тест моделей против миграций),
этап 9 (VPS: сначала спросить адрес и SSH-пользователя, разведка только на чтение, без изменений без согласования).
