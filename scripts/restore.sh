#!/bin/sh
# Restore a database dump made by backup.sh or the backup service.
#
#   scripts/restore.sh backups/db-XXXX.dump                 -> restores into a separate database
#                                                              "velox_restore_check", compares exact row
#                                                              counts with the live database, then drops it
#   RESTORE_CONFIRM=yes scripts/restore.sh <dump> live      -> replaces the live database
#                                                              (api and bot are stopped during the restore)
#   RESTORE_CONFIRM=yes scripts/restore.sh <media.tar.gz> media
#                                                           -> unpacks a media archive into the media volume
#                                                              (adds and replaces files, deletes nothing)
set -eu

cd "$(dirname "$0")/.."
dump="${1:?usage: scripts/restore.sh <dump-file> [check|live|media]}"
mode="${2:-check}"
[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 1; }

if [ "$mode" = "media" ]; then
    if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
        echo "Refusing to change the media volume without RESTORE_CONFIRM=yes" >&2
        exit 1
    fi
    gzip -t "$dump"
    docker compose exec -T api tar -xzf - -C /app/media < "$dump"
    files="$(docker compose exec -T api sh -c "tar -tzf - | grep -vc '/\$'" < "$dump")"
    echo "Media restored from $dump ($files files)"
    exit 0
fi

if [ "$mode" = "live" ]; then
    if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
        echo "Refusing to overwrite the live database without RESTORE_CONFIRM=yes" >&2
        exit 1
    fi
    # Only the app services that are running now are stopped, and started again afterwards.
    running="$(docker compose ps --services --status running | grep -E '^(api|bot)$' | tr '\n' ' ' || true)"
    if [ -n "$running" ]; then
        echo "Stopping: $running"
        docker compose stop $running
    fi
    docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$dump"
    if [ -n "$running" ]; then
        docker compose start $running
    fi
    echo "Live database restored from $dump"
    exit 0
fi

target="velox_restore_check"
# Exact row count of every table (pg_stat numbers are estimates and lag right after a restore).
counts_sql="SELECT table_name || ': ' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
count_rows() {
    docker compose exec -T -e TARGET="$1" -e SQL="$counts_sql" db sh -c 'psql -U "$POSTGRES_USER" -d "$TARGET" -At -c "$SQL"'
}

docker compose exec -T -e TARGET="$target" db sh -c \
    'dropdb --if-exists -U "$POSTGRES_USER" "$TARGET" && createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$TARGET"'
docker compose exec -T -e TARGET="$target" db sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$TARGET"' < "$dump"
restored="$(count_rows "$target")"
live="$(count_rows "$(docker compose exec -T db sh -c 'printf %s "$POSTGRES_DB"')")"
echo "Restored into $target. Row counts:"
echo "$restored"
if [ "$restored" = "$live" ]; then
    echo "OK: every table has the same number of rows as the live database."
else
    echo "Differences from the live database (expected if data changed after the dump):"
    printf '%s\n' "$live" > /tmp/velox-live.$$ && printf '%s\n' "$restored" | diff /tmp/velox-live.$$ - || true
    rm -f /tmp/velox-live.$$
fi
# The check copy holds client data too: drop it unless asked to keep it for inspection.
if [ "${KEEP_RESTORE:-}" != "yes" ]; then
    docker compose exec -T -e TARGET="$target" db sh -c 'dropdb -U "$POSTGRES_USER" "$TARGET"'
    echo "Check database $target dropped (KEEP_RESTORE=yes keeps it)."
fi
