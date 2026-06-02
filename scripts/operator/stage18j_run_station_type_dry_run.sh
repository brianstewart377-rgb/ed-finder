#!/usr/bin/env bash
set -euo pipefail
set +H

ART_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
RECON_ARTIFACT="${RECON_ARTIFACT:-$ART_DIR/enrichment_staging_reconciliation_20260602T112948Z.json}"
EXPECTED_RECON_SHA256="${EXPECTED_RECON_SHA256:-0bacd62b7de0adf749b3c0de59ac3eebd4f67a6bea18eb96510d29f999935802}"
DRY_RUN_ARTIFACT="${DRY_RUN_ARTIFACT:-$ART_DIR/station_type_canonical_pilot_dry_run_20260602T112948Z.json}"
MAX_ROWS="${MAX_ROWS:-5}"
BLOCKED_CANDIDATE_SAMPLE_LIMIT="${BLOCKED_CANDIDATE_SAMPLE_LIMIT:-100}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

REQUIRE_STAGE18J_ARTIFACT_DIR=yes ART_DIR="$ART_DIR" \
  scripts/operator/require_hetzner_operator_env.sh

if [[ "${MAX_ROWS}" == "" || ! "${MAX_ROWS}" =~ ^[0-9]+$ ]]; then
  stop "MAX_ROWS must be a non-negative integer."
fi

if (( MAX_ROWS > 20 )); then
  stop "MAX_ROWS must be <= 20 for the first Stage 18J-P station-type dry-run."
fi

if [[ "${BLOCKED_CANDIDATE_SAMPLE_LIMIT}" == "" || ! "${BLOCKED_CANDIDATE_SAMPLE_LIMIT}" =~ ^[0-9]+$ ]]; then
  stop "BLOCKED_CANDIDATE_SAMPLE_LIMIT must be a non-negative integer."
fi

if [[ ! -s "$RECON_ARTIFACT" ]]; then
  stop "reconciliation artifact is missing or empty: $RECON_ARTIFACT"
fi

case "$DRY_RUN_ARTIFACT" in
  "$ART_DIR"/*) ;;
  *) stop "DRY_RUN_ARTIFACT must be written under ART_DIR: $ART_DIR" ;;
esac

if ! command -v sha256sum >/dev/null 2>&1; then
  stop "sha256sum is required to verify the reconciliation artifact."
fi

read -r actual_recon_sha _ < <(sha256sum "$RECON_ARTIFACT")
if [[ "$actual_recon_sha" != "$EXPECTED_RECON_SHA256" ]]; then
  stop "reconciliation artifact checksum mismatch. Expected $EXPECTED_RECON_SHA256, got $actual_recon_sha"
fi

echo "== Stage 18J-P station-type dry-run =="
echo "DRY-RUN ONLY: no database connection, no approval record, no canonical apply."
echo "ART_DIR: $ART_DIR"
echo "RECON_ARTIFACT: $RECON_ARTIFACT"
echo "RECON_SHA256: $actual_recon_sha"
echo "DRY_RUN_ARTIFACT: $DRY_RUN_ARTIFACT"
echo "MAX_ROWS: $MAX_ROWS"
echo "BLOCKED_CANDIDATE_SAMPLE_LIMIT: $BLOCKED_CANDIDATE_SAMPLE_LIMIT"

python3 apps/importer/src/station_type_canonical_pilot.py \
  --reconciliation-report "$RECON_ARTIFACT" \
  --output "$DRY_RUN_ARTIFACT" \
  --limit "$MAX_ROWS" \
  --blocked-candidate-sample-limit "$BLOCKED_CANDIDATE_SAMPLE_LIMIT" \
  --json \
  --quiet

chmod 600 "$DRY_RUN_ARTIFACT"

read -r dry_run_sha _ < <(sha256sum "$DRY_RUN_ARTIFACT")

echo "== Station-type dry-run file =="
ls -lh "$DRY_RUN_ARTIFACT"
echo "dry_run_artifact_sha256: $dry_run_sha"

echo "== Station-type dry-run validation =="
python3 - "$DRY_RUN_ARTIFACT" "$EXPECTED_RECON_SHA256" "$MAX_ROWS" <<'PY'
import json
import sys

path, expected_source_sha, expected_max_rows = sys.argv[1:4]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)

summary = payload.get('summary') or {}
source_scope = payload.get('source_scope') or {}
filters = payload.get('filters') or {}
integrity = payload.get('artifact_integrity') or {}

checks = {
    'dry_run': payload.get('dry_run') is True,
    'canonical_writes_planned_zero': summary.get('canonical_writes_planned') == 0,
    'apply_run_false': summary.get('apply_run') is False,
    'approval_record_created_false': summary.get('approval_record_created') is False,
    'source_sha_matches': source_scope.get('input_artifact_sha256') == expected_source_sha,
    'max_rows_matches': str(filters.get('max_row_bound')) == str(expected_max_rows),
}

for name, ok in checks.items():
    if not ok:
        raise SystemExit(f'STOP: dry-run validation failed: {name}')

for key, value in (
    ('schema_version', payload.get('schema_version')),
    ('dry_run', payload.get('dry_run')),
    ('canonical_writes_planned', summary.get('canonical_writes_planned')),
    ('total_candidates_seen', summary.get('total_candidates_seen')),
    ('eligible_station_type_updates', summary.get('eligible_station_type_updates')),
    ('eligible_candidates', summary.get('eligible_candidates')),
    ('blocked_candidates', summary.get('blocked_candidates')),
    ('blocked_candidate_samples_included', summary.get('blocked_candidate_samples_included')),
    ('blocked_candidate_sample_limit', summary.get('blocked_candidate_sample_limit')),
    ('source_reconciliation_artifact_basename', source_scope.get('input_artifact_basename')),
    ('source_reconciliation_artifact_sha256', source_scope.get('input_artifact_sha256')),
    ('max_row_bound', filters.get('max_row_bound')),
    ('artifact_integrity_sha256', integrity.get('canonical_json_sha256')),
    ('apply_run', summary.get('apply_run')),
    ('approval_record_created', summary.get('approval_record_created')),
):
    print(f'{key}: {value}')

print('rejection_reason_counts:', json.dumps(summary.get('rejection_reason_counts') or {}, sort_keys=True))
PY

echo "== Secret/path sanity check =="
sensitive_pattern='postgre''sql://|post''gres://|pass''word=|PG''PASSWORD|SEC''RET|TOK''EN|/var/lib/ed-finder|/root/'
if grep -Eq "$sensitive_pattern" "$DRY_RUN_ARTIFACT"; then
  stop "station-type dry-run artifact may contain credentials or private paths. Review the operator artifact out of band; do not commit it."
fi
echo "OK: no obvious credential/private path markers found"

echo "OK: Stage 18J-P station-type dry-run artifact generated."
echo "OK: dry-run only; no database access, no approval record, and no canonical apply."
