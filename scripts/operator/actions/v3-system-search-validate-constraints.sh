#!/usr/bin/env bash
# Validates the 18 deferred system_search checks. Validation writes only each
# pg_constraint.convalidated catalog flag and does not modify data rows. The
# scan is detached because each check can take minutes. Re-running start safely
# resumes the remaining checks; pg_constraint.convalidated is the truth, not
# the runner log. Receipts require exact CPython 3.14.
set -euo pipefail

ACTION="${1:-}"

if command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-system-search-validate-constraints","status":"stopped","read_only":false,"db_writes_performed":false,"failures":["python314_required"]}'
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
  printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-system-search-validate-constraints","status":"stopped","read_only":false,"db_writes_performed":false,"failures":["python314_required"]}'
  exit 1
fi

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
MIGRATION_NAME="010_v3_system_search_body_type_counts.sql"
MIGRATION_SHA="a042ccd1544d95cf47407a0722497321a544f15c62ac07dc83c914a19d7acbdf"
TABLE="v3_derived.system_search"
LOCK_TIMEOUT="5s"
STATEMENT_TIMEOUT="45min"
RUN_DIR="/tmp/edfinder-validate-constraints"

CONSTRAINTS=(
  system_search_ammonia_count_check
  system_search_bio_signal_total_check
  system_search_black_hole_count_check
  system_search_elw_count_check
  system_search_gas_giant_count_check
  system_search_geo_signal_total_check
  system_search_hmc_count_check
  system_search_icy_count_check
  system_search_metal_rich_count_check
  system_search_neutron_count_check
  system_search_other_star_count_check
  system_search_ring_count_check
  system_search_rocky_count_check
  system_search_rocky_ice_count_check
  system_search_terraformable_count_check
  system_search_walkable_count_check
  system_search_white_dwarf_count_check
  system_search_ww_count_check
)

MIGRATION_VERIFIED=false
VALIDATED_BEFORE=0
QUEUED_CONSTRAINTS=()
CATALOG_VALIDATION_LAUNCHED=false

emit_start_receipt() {
  local status="$1" result="$2" failure="${3:-}"
  local queued
  queued="$(printf '%s\n' "${QUEUED_CONSTRAINTS[@]:-}")"
  "$PYTHON_BIN" -c '
import json
import sys

status, result, migration_sha, verified, validated, queued, launched, failure, lock_timeout, statement_timeout = sys.argv[1:]
receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-system-search-validate-constraints-start",
    "status": status,
    "result": result or None,
    "migration_010_sha256": migration_sha,
    "migration_010_verified": verified == "true",
    "constraints_total": 18,
    "constraints_validated_before": int(validated),
    "constraints_queued": [name for name in queued.splitlines() if name],
    "lock_timeout": lock_timeout,
    "statement_timeout": statement_timeout,
    "read_only": False,
    "db_writes_performed": launched == "true",
    "catalog_validation_launched": launched == "true",
    "catalog_writes": "pg_constraint.convalidated only",
    "data_rows_modified": False,
    "publication_performed": False,
    "canonical_writes_performed": False,
    "service_changes_performed": False,
    "failures": [failure] if failure else [],
}
print(json.dumps(receipt, separators=(",", ":")))
' "$status" "$result" "$MIGRATION_SHA" "$MIGRATION_VERIFIED" \
    "$VALIDATED_BEFORE" "$queued" "$CATALOG_VALIDATION_LAUNCHED" "$failure" \
    "$LOCK_TIMEOUT" "$STATEMENT_TIMEOUT"
}

stop_start() {
  emit_start_receipt stopped "" "$1"
  exit 1
}

emit_invalid_action_receipt() {
  "$PYTHON_BIN" -c '
import json
print(json.dumps({
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-system-search-validate-constraints",
    "status": "stopped",
    "result": None,
    "read_only": False,
    "db_writes_performed": False,
    "failures": ["expected_start_or_status"],
}, separators=(",", ":")))
'
}

require_target() {
  command -v docker >/dev/null 2>&1 || return 1
  [ "$(hostname)" = "$TARGET_HOSTNAME" ] || return 1
  [ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || return 1
  [ "$(docker context show 2>/dev/null)" = "default" ] || return 1
  docker context inspect default 2>/dev/null \
    | grep -F 'unix:///var/run/docker.sock' >/dev/null || return 1
  docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || return 1
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null)" = "true" ] \
    || return 1
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

constraint_name_list() {
  local separator="" name
  for name in "${CONSTRAINTS[@]}"; do
    printf "%s'%s'" "$separator" "$name"
    separator=,
  done
}

constraint_state() {
  local names
  names="$(constraint_name_list)"
  db_query "BEGIN READ ONLY; SELECT c.conname, c.convalidated FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='v3_derived' AND r.relname='system_search' AND c.contype='c' AND c.conname IN (${names}) ORDER BY c.conname; COMMIT;"
}

active_validation() {
  db_query "BEGIN READ ONLY; SELECT pid, state, now()-query_start, left(query,120) FROM pg_stat_activity WHERE datname=current_database() AND query ILIKE '%VALIDATE CONSTRAINT%' AND query ILIKE '%system_search%' AND state <> 'idle' AND pid<>pg_backend_pid(); COMMIT;"
}

runner_pid_alive() {
  docker exec "$POSTGRES_CONTAINER" sh -c \
    'pid_file=/tmp/edfinder-validate-constraints/run.pid
    test -f "$pid_file" || exit 1
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    case "$pid" in
      ""|*[!0-9]*) rm -f "$pid_file"; exit 1 ;;
    esac
    if kill -0 "$pid" 2>/dev/null; then
      cmdline="$(cat "/proc/$pid/cmdline" 2>/dev/null | tr "\0" " ")"
      case "$cmdline" in
        *psql*) ;;
        *) rm -f "$pid_file"; exit 1 ;;
      esac
      case "$cmdline" in
        *run.sql*) exit 0 ;;
      esac
    fi
    rm -f "$pid_file"
    exit 1'
}

parse_constraint_state() {
  local state="$1" name validated
  local state_count=0
  declare -A validation_by_name=()
  while IFS='|' read -r name validated; do
    [ -n "$name" ] || continue
    validation_by_name["$name"]="$validated"
    state_count=$((state_count + 1))
  done <<< "$state"
  [ "$state_count" -eq "${#CONSTRAINTS[@]}" ] || return 1

  VALIDATED_BEFORE=0
  QUEUED_CONSTRAINTS=()
  for name in "${CONSTRAINTS[@]}"; do
    case "${validation_by_name[$name]:-missing}" in
      t|true) VALIDATED_BEFORE=$((VALIDATED_BEFORE + 1)) ;;
      f|false) QUEUED_CONSTRAINTS+=("$name") ;;
      *) return 1 ;;
    esac
  done
}

start_operation() {
  : "$TABLE" "$RUN_DIR"
  require_target || stop_start unexpected_target_or_runtime

  local ledger_sha state active sql name
  if ! ledger_sha="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${MIGRATION_NAME}'; COMMIT;")"; then
    stop_start migration_010_not_applied_or_hash_mismatch
  fi
  if [ "$ledger_sha" != "$MIGRATION_SHA" ]; then
    stop_start migration_010_not_applied_or_hash_mismatch
  fi
  MIGRATION_VERIFIED=true

  if ! state="$(constraint_state)"; then
    stop_start constraint_set_incomplete
  fi
  parse_constraint_state "$state" || stop_start constraint_set_incomplete

  if [ "${#QUEUED_CONSTRAINTS[@]}" -eq 0 ]; then
    emit_start_receipt success nothing_to_validate
    exit 0
  fi

  if ! active="$(active_validation)"; then
    stop_start validation_activity_check_failed
  fi
  if [ -n "$active" ] || runner_pid_alive; then
    stop_start validation_already_running
  fi

  sql="\\set ON_ERROR_STOP on
\\timing on
SET lock_timeout = '5s';
SET statement_timeout = '45min';"
  for name in "${QUEUED_CONSTRAINTS[@]}"; do
    sql+=$'\n'"\\echo validating ${name}"
    sql+=$'\n'"ALTER TABLE v3_derived.system_search VALIDATE CONSTRAINT ${name};"
  done
  sql+=$'\n'"\\echo validate_constraints_complete"$'\n'

  printf '%s' "$sql" | docker exec -i "$POSTGRES_CONTAINER" sh -c \
    'umask 077; mkdir -p /tmp/edfinder-validate-constraints && cat > /tmp/edfinder-validate-constraints/run.sql' \
    || stop_start validation_sql_write_failed

  docker exec -d "$POSTGRES_CONTAINER" sh -c \
    'cd /tmp/edfinder-validate-constraints && { (psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -f /tmp/edfinder-validate-constraints/run.sql > /tmp/edfinder-validate-constraints/run.log 2>&1; echo "exit=$?" >> /tmp/edfinder-validate-constraints/run.log; rm -f /tmp/edfinder-validate-constraints/run.pid) & echo $! > /tmp/edfinder-validate-constraints/run.pid; }' \
    >/dev/null || stop_start validation_runner_launch_failed
  CATALOG_VALIDATION_LAUNCHED=true

  sleep 3
  active="$(active_validation 2>/dev/null || true)"
  if [ -z "$active" ] && ! docker exec "$POSTGRES_CONTAINER" sh -c \
    'test -f /tmp/edfinder-validate-constraints/run.log && grep -F validate_constraints_complete /tmp/edfinder-validate-constraints/run.log >/dev/null'; then
    docker exec "$POSTGRES_CONTAINER" sh -c \
      'test -f /tmp/edfinder-validate-constraints/run.log && tail -n 40 /tmp/edfinder-validate-constraints/run.log' \
      >&2 || true
    stop_start validation_runner_did_not_start
  fi

  emit_start_receipt success launched
}

status_operation() {
  local state active ledger_sha pid_alive=false log_tail names failure_text
  local ledger_query_ok=true
  local -a failures=()
  require_target || {
    "$PYTHON_BIN" -c 'import json; print(json.dumps({"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-system-search-validate-constraints-status","status":"stopped","read_only":True,"db_writes_performed":False,"failures":["unexpected_target_or_runtime"]},separators=(",",":")))'
    exit 1
  }

  if ! ledger_sha="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${MIGRATION_NAME}'; COMMIT;" 2>/dev/null)"; then
    ledger_sha=""
    ledger_query_ok=false
    failures+=(migration_ledger_query_failed)
  fi
  if [ "$ledger_query_ok" = true ]; then
    if [ -z "$ledger_sha" ]; then
      failures+=(migration_010_not_applied)
    elif [ "$ledger_sha" != "$MIGRATION_SHA" ]; then
      failures+=(migration_010_hash_mismatch)
    fi
  fi
  if ! state="$(constraint_state 2>/dev/null)"; then
    state=""
    failures+=(constraint_state_query_failed)
  fi
  if ! active="$(active_validation 2>/dev/null)"; then
    active=""
    failures+=(active_validation_query_failed)
  fi
  if runner_pid_alive; then
    pid_alive=true
  fi
  log_tail="$(docker exec "$POSTGRES_CONTAINER" sh -c \
    'test -f /tmp/edfinder-validate-constraints/run.log && tail -n 40 /tmp/edfinder-validate-constraints/run.log' \
    2>/dev/null || true)"
  names="$(printf '%s\n' "${CONSTRAINTS[@]}")"
  failure_text="$(printf '%s\n' "${failures[@]:-}")"

  "$PYTHON_BIN" -c '
import json
import sys

migration_sha, expected_sha, names_text, state_text, active_text, pid_alive, log_text, failure_text = sys.argv[1:]
names = names_text.splitlines()
failures = [failure for failure in failure_text.splitlines() if failure]
states = {}
for line in state_text.splitlines():
    fields = line.split("|", 1)
    if len(fields) == 2 and fields[1] in ("t", "true", "f", "false"):
        states[fields[0]] = fields[1] in ("t", "true")
if set(states) != set(names):
    failures.append("constraint_set_incomplete")
constraints = [{"name": name, "validated": states.get(name, False)} for name in names]
active_validations = []
for line in active_text.splitlines():
    fields = line.split("|", 3)
    if len(fields) == 4:
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        active_validations.append({
            "pid": pid,
            "state": fields[1],
            "running_for": fields[2],
            "query": fields[3],
        })
validated_count = sum(item["validated"] for item in constraints)
receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-system-search-validate-constraints-status",
    "status": "success" if not failures else "stopped",
    "read_only": True,
    "db_writes_performed": False,
    "migration_010_in_ledger": migration_sha == expected_sha,
    "constraints": constraints,
    "validated_count": validated_count,
    "all_validated": validated_count == len(names),
    "active_validations": active_validations,
    "runner_pid_alive": pid_alive == "true",
    "log_tail": log_text.splitlines(),
    "failures": sorted(set(failures)),
}
print(json.dumps(receipt, separators=(",", ":")))
sys.exit(1 if failures else 0)
' "$ledger_sha" "$MIGRATION_SHA" "$names" "$state" "$active" "$pid_alive" "$log_tail" "$failure_text"
}

case "$ACTION" in
  start) start_operation ;;
  status) status_operation ;;
  *)
    emit_invalid_action_receipt
    exit 64
    ;;
esac
