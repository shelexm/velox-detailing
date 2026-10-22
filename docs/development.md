# Разработка и тесты

Как поднять проект у себя, где что лежит, как проверять и выкладывать изменения. Устройство системы:
[architecture.md](architecture.md); правила записи: [booking-model.md](booking-model.md); API: [api.md](api.md).

## Окружение

- Python 3.12, Docker с Compose v2, Git.
- Виртуальное окружение держите **вне** синхронизируемых папок (OneDrive, Dropbox): тысячи файлов в
  синхронизации тормозят. Пример: `C:\Users\<вы>\.venvs\velox` или `~/.venvs/velox`.

```sh
python -m venv ~/.venvs/velox && . ~/.venvs/velox/bin/activate     # Windows: ...\.venvs\velox\Scripts\activate
pip install -r requirements-dev.lock && pip install -e . --no-deps
cp .env.example .env              # POSTGRES_PASSWORD заменить
docker compose up -d --build      # база, миграции, стартовые данные, сайт на 127.0.0.1:${API_PORT}
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"
```

Особенности Windows и Git Bash:
- Git Bash подменяет аргументы вида `/admin/...` и `/app/media` на пути Windows: перед такими командами
  `export MSYS_NO_PATHCONV=1`.
- В `COMPOSE_FILE` разделитель `;`, а не `:`.
- `docker compose cp` меняет файлы только в запущенном контейнере; после правок кода нужен `up -d --build`.

## Тесты

Тесты работают **только** с отдельной базой, имя которой оканчивается на `_test`, и только при `APP_ENV=test`;
иначе запуск прерывается ещё до подключения. Рабочие данные тесты не трогают.

Локально:

```sh
docker compose -f compose.test.yaml up -d --wait db-test    # тестовая база на 127.0.0.1:55432 (tmpfs)
python -m pytest -q
ruff check app tests && ruff format --check app tests
```

В Docker целиком, с покрытием (отдельный compose-проект `velox-test`):

```sh
docker compose -f compose.test.yaml run --rm --build tests
docker compose -f compose.test.yaml down
```

Наборы:

| Папка | Что проверяет |
|---|---|
| `tests/unit` | расчёт слотов (перерывы, особые дни, буфер, сроки, многодневные услуги, отпуска), переходы статусов, телефоны, настройки, маскировка в логах |
| `tests/integration` | ограничения базы (EXCLUDE), параллельные записи на один слот, удержания, изоляция студий, номера записей при гонке, миграции (откат до нуля и обратно, сверка моделей со схемой через `alembic check`), идемпотентность стартовых данных |
| `tests/api` | публичное API и форма, авторизация, CSRF, роли, межстудийный доступ, панель (все страницы), контент сайта (изменение каждого блока видно на сайте), медиа, удаление данных клиента, мини-приложение |
| `tests/bot` | диалог записи, кнопки «Назад», выбор из календаря, «Мои записи», перенос и отмена, чат администраторов, очередь уведомлений с повторами, напоминания, описание бота |

Бот тестируется на поддельных объектах Telegram, реальные сообщения в тестах не отправляются.

Перед коммитом: `ruff check`, `ruff format`, `pytest`. CI (`.github/workflows/ci.yml`) на каждый push и pull
request повторяет это на чистой PostgreSQL и дополнительно ищет в файлах репозитория токены и ключи.

## Миграции

Применяются автоматически сервисом `migrate` при каждом `docker compose up`. Вручную:

```sh
docker compose run --rm migrate                         # alembic upgrade head + стартовые данные
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
```

Новая миграция из изменённых моделей (база должна быть запущена):

```sh
docker compose run --rm migrate alembic revision --autogenerate -m "describe change"
```

Правила:
- файлы в `migrations/versions/` с именем `<дата>_<номер>_<суть>.py`, ревизии по порядку (`0001`, `0002`, ...);
- у каждой миграции рабочий `downgrade` (тест откатывает все миграции до нуля);
- `alembic check` в тестах падает, если модели и схема разошлись: значит, забыли миграцию;
- схему рабочей базы руками не меняем, только миграциями.

## Как устроен код (коротко)

- **Сервисы** (`app/services/`) содержат всю логику; маршруты API, страницы панели и бот только вызывают их.
  Любое создание или изменение записи идёт через `app/services/booking.py`.
- **Каждый запрос к данным студии** получает `studio_id` явно (из проверенного членства или публичного slug).
- **Контент сайта** (`app/content/sections.py`): у каждого блока главной есть Pydantic-схема; по ней
  проверяется сохранение и строится форма в панели. Новый блок: схема, запись в `SECTION_MODELS` (и название
  для панели), шаблон `app/templates/site/sections/<key>.html`, стартовые тексты в `app/seed/content.py`.
- **Шаблоны** не содержат пользовательских текстов, цен и фото: всё из базы.
- **JavaScript** без фреймворков, модули ES. Панель: общий `static/js/panel.js` (формы `data-form`,
  кнопки `data-api`, переключатели `data-toggle`, порядок `data-move`) и скрипты страниц.
- **Тексты бота** только в `app/bot/texts.py`, клавиатуры в `app/bot/keyboards.py`.
- **Время** хранится в UTC, показывается в часовом поясе студии (по умолчанию `Europe/Moscow`, меняется в «Настройках»).
- В текстах, документации и коммитах не используется длинное тире: только дефис, двоеточие или запятая.

## Зависимости

Версии зафиксированы в `requirements.lock` и `requirements-dev.lock` (собраны `pip-compile` для Linux из
`pyproject.toml`). Обновление:

```sh
docker run --rm -v "$PWD:/src" -w /src python:3.12-slim sh -c \
  "pip install -q pip-tools && pip-compile -q --strip-extras -o requirements.lock pyproject.toml \
   && pip-compile -q --strip-extras --extra dev -o requirements-dev.lock pyproject.toml"
```

После обновления: полный прогон тестов и сборка образа.

## Git и выкладка

- Ветка `main`, приватный репозиторий `shelexm/velox-detailing`. Коммиты маленькие, в стиле Conventional
  Commits (`feat(bot): ...`, `fix(booking): ...`, `docs: ...`).
- Никогда не коммитить `.env`, токены, ключи, дампы базы, реальные данные клиентов. `git add` только
  конкретных файлов.
- Без `push --force` и переписывания истории.
- Выкладка на сервер: `DEPLOY_HOST=root@89.110.87.55 sh scripts/deploy.sh` (подробно: [deployment.md](deployment.md#5-обновление-и-откат)).

## Локальный бот

Боевой бот работает на сервере, его токен локально не используется (один токен нельзя запускать в двух местах).
Для отладки: создать у @BotFather отдельного тестового бота, его токен в локальный `.env`,
`docker compose up -d bot`.
