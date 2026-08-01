#!/bin/bash
set -euo pipefail

WATCHDOG_HEARTBEAT_URL="${DISK_WATCHDOG_HEARTBEAT_URL:-}"
MIN_FREE_GB="${DISK_WATCHDOG_MIN_FREE_GB:-40}"
WATCHDOG_PATH="${DISK_WATCHDOG_PATH:-/data}"

if [[ -z "$WATCHDOG_HEARTBEAT_URL" ]]; then
  echo "disk watchdog: skipped (heartbeat URL unconfigured)"
  exit 0
fi

if [[ ! "$MIN_FREE_GB" =~ ^[0-9]+([.][0-9]+)?$ ]] || [[ "$MIN_FREE_GB" =~ ^0+([.]0+)?$ ]]; then
  echo "ERROR: disk watchdog cannot measure free space: DISK_WATCHDOG_MIN_FREE_GB must be a positive number; heartbeat not sent" >&2
  exit 1
fi

if ! df_output="$(df -B1 -P "$WATCHDOG_PATH" 2>&1)"; then
  echo "ERROR: disk watchdog measurement failed for ${WATCHDOG_PATH}; heartbeat not sent: ${df_output}" >&2
  exit 1
fi

available_bytes="$(printf '%s\n' "$df_output" | awk 'NR == 2 { print $4 }')"
if [[ ! "$available_bytes" =~ ^[0-9]+$ ]]; then
  echo "ERROR: disk watchdog measurement output is unparseable for ${WATCHDOG_PATH}; heartbeat not sent: ${df_output}" >&2
  exit 1
fi

if ! measurement_result="$(awk \
  -v available_bytes="$available_bytes" \
  -v threshold_gb="$MIN_FREE_GB" \
  'BEGIN {
    threshold_bytes = threshold_gb * 1000000000
    actual_gb = available_bytes / 1000000000
    state = (available_bytes >= threshold_bytes) ? "healthy" : "low"
    printf "%.2f\t%s\n", actual_gb, state
  }')"; then
  echo "ERROR: disk watchdog could not evaluate free-space measurement for ${WATCHDOG_PATH}; heartbeat not sent" >&2
  exit 1
fi

IFS=$'\t' read -r actual_free_gb disk_state <<< "$measurement_result"
if [[ "$disk_state" == "low" ]]; then
  echo "ERROR: disk watchdog low free space: actual free ${actual_free_gb} GB is below threshold ${MIN_FREE_GB} GB on ${WATCHDOG_PATH}; heartbeat not sent" >&2
  exit 1
fi
if [[ "$disk_state" != "healthy" ]]; then
  echo "ERROR: disk watchdog could not evaluate free-space state for ${WATCHDOG_PATH}; heartbeat not sent" >&2
  exit 1
fi

echo "disk watchdog: healthy; actual free ${actual_free_gb} GB (threshold ${MIN_FREE_GB} GB) on ${WATCHDOG_PATH}"
ping_exit_code=0
curl -fsS -m 10 --retry 3 "$WATCHDOG_HEARTBEAT_URL" || ping_exit_code=$?
if (( ping_exit_code == 0 )); then
  echo "disk watchdog heartbeat: sent"
else
  echo "ERROR: disk watchdog heartbeat: failed (curl exit ${ping_exit_code}); disk state is healthy" >&2
fi

# Heartbeat delivery never changes the exit status of the disk health check.
exit 0
