#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder

ARTIFACT_STAGE="${1:-stage-18j}"

if ! [[ "$ARTIFACT_STAGE" =~ ^stage-[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
  echo "STOP: invalid artifact stage: $ARTIFACT_STAGE" >&2
  exit 1
fi

ART_DIR="/var/lib/ed-finder/operator-artifacts/$ARTIFACT_STAGE"

echo "== Latest artifact summary =="
echo "artifact_stage: $ARTIFACT_STAGE"
echo "artifact_dir: $ART_DIR"

if [ ! -d "$ART_DIR" ]; then
  echo "STOP: artifact directory missing: $ART_DIR" >&2
  exit 1
fi

LATEST="$(find "$ART_DIR" -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' | sort -nr | head -n 1 | awk '{print $2}')"

if [ -z "$LATEST" ]; then
  echo "STOP: no JSON artifacts found in $ART_DIR" >&2
  exit 1
fi

if [ ! -s "$LATEST" ]; then
  echo "STOP: latest artifact is empty: $LATEST" >&2
  exit 1
fi

echo "ARTIFACT=$LATEST"
ls -lh "$LATEST"
sha256sum "$LATEST"

python3 -c '
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

print("schema_version:", payload.get("schema_version"))
print("generated_at:", payload.get("generated_at"))
print("read_only:", payload.get("read_only"))
print("dry_run:", payload.get("dry_run"))
print("write_reviewed:", payload.get("write_reviewed"))
print("offline:", payload.get("offline"))
print("report_only:", payload.get("report_only"))

git = payload.get("git") or {}
if git:
    print("git_branch:", git.get("branch"))
    print("git_head:", git.get("head"))

safety = payload.get("safety_summary") or {}
for key in (
    "db_read_only_confirmed",
    "db_writes_performed",
    "db_write_performed",
    "enum_change_performed",
    "migrations_performed",
    "station_rows_updated",
    "station_type_writes_performed",
    "canonical_apply_performed",
    "repo_edits_performed",
):
    if key in safety:
        print(f"{key}:", safety.get(key))

integrity = payload.get("artifact_integrity") or {}
if "canonical_json_sha256" in integrity:
    print("artifact_integrity_sha256:", integrity.get("canonical_json_sha256"))
' "$LATEST"

echo
echo "== Safety boundary =="
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "migrations_performed: false"
echo "station_type_writes_performed: false"
echo "canonical_apply_performed: false"
