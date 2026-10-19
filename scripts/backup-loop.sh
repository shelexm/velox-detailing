#!/bin/sh
# Runs inside the `backup` compose service: a PostgreSQL dump plus a media archive
# every BACKUP_INTERVAL_SECONDS, keeping BACKUP_KEEP_DAYS days of files in /backups.
set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
umask 077
trap 'echo "backup: stopping"; exit 0' TERM INT

run_backup() {
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    if pg_dump --format=custom --file="/backups/db-${stamp}.dump.partial"; then
        mv "/backups/db-${stamp}.dump.partial" "/backups/db-${stamp}.dump"
        echo "backup: database saved to db-${stamp}.dump"
    else
        rm -f "/backups/db-${stamp}.dump.partial"
        echo "backup: pg_dump failed" >&2
    fi
    if [ -d /srv/media ]; then
        tar -czf "/backups/media-${stamp}.tar.gz.partial" -C /srv/media . \
            && mv "/backups/media-${stamp}.tar.gz.partial" "/backups/media-${stamp}.tar.gz" \
            && echo "backup: media saved to media-${stamp}.tar.gz"
    fi
    find /backups -maxdepth 1 -type f -name '*.partial' -mtime +1 -delete
    # Old copies go only while a recent dump exists: if dumps have been failing, the last good ones stay.
    if [ -n "$(find /backups -maxdepth 1 -type f -name 'db-*.dump' -mtime "-${KEEP_DAYS}" | head -n 1)" ]; then
        find /backups -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) -mtime "+${KEEP_DAYS}" -delete
    fi
}

# Give the database a moment after startup, then back up on the interval.
sleep 30 &
wait $!
while true; do
    run_backup
    sleep "${INTERVAL}" &
    wait $!
done
