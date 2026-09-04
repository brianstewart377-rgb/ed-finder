#!/bin/bash
# LEGACY/SELF-HOST/LOCAL COMPOSE HELPER ONLY; NOT V3 PRODUCTION AUTHORITY.
set -euo pipefail

WATCHDOG_HEARTBEAT_URL="${EDDN_WATCHDOG_HEARTBEAT_URL:-}"
MAX_AGE_MINUTES="${EDDN_WATCHDOG_MAX_AGE_MINUTES:-30}"

if [[ -z "$WATCHDOG_HEARTBEAT_URL" ]]; then
  echo "EDDN ingest watchdog: skipped (heartbeat URL unconfigured)"
  exit 0
fi

if [[ ! "$MAX_AGE_MINUTES" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: EDDN_WATCHDOG_MAX_AGE_MINUTES must be a non-negative number" >&2
  exit 1
fi

# Keep the direct database URL precedence identical to
# scripts/run_data_invariants_receipted.sh.
DATABASE_URL_OVERRIDE="${DATA_INVARIANTS_DATABASE_URL:-}"
effective_database_url="$DATABASE_URL_OVERRIDE"
if [[ -z "$effective_database_url" && -n "${DATABASE_URL:-}" ]]; then
  effective_database_url="$DATABASE_URL"
fi

if [[ -z "$effective_database_url" ]]; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: DATABASE_URL is not configured" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: psql is not available" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: python is not available" >&2
  exit 1
fi
python_bin="$(command -v python3 || command -v python)"

if ! newest_eddn_update="$({
  psql "$effective_database_url" \
    --no-psqlrc \
    --tuples-only \
    --no-align \
    --set=ON_ERROR_STOP=1 \
    --command='SELECT MAX(eddn_updated_at) FROM systems;'
} 2>&1)"; then
  echo "ERROR: EDDN ingest watchdog query failed; heartbeat not sent: $newest_eddn_update" >&2
  exit 1
fi

newest_eddn_update="$(printf '%s\n' "$newest_eddn_update" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tail -n 1)"
if [[ -z "$newest_eddn_update" ]]; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: systems.eddn_updated_at has no value; heartbeat not sent" >&2
  exit 1
fi

if ! freshness_result="$("$python_bin" - "$newest_eddn_update" "$MAX_AGE_MINUTES" <<'PY'
from datetime import datetime, timezone
import sys

timestamp = sys.argv[1].strip()
threshold_minutes = float(sys.argv[2])

try:
    newest = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
except ValueError as exc:
    raise SystemExit(f"invalid database timestamp {timestamp!r}: {exc}")

if newest.tzinfo is None:
    newest = newest.replace(tzinfo=timezone.utc)

age_seconds = max(
    0.0,
    (datetime.now(timezone.utc) - newest.astimezone(timezone.utc)).total_seconds(),
)
age_minutes = age_seconds / 60
state = "fresh" if age_minutes <= threshold_minutes else "stale"
print(f"{age_seconds:.3f}\t{age_minutes:.1f}\t{state}")
PY
)"; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness from database timestamp; heartbeat not sent" >&2
  exit 1
fi

IFS=$'\t' read -r _age_seconds age_minutes freshness_state <<< "$freshness_result"
if [[ "$freshness_state" == "stale" ]]; then
  echo "ERROR: EDDN ingest watchdog is stale: actual age ${age_minutes} minutes exceeds threshold ${MAX_AGE_MINUTES} minutes; heartbeat not sent" >&2
  exit 1
fi
if [[ "$freshness_state" != "fresh" ]]; then
  echo "ERROR: EDDN ingest watchdog cannot verify freshness: unexpected age calculation result; heartbeat not sent" >&2
  exit 1
fi

echo "EDDN ingest watchdog: healthy; actual age ${age_minutes} minutes (threshold ${MAX_AGE_MINUTES} minutes)"
ping_exit_code=0
curl -fsS -m 10 --retry 3 "$WATCHDOG_HEARTBEAT_URL" || ping_exit_code=$?
if (( ping_exit_code == 0 )); then
  echo "EDDN ingest watchdog heartbeat: sent"
else
  echo "ERROR: EDDN ingest watchdog heartbeat: failed (curl exit ${ping_exit_code}); data is fresh" >&2
fi

# Heartbeat delivery never changes the exit status of the data freshness check.
exit 0
