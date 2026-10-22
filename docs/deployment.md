# Сервер: установка, обновление, бэкапы

Документ для того, кто обслуживает сервер. Команды выполняются по SSH от root (или через `sudo`).

Содержание:
1. [Текущая установка](#1-текущая-установка)
2. [Требования к серверу](#2-требования-к-серверу)
3. [Установка с нуля](#3-установка-с-нуля)
4. [Первый владелец](#первый-владелец)
5. [Обновление и откат](#5-обновление-и-откат)
6. [Резервные копии](#6-резервные-копии)
7. [Ежедневное обслуживание](#7-ежедневное-обслуживание)
8. [Известные особенности этого сервера](#известные-особенности-этого-сервера)
9. [Переезд на другой сервер (например, в Россию)](#9-переезд-на-другой-сервер)
10. [Смена домена](#10-смена-домена)
11. [Безопасность сервера](#11-безопасность-сервера)

## 1. Текущая установка

| | |
|---|---|
| Адрес | https://topsite.goroshka.ru (DNS: afraid.org, A-запись на IP сервера) |
| Сервер | VPS Ubuntu 24.04, 1 CPU, 1 ГБ RAM + swap 1 ГБ (`/swapfile`), диск 10 ГБ, Нидерланды |
| Соседи | 3x-ui (xray) и nginx пользователя: работают как раньше |
| Проект | `/opt/velox`: код, `.env` (права 600), `backups/`, `deploy.log`, `REVISION` (выложенный коммит) |
| Docker | compose-проект `velox`: `db`, `migrate`, `media-init`, `api`, `bot`, `backup`; тома `velox_pgdata`, `velox_media` |
| Наружу | только через nginx; API слушает `127.0.0.1:8000`, PostgreSQL не опубликован; фаервол не менялся |
| Сертификат | Let's Encrypt через certbot (способ webroot), продлевается таймером `certbot.timer` |

Схема:

```
интернет :443 ─ nginx stream (SNI) ─┬─ домены 3x-ui ─ как раньше (xray, панель)
                                    └─ topsite.goroshka.ru ─ 127.0.0.1:10443 (nginx, TLS) ─ 127.0.0.1:8000 (api)
интернет :80  ─ nginx ─ /.well-known/acme-challenge (проверка Let's Encrypt), остальное ─ редирект на https
```

Что было добавлено в nginx (копии всего до изменений: `/root/velox-nginx-backup/`):
- `/etc/nginx/sites-available/topsite.goroshka.ru` и ссылка в `sites-enabled`;
- в `/etc/nginx/stream-enabled/stream.conf` строка `topsite.goroshka.ru velox;` в карте доменов и блок
  `upstream velox { server 127.0.0.1:10443; }`.

## 2. Требования к серверу

- Linux (проверено на Ubuntu 22.04/24.04), Docker 24+ с Compose v2 (`docker compose version`).
- Минимум 1 ГБ RAM **и** swap 1 ГБ (сборка образа и PostgreSQL). Комфортно: 2 ГБ.
- 3 ГБ свободного диска: образы около 0,8 ГБ, плюс бэкапы (около 30 МБ в сутки за счёт фото, хранятся 14 дней).
- Исходящий доступ в интернет (PyPI при сборке, `api.telegram.org` для бота).
- Домен с A-записью на сервер и открытые порты 80 и 443 для HTTPS.
- Для реальных клиентов из России: сервер в России (152-ФЗ, хранение персональных данных).

## 3. Установка с нуля

### 3.1. Подготовка сервера

```sh
apt-get update && apt-get install -y docker.io docker-compose-v2   # или Docker из официального репозитория
systemctl enable --now docker
# swap 1 ГБ, если памяти 1-2 ГБ
fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-velox-swap.conf && sysctl -p /etc/sysctl.d/99-velox-swap.conf
```

Проверка, что контейнеры видят интернет (важно, см. [особенности](#известные-особенности-этого-сервера)):

```sh
docker run --rm postgres:17-alpine sh -c 'wget -q -T 8 -O /dev/null https://pypi.org/simple/ && echo ok'
```

### 3.2. Код

С компьютера разработчика (в репозитории, рабочее дерево чистое). Здесь и ниже `ПОЛЬЗОВАТЕЛЬ@СЕРВЕР`: SSH-пользователь
и адрес вашего сервера, настоящие значения в документацию не пишутся.

```sh
ssh ПОЛЬЗОВАТЕЛЬ@СЕРВЕР 'mkdir -p /opt/velox && chmod 750 /opt/velox'
git archive --format=tar HEAD -- . ':!design-reference' | gzip | ssh ПОЛЬЗОВАТЕЛЬ@СЕРВЕР 'tar -xzf - -C /opt/velox'
```

(Или `git clone` приватного репозитория на сервер через read-only deploy key.)

### 3.3. Файл `.env`

На сервере, в `/opt/velox` (полное описание переменных: [configuration.md](configuration.md)):

```sh
cd /opt/velox
umask 077
cat > .env <<ENV
COMPOSE_FILE=compose.yaml:compose.prod.yaml
APP_ENV=production
POSTGRES_DB=velox
POSTGRES_USER=velox
POSTGRES_PASSWORD=$(openssl rand -hex 24)
PUBLIC_BASE_URL=https://ДОМЕН
ALLOWED_HOSTS=ДОМЕН
COOKIE_SECURE=true
API_PORT=8000
DEFAULT_STUDIO_SLUG=velox
BACKUP_DIR=./backups
BACKUP_INTERVAL_SECONDS=86400
BACKUP_KEEP_DAYS=14
TELEGRAM_BOT_TOKEN=
ENV
```

Токен бота вписать отдельно (редактором на сервере), не передавая его через чат или почту.

### 3.4. Запуск

```sh
cd /opt/velox
docker compose up -d --build          # сборка 3-5 минут на 1 CPU
docker compose ps                     # api: healthy, db: healthy, migrate: exited (0)
curl -s http://127.0.0.1:8000/health/ready   # {"status":"ok",...}
```

При первом запуске `migrate` создаёт таблицы и стартовые данные (услуги, цены, мастера, часы работы,
тексты и фото сайта). Стартовые данные создаются один раз, для новой студии: при следующих запусках (а они идут при каждой выкладке) ничего не создаётся и не меняется, поэтому переименованные, удалённые и изменённые вами мастера, услуги, отзывы и тексты не возвращаются.

Если связь по SSH может оборваться, запускайте сборку отвязанной от сессии:
`setsid nohup sh -c 'docker compose up -d --build; echo DONE' > deploy.log 2>&1 &`

### 3.5. HTTPS через nginx

**Вариант А: на сервере нет других сайтов на 443.** Обычный nginx и certbot:

```nginx
# /etc/nginx/sites-available/ДОМЕН
server {
    listen 80;
    server_name ДОМЕН;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name ДОМЕН;
    ssl_certificate /etc/letsencrypt/live/ДОМЕН/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ДОМЕН/privkey.pem;
    client_max_body_size 8m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Порядок: сначала только блок на 80, `nginx -t && systemctl reload nginx`, затем
`certbot certonly --webroot -w /var/www/html -d ДОМЕН --deploy-hook "systemctl reload nginx"`, затем блок на 443,
снова `nginx -t && systemctl reload nginx`.

**Вариант Б: порт 443 уже делится по SNI (как на текущем сервере с 3x-ui).** Наш сайт слушает
`127.0.0.1:10443 ssl http2 proxy_protocol`, в карту `stream` добавляется строка с доменом. Готовый файл:
`/etc/nginx/sites-available/topsite.goroshka.ru` на текущем сервере. Реальный IP посетителя берётся из
`$proxy_protocol_addr` (иначе ограничения частоты запросов считали бы всех посетителей одним адресом).

Заголовки безопасности (HSTS, CSP и другие) ставит само приложение, в nginx их добавлять не нужно.

### Первый владелец

```sh
cd /opt/velox
docker compose run --rm api python -m app.cli create-admin --email owner@example.com --name "Имя Фамилия"
```

Пароль вводится дважды прямо в терминале (не короче 12 символов) и нигде не сохраняется в открытом виде.
Остальных сотрудников владелец добавляет в панели («Доступ»).

Забыт пароль владельца:

```sh
docker compose run --rm api python -m app.cli create-admin --email owner@example.com --name "Имя" --reset-password
```

Другая роль: `--role admin` или `--role master`.

## 5. Обновление и откат

С компьютера разработчика, из чистого рабочего дерева (уходит только закоммиченный код, `.env`, бэкапы и тома
на сервере не трогаются):

```sh
DEPLOY_HOST=ПОЛЬЗОВАТЕЛЬ@СЕРВЕР sh scripts/deploy.sh
ssh ПОЛЬЗОВАТЕЛЬ@СЕРВЕР 'tail -f /opt/velox/deploy.log'     # ждать DEPLOY-OK или DEPLOY-FAILED
```

Скрипт копирует код в `/opt/velox`, записывает коммит в `REVISION` и запускает на сервере
`scripts/server-deploy.sh` отвязанно от SSH. Тот по порядку: делает дамп базы `db-predeploy-<время>.dump` в папку
бэкапов (если дамп не получился, ничего не меняет и пишет `DEPLOY-FAILED`), помечает работающий образ тегом
`velox-app:prev`, собирает и запускает стек (миграции применяет `migrate` перед стартом `api` и `bot`), ждёт
до трёх минут, пока `/health/ready` не ответит `ok`, чистит кэш сборки и ненужные образы и пишет `DEPLOY-OK`.
Если сервис не поднялся, в `deploy.log` будет `DEPLOY-FAILED` и готовая команда отката.
Перезапуск `api` занимает несколько секунд; бот при перезапуске теряет незаконченные диалоги (клиенты
начинают запись заново).

Проверка после выкладки:

```sh
curl -s https://topsite.goroshka.ru/health/ready
ssh ПОЛЬЗОВАТЕЛЬ@СЕРВЕР 'cd /opt/velox && cat REVISION && docker compose ps'
```

**Откат кода:** быстрый, без пересборки, пока образ `velox-app:prev` на месте:
`docker tag velox-app:prev velox-app:latest && docker compose up -d --no-build`. Либо выложить предыдущий коммит
(`git checkout <коммит>` во временной ветке, тот же скрипт, затем вернуться на `main`). Если новая версия успела
применить миграцию базы, сначала восстановить базу из `db-predeploy-<время>.dump` (см. ниже), потом возвращать код.

Дамп перед каждой выкладкой делается сам; ручной бэкап (`ssh ПОЛЬЗОВАТЕЛЬ@СЕРВЕР 'cd /opt/velox && sh scripts/backup.sh'`) нужен перед работами на самом сервере.

## 6. Резервные копии

**Автоматически:** сервис `backup` раз в сутки (`BACKUP_INTERVAL_SECONDS`) кладёт в `/opt/velox/backups`
дамп базы `db-<время>.dump` и архив фото `media-<время>.tar.gz`, файлы старше 14 дней (`BACKUP_KEEP_DAYS`)
удаляет, но только пока есть свежий дамп: если дампы перестали получаться, последние рабочие копии остаются. Первая копия делается через 30 секунд после запуска сервиса.

**Вручную:** `cd /opt/velox && sh scripts/backup.sh`.

**Копия за пределами сервера** (бэкапы на том же сервере не спасут при его потере):

```sh
scp 'ПОЛЬЗОВАТЕЛЬ@СЕРВЕР:/opt/velox/backups/db-*.dump' ./velox-backups/
```

Храните копии там, где есть только у вас доступ: в них телефоны и имена клиентов.

**Проверка, что бэкап восстанавливается** (безопасно, рабочая база не трогается):

```sh
sh scripts/restore.sh backups/db-XXXX.dump
```

Восстанавливает во временную базу `velox_restore_check`, сравнивает число строк каждой таблицы с рабочей
базой, печатает «OK» или различия и удаляет временную базу (`KEEP_RESTORE=yes` оставит её для просмотра).
Делать раз в месяц.

**Восстановление рабочей базы** (заменяет текущие данные; на время останавливает `api` и `bot`):

```sh
RESTORE_CONFIRM=yes sh scripts/restore.sh backups/db-XXXX.dump live
```

**Восстановление фото** (добавляет и заменяет файлы, ничего не удаляет):

```sh
RESTORE_CONFIRM=yes sh scripts/restore.sh backups/media-XXXX.tar.gz media
```

## 7. Ежедневное обслуживание

```sh
cd /opt/velox
docker compose ps                               # состояние сервисов
docker compose logs --tail 100 api              # логи сайта (телефоны и токены в логах маскируются)
docker compose logs --tail 100 bot              # логи бота
docker stats --no-stream                        # память контейнеров (лимиты: api 320 МБ, bot 192 МБ, db 256 МБ)
df -h / && du -sh backups                       # диск
free -h                                         # память и swap
certbot certificates                            # срок сертификатов
certbot renew --dry-run                         # проверка продления
```

`/health/live` отвечает, если процесс жив; `/health/ready` дополнительно проверяет базу и что миграции применены.
Их удобно подключить к внешнему мониторингу (например, UptimeRobot: проверка `https://ДОМЕН/health/ready`
раз в 5 минут).

Логи Docker ротируются: до 5 файлов по 10 МБ на сервис.

## Известные особенности этого сервера

- **Docker без доступа в интернет.** Установка 3x-ui однажды сбросила правила iptables, и контейнеры потеряли
  выход наружу (сборка не видела PyPI, бот не видел Telegram). Признак: в логах бота
  `Cannot connect to host api.telegram.org`. Лечение: `systemctl restart docker` (Docker заново создаёт свои
  правила; xray от этого не зависит). Если повторится после перезапуска 3x-ui или сервера, сделать то же самое.
- **SSH иногда отвечает таймаутом** с первой попытки (и сайт с того же компьютера иногда не открывается, вместе
  с доменом панели 3x-ui): это связь между компьютером и сервером, а не сайт. Помогает
  `ssh -o ConnectionAttempts=4 ...`; доступность сайта проверять из другой сети (телефон через мобильный интернет).
- **Память.** Свободно около 250-450 МБ, swap используется. Лимиты памяти в `compose.prod.yaml` не дают
  нашим сервисам вытеснить xray.
- **152-ФЗ.** Сервер в Нидерландах: до приёма реальных клиентов из РФ перенести на сервер в России (раздел 9).

## 9. Переезд на другой сервер

Например, на российский VPS. Простой сайта около 10-15 минут (время смены DNS).

1. На новом сервере: [подготовка](#31-подготовка-сервера), [код](#32-код), [`.env`](#33-файл-env) (тот же домен,
   новый пароль базы, тот же токен бота), но **пока не запускать**.
2. На старом сервере: `cd /opt/velox && docker compose stop bot api && sh scripts/backup.sh` (бот и сайт
   остановлены, чтобы не появились новые записи).
3. Перенести последние `db-*.dump` и `media-*.tar.gz` в `/opt/velox/backups` нового сервера (`scp`), сверить
   `md5sum` на обоих концах.
4. На новом: `docker compose up -d --wait db`, затем
   `RESTORE_CONFIRM=yes sh scripts/restore.sh backups/db-XXXX.dump live`, затем `docker compose up -d`,
   затем `RESTORE_CONFIRM=yes sh scripts/restore.sh backups/media-XXXX.tar.gz media`.
5. Сменить A-запись домена на новый IP (afraid.org), дождаться обновления DNS, выпустить сертификат на новом
   сервере ([раздел 3.5](#35-https-через-nginx)).
6. Проверить сайт, вход в панель, бота (`/start`). Чат администраторов привязан в базе и продолжит работать.
7. На старом сервере: `cd /opt/velox && docker compose down` (тома и бэкапы остаются, пока их не удалить вручную),
   убрать строку домена из `stream.conf` и файл сайта, `nginx -t && systemctl reload nginx`.

## 10. Смена домена

1. A-запись нового домена на сервер.
2. nginx: строка нового домена в карте `stream.conf` (вариант Б) или новый `server_name` (вариант А), файл сайта
   под новое имя, `certbot certonly --webroot -w /var/www/html -d НОВЫЙ_ДОМЕН`.
3. В `/opt/velox/.env`: `PUBLIC_BASE_URL=https://НОВЫЙ_ДОМЕН`, `ALLOWED_HOSTS=НОВЫЙ_ДОМЕН`.
4. `cd /opt/velox && docker compose up -d` (пересборка не нужна).

Ссылки в старых сообщениях бота и в письмах клиентов будут вести на старый домен: если возможно, оставьте на
старом домене редирект на новый.

## 11. Безопасность сервера

Сделано: вход по SSH-ключу, `.env` с правами 600 и владельцем root, база и API не опубликованы наружу,
фаервол (ufw: 22, 80, 443) не менялся, лимиты памяти контейнеров.

Рекомендуется (по решению владельца сервера, это влияет и на 3x-ui):
- отключить вход по паролю в SSH (`PasswordAuthentication no` в `/etc/ssh/sshd_config.d/`), убедившись, что
  ключ работает;
- поставить `fail2ban` для SSH;
- регулярно `apt-get upgrade` (обновления безопасности Ubuntu);
- хранить копии бэкапов вне сервера.

Подробности защиты самого приложения: [security.md](security.md).
