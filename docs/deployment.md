# Выкладка на сервер

Текущая установка: VPS Ubuntu 24.04 (1 CPU, 1 ГБ RAM + swap 1 ГБ), адрес `https://topsite.goroshka.ru`
(DNS у afraid.org). На том же сервере работают 3x-ui (xray) и nginx: проект установлен рядом и их не меняет,
кроме одной строки в карте доменов nginx.

## Как устроено

```
интернет :443 ─ nginx stream (SNI) ─┬─ свои домены 3x-ui ─ как раньше
                                    └─ topsite.goroshka.ru ─ 127.0.0.1:10443 (nginx, TLS) ─ 127.0.0.1:8000 (api)
интернет :80  ─ nginx ─ /.well-known/acme-challenge (Let's Encrypt), остальное ─ редирект на https
```

- Проект: `/opt/velox` (код, `.env` с правами 600, `backups/`). Docker compose-проект `velox`, своя сеть,
  тома `velox_pgdata` и `velox_media`. PostgreSQL наружу не публикуется, API слушает только `127.0.0.1:8000`.
- `.env` сервера: `COMPOSE_FILE=compose.yaml:compose.prod.yaml` (лимиты памяти), `APP_ENV=production`,
  `PUBLIC_BASE_URL=https://topsite.goroshka.ru`, `ALLOWED_HOSTS=topsite.goroshka.ru`, `COOKIE_SECURE=true`,
  пароль базы сгенерирован на сервере, `TELEGRAM_BOT_TOKEN` перенесён без вывода на экран.
- nginx: `/etc/nginx/sites-available/topsite.goroshka.ru` (+ ссылка в `sites-enabled`), строка
  `topsite.goroshka.ru velox;` и `upstream velox` в `/etc/nginx/stream-enabled/stream.conf`.
  Копии до изменений: `/root/velox-nginx-backup/` (весь `/etc/nginx`, `stream.conf.before-velox`).
- Сертификат: certbot, способ webroot (`/var/www/html`), продлевается сам, после продления `systemctl reload nginx`.

## Обновление

С компьютера разработчика, из чистого рабочего дерева (уходит только закоммиченный код):

```sh
DEPLOY_HOST=root@89.110.87.55 sh scripts/deploy.sh
ssh root@89.110.87.55 'tail -f /opt/velox/deploy.log'      # ждать DEPLOY-OK
```

Миграции применяет сервис `migrate` при каждом запуске. Откат кода: выложить предыдущий коммит
(`git checkout <commit>` во временной ветке и тот же скрипт); если миграция уже применилась, сначала
восстановить базу из бэкапа.

## Команды на сервере

```sh
cd /opt/velox
docker compose ps                         # состояние
docker compose logs -f api                # логи (телефоны и токены маскируются)
docker compose run --rm api python -m app.cli create-admin --email you@example.com --name "Имя"
sh scripts/backup.sh                      # бэкап вручную в ./backups
sh scripts/restore.sh backups/db-XXXX.dump        # проверка восстановления в отдельную базу
```

Автоматический бэкап базы раз в сутки, хранение 14 дней, `/opt/velox/backups`. Копировать бэкапы за пределы
сервера: `scp root@89.110.87.55:/opt/velox/backups/db-*.dump .`

## Известные особенности сервера

- Скрипт установки 3x-ui однажды сбросил правила iptables, и контейнеры потеряли выход в интернет (сборка
  не видела PyPI). Признак: бот пишет `Cannot connect to host api.telegram.org`. Лечение:
  `systemctl restart docker` (Docker заново создаёт свои правила; xray от этого не зависит).
- SSH иногда отвечает таймаутом с первой попытки: помогает `-o ConnectionAttempts=4`.
- 152-ФЗ: сервер в Нидерландах. Перед приёмом реальных клиентов из РФ базу нужно перенести на сервер в России
  (бэкап, восстановление на новом сервере, смена DNS-записи).

## Переход на другой домен

Новая A-запись на сервер, затем на сервере: блок в карте `stream.conf` и файл сайта под новое имя,
`certbot certonly --webroot -w /var/www/html -d <домен>`, в `.env` поменять `PUBLIC_BASE_URL` и
`ALLOWED_HOSTS`, `docker compose up -d`.
