#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder

ART_DIR="/var/lib/ed-finder/operator-artifacts/stage-18j"

echo "== Latest operator artifacts =="
if [ -d "$ART_DIR" ]; then
  find "$ART_DIR" -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' \
    | sort -nr \
    | head -n 20 \
    | while read -r _ path; do
        echo
        echo "ARTIFACT=$path"
        ls -lh "$path"
        sha256sum "$path"

        python3 - "$path" <<'PY_ART_SUMMARY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception as exc:
    print(f"summary_error: {exc}")
    raise SystemExit(0)

print("schema_version:", payload.get("schema_version"))
print("read_only:", payload.get("read_only"))
print("dry_run:", payload.get("dry_run"))
print("write_reviewed:", payload.get("write_reviewed"))
print("offline:", payload.get("offline"))

safety = payload.get("safety_summary") or {}
for key in (
    "db_read_only_confirmed",
    "db_writes_performed",
    "station_rows_updated",
    "station_type_writes_performed",
    "canonical_apply_performed",
):
    if key in safety:
        print(f"{key}:", safety.get(key))

integrity = payload.get("artifact_integrity") or {}
if "canonical_json_sha256" in integrity:
    print("artifact_integrity_sha256:", integrity.get("canonical_json_sha256"))
PY_ART_SUMMARY
      done
else
  echo "No artifact directory found: $ART_DIR"
fi

echo
echo "== Safety boundary =="
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "migrations_performed: false"
echo "station_type_writes_performed: false"
echo "canonical_apply_performed: false"
