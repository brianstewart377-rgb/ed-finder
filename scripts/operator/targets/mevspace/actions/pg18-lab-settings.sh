#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder
bash scripts/operator/targets/mevspace/require_mevspace_operator_env.sh

container="pg18-lab"

docker inspect "$container" >/dev/null 2>&1 || {
  echo "STOP: expected lab container '$container' was not found" >&2
  exit 1
}

[[ "$(docker inspect -f '{{.State.Running}}' "$container")" == "true" ]] || {
  echo "STOP: expected lab container '$container' is not running" >&2
  exit 1
}

echo "== PG18 selected settings =="
docker exec "$container" psql -U postgres -d edfinder_lab -P pager=off -c "
SELECT name, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
  'shared_buffers',
  'effective_cache_size',
  'work_mem',
  'maintenance_work_mem',
  'max_connections',
  'max_worker_processes',
  'max_parallel_workers',
  'max_parallel_workers_per_gather',
  'max_parallel_maintenance_workers',
  'wal_buffers',
  'max_wal_size',
  'checkpoint_completion_target',
  'random_page_cost',
  'effective_io_concurrency',
  'maintenance_io_concurrency',
  'io_method',
  'io_workers',
  'io_max_concurrency'
)
ORDER BY name;
"

echo
echo "== Safety boundary =="
echo "target: mevspace"
echo "db_access_performed: true"
echo "db_read_only_queries_only: true"
echo "db_writes_performed: false"
echo "docker_writes_performed: false"
