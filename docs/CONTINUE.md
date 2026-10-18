# Как продолжить работу

Состояние: `docs/PROGRESS.md`. Все 9 этапов готовы, сайт: https://topsite.goroshka.ru. Сервер: `docs/deployment.md`.

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

@velox_detailing_bot работает на сервере (токен только в `/opt/velox/.env`). В локальном `.env` токен пустой:
для локальной отладки бота нужен отдельный тестовый бот, иначе два процесса будут забирать одни обновления.

## Обновление сервера

`DEPLOY_HOST=root@89.110.87.55 sh scripts/deploy.sh` из чистого рабочего дерева, затем ждать `DEPLOY-OK`
в `/opt/velox/deploy.log`.

## Дальше (по желанию владельца)

- Перед реальными клиентами: перенос на VPS в России (152-ФЗ), см. `docs/deployment.md`.
- Сменить пароль демо-аккаунта панели («Аккаунт» в панели) или завести свой аккаунт владельца.
- Заменить стоковые фото и демо-отзывы своими через панель.
