#!/usr/bin/env bash
# Read-only ranking plan probe for the pinned F2d Finder products.
# Exit 24: DATABASE_URL or connected database/user differs from the pinned target.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

# Identity deliberately precedes target, stage, generation, database and image
# inspection. A missing helper is itself an identity refusal.
IDENTITY_HELPER="$REPO_ROOT/scripts/operator/lib/f2d_operator_identity.sh"
[ -f "$IDENTITY_HELPER" ] && [ ! -L "$IDENTITY_HELPER" ] || {
  printf '%s\n' 'v3 archetype plan probe: identity helper is missing or symlinked' >&2
  exit 64
}
# shellcheck source=../lib/f2d_operator_identity.sh
source "$IDENTITY_HELPER"
F2D_IDENTITY="$(require_f2d_operator_code_identity "$REPO_ROOT")" || exit $?

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
COMPOSE_PROJECT="edfinder-v3-production"
WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"
TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"
TARGET_PUBLICATION_SEQUENCE="1"
OPERATION_LABEL="ed-finder.operation=v3-archetype-plan-probe"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-archetype-plan-probe"
SEARCH_FINAL_RECEIPT="${HOME}/.local/state/ed-finder/v3-system-search/build-final-receipt.json"
ARCHETYPE_FINAL_RECEIPT="${HOME}/.local/state/ed-finder/v3-system-archetype/build-final-receipt.json"
PYTHON_BIN=""

fail() {
  printf 'v3 archetype plan probe: %s\n' "$*" >&2
  exit 64
}

require_target() {
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
  PYTHON_BIN="$(command -v python3.14 || true)"
  [ -n "$PYTHON_BIN" ] || fail "python3.14 is unavailable"
  [ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
  [ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
  [ "$(docker context show)" = "default" ] || fail "unexpected docker context"
  docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
    || fail "default docker context is not the local rootful socket"
  docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 \
    || fail "retained postgres container is unavailable"
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER")" = "true" ] \
    || fail "retained postgres container is not running"
}

require_stage() {
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in
    /var/tmp/edfinder-v3-plan-probe-"$SOURCE_SHA") ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ ! -L "$REPO_ROOT/.v3-plan-probe-source-sha" ] \
    || fail "trusted main bundle SHA marker is a symlink"
  [ "$(cat "$REPO_ROOT/.v3-plan-probe-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_plan_probe_statements.py" ] \
    || fail "plan statement generator is missing"
  [ -f "$REPO_ROOT/scripts/v3_archetype_plan_probe.py" ] \
    || fail "plan probe program is missing"
  [ -d "$REPO_ROOT/.v3-probe-wheelhouse" ] \
    || fail "offline plan probe dependency wheelhouse is missing"
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

require_generation() {
  local row key identifier state sequence current
  row="$(db_query "BEGIN READ ONLY; SELECT g.generation_key || E'\\t' || g.derived_generation_id::text || E'\\t' || g.lifecycle_state || E'\\t' || p.publication_sequence::text || E'\\t' || (p.derived_generation_id IS NOT NULL)::text FROM v3_meta.derived_generation g LEFT JOIN v3_meta.current_derived_generation p ON p.singleton AND p.derived_generation_id=g.derived_generation_id WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] \
    || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r key identifier state sequence current <<< "$row"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  [ "$identifier" = "$TARGET_GENERATION_ID" ] || fail "target generation UUID mismatch"
  [ "$state" = "PUBLISHED" ] || fail "target generation is not PUBLISHED"
  [ "$sequence" = "$TARGET_PUBLICATION_SEQUENCE" ] \
    || fail "target generation publication sequence mismatch"
  [ "$current" = "true" ] || fail "target generation is not the current pointer"
}

active_api_container() {
  local -a matches=()
  local container service
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")"
    case "$service" in api-*) matches+=("$container") ;; esac
  done < <(docker ps --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --format '{{.Names}}')
  [ "${#matches[@]}" -eq 1 ] \
    || fail "expected exactly one running production API slot, found ${#matches[@]}"
  printf '%s\n' "${matches[0]}"
}

api_database_url() {
  local api="$1" value count network
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')" || return 24
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || return 24
  network="$(docker inspect -f "{{json (index .NetworkSettings.Networks \"$WORKER_NETWORK\")}}" "$POSTGRES_CONTAINER")" || return 24
  # Host rule: the pinned container name or its inspected IPv4 address, with
  # a verified attachment to WORKER_NETWORK. Never resolve arbitrary DNS.
  # The DSN stays in the environment/private command substitution, not argv,
  # diagnostics or receipts. Emit it only to the caller's private capture.
  ACTIVE_API_DATABASE_URL="$value" "$PYTHON_BIN" - \
    "$DATABASE_NAME" "$DATABASE_USER" "$POSTGRES_CONTAINER" "$network" <<'PY'
import ipaddress, json, os, sys
from urllib.parse import parse_qsl, unquote, urlsplit
try:
    value = os.environ['ACTIVE_API_DATABASE_URL']
    if any(character in value for character in '\r\n\x00'):
        raise ValueError
    parsed = urlsplit(value)
    network = json.loads(sys.argv[4])
    address = str(ipaddress.IPv4Address(network['IPAddress']))
    # libpq query parameters can override URI authority/path fields. Refuse
    # target overrides and service indirection even when the URI looks pinned.
    overrides = {'host', 'hostaddr', 'port', 'dbname', 'user', 'service', 'servicefile'}
    if (
        parsed.scheme not in {'postgres', 'postgresql'}
        or unquote(parsed.path) != '/' + sys.argv[1]
        or unquote(parsed.username or '') != sys.argv[2]
        or parsed.hostname not in {sys.argv[3], address}
        or parsed.port not in {None, 5432}
        or parsed.fragment
        or any(key.lower() in overrides for key, _ in parse_qsl(parsed.query))
    ):
        raise ValueError
except (KeyError, TypeError, ValueError):
    # Exception messages from URI parsing can contain credentials.
    raise SystemExit(24) from None
sys.stdout.write(value)
PY
}


require_products() {
  local rows
  rows="$(db_query "BEGIN READ ONLY; SELECT product_code || E'\\t' || lifecycle_state || E'\\t' || (published_at IS NOT NULL)::text FROM v3_meta.derived_product WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND product_code IN ('system_search','system_archetype') ORDER BY product_code; COMMIT;")"
  [ "$(printf '%s\n' "$rows" | wc -l)" -eq 2 ] || return 23
  printf '%s\n' "$rows" | awk -F '\t' \
    '$1 == "system_archetype" && $2 == "READY" && $3 == "true" {a=1}
     $1 == "system_search" && $2 == "READY" && $3 == "true" {s=1}
     END {exit !(a && s)}' || return 23
}

load_final_receipts() {
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - \
    "$SEARCH_FINAL_RECEIPT" "$ARCHETYPE_FINAL_RECEIPT" \
    "$TARGET_GENERATION_ID" "$F2D_IDENTITY" <<'PY'
import sys
from scripts.operator.lib.f2d_evidence import load_sealed

search_path, archetype_path, generation_id, identity = sys.argv[1:]
values = []
for path, product in ((search_path, 'system_search'), (archetype_path, 'system_archetype')):
    receipt = load_sealed(path)
    expected = {
        'schema_version': 'ed-finder/v3-build-final-receipt/v1',
        'product_code': product,
        'derived_generation_id': generation_id,
        'lifecycle_state': 'READY',
        'validation_status': 'VERIFIED',
        'f2d_operator_code_sha256': identity,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise SystemExit(f'{product} build-final receipt identity mismatch')
    for key in ('final_insert_at', 'last_vacuum', 'last_analyze'):
        if not receipt.get(key):
            raise SystemExit(f'{product} build-final receipt lacks {key}')
    values.append(receipt['final_insert_at'])
print('\t'.join(values))
PY
}

dense_anchor() {
  db_query "BEGIN READ ONLY;
WITH target AS (
    SELECT canonical_generation_id
    FROM v3_meta.derived_generation
    WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid
), current_pyramid AS (
    SELECT g.spatial_generation_id, g.pyramid_version
    FROM v3_spatial.current_spatial_generation c
    JOIN v3_spatial.spatial_generation g USING (spatial_generation_id)
    JOIN target t ON t.canonical_generation_id=g.canonical_generation_id
    WHERE g.lifecycle_state='PUBLISHED'
), finest AS (
    SELECT max(c.level) AS level
    FROM v3_spatial.cell_summary c
    JOIN current_pyramid p USING (spatial_generation_id)
)
SELECT json_build_object(
    'spatial_generation_id', p.spatial_generation_id,
    'spatial_pyramid_version', p.pyramid_version,
    'level', c.level,
    'cell_key', c.cell_key,
    'system_count', c.system_count,
    'coordinates', json_build_object(
        'x', c.centroid_x_ly, 'y', c.centroid_y_ly, 'z', c.centroid_z_ly
    )
)::text
FROM v3_spatial.cell_summary c
JOIN current_pyramid p USING (spatial_generation_id)
JOIN finest f ON f.level=c.level
ORDER BY c.system_count DESC, c.cell_key ASC
LIMIT 1;
COMMIT;"
}

emit_result() {
  local exit_code="$1" run_dir="$2" image_reference="${3:-}" image_id="${4:-}" image_digest="${5:-}"
  EXIT_CODE_VALUE="$exit_code" RUN_DIR_VALUE="$run_dir" \
  F2D_IDENTITY_VALUE="$F2D_IDENTITY" IMAGE_REFERENCE_VALUE="$image_reference" \
  IMAGE_ID_VALUE="$image_id" IMAGE_DIGEST_VALUE="$image_digest" \
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path
from scripts.operator.lib.f2d_evidence import load_sealed

exit_code = int(os.environ['EXIT_CODE_VALUE'])
path = Path(os.environ['RUN_DIR_VALUE']) / 'receipt.json'
try:
    receipt = load_sealed(path)
except ValueError:
    receipt = None
status = 'passed' if exit_code == 0 else 'refused' if exit_code in {2,20,21,23,24} else 'failed'
failures = receipt.get('failures', []) if isinstance(receipt, dict) else []
if exit_code and not failures:
    failures = ['database_target_identity_mismatch'] if exit_code == 24 else [f'plan_probe_exit_{exit_code}']
payload = {
    'schema_version': 'ed-finder/operator-operation-result/v1',
    'operation': 'v3-archetype-plan-probe',
    'status': status,
    'exit_code': exit_code,
    'failures': failures,
    'read_only': True,
    'db_writes_performed': False,
    'publication_performed': False,
    'canonical_writes_performed': False,
    'application_service_changes_performed': False,
    'f2d_operator_code_sha256': os.environ['F2D_IDENTITY_VALUE'],
    'image_reference': os.environ['IMAGE_REFERENCE_VALUE'],
    'image_id': os.environ['IMAGE_ID_VALUE'],
    'image_digest': os.environ['IMAGE_DIGEST_VALUE'],
    'receipt': receipt,
}
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY
}

run_operation() {
  require_target
  require_stage
  require_generation

  local timestamp run_dir products_exit api image_reference image_id image_digest expected_digest
  local dsn receipt_values search_final_insert_at archetype_final_insert_at dense_cell
  local dense_x dense_y dense_z statements_sha env_file worker output_file exit_code generation_exit
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="$STATE_ROOT/runs/${timestamp}-$$"
  install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/runs" "$run_dir"

  set +e
  require_products
  products_exit=$?
  set -e
  if [ "$products_exit" -ne 0 ]; then
    emit_result 23 "$run_dir"
    return 23
  fi

  receipt_values="$(load_final_receipts)" || fail "build-final receipts are invalid"
  IFS=$'\t' read -r search_final_insert_at archetype_final_insert_at \
    <<< "$receipt_values"
  [ -n "$search_final_insert_at" ] && [ -n "$archetype_final_insert_at" ] \
    || fail "build-final receipt timestamps are missing"
  dense_cell="$(dense_anchor)"
  [ -n "$dense_cell" ] || fail "densest finest-level spatial cell is unavailable"
  IFS=$'\t' read -r dense_x dense_y dense_z <<< "$(DENSE_CELL="$dense_cell" "$PYTHON_BIN" - <<'PY'
import json, os
value = json.loads(os.environ['DENSE_CELL'])['coordinates']
print(f"{value['x']}\t{value['y']}\t{value['z']}")
PY
)"

  api="$(active_api_container)"
  image_reference="$(docker inspect -f '{{.Config.Image}}' "$api")"
  image_id="$(docker inspect -f '{{.Image}}' "$api")"
  image_digest="$(docker image inspect -f '{{index .RepoDigests 0}}' "$image_id")"
  [ -n "$image_reference" ] && [ -n "$image_id" ] && [ -n "$image_digest" ] \
    || fail "active API image identity is incomplete"
  expected_digest="$("$PYTHON_BIN" - "$REPO_ROOT/deploy/v3-production/target-authority.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding='utf-8'))
print(value['accepted_release_schema_compatibility']['images']['backend'])
PY
)"
  [ "$image_digest" = "$expected_digest" ] \
    || fail "active API RepoDigest differs from target authority"

  set +e
  docker exec -i "$api" /app/.venv/bin/python - \
    --dense-anchor "$dense_x" "$dense_y" "$dense_z" \
    < "$REPO_ROOT/scripts/v3_plan_probe_statements.py" \
    > "$run_dir/statements.json"
  generation_exit=$?
  set -e
  if [ "$generation_exit" -ne 0 ]; then
    emit_result 21 "$run_dir" "$image_reference" "$image_id" "$image_digest"
    return 21
  fi
  if ! statements_sha="$(PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$run_dir/statements.json" <<'PY'
import json, sys
from scripts.operator.lib.f2d_evidence import canonical_sha256
value = json.load(open(sys.argv[1], encoding='utf-8'))
if len(value.get('statements', [])) != 80:
    raise SystemExit('statement count mismatch')
print(canonical_sha256(value))
PY
)"; then
    emit_result 21 "$run_dir" "$image_reference" "$image_id" "$image_digest"
    return 21
  fi

  if ! dsn="$(api_database_url "$api")"; then
    emit_result 24 "$run_dir" "$image_reference" "$image_id" "$image_digest"
    return 24
  fi
  env_file="$run_dir/plan-probe.env"
  output_file="$run_dir/program-output.json"
  worker="edfinder-v3-plan-probe-${SOURCE_SHA:0:12}-$$"
  umask 077
  printf 'V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$env_file"
  printf 'V3_PLAN_PROBE_STATEMENTS_SHA256=%s\n' "$statements_sha" >> "$env_file"
  printf 'V3_PLAN_PROBE_IMAGE_DIGEST=%s\n' "$image_digest" >> "$env_file"
  printf 'V3_PLAN_PROBE_SEARCH_FINAL_INSERT_AT=%s\n' "$search_final_insert_at" >> "$env_file"
  printf 'V3_PLAN_PROBE_ARCHETYPE_FINAL_INSERT_AT=%s\n' "$archetype_final_insert_at" >> "$env_file"
  printf 'V3_PLAN_PROBE_DENSE_CELL=%s\n' "$dense_cell" >> "$env_file"
  chmod 600 "$env_file"
  trap 'rm -f -- "$env_file"' EXIT

  set +e
  timeout --signal=TERM 1800 docker run --rm \
    --name "$worker" \
    --label "$OPERATION_LABEL" \
    --network "$WORKER_NETWORK" \
    --cpus 2 \
    --memory 4g \
    --memory-swap 4g \
    --pids-limit 128 \
    --read-only \
    --tmpfs /tmp \
    --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --mount "type=bind,src=${run_dir},dst=/gate" \
    --entrypoint /bin/sh \
    "$image_digest" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-probe-wheelhouse --target /tmp/v3-plan-probe-deps \
        "psycopg[binary]==3.3.4" 1>&2
      export PYTHONPATH="/tmp/v3-plan-probe-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_archetype_plan_probe.py \
        --statements /gate/statements.json \
        --statements-sha256 "$V3_PLAN_PROBE_STATEMENTS_SHA256" \
        --image-digest "$V3_PLAN_PROBE_IMAGE_DIGEST" \
        --generation-key ratings_v4_prod_p4_parallel_v1 \
        --generation-id cfc25d36-3bc7-4011-a465-d6460eaaf826 \
        --publication-sequence 1 \
        --search-final-insert-at "$V3_PLAN_PROBE_SEARCH_FINAL_INSERT_AT" \
        --archetype-final-insert-at "$V3_PLAN_PROBE_ARCHETYPE_FINAL_INSERT_AT" \
        --dense-anchor-cell "$V3_PLAN_PROBE_DENSE_CELL" \
        --output /gate/receipt.json
    ' > "$output_file"
  exit_code=$?
  set -e
  rm -f -- "$env_file"
  trap - EXIT

  emit_result "$exit_code" "$run_dir" "$image_reference" "$image_id" "$image_digest"
  return "$exit_code"
}

case "$ACTION" in
  run) run_operation ;;
  *) fail "expected run <REPO_ROOT> <SOURCE_SHA>" ;;
esac
