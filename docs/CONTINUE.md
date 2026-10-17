# Как продолжить работу

Этапы 1-5 готовы (см. `docs/PROGRESS.md`). Следующий этап 6: админка.

## Этап 6. Админка

- Экраны по `design-reference/4` (распакованные артборды в `design-reference/extracted/`): вход, главная (KPI, таймлайн боксов, новые заявки), записи (неделя/день, drawer, создание, отмена), расписание, услуги, мастера, слоты и вместимость, клиенты, мобильная админка.
- Экраны вне макета в той же визуальной системе: медиатека (`app/services/media.py`), портфолио до/после, отзывы, контент сайта (формы по `app/content/sections.py`, видимость и порядок блоков, пакеты, сертификаты, короткие названия направлений), настройки студии, пользователи (owner).
- API уже есть: `/api/v1/auth/*`, `/api/v1/admin/studios/{studio_id}/*` (записи, доступность, клиенты, настройки). Нужно добавить CRUD каталога, расписания, медиа и контента.
- Первый владелец: `docker compose run --rm api python -m app.cli create-admin` (пароль вводится интерактивно).

## Команды

```sh
docker compose -f compose.test.yaml up -d --wait db-test   # тестовая БД
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m ruff check . && C:/Users/arizo/.venvs/velox/Scripts/python.exe -m ruff format --check .
docker compose up -d --build                                # стек (API_PORT=8010 в .env)
docker compose -f compose.test.yaml run --rm --build tests  # тесты в Docker
```

Проверка сайта: `http://127.0.0.1:8010/`, сравнение с PNG в `design-reference/2` (desktop) и `design-reference/3` (mobile, 390 px).

## Потом

Этап 7 (бот aiogram по `design-reference/5`, outbox-воркер), этап 8 (финальная проверка), этап 9 (деплой: сначала спросить SSH-хост и пользователя, только чтение до согласования).
