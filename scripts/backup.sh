#!/bin/sh
# Manual backup from the host: database dump and media archive into ./backups (or $BACKUP_DIR).
# Usage: scripts/backup.sh
set -eu

cd "$(dirname "$0")/.."
backup_dir="${BACKUP_DIR:-./backups}"
mkdir -p "$backup_dir"
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

docker compose exec -T db sh -c 'pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "$backup_dir/db-$stamp.dump.partial"
mv "$backup_dir/db-$stamp.dump.partial" "$backup_dir/db-$stamp.dump"
echo "database: $backup_dir/db-$stamp.dump"

docker compose exec -T api tar -czf - -C /app/media . > "$backup_dir/media-$stamp.tar.gz"
echo "media:    $backup_dir/media-$stamp.tar.gz"
