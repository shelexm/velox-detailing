# Как продолжить работу

## Уже готово (этап 5)

- `app/models/content.py`, миграция `migrations/versions/20261017_0004_*`: медиатека, кейсы до/после, отзывы, сертификаты, блоки сайта.
- `app/services/media.py`: проверка загрузок, варианты AVIF/WebP/JPEG, запрет удаления используемых фото.
- `app/content/sections.py`: модели всех блоков лендинга с текстами из макетов.
- `app/seed/` (`media_data.py`, `content.py`, `media/`): 29 стартовых изображений с лицензиями, тексты, кейсы, отзывы (ДЕМО), сертификаты. Запуск: `python -m app.cli seed`.
- `app/web/context.py`, `app/web/templating.py`, `app/web/site.py`: данные страницы, хелперы `picture`/`art_picture`, маршруты `/`, `/services/{slug}`, `/booking/{token}`, `/privacy`, `/credits`, `/media/...`, `robots.txt`, `sitemap.xml`.
- `app/templates/site/*`: все шаблоны. `static/css/site.css`, `static/fonts/*`, `static/img/*`.

## Шаги подключения (по порядку)

1. `app/main.py`:
   - `from fastapi.staticfiles import StaticFiles`, `from app.web import site`;
   - `app.include_router(site.router)` (после API-роутеров);
   - `app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")`;
   - `app.state.html_error_renderer = site.render_error`.
2. `app/core/security.py`: в `CSP` добавить `"style-src-attr 'unsafe-inline'"` (шаблоны используют `style="object-position: ..."`).
3. QR-код: добавить `segno` в `pyproject.toml`, пересобрать lock-файлы (команда в README), в `templating.py` добавить глобальную функцию `qr_svg(url)` (`segno.make(url).svg_inline(...)`), её вызывает `sections/telegram.html`.
4. `compose.yaml`: сервису `migrate` добавить `volumes: - media:/app/media` (seed пишет туда изображения).
5. Написать `static/js/site.js` (подключён в `base.html` как модуль). Нужно: шапка `.is-compact` при прокрутке, `<dialog id="mobile-menu">`, `.reveal` через IntersectionObserver, слайдер до/после (CSS-переменная `--pos` на `.ba`, кнопки `[data-case-pick]`), аккордеон цен на мобильном, выбор сертификата `[data-gift-pick]`, окно услуги (`fetch('/services/<slug>?fragment=1')` в `#service-dialog`), `.sticky-bar.is-visible` после первого экрана, мобильный мастер записи `#booking-sheet`.
6. Логика формы записи `[data-booking-form]`: API `/api/v1/public/studios/velox/services`, `/availability?service_id=&date_from=&days=14&staff_id=`, `POST /bookings` (`service_id, starts_at, staff_id, name, phone, vehicle, consent: true, website: ""`). Ошибки: 422 `details[].field`, 409 `slot_taken` с `details.alternatives`.
7. Тесты: страницы отдают 200, нет заглушек (`[ГОРОД]`, `+7 [000]`, `VELOX_BOT_USERNAME`), пути `/static` и `/media` существуют, пустые контакты не выводятся.

## Команды

```sh
docker compose -f compose.test.yaml up -d --wait db-test   # тестовая БД
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m ruff check . && C:/Users/arizo/.venvs/velox/Scripts/python.exe -m ruff format --check .
docker compose up -d --build                                # стек (API_PORT=8010 в .env)
docker compose -f compose.test.yaml run --rm --build tests  # тесты в Docker
```

Проверка сайта: открыть `http://127.0.0.1:8010/` в Chrome, сравнить с PNG в `design-reference/2` (desktop) и `design-reference/3` (mobile, ширина 390).

## Потом

Этап 6 (экраны админки по `design-reference/4`), этап 7 (бот aiogram по `design-reference/5`, outbox-воркер), этап 8 (финальная проверка), этап 9 (деплой: сначала спросить SSH-хост и пользователя, только чтение до согласования).
