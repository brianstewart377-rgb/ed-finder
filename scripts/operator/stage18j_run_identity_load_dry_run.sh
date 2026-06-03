#!/usr/bin/env bash
set -euo pipefail
set +H

ART_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
REVIEW_PACKET="${REVIEW_PACKET:-$ART_DIR/station_external_identity_review_packet_20260603T110848Z.json}"
EXPECTED_REVIEW_PACKET_SHA256="${EXPECTED_REVIEW_PACKET_SHA256:-8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6}"
MAX_ROWS="${MAX_ROWS:-20}"
LOAD_DRY_RUN_ARTIFACT="${LOAD_DRY_RUN_ARTIFACT:-$ART_DIR/station_external_identity_load_execution_plan_$(date -u +%Y%m%dT%H%M%SZ).json}"
DRY_RUN_DSN="${DRY_RUN_DSN:-stage18j-p14-dry-run-no-db-connection}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

REQUIRE_STAGE18J_ARTIFACT_DIR=yes ART_DIR="$ART_DIR" \
  scripts/operator/require_hetzner_operator_env.sh

if [[ "${MAX_ROWS}" == "" || ! "${MAX_ROWS}" =~ ^[0-9]+$ ]]; then
  stop "MAX_ROWS must be a positive integer."
fi

if (( MAX_ROWS < 1 || MAX_ROWS > 20 )); then
  stop "MAX_ROWS must be between 1 and 20 for Stage 18J-P14 load dry-run."
fi

if [[ ! -s "$REVIEW_PACKET" ]]; then
  stop "review packet is missing or empty: $REVIEW_PACKET"
fi

case "$REVIEW_PACKET" in
  "$ART_DIR"/*) ;;
  *) stop "REVIEW_PACKET must be read from ART_DIR: $ART_DIR" ;;
esac

case "$LOAD_DRY_RUN_ARTIFACT" in
  "$ART_DIR"/*) ;;
  *) stop "LOAD_DRY_RUN_ARTIFACT must be written under ART_DIR: $ART_DIR" ;;
esac

if ! command -v sha256sum >/dev/null 2>&1; then
  stop "sha256sum is required to verify the review packet."
fi

read -r actual_review_packet_sha _ < <(sha256sum "$REVIEW_PACKET")
if [[ "$actual_review_packet_sha" != "$EXPECTED_REVIEW_PACKET_SHA256" ]]; then
  stop "review packet checksum mismatch. Expected $EXPECTED_REVIEW_PACKET_SHA256, got $actual_review_packet_sha"
fi

echo "== Stage 18J-P14 external identity load dry-run =="
echo "DRY-RUN ONLY: no database connection, no identity load, no station-type dry-run, no canonical apply."
echo "ART_DIR: $ART_DIR"
echo "REVIEW_PACKET: $REVIEW_PACKET"
echo "REVIEW_PACKET_SHA256: $actual_review_packet_sha"
echo "LOAD_DRY_RUN_ARTIFACT: $LOAD_DRY_RUN_ARTIFACT"
echo "MAX_ROWS: $MAX_ROWS"

python3 apps/importer/src/station_external_identity_loader.py \
  --review-packet "$REVIEW_PACKET" \
  --expected-review-packet-sha256 "$EXPECTED_REVIEW_PACKET_SHA256" \
  --dsn "$DRY_RUN_DSN" \
  --max-rows "$MAX_ROWS" \
  --dry-run \
  --output "$LOAD_DRY_RUN_ARTIFACT"

chmod 600 "$LOAD_DRY_RUN_ARTIFACT"

read -r load_dry_run_sha _ < <(sha256sum "$LOAD_DRY_RUN_ARTIFACT")

echo "== Load dry-run file =="
ls -lh "$LOAD_DRY_RUN_ARTIFACT"
echo "load_dry_run_sha256: $load_dry_run_sha"

echo "== Load dry-run summary =="
python3 - "$LOAD_DRY_RUN_ARTIFACT" "$EXPECTED_REVIEW_PACKET_SHA256" "$MAX_ROWS" <<'PY'
import json
import sys

path, expected_review_sha, expected_max_rows = sys.argv[1:4]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)

validation = payload.get('validation_summary') or {}

checks = {
    'schema_version': payload.get('schema_version') == 'station_external_identity_load_execution_plan/v1',
    'dry_run': payload.get('dry_run') is True,
    'write_reviewed_false': payload.get('write_reviewed') is False,
    'review_packet_sha_matches': payload.get('review_packet_sha256') == expected_review_sha,
    'max_rows_matches': str(payload.get('max_rows')) == str(expected_max_rows),
    'identity_rows_selected_within_max': int(payload.get('identity_rows_selected') or 0) <= int(expected_max_rows),
    'canonical_writes_planned_zero': payload.get('canonical_writes_planned') == 0,
    'station_type_writes_planned_zero': payload.get('station_type_writes_planned') == 0,
    'identity_rows_written_zero': payload.get('identity_rows_written') == 0,
    'all_required_checks_passed': validation.get('all_required_checks_passed') is True,
}

for name, ok in checks.items():
    if not ok:
        raise SystemExit(f'STOP: load dry-run validation failed: {name}')

for key, value in (
    ('schema_version', payload.get('schema_version')),
    ('dry_run', payload.get('dry_run')),
    ('write_reviewed', payload.get('write_reviewed')),
    ('review_packet_basename', payload.get('review_packet_basename')),
    ('review_packet_sha256', payload.get('review_packet_sha256')),
    ('identity_rows_selected', payload.get('identity_rows_selected')),
    ('identity_rows_written', payload.get('identity_rows_written')),
    ('max_rows', payload.get('max_rows')),
    ('selected_review_item_ids_count', len(payload.get('selected_review_item_ids') or [])),
    ('selected_plan_row_ids_count', len(payload.get('selected_plan_row_ids') or [])),
    ('canonical_writes_planned', payload.get('canonical_writes_planned')),
    ('station_type_writes_planned', payload.get('station_type_writes_planned')),
    ('approval_allowlist_required', validation.get('approval_allowlist_required')),
):
    print(f'{key}: {value}')
PY

echo "== Secret/path sanity check =="
sensitive_pattern='postgre''sql://|post''gres://|pass''word=|PG''PASSWORD|SEC''RET|TOK''EN'
if grep -Eq "$sensitive_pattern" "$LOAD_DRY_RUN_ARTIFACT"; then
  stop "load dry-run artifact may contain credentials. Review the operator artifact out of band; do not commit it."
fi
echo "OK: no obvious credential markers found"

echo "OK: Stage 18J-P14 external identity load dry-run generated."
echo "OK: dry-run only; no DB access, no identity load, no imports, no reconciliation, no summarizer, no station-type dry-run, no approval record, and no canonical apply."
