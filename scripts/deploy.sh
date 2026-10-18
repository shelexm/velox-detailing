#!/bin/sh
# Ship the committed code (HEAD, without design-reference) to the server and rebuild the stack there.
#
#   DEPLOY_HOST=root@203.0.113.10 sh scripts/deploy.sh
#
# The server keeps its own .env, backups and Docker volumes; only the code is replaced. The build runs
# detached on the server (a dropped SSH connection does not stop it); its log is in $DEPLOY_DIR/deploy.log.
set -eu

cd "$(dirname "$0")/.."
host="${DEPLOY_HOST:?set DEPLOY_HOST, e.g. root@203.0.113.10}"
dir="${DEPLOY_DIR:-/opt/velox}"
ssh_opts="-o BatchMode=yes -o ConnectTimeout=20 -o ConnectionAttempts=4"

if [ -n "$(git status --porcelain)" ]; then
    echo "Commit or stash local changes first: only HEAD is shipped" >&2
    exit 1
fi
rev="$(git rev-parse --short HEAD)"
echo "Shipping $rev to $host:$dir"
# shellcheck disable=SC2086
git archive --format=tar HEAD -- . ':!design-reference' | gzip | ssh $ssh_opts "$host" \
    "set -e; test -f '$dir/.env' || { echo 'no $dir/.env on the server' >&2; exit 1; }; tar -xzf - -C '$dir'; echo $rev > '$dir/REVISION'"
# shellcheck disable=SC2086
ssh $ssh_opts -f "$host" "cd '$dir' && setsid nohup sh -c 'docker compose up -d --build --remove-orphans && echo DEPLOY-OK || echo DEPLOY-FAILED' > deploy.log 2>&1 < /dev/null &"
echo "Build started on the server. Follow it with:"
echo "  ssh $host 'tail -f $dir/deploy.log'"
