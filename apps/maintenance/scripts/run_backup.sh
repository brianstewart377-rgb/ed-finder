#!/bin/bash
#
# scripts/run_backup.sh — scheduled Postgres backups for the maintenance sidecar.
#
# This is the immediate, committed stopgap requested by the audit:
#   - nightly custom-format pg_dump archives
#   - deterministic output path under /data/backups
#   - local retention pruning
#   - archive validation via pg_restore --list
#
# It is intentionally simple and boring. This is not WAL archiving or PITR.
# The committed path is:
#   - always produce a validated local archive first
#   - optionally mirror that archive offsite through rclone
#   - keep the metadata honest about whether the offsite hop happened
set -euo pipefail

TASK="${1:-nightly}"
DB_URL="${DATABASE_URL:?DATABASE_URL must be set}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
LOG_FILE="${BACKUP_LOG_FILE:-/data/logs/backup.log}"
BACKUP_OFFSITE_REMOTE="${BACKUP_OFFSITE_REMOTE:-}"

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

exec > >(tee -a >(while IFS= read -r line; do
    printf '%s [%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$TASK" "$line"
done >> "$LOG_FILE")) 2>&1

if [[ "$TASK" != "nightly" && "$TASK" != "manual" ]]; then
    echo "usage: $0 {nightly|manual}" >&2
    exit 2
fi

STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
BASE="edfinder_${STAMP}"
ARCHIVE="$BACKUP_DIR/${BASE}.dump"
TMP_ARCHIVE="${ARCHIVE}.tmp"
SHA_FILE="${ARCHIVE}.sha256"
META_FILE="${ARCHIVE}.json"
LATEST_LINK="$BACKUP_DIR/latest.dump"
LATEST_META_LINK="$BACKUP_DIR/latest.json"

echo "===== Postgres backup starting ====="
echo "backup dir: $BACKUP_DIR"
echo "retention:  ${RETENTION_DAYS} days"
echo "archive:    $ARCHIVE"
if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    echo "offsite:    $BACKUP_OFFSITE_REMOTE"
else
    echo "offsite:    disabled"
fi

pg_dump "$DB_URL" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges \
    --file="$TMP_ARCHIVE"

mv "$TMP_ARCHIVE" "$ARCHIVE"
pg_restore --list "$ARCHIVE" >/dev/null
sha256sum "$ARCHIVE" > "$SHA_FILE"

SIZE_BYTES="$(wc -c < "$ARCHIVE" | tr -d '[:space:]')"
OFFSITE_SYNC_STATUS="disabled"
OFFSITE_SYNCED_AT_JSON="null"
OFFSITE_REMOTE_JSON="null"

if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    command -v rclone >/dev/null 2>&1 || {
        echo "BACKUP_OFFSITE_REMOTE is set but rclone is unavailable" >&2
        exit 1
    }
    OFFSITE_REMOTE_JSON="\"$BACKUP_OFFSITE_REMOTE\""
    rclone copyto "$ARCHIVE" "$BACKUP_OFFSITE_REMOTE/$(basename "$ARCHIVE")"
    rclone copyto "$SHA_FILE" "$BACKUP_OFFSITE_REMOTE/$(basename "$SHA_FILE")"
    OFFSITE_SYNC_STATUS="synced"
    OFFSITE_SYNCED_AT_JSON="\"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\""
fi

cat > "$META_FILE" <<EOF
{
  "created_at_utc": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "task": "$TASK",
  "archive_file": "$(basename "$ARCHIVE")",
  "sha256_file": "$(basename "$SHA_FILE")",
  "size_bytes": $SIZE_BYTES,
  "retention_days": $RETENTION_DAYS,
  "format": "pg_dump_custom",
  "validated_with": "pg_restore --list",
  "offsite_remote": $OFFSITE_REMOTE_JSON,
  "offsite_sync_status": "$OFFSITE_SYNC_STATUS",
  "offsite_synced_at_utc": $OFFSITE_SYNCED_AT_JSON
}
EOF

if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    rclone copyto "$META_FILE" "$BACKUP_OFFSITE_REMOTE/$(basename "$META_FILE")"
    rclone copyto "$META_FILE" "$BACKUP_OFFSITE_REMOTE/latest.json"
fi

ln -sfn "$(basename "$ARCHIVE")" "$LATEST_LINK"
ln -sfn "$(basename "$META_FILE")" "$LATEST_META_LINK"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'edfinder_*.dump' -mtime +"$RETENTION_DAYS" -print -delete
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'edfinder_*.dump.sha256' -mtime +"$RETENTION_DAYS" -print -delete
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'edfinder_*.dump.json' -mtime +"$RETENTION_DAYS" -print -delete

echo "===== Postgres backup complete ====="
echo "archive size bytes: $SIZE_BYTES"
echo "latest symlink:     $LATEST_LINK"
echo "offsite status:     $OFFSITE_SYNC_STATUS"
