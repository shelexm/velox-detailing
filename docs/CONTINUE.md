# Как продолжить работу

Состояние: `docs/PROGRESS.md`. Последний коммит на `main` содержит API мастеров (без экрана).

## Запуск и проверка (Windows, Git Bash)

```sh
docker compose -f compose.test.yaml up -d --wait db-test       # тестовая БД на 127.0.0.1:55432
C:/Users/arizo/.venvs/velox/Scripts/python.exe -m pytest -q     # ожидается 115 passed
C:/Users/arizo/.venvs/velox/Scripts/ruff.exe check app tests
docker compose up -d --build                                    # сайт: http://127.0.0.1:8010/ (API_PORT=8010 в .env)
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"   # пароль вводится интерактивно
```

Админка: `http://127.0.0.1:8010/admin`. Сайт уже открывается и работает (этап 5 закрыт).

Подсказки по окружению: в Git Bash пути вида `/admin/...` в аргументах подменяются (ставить `MSYS_NO_PATHCONV=1`), heredoc с длинным текстом иногда не разбирается: длинные файлы писать инструментом записи. Файлы в контейнер можно скопировать `docker compose cp`, но `docker compose up` возвращает образ: после правок пересобирать `--build`.

## Следующий конкретный шаг: экран «Мастера»

1. `app/web/panel/staff.py` (по образцу `app/web/panel/services.py`): список мастеров слева, карточка справа по `design-reference/4/Админка — мастера.png`; загрузка недели: `app/services/stats.py` (добавить расчёт по мастеру).
2. `app/templates/panel/staff.html`: профиль (форма PATCH `/staff/{id}`), услуги (чекбоксы, PUT `/staff/{id}/services`), график 7 дней (PUT `/staff/{id}/hours`, тело `{"days": [...]}`), отсутствия (POST/DELETE `/staff/{id}/absences`), «Добавить мастера», «Убрать мастера» (409 при будущих записях).
3. Подключить в `app/web/panel/__init__.py`, тесты в `tests/api/test_admin_staff.py` и `tests/api/test_panel_pages.py`.

Общие компоненты админки уже есть: `static/js/panel.js` (формы `data-form`, `data-type="int|bool|lines|list|nullable"`, кнопки `data-api`, переключатели `data-toggle`, сортировка `data-move` + `data-order-api`, повторяющиеся строки `data-repeat`), `static/js/media-picker.js`, макросы `app/templates/panel/_macros.html` (`field`, `toggle`, `media_field`, `media_dialog`, `move_buttons`), стили `static/css/panel.css`.

## Дальше по порядку

1. Этап 6: Расписание, Слоты и вместимость, Контент сайта, Медиатека (экран), До и после, Отзывы, Настройки, Доступ; правило приёмки: каждый текст, цена и фото сайта меняются из админки (тест на каждый блок).
2. Этап 7: Telegram-бот (aiogram, outbox-воркер, напоминания), бота создать через Telegram Web пользователя, токен только в `.env`.
3. Этап 8: полный прогон, Docker с нуля, бэкап и восстановление, поиск секретов, CI.
4. Этап 9: деплой на VPS: сначала спросить адрес и SSH-пользователя, разведка только на чтение, ничего не менять без согласования.
