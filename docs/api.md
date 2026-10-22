# HTTP API

Сайт и панель сами работают через этот API, отдельного «закрытого» API нет. Формат: JSON, кодировка UTF-8,
время в ISO 8601 с часовым поясом (`2026-10-21T10:00:00+03:00`). Цены в рублях, целым числом.

В режиме разработки интерактивное описание всех методов: `/api/docs` (Swagger), схема `/api/openapi.json`.
В `production` оба адреса выключены.

## Общие правила

### Ошибки

Любая ошибка возвращается в одном формате:

```json
{
  "error": {"code": "slot_taken", "message": "Это время уже занято. Выберите другое", "details": {"alternatives": ["2026-10-21T11:00:00+03:00"]}},
  "request_id": "8ff62253322e4c258166803e2ba81798"
}
```

`message` можно показывать человеку (по-русски), `code` предназначен для программ, `request_id` совпадает
с заголовком ответа `X-Request-ID` и строкой в логах сервера. Внутренние подробности (трассировки, SQL)
наружу не выдаются.

| HTTP | `code` | Когда |
|---|---|---|
| 400 | `bad_request` | некорректный запрос |
| 401 | `unauthorized`, `invalid_credentials` | нет входа или неверный e-mail или пароль |
| 403 | `forbidden`, `csrf_failed`, `bad_origin` | нет прав; нет или неверен CSRF-токен; запрос с чужого сайта |
| 404 | `not_found` | нет такого объекта или он принадлежит другой студии |
| 409 | `slot_taken`, `stale_booking`, `hold_expired`, `deadline_passed`, `invalid_status_transition`, `booking_disabled` | время занято (в `details.alternatives` ближайшие свободные), запись изменили параллельно, удержание истекло, поздно отменять онлайн, недопустимая смена статуса, онлайн-запись выключена |
| 409 | `client_has_active_bookings`, `media_in_use`, `staff_has_bookings`, `box_has_bookings`, `last_box`, `category_in_use`, `group_in_use`, `last_owner`, `self_removal`, `member_exists`, `client_exists` | действие нарушает правило данных (смысл понятен из `message`) |
| 422 | `validation_error` | ошибки полей: `details` содержит список `{"field", "message"}` |
| 429 | `rate_limited` | слишком много запросов, повторить позже |
| 503 | | база недоступна (`/health/ready`) |

### Ограничения частоты (по IP посетителя)

| Что | Лимит |
|---|---|
| Чтение публичного API (услуги, свободное время) | 240 запросов в минуту |
| Создание и отмена записи | 10 за 10 минут |
| Вход в панель | 5 неудачных попыток на e-mail и 20 на IP за 15 минут |

### Авторизация (панель)

1. `POST /api/v1/auth/login` с `{"email", "password"}`. В ответе данные пользователя и список студий с ролями;
   ставятся cookie `velox_session` (HttpOnly) и `velox_csrf` (читается скриптом), обе `SameSite`, `Secure`
   при HTTPS.
2. Каждый изменяющий запрос (`POST`, `PATCH`, `PUT`, `DELETE`) к API панели передаёт заголовок
   `X-CSRF-Token` со значением cookie `velox_csrf`. Если браузер прислал `Origin`, он должен совпадать с адресом
   сайта.
3. `POST /api/v1/auth/logout` завершает сессию. `POST /api/v1/auth/password`
   (`{"current_password", "new_password"}`) меняет пароль и завершает сессии на других устройствах.

Роли: **владелец** (owner), **администратор** (admin), **мастер** (master). В таблицах ниже: «все» = любая
роль студии, «упр.» = владелец и администратор, «влад.» = только владелец.

## Служебные

| Метод | Адрес | Ответ |
|---|---|---|
| GET | `/health/live` | `{"status":"ok"}`, если процесс жив |
| GET | `/health/ready` | проверка базы и миграций: `{"status":"ok","checks":{"database":"ok","migrations":"ok"}}`, иначе 503 |

## Публичное API

Префикс: `/api/v1/public/studios/{slug}` (сейчас `slug` = `velox`). Без авторизации.

| Метод | Адрес | Что делает |
|---|---|---|
| GET | `` (сам префикс) | данные студии: название, часовой пояс, город, адрес, телефон, мессенджеры, график, реквизиты |
| GET | `/services` | услуги с онлайн-записью: `id`, `slug`, `name`, `short_description`, `price_from`, `duration_label`, `duration_minutes` или `duration_days`, `staff_selection` (`client` или `studio`), `staff` (мастера для выбора), направление, плашка |
| GET | `/availability?service_id=&date_from=&days=&staff_id=` | свободное время: до 14 дней от `date_from` (по умолчанию сегодня), по каждому дню список слотов `start`, `end`, `available`, `free_places`, `total_places` |
| POST | `/bookings` | создать запись (ниже) |
| GET | `/bookings/manage/{token}` | запись по секретной ссылке: номер, статус, услуга, время, мастер, цена, `can_cancel`, дедлайн отмены |
| POST | `/bookings/manage/{token}/cancel` | отменить по ссылке (не позже дедлайна) |
| GET | `/bookings/manage/{token}/calendar.ics` | файл для календаря |

### Создание записи

```http
POST /api/v1/public/studios/velox/bookings
Content-Type: application/json

{
  "service_id": 14,
  "starts_at": "2026-10-21T10:00:00+03:00",
  "staff_id": null,
  "name": "Алексей",
  "phone": "+7 913 452-18-07",
  "vehicle": "Audi A6, 2021",
  "comment": "Позвоните после 18:00",
  "consent": true
}
```

- `starts_at` берётся из `availability`; `staff_id` можно передать, только если у услуги `staff_selection = client`.
- `phone`: российский номер в любом написании, хранится как `+7XXXXXXXXXX`.
- `consent` обязателен (`true`), иначе 422.
- Поле `website` должно отсутствовать или быть пустым (ловушка для ботов).

Ответ `201`:

```json
{
  "number": 1009, "status": "new", "service_name": "Детейлинг-мойка",
  "starts_at": "2026-10-21T10:00:00+03:00", "ends_at": "2026-10-21T13:00:00+03:00",
  "staff_name": "Олег Г.", "price_from": 4500, "duration_label": "2-3 ч",
  "manage_url": "https://velox.stakko.online/booking/<token>",
  "calendar_url": "https://velox.stakko.online/api/v1/public/studios/velox/bookings/manage/<token>/calendar.ics"
}
```

Если время заняли: `409` с `details.alternatives`. Токен в `manage_url` выдаётся один раз и в базе хранится
только его хеш.

## API панели

Префикс: `/api/v1/admin/studios/{studio_id}`. Нужна сессия и (для изменений) CSRF-токен. Чужая студия
отвечает 404.

### Записи и клиенты

| Метод | Адрес | Роль | Что делает |
|---|---|---|---|
| GET | `/me` | все | роль текущего пользователя в студии |
| GET | `/bookings?date_from=&date_to=&status=&staff_id=&q=` | все | записи за период, `status` можно повторять (мастер видит только свои) |
| GET | `/bookings/{id}` | все | одна запись |
| POST | `/bookings` | упр. | запись из панели (по звонку) |
| PATCH | `/bookings/{id}` | упр. | изменить данные записи (с `version` для защиты от параллельной правки) |
| POST | `/bookings/{id}/status` | упр. | сменить статус |
| POST | `/bookings/{id}/reschedule` | упр. | перенести (время, мастер) |
| GET | `/availability?service_id=&date_from=&days=&staff_id=` | все | тот же расчёт, что видит клиент, плюс заблокированное время (для предпросмотра «Как это видит клиент») |
| GET | `/clients?q=&segment=&limit=&offset=` | упр. | клиенты (сегменты `all`, `regular`, `new`, `lapsed`; до 200 за запрос) |
| POST | `/clients` | упр. | добавить клиента |
| GET, PATCH | `/clients/{id}` | упр. | карточка, правка (имя, метки, заметка, автомобиль, напоминания) |
| DELETE | `/clients/{id}` | влад. | удалить персональные данные (152-ФЗ); ответ `{"bookings_anonymized": N}` |

### Каталог, мастера, расписание, слоты

| Метод | Адрес | Роль | Что делает |
|---|---|---|---|
| POST | `/services` | упр. | новая услуга |
| GET, PATCH, DELETE | `/services/{id}` | упр. | услуга; `DELETE` снимает услугу с сайта, прошлые записи остаются |
| POST | `/services/order` | упр. | порядок услуг |
| POST, PATCH, DELETE | `/categories`, `/categories/{id}`, `/categories/order` | упр. | разделы прайса |
| POST, PATCH, DELETE | `/groups`, `/groups/{id}`, `/groups/order` | упр. | направления на сайте |
| POST | `/staff` | упр. | новый мастер |
| PATCH, DELETE | `/staff/{id}` | упр. | профиль; убрать мастера |
| PUT | `/staff/{id}/hours` | упр. | график мастера |
| PUT | `/staff/{id}/services` | упр. | услуги мастера |
| POST, DELETE | `/staff/{id}/absences`, `/staff/{id}/absences/{absence_id}` | упр. | отпуска и больничные |
| POST | `/staff/order` | упр. | порядок мастеров |
| PUT | `/schedule/hours` | упр. | часы студии и перерывы по дням недели |
| POST, DELETE | `/schedule/special-days`, `/schedule/special-days/{id}` | упр. | выходные и особые дни |
| POST, DELETE | `/schedule/blocks`, `/schedule/blocks/{id}` | упр. | блокировки времени |
| PATCH | `/booking-rules` | упр. | правила записи: шаг, буфер, сроки, удержание, учёт мастеров, онлайн-запись вкл/выкл |
| POST, PATCH, DELETE | `/resources`, `/resources/{id}`, `/resources/order` | упр. | места (боксы) |

### Сайт и медиа

| Метод | Адрес | Роль | Что делает |
|---|---|---|---|
| PATCH | `/sections/{key}` | упр. | содержимое, видимость блока сайта (`hero`, `services`, `works`, `prices`, `telegram`, `about`, `materials`, `process`, `reviews`, `gift`, `contacts`, `final_cta`, `footer`, `seo`); проверяется по схеме блока |
| POST | `/sections/{key}/reset` | упр. | вернуть тексты макета |
| POST | `/sections/order` | упр. | порядок блоков |
| POST, PATCH, DELETE | `/portfolio`, `/portfolio/{id}`, `/portfolio/order` | упр. | «до и после» |
| POST, PATCH, DELETE | `/reviews`, `/reviews/{id}`, `/reviews/order` | упр. | отзывы |
| POST, PATCH, DELETE | `/gifts`, `/gifts/{id}`, `/gifts/order` | упр. | номиналы сертификатов |
| GET | `/media` | упр. | медиатека |
| POST | `/media` | упр. | загрузка (`multipart/form-data`, JPG/PNG/WebP/AVIF до 5 МБ) |
| GET, PATCH, DELETE | `/media/{id}` | упр. | фото: описание, автор, лицензия; удаление только неиспользуемого |
| POST | `/media/{id}/file` | упр. | заменить файл, сохранив все места использования |
| POST | `/media/order` | упр. | порядок |

### Настройки и доступ

| Метод | Адрес | Роль | Что делает |
|---|---|---|---|
| GET | `/settings` | упр. | настройки студии |
| PATCH | `/settings` | влад. | контакты, адрес, реквизиты, username бота, бренд (`brand_name`, `brand_tagline`, `logo_image_id` из медиатеки этой студии); меняются только переданные поля |
| POST | `/telegram/link-code` | влад. | одноразовый код для `/link` в чате администраторов (15 минут) |
| DELETE | `/telegram/admin-chat` | влад. | отвязать чат администраторов |
| POST | `/users` | влад. | выдать доступ (ответ содержит временный пароль, показывается один раз) |
| PATCH, DELETE | `/users/{id}` | влад. | роль, карточка мастера; закрыть доступ |
| POST | `/users/{id}/reset-password` | влад. | новый временный пароль |

## Страницы (HTML)

| Адрес | Что |
|---|---|
| `/`, `/services/{slug}`, `/privacy`, `/credits`, `/booking/{token}` | сайт |
| `/sitemap.xml`, `/robots.txt` | для поисковиков |
| `/favicon.svg` | иконка вкладки: первая буква бренда |
| `/admin/login`, `/admin/{studio_id}/...` | панель |
| `/tg/app?service=` | календарь для бота |
| `/media/{studio_id}/{key}/{file}` | загруженные фото |
| `/static/...` | стили, скрипты, шрифты |
