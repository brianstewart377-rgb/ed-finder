#!/usr/bin/env bash
# Monthly backup rehearsal: validate that production backups can actually restore
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_FILE="/data/logs/backup_rehearsal.log"
REHEARSAL_DATE=$(date -u +'%Y-%m-%d')
RECEIPT_FILE="/data/backups/postgres/restore_rehearsal_${REHEARSAL_DATE}.json"

{
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting backup rehearsal..."

  # Run the rehearsal script from the repo
  if [ ! -f "$REPO_DIR/scripts/rehearse_postgres_restore.sh" ]; then
    echo "[ERROR] rehearsal script not found at $REPO_DIR/scripts/rehearse_postgres_restore.sh"
    exit 1
  fi

  bash "$REPO_DIR/scripts/rehearse_postgres_restore.sh" \
    --backup-file /data/backups/postgres/latest.dump \
    --target-db "edfinder_restore_monthly_${REHEARSAL_DATE}" \
    --receipt-file "$RECEIPT_FILE"

  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Backup rehearsal completed successfully"
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Receipt saved to $RECEIPT_FILE"

} >> "$LOG_FILE" 2>&1

exit 0
