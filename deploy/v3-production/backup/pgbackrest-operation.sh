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

info="$(docker exec -u postgres "$c" pgbackrest --stanza=edfinder_v3 --log-level-console=off --output=json info)"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert len(d)==1 and d[0].get("status",{}).get("message")=="ok"' <<<"$info"

echo "START: pgBackRest $op"
if [ "$op" = verify ]; then
  nice -n 10 ionice -c2 -n7 docker exec -u postgres "$c" \
    pgbackrest --stanza=edfinder_v3 --log-level-console=info verify
else
  nice -n 10 ionice -c2 -n7 docker exec -u postgres "$c" \
    pgbackrest --stanza=edfinder_v3 --type="$op" --log-level-console=info backup
fi
echo "PASS: pgBackRest $op"
