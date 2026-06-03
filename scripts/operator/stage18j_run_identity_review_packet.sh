#!/usr/bin/env bash
set -euo pipefail
set +H

ART_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
LOAD_PLAN_ARTIFACT="${LOAD_PLAN_ARTIFACT:-$ART_DIR/station_external_identity_load_plan_20260603T071913Z.json}"
EXPECTED_LOAD_PLAN_SHA256="${EXPECTED_LOAD_PLAN_SHA256:-3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1}"
MAX_PLANNED_ROWS="${MAX_PLANNED_ROWS:-20}"
REVIEW_PACKET="${REVIEW_PACKET:-$ART_DIR/station_external_identity_review_packet_$(date -u +%Y%m%dT%H%M%SZ).json}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

REQUIRE_STAGE18J_ARTIFACT_DIR=yes ART_DIR="$ART_DIR" \
  scripts/operator/require_hetzner_operator_env.sh

if [[ "${MAX_PLANNED_ROWS}" == "" || ! "${MAX_PLANNED_ROWS}" =~ ^[0-9]+$ ]]; then
  stop "MAX_PLANNED_ROWS must be a positive integer."
fi

if (( MAX_PLANNED_ROWS < 1 || MAX_PLANNED_ROWS > 20 )); then
  stop "MAX_PLANNED_ROWS must be between 1 and 20 for Stage 18J-P12/P13 review."
fi

if [[ ! -s "$LOAD_PLAN_ARTIFACT" ]]; then
  stop "load-plan artifact is missing or empty: $LOAD_PLAN_ARTIFACT"
fi

case "$LOAD_PLAN_ARTIFACT" in
  "$ART_DIR"/*) ;;
  *) stop "LOAD_PLAN_ARTIFACT must be read from ART_DIR: $ART_DIR" ;;
esac

case "$REVIEW_PACKET" in
  "$ART_DIR"/*) ;;
  *) stop "REVIEW_PACKET must be written under ART_DIR: $ART_DIR" ;;
esac

if ! command -v sha256sum >/dev/null 2>&1; then
  stop "sha256sum is required to verify the load-plan artifact."
fi

read -r actual_load_plan_sha _ < <(sha256sum "$LOAD_PLAN_ARTIFACT")
if [[ "$actual_load_plan_sha" != "$EXPECTED_LOAD_PLAN_SHA256" ]]; then
  stop "load-plan artifact checksum mismatch. Expected $EXPECTED_LOAD_PLAN_SHA256, got $actual_load_plan_sha"
fi

echo "== Stage 18J-P12/P13 identity review packet =="
echo "OFFLINE REVIEW ONLY: no database connection, no identity load, no station-type dry-run, no canonical apply."
echo "ART_DIR: $ART_DIR"
echo "LOAD_PLAN_ARTIFACT: $LOAD_PLAN_ARTIFACT"
echo "LOAD_PLAN_SHA256: $actual_load_plan_sha"
echo "REVIEW_PACKET: $REVIEW_PACKET"
echo "MAX_PLANNED_ROWS: $MAX_PLANNED_ROWS"

python3 apps/importer/src/station_external_identity_review_packet.py \
  --load-plan-artifact "$LOAD_PLAN_ARTIFACT" \
  --expected-load-plan-sha256 "$EXPECTED_LOAD_PLAN_SHA256" \
  --output "$REVIEW_PACKET" \
  --max-planned-rows "$MAX_PLANNED_ROWS"

chmod 600 "$REVIEW_PACKET"

read -r review_packet_sha _ < <(sha256sum "$REVIEW_PACKET")

echo "== Review packet file =="
ls -lh "$REVIEW_PACKET"
echo "review_packet_sha256: $review_packet_sha"

echo "== Review packet summary =="
python3 - "$REVIEW_PACKET" "$EXPECTED_LOAD_PLAN_SHA256" "$MAX_PLANNED_ROWS" <<'PY'
import json
import sys

path, expected_source_sha, expected_max_rows = sys.argv[1:4]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)

summary = payload.get('summary') or {}
source_artifact = payload.get('source_artifact') or {}
source_scope = payload.get('source_scope') or {}

checks = {
    'schema_version': payload.get('schema_version') == 'station_external_identity_review_packet/v1',
    'dry_run': payload.get('dry_run') is True,
    'read_only': payload.get('read_only') is True,
    'report_only': payload.get('report_only') is True,
    'source_sha_matches': source_artifact.get('sha256') == expected_source_sha,
    'max_planned_rows_matches': str(payload.get('max_planned_rows')) == str(expected_max_rows),
    'canonical_writes_planned_zero': payload.get('canonical_writes_planned') == 0,
    'station_type_writes_planned_zero': payload.get('station_type_writes_planned') == 0,
    'identity_rows_written_zero': payload.get('identity_rows_written') == 0,
    'approval_record_created_false': payload.get('approval_record_created') is False,
}

for name, ok in checks.items():
    if not ok:
        raise SystemExit(f'STOP: review packet validation failed: {name}')

for key, value in (
    ('schema_version', payload.get('schema_version')),
    ('source_artifact_basename', source_artifact.get('basename')),
    ('source_artifact_sha256', source_artifact.get('sha256')),
    ('source_artifact_integrity_sha256', source_artifact.get('artifact_integrity_sha256')),
    ('source_run_key', source_scope.get('source_run_key')),
    ('source_file_key', source_scope.get('source_file_key')),
    ('total_candidates_seen', source_scope.get('total_candidates_seen')),
    ('eligible_confirmed_candidates_seen', source_scope.get('eligible_confirmed_candidates_seen')),
    ('source_planned_rows_count', source_scope.get('source_planned_rows_count')),
    ('planned_rows_included', summary.get('planned_rows_included')),
    ('manual_review_items_count', summary.get('manual_review_items_count')),
    ('manual_review_status_counts', json.dumps(summary.get('manual_review_status_counts') or {}, sort_keys=True)),
    ('canonical_writes_planned', payload.get('canonical_writes_planned')),
    ('station_type_writes_planned', payload.get('station_type_writes_planned')),
    ('identity_rows_written', payload.get('identity_rows_written')),
    ('approval_record_created', payload.get('approval_record_created')),
):
    print(f'{key}: {value}')
PY

echo "== Secret/path sanity check =="
sensitive_pattern='postgre''sql://|post''gres://|pass''word=|PG''PASSWORD|SEC''RET|TOK''EN'
if grep -Eq "$sensitive_pattern" "$REVIEW_PACKET"; then
  stop "review packet may contain credentials. Review the operator artifact out of band; do not commit it."
fi
echo "OK: no obvious credential markers found"

echo "OK: Stage 18J-P12/P13 review packet generated."
echo "OK: offline review only; no DB access, no identity load, no imports, no reconciliation, no summarizer, no station-type dry-run, no approval record, and no canonical apply."
