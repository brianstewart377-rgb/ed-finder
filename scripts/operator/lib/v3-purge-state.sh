#!/usr/bin/env bash
# The SQL and lease probe live only in the Python module. Streamed actions receive
# an inline v3_purge_state_check definition generated from that committed module.
if ! declare -F v3_purge_state_check >/dev/null; then
  V3_PURGE_STATE_MODULE="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/v3_purge_state.py"
  v3_purge_state_check() {
    python3.14 -I -S "$V3_PURGE_STATE_MODULE"
  }
fi

v3_purge_require_clear() {
  local operation="$1" report
  if report="$(v3_purge_state_check)"; then return 0; fi
  printf '%s' "$report" | python3.14 -I -S -c '
import json,sys
try:
    report=json.load(sys.stdin)
except (ValueError,TypeError):
    report={"failures":["purge_state_query_failed"]}
print(json.dumps({"schema_version":"ed-finder/operator-operation-result/v1",
    "operation":sys.argv[1],"status":"stopped","read_only":False,
    "db_writes_performed":False,"failures":report.get("failures",["purge_state_query_failed"]),
    "purge_state":report},sort_keys=True))' "$operation"
  return 78
}
