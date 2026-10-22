# Настройки (`.env`)

Все настройки приложения берутся из переменных окружения; Docker Compose читает их из файла `.env` рядом
с `compose.yaml`. Образец с безопасными заглушками: `.env.example`. Файл `.env` никогда не попадает в Git
и в Docker-образ (исключён в `.gitignore` и `.dockerignore`).

Настройки студии (контакты, правила записи, тексты сайта) хранятся не здесь, а в базе и меняются в панели.

## Переменные

| Переменная | По умолчанию | Описание |
|---|---|---|
| `COMPOSE_FILE` | `compose.yaml` | На сервере: `compose.yaml:compose.prod.yaml` (лимиты памяти). Разделитель `:` в Linux, `;` в Windows |
| `APP_ENV` | `development` | `development`, `production` или `test`. В `production` включаются строгие проверки (ниже) и выключается `/api/docs` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `POSTGRES_DB` | `velox` | имя базы |
| `POSTGRES_USER` | `velox` | пользователь базы |
| `POSTGRES_PASSWORD` | (обязательно) | пароль базы; в `production` не короче 16 символов. Сгенерировать: `openssl rand -hex 24` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | задаёт compose: `db`, `5432` | менять только при запуске без Docker |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `5`, `10` | размер пула соединений к базе на процесс |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | внешний адрес сайта (`https://velox.stakko.online`). Используется в ссылках бота, в мини-приложении (кнопка календаря появляется только при `https://`), в `sitemap.xml` |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | имена хостов через запятую, на которые отвечает сайт; запросы с другим `Host` отклоняются. Шаблоны вида `*.example.com` разрешены, `*` в `production` запрещён |
| `COOKIE_SECURE` | `true` в `production`, иначе `false` | cookie панели только по HTTPS; в `production` выключить нельзя |
| `SESSION_TTL_HOURS` | `12` | сколько живёт вход в панель |
| `API_PORT` | `8000` | порт на `127.0.0.1` хоста, на который nginx проксирует сайт. Наружу не публикуется |
| `DEFAULT_STUDIO_SLUG` | `velox` | какая студия показывается на сайте и обслуживается ботом |
| `MEDIA_ROOT` | задаёт compose: `/app/media` | где лежат загруженные фото (том `velox_media`) |
| `TELEGRAM_BOT_TOKEN` | пусто | токен бота от @BotFather. Пусто: бот выключен, сайт и панель работают |
| `TELEGRAM_USE_WEBHOOK` | `false` | зарезервировано; бот работает в режиме long polling |
| `BACKUP_DIR` | `./backups` | куда сервис `backup` и `scripts/backup.sh` складывают копии |
| `BACKUP_INTERVAL_SECONDS` | `86400` | как часто делать копию (раз в сутки) |
| `BACKUP_KEEP_DAYS` | `14` | сколько дней хранить копии |
| `FORWARDED_ALLOW_IPS` | задаёт compose: `*` | от кого принимать заголовки `X-Forwarded-*`; безопасно, пока порт API открыт только на `127.0.0.1` |

Только для команды `create-admin`: `ADMIN_PASSWORD` (пароль из переменной вместо ввода с клавиатуры, для
автоматизации; в обычной работе не нужен, вводите пароль интерактивно).

## Проверки в `production`

Приложение не запустится и напишет причину в лог, если:
- `POSTGRES_PASSWORD` короче 16 символов;
- `COOKIE_SECURE=false`;
- в `ALLOWED_HOSTS` есть `*`.

## Пример для сервера

```ini
COMPOSE_FILE=compose.yaml:compose.prod.yaml
APP_ENV=production
LOG_LEVEL=INFO
POSTGRES_DB=velox
POSTGRES_USER=velox
POSTGRES_PASSWORD=<openssl rand -hex 24>
PUBLIC_BASE_URL=https://velox.stakko.online
ALLOWED_HOSTS=velox.stakko.online,topsite.goroshka.ru
COOKIE_SECURE=true
API_PORT=8000
DEFAULT_STUDIO_SLUG=velox
BACKUP_DIR=./backups
BACKUP_INTERVAL_SECONDS=86400
BACKUP_KEEP_DAYS=14
TELEGRAM_BOT_TOKEN=<токен от @BotFather>
```

## Пример для своего компьютера

```ini
APP_ENV=development
POSTGRES_PASSWORD=<любой длинный пароль>
PUBLIC_BASE_URL=http://127.0.0.1:8000
ALLOWED_HOSTS=127.0.0.1,localhost
API_PORT=8000
TELEGRAM_BOT_TOKEN=
```

## Как применить изменения

```sh
cd /opt/velox
nano .env                      # или другой редактор
docker compose up -d           # пересоздаст сервисы, у которых изменились переменные
```

Пересборка образа (`--build`) для смены настроек не нужна.

## Лимиты памяти (`compose.prod.yaml`)

| Сервис | Лимит |
|---|---|
| `db` (PostgreSQL, `shared_buffers=64MB`, до 40 соединений) | 256 МБ |
| `api` | 320 МБ |
| `bot` | 192 МБ |
| `migrate` | 256 МБ (только при запуске) |
| `backup` | 96 МБ |

Рассчитаны на сервер с 1 ГБ памяти, где работают и другие сервисы. На сервере с 2 ГБ и больше лимиты можно
поднять или не подключать `compose.prod.yaml`.
