#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder
bash scripts/operator/targets/mevspace/require_mevspace_operator_env.sh

container="pg18-lab"
lines="${PG18_LOG_LINES:-100}"

case "$lines" in
  ''|*[!0-9]*)
    echo "STOP: PG18_LOG_LINES must be an integer" >&2
    exit 1
    ;;
esac

if (( lines < 1 || lines > 500 )); then
  echo "STOP: PG18_LOG_LINES must be between 1 and 500" >&2
  exit 1
fi

docker inspect "$container" >/dev/null 2>&1 || {
  echo "STOP: expected lab container '$container' was not found" >&2
  exit 1
}

echo "== PG18 lab logs (last $lines lines) =="
docker logs --tail "$lines" "$container" 2>&1

echo
echo "== Safety boundary =="
echo "target: mevspace"
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "docker_writes_performed: false"
