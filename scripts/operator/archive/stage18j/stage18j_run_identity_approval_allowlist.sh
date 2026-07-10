#!/usr/bin/env bash
set -euo pipefail
set +H

ART_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
REVIEW_PACKET="${REVIEW_PACKET:-$ART_DIR/station_external_identity_review_packet_20260603T110848Z.json}"
EXPECTED_REVIEW_PACKET_SHA256="${EXPECTED_REVIEW_PACKET_SHA256:-8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6}"
EXPECTED_REVIEW_PACKET_INTEGRITY_SHA256="${EXPECTED_REVIEW_PACKET_INTEGRITY_SHA256:-8cbcf4f2c0d4e3180c3fa6fcbf44f41e71269254168fee0b121f4c6b07bcab84}"
MAX_ROWS="${MAX_ROWS:-20}"
REVIEWER="${REVIEWER:-stage-18j-p14c-operator}"
REVIEWER_DECISION="${REVIEWER_DECISION:-approve_selected_identity_rows}"
ALLOWLIST_ARTIFACT="${ALLOWLIST_ARTIFACT:-$ART_DIR/station_external_identity_load_approval_allowlist_$(date -u +%Y%m%dT%H%M%SZ).json}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

REQUIRE_STAGE18J_ARTIFACT_DIR=yes ART_DIR="$ART_DIR" \
  scripts/operator/require_hetzner_operator_env.sh

if [[ "${CONFIRM_IDENTITY_ALLOWLIST:-}" != "yes" ]]; then
  stop "CONFIRM_IDENTITY_ALLOWLIST=yes is required to create the offline allowlist artifact."
fi

if [[ "${MAX_ROWS}" == "" || ! "${MAX_ROWS}" =~ ^[0-9]+$ ]]; then
  stop "MAX_ROWS must be a positive integer."
fi

if (( MAX_ROWS < 1 || MAX_ROWS > 20 )); then
  stop "MAX_ROWS must be between 1 and 20 for Stage 18J-P14C approval allowlist."
fi

if [[ "$REVIEWER_DECISION" != "approve_selected_identity_rows" ]]; then
  stop "REVIEWER_DECISION must be approve_selected_identity_rows."
fi

if [[ ! -s "$REVIEW_PACKET" ]]; then
  stop "review packet is missing or empty: $REVIEW_PACKET"
fi

case "$REVIEW_PACKET" in
  "$ART_DIR"/*) ;;
  *) stop "REVIEW_PACKET must be read from ART_DIR: $ART_DIR" ;;
esac

case "$ALLOWLIST_ARTIFACT" in
  "$ART_DIR"/*) ;;
  *) stop "ALLOWLIST_ARTIFACT must be written under ART_DIR: $ART_DIR" ;;
esac

if ! command -v sha256sum >/dev/null 2>&1; then
  stop "sha256sum is required to verify the review packet."
fi

read -r actual_review_packet_sha _ < <(sha256sum "$REVIEW_PACKET")
if [[ "$actual_review_packet_sha" != "$EXPECTED_REVIEW_PACKET_SHA256" ]]; then
  stop "review packet checksum mismatch. Expected $EXPECTED_REVIEW_PACKET_SHA256, got $actual_review_packet_sha"
fi

echo "== Stage 18J-P14C external identity approval allowlist =="
echo "OFFLINE ARTIFACT ONLY: no database connection, no identity load, no station-type dry-run, no canonical apply."
echo "ART_DIR: $ART_DIR"
echo "REVIEW_PACKET: $REVIEW_PACKET"
echo "REVIEW_PACKET_SHA256: $actual_review_packet_sha"
echo "ALLOWLIST_ARTIFACT: $ALLOWLIST_ARTIFACT"
echo "MAX_ROWS: $MAX_ROWS"
echo "REVIEWER_DECISION: $REVIEWER_DECISION"

python3 apps/importer/src/station_external_identity_approval_allowlist.py \
  --review-packet "$REVIEW_PACKET" \
  --expected-review-packet-sha256 "$EXPECTED_REVIEW_PACKET_SHA256" \
  --output "$ALLOWLIST_ARTIFACT" \
  --confirm-reviewed \
  --reviewer-decision "$REVIEWER_DECISION" \
  --max-rows "$MAX_ROWS" \
  --reviewer "$REVIEWER"

chmod 600 "$ALLOWLIST_ARTIFACT"

read -r allowlist_sha _ < <(sha256sum "$ALLOWLIST_ARTIFACT")

echo "== Approval allowlist file =="
ls -lh "$ALLOWLIST_ARTIFACT"
echo "allowlist_sha256: $allowlist_sha"

echo "== Approval allowlist summary =="
python3 - "$ALLOWLIST_ARTIFACT" "$EXPECTED_REVIEW_PACKET_SHA256" "$EXPECTED_REVIEW_PACKET_INTEGRITY_SHA256" "$MAX_ROWS" <<'PY'
import json
import sys

path, expected_review_sha, expected_integrity_sha, expected_max_rows = sys.argv[1:5]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)

safety = payload.get('safety_summary') or {}

checks = {
    'schema_version': payload.get('schema_version') == 'station_external_identity_load_approval_allowlist/v1',
    'offline': payload.get('offline') is True,
    'read_only': payload.get('read_only') is True,
    'review_packet_sha_matches': payload.get('source_review_packet_sha256') == expected_review_sha,
    'review_packet_integrity_matches': payload.get('source_review_packet_integrity_sha256') == expected_integrity_sha,
    'reviewer_decision': payload.get('reviewer_decision') == 'approve_selected_identity_rows',
    'max_rows_matches': str(payload.get('max_rows')) == str(expected_max_rows),
    'approved_rows_within_max': int(payload.get('approved_rows_count') or 0) <= int(expected_max_rows),
    'approval_record_created_false': payload.get('approval_record_created') is False,
    'identity_rows_written_zero': payload.get('identity_rows_written') == 0,
    'canonical_writes_planned_zero': payload.get('canonical_writes_planned') == 0,
    'station_type_writes_planned_zero': payload.get('station_type_writes_planned') == 0,
    'all_required_checks_passed': safety.get('all_required_checks_passed') is True,
    'db_write_statements_absent': safety.get('db_write_statements_included') is False,
}

for name, ok in checks.items():
    if not ok:
        raise SystemExit(f'STOP: approval allowlist validation failed: {name}')

for key, value in (
    ('schema_version', payload.get('schema_version')),
    ('offline', payload.get('offline')),
    ('read_only', payload.get('read_only')),
    ('source_review_packet_basename', payload.get('source_review_packet_basename')),
    ('source_review_packet_sha256', payload.get('source_review_packet_sha256')),
    ('source_review_packet_integrity_sha256', payload.get('source_review_packet_integrity_sha256')),
    ('reviewer_decision', payload.get('reviewer_decision')),
    ('approved_rows_count', payload.get('approved_rows_count')),
    ('approved_review_item_ids_count', len(payload.get('approved_review_item_ids') or [])),
    ('approved_plan_row_ids_count', len(payload.get('approved_plan_row_ids') or [])),
    ('approval_record_created', payload.get('approval_record_created')),
    ('identity_rows_written', payload.get('identity_rows_written')),
    ('canonical_writes_planned', payload.get('canonical_writes_planned')),
    ('station_type_writes_planned', payload.get('station_type_writes_planned')),
):
    print(f'{key}: {value}')
PY

echo "== Secret/path sanity check =="
sensitive_pattern='postgre''sql://|post''gres://|pass''word=|PG''PASSWORD|SEC''RET|TOK''EN'
if grep -Eq "$sensitive_pattern" "$ALLOWLIST_ARTIFACT"; then
  stop "approval allowlist artifact may contain credentials. Review the operator artifact out of band; do not commit it."
fi
echo "OK: no obvious credential markers found"

echo "OK: Stage 18J-P14C external identity approval allowlist generated."
echo "OK: allowlist artifact only; no DB access, no identity load, no imports, no reconciliation, no summarizer, no station-type dry-run, no production approval record, and no canonical apply."
