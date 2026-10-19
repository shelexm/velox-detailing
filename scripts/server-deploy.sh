#!/bin/sh
# Runs on the server, inside the project directory, after deploy.sh has unpacked the new code.
# Order: dump the database, keep the previous image, build and start, wait until the API is ready, tidy up.
# Output goes to deploy.log; the last line is DEPLOY-OK or DEPLOY-FAILED.
set -u

cd "$(dirname "$0")/.."

env_value() { # value of NAME in .env, empty when absent
    grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2-
}

rev="$(cat REVISION 2>/dev/null || echo unknown)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$(env_value BACKUP_DIR)"
backup_dir="${backup_dir:-./backups}"
port="$(env_value API_PORT)"
port="${port:-8000}"

fail() {
    echo "DEPLOY-FAILED: $1"
    exit 1
}

echo "deploy $rev, $stamp"

# 1. A restore point taken right before the migrations run (the scheduled dump may be a day old).
if docker compose ps --status running --services 2>/dev/null | grep -qx db; then
    mkdir -p "$backup_dir"
    umask 077
    target="$backup_dir/db-predeploy-$stamp.dump"
    if docker compose exec -T db sh -c 'pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"$target.partial" \
        && [ -s "$target.partial" ]; then
        mv "$target.partial" "$target"
        echo "database saved to $target"
    else
        rm -f "$target.partial"
        fail "could not dump the database first; nothing was changed"
    fi
else
    echo "no running database: first deploy, nothing to dump"
fi

# 2. Keep the image that is running now, so going back does not need a rebuild.
if docker image inspect velox-app:latest >/dev/null 2>&1; then
    docker tag velox-app:latest velox-app:prev
fi

# 3. Build and start. The migrate service runs the migrations before api and bot start.
docker compose up -d --build --remove-orphans || fail "docker compose up failed"

# 4. Ready means the database answers and the schema is at the head this code expects.
tries=0
until curl -fsS "http://127.0.0.1:$port/health/ready" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 36 ]; then
        echo "To go back to the previous code:"
        echo "  docker tag velox-app:prev velox-app:latest && docker compose up -d --no-build"
        echo "The database stays at the new schema; restore $backup_dir/db-predeploy-$stamp.dump if the migration is the cause."
        fail "the API is not ready after 3 minutes"
    fi
    sleep 5
done
echo "the API is ready"

# 5. Build cache and dangling images pile up on a small disk; the previous image is tagged and stays.
docker builder prune -f --filter until=72h >/dev/null 2>&1 || true
docker image prune -f >/dev/null 2>&1 || true

echo "DEPLOY-OK"
