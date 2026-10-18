# VÉLOX Detailing Studio

Сайт, онлайн-запись, панель студии и Telegram-бот для студии детейлинга VÉLOX. Архитектура готова к подключению нескольких студий (SaaS): каждая сущность студии хранит `studio_id`, доступ изолирован.

Стек: Python 3.12, FastAPI, PostgreSQL 17, SQLAlchemy 2 (async), Alembic, Pydantic, aiogram 3, Jinja2 + ванильный JS, Docker Compose.

## Быстрый старт (локально)

Нужны Docker и Docker Compose v2.

```sh
cp .env.example .env
# в .env замените POSTGRES_PASSWORD на длинный случайный пароль, например: openssl rand -hex 24
docker compose up --build
```

Сервисы:

| Сервис | Что делает |
|---|---|
| `db` | PostgreSQL 17, данные в volume `pgdata`, наружу не публикуется |
| `migrate` | Однократно применяет миграции Alembic, затем завершается. Только он меняет схему |
| `api` | FastAPI на `http://127.0.0.1:${API_PORT:-8000}` (порт открыт только на localhost) |
| `bot` | Telegram-бот. Без `TELEGRAM_BOT_TOKEN` пишет предупреждение и завершается с кодом 0 |
| `backup` | Раз в сутки `pg_dump` и архив медиа в `./backups`, хранит 14 дней |

Проверка: `curl http://127.0.0.1:8000/health/ready` отвечает `{"status":"ok","checks":{"database":"ok","migrations":"ok"}}`.

Если порт 8000 занят, задайте `API_PORT` в `.env`.

## Первый администратор

Публичной регистрации нет. Владелец студии создаётся командой (пароль спросит интерактивно, не короче 12 символов):

```sh
docker compose run --rm api python -m app.cli create-admin --email owner@example.com --name "Имя Фамилия"
```

Роли: `--role owner|admin|master` (по умолчанию owner). Сменить пароль: добавить `--reset-password`.
Стартовые данные студии (услуги и цены из макетов, мастера, часы работы) создаёт `python -m app.cli seed`; сервис `migrate` запускает его автоматически и не перезаписывает изменения, сделанные в панели.

## API

- Публичное API формы записи: `/api/v1/public/studios/{slug}/...` (услуги, свободное время, создание заявки, управление заявкой по ссылке, `.ics`).
- Панель студии: `/api/v1/auth/*` (вход, выход), `/api/v1/admin/studios/{studio_id}/...`.
- Интерактивная документация в режиме разработки: `http://127.0.0.1:8000/api/docs`.

Подробности защиты: `docs/security.md`.

## Миграции

Применяются автоматически сервисом `migrate` при каждом `docker compose up`. Вручную:

```sh
docker compose run --rm migrate                       # alembic upgrade head
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
```

Новую миграцию создают из изменённых моделей (нужна запущенная БД):

```sh
docker compose run --rm migrate alembic revision --autogenerate -m "describe change"
```

Схему production-базы руками не меняем: только через миграции.

## Тесты

Тесты работают только с отдельной базой, имя которой оканчивается на `_test`, и только при `APP_ENV=test`. Иначе запуск прерывается.

В Docker (отдельный проект `velox-test`, база на tmpfs, основные данные не затрагиваются):

```sh
docker compose -f compose.test.yaml run --rm --build tests
docker compose -f compose.test.yaml down
```

Локально (Python 3.12):

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.lock && pip install -e . --no-deps
docker compose -f compose.test.yaml up -d --wait db-test   # тестовая БД на 127.0.0.1:55432
pytest
ruff check . && ruff format --check .
```

## Резервное копирование и восстановление

- Автоматически: сервис `backup` (интервал `BACKUP_INTERVAL_SECONDS`, хранение `BACKUP_KEEP_DAYS`, каталог `BACKUP_DIR`).
- Вручную: `sh scripts/backup.sh` (дамп БД и архив медиа в `./backups`).
- Проверка восстановления без риска: `sh scripts/restore.sh backups/db-XXXX.dump` восстанавливает в отдельную базу
  `velox_restore_check`, сравнивает точное число строк каждой таблицы с рабочей базой и удаляет проверочную базу
  (`KEEP_RESTORE=yes` оставляет её для просмотра).
- Восстановление рабочей базы (останавливает работающие api и bot на время восстановления):
  `RESTORE_CONFIRM=yes sh scripts/restore.sh backups/db-XXXX.dump live`
- Восстановление фото из архива (добавляет и заменяет файлы, ничего не удаляет):
  `RESTORE_CONFIRM=yes sh scripts/restore.sh backups/media-XXXX.tar.gz media`
- В Git Bash на Windows перед скриптами нужен `export MSYS_NO_PATHCONV=1` (иначе он подменяет пути вида `/app/media`).

## Зависимости

Версии зафиксированы в `requirements.lock` и `requirements-dev.lock` (собраны `pip-compile` для Linux, из `pyproject.toml`). Обновление:

```sh
docker run --rm -v "$PWD:/src" -w /src python:3.12-slim sh -c \
  "pip install -q pip-tools && pip-compile -q --strip-extras -o requirements.lock pyproject.toml \
   && pip-compile -q --strip-extras --extra dev -o requirements-dev.lock pyproject.toml"
```

## Структура

```
app/            приложение (core, db, models, schemas, repositories, services, api, web, bot)
migrations/     миграции Alembic
tests/          unit, integration, api, bot
scripts/        распаковка макетов, бэкап и восстановление
docs/           документация (аудит макетов и др.)
design-reference/  исходные макеты без изменений + распакованные артборды
```

## Документация

- `docs/design-audit.md`: аудит исходных макетов, карта экранов, медиа, шрифты, проблемы.
