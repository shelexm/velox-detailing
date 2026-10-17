#!/bin/sh
# Restore a database dump made by backup.sh or the backup service.
#
#   scripts/restore.sh backups/db-XXXX.dump                 -> restores into a separate database
#                                                              "velox_restore_check" and prints row counts
#   RESTORE_CONFIRM=yes scripts/restore.sh <dump> live      -> replaces the live database
#                                                              (api and bot are stopped during the restore)
set -eu

cd "$(dirname "$0")/.."
dump="${1:?usage: scripts/restore.sh <dump-file> [check|live]}"
mode="${2:-check}"
[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 1; }

if [ "$mode" = "live" ]; then
    if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
        echo "Refusing to overwrite the live database without RESTORE_CONFIRM=yes" >&2
        exit 1
    fi
    echo "Stopping api and bot..."
    docker compose stop api bot
    docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$dump"
    docker compose start api bot
    echo "Live database restored from $dump"
    exit 0
fi

target="velox_restore_check"
docker compose exec -T -e TARGET="$target" db sh -c \
    'dropdb --if-exists -U "$POSTGRES_USER" "$TARGET" && createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$TARGET"'
docker compose exec -T -e TARGET="$target" db sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$TARGET"' < "$dump"
echo "Restored into $target. Row counts:"
docker compose exec -T -e TARGET="$target" db sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$TARGET\" -At -c \"SELECT relname || ': ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname\""
