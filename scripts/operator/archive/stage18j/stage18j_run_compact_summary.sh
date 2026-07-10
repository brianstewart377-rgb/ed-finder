#!/usr/bin/env bash
set -euo pipefail
set +H

ART_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
RECON_ARTIFACT="${RECON_ARTIFACT:-$ART_DIR/enrichment_staging_reconciliation_20260602T112948Z.json}"
COMPACT_SUMMARY="${COMPACT_SUMMARY:-$ART_DIR/reconciliation_compact_summary_20260602T112948Z.json}"
MAX_CANDIDATE_SAMPLES="${MAX_CANDIDATE_SAMPLES:-50}"
CHECK_CANONICAL_COUNT="${CHECK_CANONICAL_COUNT:-no}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

REQUIRE_STAGE18J_ARTIFACT_DIR=yes ART_DIR="$ART_DIR" \
  scripts/operator/require_hetzner_operator_env.sh

if [[ ! "$MAX_CANDIDATE_SAMPLES" =~ ^[0-9]+$ ]]; then
  stop "MAX_CANDIDATE_SAMPLES must be a non-negative integer."
fi

if [[ ! -s "$RECON_ARTIFACT" ]]; then
  stop "reconciliation artifact is missing or empty: $RECON_ARTIFACT"
fi

if ! python3 -c 'import ijson' >/dev/null 2>&1; then
  stop "Python module ijson is missing. Install importer Python requirements or install the OS package, for example: sudo apt-get update && sudo apt-get install -y python3-ijson"
fi

python3 apps/importer/src/reconciliation_artifact_summary.py \
  --artifact "$RECON_ARTIFACT" \
  --output "$COMPACT_SUMMARY" \
  --max-candidate-samples "$MAX_CANDIDATE_SAMPLES"

chmod 600 "$COMPACT_SUMMARY"

echo "== Compact summary file =="
ls -lh "$COMPACT_SUMMARY"

echo "== Compact summary validation =="
python3 - "$COMPACT_SUMMARY" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)

candidate_samples = payload.get('candidate_samples') or {}
if isinstance(candidate_samples, dict):
    sample_count = candidate_samples.get('samples_included')
    if sample_count is None:
        sample_count = len(candidate_samples.get('samples') or [])
else:
    sample_count = len(candidate_samples)

for key in (
    'schema_version',
    'safe_for_git',
    'source_artifact_basename',
    'source_artifact_sha256',
    'source_artifact_size_bytes',
    'canonical_writes_planned',
    'station_candidate_count',
):
    print(f'{key}:', payload.get(key))
print('candidate_samples:', sample_count)
PY

echo "== Secret/path sanity check =="
sensitive_pattern='postgre''sql://|post''gres://|pass''word=|PG''PASSWORD|SEC''RET|TOK''EN|/var/lib/ed-finder|/root/'
if grep -Eq "$sensitive_pattern" "$COMPACT_SUMMARY"; then
  stop "compact summary may contain credentials or private paths. Review the operator artifact out of band; do not commit it."
fi
echo "OK: no obvious credential/private path markers found"

if [[ "$CHECK_CANONICAL_COUNT" == "yes" ]]; then
  echo "== Canonical station count =="
  docker compose exec -T postgres psql -U edfinder -d edfinder -t -A -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM stations;"
else
  echo "== Canonical station count =="
  echo "SKIPPED: set CHECK_CANONICAL_COUNT=yes to run the read-only Docker/Postgres count check."
fi

echo "OK: compact reconciliation summary generated."
echo "OK: no reconciliation, station-type dry-run, or apply was run by this script."
