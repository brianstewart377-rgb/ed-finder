#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder
bash scripts/operator/targets/mevspace/require_mevspace_operator_env.sh

container="pg18-lab"

if ! docker inspect "$container" >/dev/null 2>&1; then
  echo "STOP: expected lab container '$container' was not found" >&2
  exit 1
fi

echo "== PG18 lab container =="
docker ps -a --filter "name=^/${container}$" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

echo
echo "== PostgreSQL identity =="
if [[ "$(docker inspect -f '{{.State.Running}}' "$container")" == "true" ]]; then
  docker exec "$container" psql -U postgres -d edfinder_lab -Atc "SELECT version();"
  docker exec "$container" psql -U postgres -d edfinder_lab -Atc "SELECT postgis_full_version();"
  docker exec "$container" psql -U postgres -d edfinder_lab -Atc "SHOW data_directory;"
  docker exec "$container" psql -U postgres -d edfinder_lab -Atc "SHOW io_method;"
else
  echo "container_running: false"
fi

echo
echo "== Safety boundary =="
echo "target: mevspace"
echo "db_access_performed: true"
echo "db_read_only_queries_only: true"
echo "db_writes_performed: false"
echo "docker_writes_performed: false"
