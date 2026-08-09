#!/bin/bash
set -euo pipefail

WATCHDOG_HEARTBEAT_URL="${DISK_WATCHDOG_HEARTBEAT_URL:-}"
MIN_FREE_GB="${DISK_WATCHDOG_MIN_FREE_GB:-40}"
MAX_PERCENT_USED="${DISK_WATCHDOG_MAX_PERCENT_USED:-80}"
WATCHDOG_PATH="${DISK_WATCHDOG_PATH:-/data}"

if [[ -z "$WATCHDOG_HEARTBEAT_URL" ]]; then
  echo "disk watchdog: skipped (heartbeat URL unconfigured)"
  exit 0
fi

if [[ ! "$MIN_FREE_GB" =~ ^[0-9]+([.][0-9]+)?$ ]] || [[ "$MIN_FREE_GB" =~ ^0+([.]0+)?$ ]]; then
  echo "ERROR: disk watchdog cannot measure free space: DISK_WATCHDOG_MIN_FREE_GB must be a positive number; heartbeat not sent" >&2
  exit 1
fi

# Bounded to at most 3 digits before any arithmetic runs, so a value like
# 18446744073709551716 (2^64 + 100) can never reach bash's (( )) context and
# wrap around to something in range - it is rejected as malformed input by
# the regex alone, before overflow could occur.
if [[ ! "$MAX_PERCENT_USED" =~ ^[0-9]{1,3}$ ]] || (( 10#$MAX_PERCENT_USED < 1 || 10#$MAX_PERCENT_USED > 100 )); then
  echo "ERROR: disk watchdog cannot measure usage: DISK_WATCHDOG_MAX_PERCENT_USED must be an integer 1-100; heartbeat not sent" >&2
  exit 1
fi
# Normalize away any leading zeros now that the value is validated: bash's
# (( )) arithmetic context treats a leading-zero operand as octal, so an
# unnormalized zero-padded value (e.g. "0999", which contains the invalid
# octal digit '9') would make the guard above error out silently inside the
# `if` condition and skip validation entirely, while the later awk
# comparison - which has no such octal rule - would parse it as decimal 999,
# disabling the percentage check for any real disk.
MAX_PERCENT_USED=$((10#$MAX_PERCENT_USED))

if ! df_output="$(df -B1 -P "$WATCHDOG_PATH" 2>&1)"; then
  echo "ERROR: disk watchdog measurement failed for ${WATCHDOG_PATH}; heartbeat not sent: ${df_output}" >&2
  exit 1
fi

available_bytes="$(printf '%s\n' "$df_output" | awk 'NR == 2 { print $4 }')"
percent_used="$(printf '%s\n' "$df_output" | awk 'NR == 2 { gsub("%", "", $5); print $5 }')"
if [[ ! "$available_bytes" =~ ^[0-9]+$ ]] || [[ ! "$percent_used" =~ ^[0-9]+$ ]]; then
  echo "ERROR: disk watchdog measurement output is unparseable for ${WATCHDOG_PATH}; heartbeat not sent: ${df_output}" >&2
  exit 1
fi

if ! measurement_result="$(awk \
  -v available_bytes="$available_bytes" \
  -v threshold_gb="$MIN_FREE_GB" \
  -v percent_used="$percent_used" \
  -v max_percent="$MAX_PERCENT_USED" \
  'BEGIN {
    threshold_bytes = threshold_gb * 1000000000
    actual_gb = available_bytes / 1000000000
    free_ok = (available_bytes >= threshold_bytes)
    percent_ok = (percent_used <= max_percent)
    state = (free_ok && percent_ok) ? "healthy" : "low"
    printf "%.2f\t%s\t%s\t%s\n", actual_gb, state, (free_ok ? "1" : "0"), (percent_ok ? "1" : "0")
  }')"; then
  echo "ERROR: disk watchdog could not evaluate free-space measurement for ${WATCHDOG_PATH}; heartbeat not sent" >&2
  exit 1
fi

IFS=$'\t' read -r actual_free_gb disk_state free_ok percent_ok <<< "$measurement_result"
if [[ "$disk_state" == "low" ]]; then
  reasons=()
  if [[ "$free_ok" == "0" ]]; then
    reasons+=("actual free ${actual_free_gb} GB is below threshold ${MIN_FREE_GB} GB")
  fi
  if [[ "$percent_ok" == "0" ]]; then
    reasons+=("usage ${percent_used}% exceeds threshold ${MAX_PERCENT_USED}%")
  fi
  reason_text="$(IFS='; '; echo "${reasons[*]}")"
  echo "ERROR: disk watchdog low disk health on ${WATCHDOG_PATH}: ${reason_text}; heartbeat not sent" >&2
  exit 1
fi
if [[ "$disk_state" != "healthy" ]]; then
  echo "ERROR: disk watchdog could not evaluate free-space state for ${WATCHDOG_PATH}; heartbeat not sent" >&2
  exit 1
fi

echo "disk watchdog: healthy; actual free ${actual_free_gb} GB (threshold ${MIN_FREE_GB} GB), usage ${percent_used}% (threshold ${MAX_PERCENT_USED}%) on ${WATCHDOG_PATH}"
ping_exit_code=0
curl -fsS -m 10 --retry 3 "$WATCHDOG_HEARTBEAT_URL" || ping_exit_code=$?
if (( ping_exit_code == 0 )); then
  echo "disk watchdog heartbeat: sent"
else
  echo "ERROR: disk watchdog heartbeat: failed (curl exit ${ping_exit_code}); disk state is healthy" >&2
fi

# Heartbeat delivery never changes the exit status of the disk health check.
exit 0
