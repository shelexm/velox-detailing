# Как продолжить работу

Состояние: `docs/PROGRESS.md`. Этапы 1-8 готовы, следующий этап 9: выкладка на VPS.

## Запуск и проверка (Windows, Git Bash)

```sh
docker compose -f compose.test.yaml up -d --wait db-test       # тестовая БД на 127.0.0.1:55432
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q     # ожидается 163 passed
C:/Users/arizo/.venvs/velox/Scripts/ruff.exe check app tests
docker compose up -d --build                                    # сайт: http://127.0.0.1:8010/ (API_PORT=8010 в .env)
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"   # пароль вводится интерактивно
```

Админка: `http://127.0.0.1:8010/admin` (описание: `docs/admin-panel.md`).

Подсказки по окружению: в Git Bash пути вида `/admin/...` в аргументах подменяются (ставить `MSYS_NO_PATHCONV=1`),
длинные файлы лучше писать инструментом записи, а не heredoc. `docker compose cp` меняет файлы только в текущем
контейнере, после `docker compose up` нужно `--build`.

## Бот

@velox_detailing_bot создан, токен только в локальном `.env`. Локально бот работает против локальной базы.
При выкладке: токен в `.env` сервера, локальный бот остановить (`docker compose stop bot`), иначе два процесса
будут забирать одни и те же обновления; чат администраторов привязать заново кодом из «Настроек».

## Потом

Этап 9 (VPS: сначала спросить адрес и SSH-пользователя, разведка только на чтение, без изменений без согласования).
