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
RETENTION_MIN_ARCHIVES="${BACKUP_RETENTION_MIN_ARCHIVES:-3}"
LOG_FILE="${BACKUP_LOG_FILE:-/data/logs/backup.log}"
BACKUP_OFFSITE_REMOTE="${BACKUP_OFFSITE_REMOTE:-}"
OFFSITE_RETENTION_DAYS="${BACKUP_OFFSITE_RETENTION_DAYS:-30}"
OFFSITE_RETENTION_MIN_ARCHIVES="${BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES:-3}"
BACKUP_HEARTBEAT_URL="${BACKUP_HEARTBEAT_URL:-}"
BACKUP_OFFSITE_HEARTBEAT_URL="${BACKUP_OFFSITE_HEARTBEAT_URL:-}"

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

cleanup_tmp_archive() {
    rm -f -- "${TMP_ARCHIVE:-}" || true
}
trap cleanup_tmp_archive EXIT

prune_local_backups() {
    local archive
    local archive_count
    local -a expired_archives=()

    archive_count="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'edfinder_*.dump' | wc -l | tr -d '[:space:]')"
    mapfile -t expired_archives < <(
        find "$BACKUP_DIR" -maxdepth 1 -type f -name 'edfinder_*.dump' -mtime +"$RETENTION_DAYS" -print | sort
    )

    for archive in "${expired_archives[@]}"; do
        if (( archive_count <= RETENTION_MIN_ARCHIVES )); then
            echo "retention floor: keeping $archive because only $archive_count archive(s) remain (minimum $RETENTION_MIN_ARCHIVES)"
            break
        fi

        rm -f -- "$archive" "${archive}.sha256" "${archive}.json"
        echo "$archive"
        echo "${archive}.sha256"
        echo "${archive}.json"
        archive_count=$((archive_count - 1))
    done
}

prune_offsite_backups() {
    local archive
    local archive_count
    local archive_stamp
    local cutoff_epoch
    local cutoff_stamp
    local listing
    local now_epoch
    local remote_name
    local sidecar
    local -a remote_archives=()
    local -A remote_files=()

    if [[ ! "$OFFSITE_RETENTION_DAYS" =~ ^[0-9]+$ \
        || ! "$OFFSITE_RETENTION_MIN_ARCHIVES" =~ ^[0-9]+$ ]]; then
        echo "ERROR: offsite retention settings must be non-negative integers" >&2
        return 1
    fi

    if ! now_epoch="$(date -u +%s)"; then
        echo "ERROR: unable to read current time for offsite retention" >&2
        return 1
    fi
    cutoff_epoch=$((now_epoch - OFFSITE_RETENTION_DAYS * 86400))
    if ! cutoff_stamp="$(date -u -d "@$cutoff_epoch" +'%Y%m%dT%H%M%SZ')"; then
        echo "ERROR: unable to calculate offsite retention cutoff" >&2
        return 1
    fi

    if ! listing="$(rclone lsf "$BACKUP_OFFSITE_REMOTE" --files-only)"; then
        echo "ERROR: unable to list offsite backup archives" >&2
        return 1
    fi

    while IFS= read -r remote_name; do
        [[ -n "$remote_name" ]] || continue
        remote_files["$remote_name"]=1
        if [[ "$remote_name" =~ ^edfinder_[0-9]{8}T[0-9]{6}Z\.dump$ ]]; then
            remote_archives+=("$remote_name")
        fi
    done <<< "$listing"

    archive_count="${#remote_archives[@]}"
    if (( archive_count == 0 )); then
        echo "offsite retention: no edfinder_*.dump archives found"
        return 0
    fi

    mapfile -t remote_archives < <(printf '%s\n' "${remote_archives[@]}" | sort)
    for archive in "${remote_archives[@]}"; do
        archive_stamp="${archive#edfinder_}"
        archive_stamp="${archive_stamp%.dump}"
        if [[ "$archive_stamp" == "$cutoff_stamp" || "$archive_stamp" > "$cutoff_stamp" ]]; then
            continue
        fi

        if (( archive_count <= OFFSITE_RETENTION_MIN_ARCHIVES )); then
            echo "offsite retention floor: keeping $archive because only $archive_count archive(s) remain (minimum $OFFSITE_RETENTION_MIN_ARCHIVES)"
            break
        fi

        # Remove existing sidecars first so a failed group deletion can never
        # leave a checksum or metadata object orphaned from its archive.
        for sidecar in "${archive}.sha256" "${archive}.json"; do
            if [[ -n "${remote_files[$sidecar]:-}" ]] \
                && ! rclone deletefile "$BACKUP_OFFSITE_REMOTE/$sidecar"; then
                echo "ERROR: unable to prune offsite sidecar $sidecar" >&2
                return 1
            fi
        done
        if ! rclone deletefile "$BACKUP_OFFSITE_REMOTE/$archive"; then
            echo "ERROR: unable to prune offsite archive $archive" >&2
            return 1
        fi

        echo "offsite pruned: $archive with sidecars"
        archive_count=$((archive_count - 1))
    done
}

log_heartbeat_skipped() {
    local label="$1"
    local url="$2"
    local reason="$3"

    if [[ -z "$url" ]]; then
        echo "$label heartbeat: skipped (unconfigured)"
    else
        echo "$label heartbeat: skipped ($reason)"
    fi
}

send_heartbeat() {
    local label="$1"
    local url="$2"

    if [[ -z "$url" ]]; then
        echo "$label heartbeat: skipped (unconfigured)"
        return 0
    fi

    if curl -fsS -m 10 --retry 3 "$url"; then
        echo "$label heartbeat: sent"
    else
        echo "$label heartbeat: failed" >&2
    fi
    return 0
}

echo "===== Postgres backup starting ====="
echo "backup dir: $BACKUP_DIR"
echo "retention:  ${RETENTION_DAYS} days"
echo "minimum:    ${RETENTION_MIN_ARCHIVES} archives"
echo "archive:    $ARCHIVE"
if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    echo "offsite:    $BACKUP_OFFSITE_REMOTE"
    echo "offsite retention: ${OFFSITE_RETENTION_DAYS} days"
    echo "offsite minimum:   ${OFFSITE_RETENTION_MIN_ARCHIVES} archives"
else
    echo "offsite:    disabled"
fi

if pg_dump "$DB_URL" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges \
    --file="$TMP_ARCHIVE"; then
    ARCHIVE_CREATED_AT_UTC="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
else
    DUMP_EXIT_CODE=$?
    prune_local_backups
    log_heartbeat_skipped "local" "$BACKUP_HEARTBEAT_URL" "no valid local archive"
    log_heartbeat_skipped "offsite" "$BACKUP_OFFSITE_HEARTBEAT_URL" "no valid local archive"
    echo "offsite prune: skipped (no valid local archive)"
    echo "ERROR: pg_dump failed for $ARCHIVE; local retention completed" >&2
    exit "$DUMP_EXIT_CODE"
fi

mv "$TMP_ARCHIVE" "$ARCHIVE"
pg_restore --list "$ARCHIVE" >/dev/null
sha256sum "$ARCHIVE" > "$SHA_FILE"

SIZE_BYTES="$(wc -c < "$ARCHIVE" | tr -d '[:space:]')"
OFFSITE_SYNC_STATUS="disabled"
OFFSITE_SYNCED_AT_JSON="null"
OFFSITE_REMOTE_JSON="null"
OFFSITE_PRUNE_STATUS="disabled"

if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    OFFSITE_SYNC_STATUS="failed"
    OFFSITE_REMOTE_JSON="\"$BACKUP_OFFSITE_REMOTE\""
    OFFSITE_PRUNE_STATUS="not_run"
fi

write_metadata() {
    cat > "$META_FILE" <<EOF
{
  "created_at_utc": "$ARCHIVE_CREATED_AT_UTC",
  "task": "$TASK",
  "archive_file": "$(basename "$ARCHIVE")",
  "sha256_file": "$(basename "$SHA_FILE")",
  "size_bytes": $SIZE_BYTES,
  "retention_days": $RETENTION_DAYS,
  "format": "pg_dump_custom",
  "validated_with": "pg_restore --list",
  "offsite_remote": $OFFSITE_REMOTE_JSON,
  "offsite_sync_status": "$OFFSITE_SYNC_STATUS",
  "offsite_synced_at_utc": $OFFSITE_SYNCED_AT_JSON,
  "offsite_retention_days": $OFFSITE_RETENTION_DAYS,
  "offsite_retention_min_archives": $OFFSITE_RETENTION_MIN_ARCHIVES,
  "offsite_prune_status": "$OFFSITE_PRUNE_STATUS"
}
EOF
}

write_metadata

ln -sfn "$(basename "$ARCHIVE")" "$LATEST_LINK"
ln -sfn "$(basename "$META_FILE")" "$LATEST_META_LINK"

prune_local_backups
send_heartbeat "local" "$BACKUP_HEARTBEAT_URL"

OFFSITE_EXIT_CODE=0
if [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    if ! command -v rclone >/dev/null 2>&1; then
        echo "BACKUP_OFFSITE_REMOTE is set but rclone is unavailable" >&2
        OFFSITE_EXIT_CODE=1
    elif rclone copyto "$ARCHIVE" "$BACKUP_OFFSITE_REMOTE/$(basename "$ARCHIVE")" \
        && rclone copyto "$SHA_FILE" "$BACKUP_OFFSITE_REMOTE/$(basename "$SHA_FILE")"; then
        OFFSITE_SYNC_STATUS="synced"
        OFFSITE_SYNCED_AT_JSON="\"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\""
        write_metadata
        if ! rclone copyto "$META_FILE" "$BACKUP_OFFSITE_REMOTE/$(basename "$META_FILE")" \
            || ! rclone copyto "$META_FILE" "$BACKUP_OFFSITE_REMOTE/latest.json"; then
            OFFSITE_EXIT_CODE=1
            OFFSITE_SYNC_STATUS="synced_metadata_failed"
            write_metadata
        fi
    else
        OFFSITE_EXIT_CODE=1
    fi

    if [[ "$OFFSITE_EXIT_CODE" -ne 0 ]]; then
        if [[ "$OFFSITE_SYNC_STATUS" == "synced_metadata_failed" ]]; then
            echo "ERROR: offsite backup metadata sync failed for $ARCHIVE; archive and checksum are synced; local archive, metadata, latest symlinks, and retention completed" >&2
        else
            OFFSITE_SYNC_STATUS="failed"
            OFFSITE_SYNCED_AT_JSON="null"
            write_metadata
            echo "ERROR: offsite backup sync failed for $ARCHIVE; local archive, metadata, latest symlinks, and retention completed" >&2
        fi
    fi
fi

if [[ "$OFFSITE_SYNC_STATUS" == "synced" ]]; then
    if prune_offsite_backups; then
        OFFSITE_PRUNE_STATUS="succeeded"
    else
        OFFSITE_PRUNE_STATUS="failed"
        echo "ERROR: offsite backup prune failed; backup upload and local retention remain successful" >&2
    fi
    write_metadata
elif [[ -n "$BACKUP_OFFSITE_REMOTE" ]]; then
    echo "offsite prune: skipped (offsite status $OFFSITE_SYNC_STATUS)"
fi

if [[ "$OFFSITE_SYNC_STATUS" == "synced" ]]; then
    send_heartbeat "offsite" "$BACKUP_OFFSITE_HEARTBEAT_URL"
else
    log_heartbeat_skipped "offsite" "$BACKUP_OFFSITE_HEARTBEAT_URL" "offsite status $OFFSITE_SYNC_STATUS"
fi

echo "===== Postgres backup complete ====="
echo "archive size bytes: $SIZE_BYTES"
echo "latest symlink:     $LATEST_LINK"
echo "offsite status:     $OFFSITE_SYNC_STATUS"
echo "offsite prune:      $OFFSITE_PRUNE_STATUS"

if [[ "$OFFSITE_EXIT_CODE" -ne 0 ]]; then
    exit "$OFFSITE_EXIT_CODE"
fi
