#!/usr/bin/env bash
set -euo pipefail
op="${1:?operation required}"
c='edfinder-v3-phase4c-full-20260827_r5-postgres'
mount='/mnt/ed-storagebox'
lock='/run/lock/edfinder-v3-pgbackrest-schedule.lock'

case "$op" in full|diff|verify) ;; *) echo "unsupported pgBackRest operation: $op" >&2; exit 64 ;; esac

# Never fall back to the underlying local mount directory.
mountpoint -q "$mount" || { echo 'SKIP: Storage Box is not mounted' >&2; exit 0; }
fstype="$(findmnt -n -o FSTYPE -T "$mount" || true)"
[ "$fstype" = 'fuse.rclone' ] || { echo "SKIP: unexpected Storage Box filesystem: $fstype" >&2; exit 0; }
docker inspect "$c" >/dev/null 2>&1 || { echo 'SKIP: PG18 container missing' >&2; exit 0; }

exec 9>"$lock"
flock -n 9 || { echo 'SKIP: another scheduled pgBackRest operation owns the host lock'; exit 0; }

# Also respect manually-started or externally-tracked operations.
active="$(docker top "$c" -eo pid,args | awk 'tolower($0) ~ /pgbackrest/ && tolower($0) ~ /(backup|verify)/ {n++} END {print n+0}')"
if [ "$active" -gt 0 ]; then
  echo "SKIP: $active pgBackRest backup/verify process(es) already active"
  exit 0
fi

# Keep this SQL in the installed wrapper: scheduled units have no checkout.
# Reuse 016's open-event definition, including its plan/relation matching rules.
# A dead recorded backend cannot indefinitely suppress backups.
purge_records="$(docker exec -i -u postgres "$c" \
  psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 \
  --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SET LOCAL lock_timeout = '5s';
WITH candidates AS (
  SELECT DISTINCT purge_id, relation_code, event_kind
  FROM v3_meta.derived_generation_purge_event
  WHERE event_kind IN ('BATCH_STARTED', 'REWRITE_STARTED')
), open_records AS (
  SELECT DISTINCT opened.*
  FROM candidates c
  CROSS JOIN LATERAL v3_meta.purge_open_event(
    c.purge_id, c.relation_code, c.event_kind,
    CASE c.event_kind WHEN 'BATCH_STARTED'
      THEN ARRAY['BATCH_COMMITTED', 'BATCH_ROLLED_BACK']
      ELSE ARRAY['REWRITE_VERIFIED', 'REWRITE_ROLLED_BACK', 'FAILED_STOP'] END
  ) opened
  WHERE opened.event_sequence IS NOT NULL
)
SELECT format('purge_id=%s event_sequence=%s kind=%s relation=%s backend_pid=%s backend_start=%s',
  e.purge_id, e.event_sequence, e.event_kind, e.relation_code, e.backend_pid, e.backend_start)
FROM open_records e JOIN pg_stat_activity a
  ON a.pid=e.backend_pid AND a.backend_start=e.backend_start
WHERE a.datname=current_database()
ORDER BY e.event_sequence;
COMMIT;
SQL
)"
if [ -n "$purge_records" ]; then
  while IFS= read -r record; do
    echo "SKIP: live purge backend: $record"
  done <<<"$purge_records"
  exit 0
fi

info="$(docker exec -u postgres "$c" pgbackrest --stanza=edfinder_v3 --log-level-console=off --output=json info)"
python3.14 -I -S -c 'import json,sys; d=json.load(sys.stdin); assert len(d)==1 and d[0].get("status",{}).get("message")=="ok"' <<<"$info"

echo "START: pgBackRest $op"
if [ "$op" = verify ]; then
  nice -n 10 ionice -c2 -n7 docker exec -u postgres "$c" \
    pgbackrest --stanza=edfinder_v3 --log-level-console=info verify
else
  nice -n 10 ionice -c2 -n7 docker exec -u postgres "$c" \
    pgbackrest --stanza=edfinder_v3 --type="$op" --log-level-console=info backup
fi
echo "PASS: pgBackRest $op"
