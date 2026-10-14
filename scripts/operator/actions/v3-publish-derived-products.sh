#!/usr/bin/env bash
# Governed, paired Finder product publication. Production workflow only.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"
ACTOR="${4:-}"

# Identity deliberately precedes target, stage, generation, database and image
# inspection. A missing helper is itself an identity refusal.
IDENTITY_HELPER="$REPO_ROOT/scripts/operator/lib/f2d_operator_identity.sh"
[ -f "$IDENTITY_HELPER" ] && [ ! -L "$IDENTITY_HELPER" ] || {
  printf '%s\n' 'v3 product publication: identity helper is missing or symlinked' >&2
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
OPERATION_LABEL="ed-finder.operation=v3-publish-derived-products"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-publish-derived-products"
SEARCH_FINAL_RECEIPT="${HOME}/.local/state/ed-finder/v3-system-search/build-final-receipt.json"
ARCHETYPE_FINAL_RECEIPT="${HOME}/.local/state/ed-finder/v3-system-archetype/build-final-receipt.json"
PYTHON_BIN=""
RUN_DIR=""
ENV_FILE=""
WORKER_PID=""
WORKER=""
COMMITTED=false
RESULT_EMITTED=false

fail() {
  printf 'v3 product publication: %s\n' "$*" >&2
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
    /var/tmp/edfinder-v3-publish-"$SOURCE_SHA") ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ ! -L "$REPO_ROOT/.v3-publish-source-sha" ] \
    || fail "trusted main bundle SHA marker is a symlink"
  [ "$(cat "$REPO_ROOT/.v3-publish-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_plan_probe_statements.py" ] \
    || fail "plan statement generator is missing"
  [ -f "$REPO_ROOT/scripts/v3_archetype_plan_probe.py" ] \
    || fail "plan probe program is missing"
  [[ "$ACTOR" =~ ^[A-Za-z0-9._@:/-]{1,128}$ ]] || fail "actor is invalid"
  [ -f "$REPO_ROOT/scripts/v3_publish_derived_products.py" ] || fail "publisher is missing"
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

# Refusal codes: 70 deployment lock; 71 product state; 72 already published;
# 73 image/attestation; 74 behavioural probes; 75 code/model identity;
# 76 maintenance; 77 commit handshake; 78 timeout; 79 database target identity;
# 80 published_unhealthy: committed publication failed postcommit verification.
api_database_url() {
  local api="$1" value count network
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')" || return 79
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || return 79
  network="$(docker inspect -f "{{json (index .NetworkSettings.Networks \"$WORKER_NETWORK\")}}" "$POSTGRES_CONTAINER")" || return 79
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
    raise SystemExit(79) from None
sys.stdout.write(value)
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

# The inherited descriptor holds the same flock as v3_production_deploy.py.
# Never unlock until the worker has terminated and commit evidence is recorded.
acquire_deployment_lock() {
  local receipt_directory
  receipt_directory="$("$PYTHON_BIN" - "$REPO_ROOT/deploy/v3-production/target-authority.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding='utf-8'))
path = value['external_authority']['receipt_directory']
if path != '/var/lib/ed-finder/v3-production/receipts':
    raise SystemExit('unexpected deployment receipt directory')
print(path)
PY
)" || refuse 70 deployment_lock_path
  [ -d "$receipt_directory" ] && [ ! -L "$receipt_directory" ] \
    && [ ! -L "$receipt_directory/deploy.lock" ] || refuse 70 deployment_lock_path
  exec {DEPLOY_LOCK_FD}>>"$receipt_directory/deploy.lock" || refuse 70 deployment_lock_open
  chmod 600 "$receipt_directory/deploy.lock"
  flock -n "$DEPLOY_LOCK_FD" || refuse 70 deployment_lock_held
}

write_result() {
  local code="$1" item="$2"
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$RUN_DIR" "$code" "$item" \
    "$F2D_IDENTITY" "$ACTOR" "$COMMITTED" "$TARGET_GENERATION_KEY" \
    "$TARGET_GENERATION_ID" "$TARGET_PUBLICATION_SEQUENCE" <<'PY'
import json, os, sys
from pathlib import Path
from scripts.operator.lib.f2d_evidence import canonical_json, load_sealed, seal
(directory, code, item, identity, actor, committed, key, identifier, sequence) = sys.argv[1:]
root = Path(directory)
code = int(code)
performed = committed == 'true'
body = {
    'schema_version': 'ed-finder/v3-publish-derived-products/v1',
    'generation': {'generation_key': key, 'derived_generation_id': identifier,
                   'publication_sequence': int(sequence), 'lifecycle_state': 'PUBLISHED'},
    'actor': actor, 'f2d_operator_code_sha256': identity,
    'status': 'published' if code == 0 else 'published_unhealthy' if code == 80 and performed else 'refused' if 70 <= code <= 79 else 'failed',
    'exit_code': code, 'failures': [item] if item else [],
    'publication_performed': performed, 'db_writes_performed': performed,
}
for filename, field in (
    ('products.json', 'manifest_identities'), ('verified-identities.json', 'verified_manifest_identities'),
    ('attestation.json', 'attestation'),
    ('image-first.json', 'image_digest_first'), ('image-last.json', 'image_digest_last'),
    ('probe-pairs.json', 'probe_pair_statuses'), ('maintenance.json', 'vacuum_analyze'),
    ('statements-identity.json', 'statements_sha256'), ('postcommit.json', 'postcommit'),
    ('live-finder.json', 'live_finder_verification'),
):
    path = root / filename
    if path.is_file():
        try:
            body[field] = json.loads(path.read_text())
        except (OSError, ValueError):
            body[field] = {'evidence_unreadable': True}
if code == 80:
    body['failures'].extend((body.get('live_finder_verification') or {}).get('failures', []))
program = None
for filename in ('receipt.json', 'program-output.json'):
    try:
        program = load_sealed(root / filename)
        break
    except ValueError:
        continue
if program:
    body['program_receipt'] = program
    body['plan_probe_receipt_sha256'] = (program.get('plan_probe_receipt') or {}).get('content_sha256')
    body['plan_probe_status'] = (program.get('plan_probe_receipt') or {}).get('status')
    for field in ('published_at', 'audit_rows', 'view_visibility'):
        body[field] = program.get(field)
receipt = seal(body)
path = root / 'action-receipt.json'
temporary = path.with_suffix('.tmp')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(canonical_json(receipt) + '\n')
os.replace(temporary, path)
print(canonical_json({
    'schema_version': 'ed-finder/operator-operation-result/v1',
    'operation': 'v3-publish-derived-products', 'status': body['status'],
    'exit_code': code, 'failures': body['failures'], 'read_only': False,
    'db_writes_performed': performed, 'publication_performed': performed,
    'canonical_writes_performed': False, 'application_service_changes_performed': False,
    'f2d_operator_code_sha256': identity, 'receipt': receipt,
}))
PY
  RESULT_EMITTED=true
}

refuse() {
  local code="$1" item="$2"
  printf 'v3 product publication: %s\n' "$item" >&2
  write_result "$code" "$item"
  exit "$code"
}

cleanup() {
  local code=$?
  trap - EXIT HUP INT TERM
  if [ -n "$WORKER_PID" ]; then
    # Stop the database session before releasing the host lock on cancellation.
    docker stop --time 10 "$WORKER" >/dev/null 2>&1 || true
    kill -TERM "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
  if [ "$COMMITTED" = false ]; then detect_commit || true; fi
  [ -z "$ENV_FILE" ] || rm -f -- "$ENV_FILE"
  if [ "$RESULT_EMITTED" = false ]; then
    write_result "$code" unexpected_action_failure || true
  fi
  # Closing the inherited descriptor here (and process exit) releases the lock.
  if [ -n "${DEPLOY_LOCK_FD:-}" ]; then exec {DEPLOY_LOCK_FD}>&-; fi
}

require_products() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(json_agg(json_build_object('product_code',product_code,'lifecycle_state',lifecycle_state,'validation_status',validation_receipt->>'status','published_at',published_at,'manifest',manifest,'manifest_sha256',encode(manifest_sha256,'hex')) ORDER BY product_code),'[]'::json)::text FROM v3_meta.derived_product WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND product_code IN ('system_search','system_archetype'); COMMIT;" > "$RUN_DIR/products.json" \
    || refuse 71 product_state_read
  local code=0
  "$PYTHON_BIN" - "$RUN_DIR/products.json" <<'PY' || code=$?
import json, sys
rows = json.load(open(sys.argv[1]))
if any(row['published_at'] is not None for row in rows):
    raise SystemExit(72)
if {row['product_code'] for row in rows} != {'system_search', 'system_archetype'} or len(rows) != 2:
    raise SystemExit(71)
if any(row['lifecycle_state'] != 'READY' or row['validation_status'] != 'VERIFIED' for row in rows):
    raise SystemExit(71)
PY
  if [ "$code" -eq 72 ]; then refuse 72 publication_already_happened; fi
  [ "$code" -eq 0 ] || refuse 71 products_not_ready_verified_unpublished
}

load_attestation() {
  "$PYTHON_BIN" - "$REPO_ROOT/deploy/v3-production/target-authority.json" \
    "$F2D_IDENTITY" > "$RUN_DIR/attestation.json" <<'PY'
import json, re, sys
value = json.load(open(sys.argv[1]))['accepted_release_schema_compatibility']
if not isinstance(value.get('ranking_version'), str) or not value['ranking_version'].strip():
    raise SystemExit('ranking_version absent')
if re.fullmatch(r'[0-9a-f]{64}', str(value.get('ranking_sha256', ''))) is None:
    raise SystemExit('ranking_sha256 absent or invalid')
if value.get('f2d_operator_code_sha256') != sys.argv[2]:
    raise SystemExit('f2d_operator_code_sha256 absent or mismatched')
if re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', str(value['images']['backend'])) is None:
    raise SystemExit('backend digest absent or invalid')
print(json.dumps(value, sort_keys=True))
PY
}

read_image() {
  local api image_id image_digest
  api="$(active_api_container)" || return 1
  image_id="$(docker inspect -f '{{.Image}}' "$api")" || return 1
  image_digest="$(docker image inspect -f '{{index .RepoDigests 0}}' "$image_id")" || return 1
  "$PYTHON_BIN" - "$api" "$image_id" "$image_digest" <<'PY'
import json, re, sys
api, image_id, digest = sys.argv[1:]
if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) or not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', digest):
    raise SystemExit('active image identity invalid')
print(json.dumps({'container': api, 'image_id': image_id, 'image_digest': digest}))
PY
}

check_image() {
  "$PYTHON_BIN" - "$RUN_DIR/attestation.json" "$1" <<'PY'
import json, sys
attestation = json.load(open(sys.argv[1]))
image = json.load(open(sys.argv[2]))
if image['image_digest'] != attestation['images']['backend']:
    raise SystemExit('active API digest differs from accepted release')
PY
}

probe_pairs() {
  "$PYTHON_BIN" - "$RUN_DIR/probe-pairs.json" <<'PY'
import json, sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = build_opener(ProxyHandler({}), NoRedirect())
origin = 'http://127.0.0.1:58080'
max_body = 64 * 1024
# _current_derived_generation() names both READY, unpublished dependencies.
expected_not_ready = (
    'Finder ranking products are not available for the published generation '
    '(system_archetype=READY-unpublished, system_search=READY-unpublished).'
)
pairs = [
    ('GET', '/api/archetypes/rankings?archetype=paradise&offset=9999&limit=1', None, 503),
    ('GET', '/api/archetypes/rankings?archetype=paradise&offset=9999&limit=2', None, 422),
    ('POST', '/api/local/search', {'galaxy_wide': True, 'sort_by': 'development', 'from': 9999, 'size': 1}, 503),
    ('POST', '/api/local/search', {'galaxy_wide': True, 'sort_by': 'development', 'from': 9999, 'size': 2}, 422),
]
statuses = []
for method, path, body, expected in pairs:
    payload = b''
    detail = None
    reason_verified = None
    request = Request(origin + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'}, method=method)
    try:
        with opener.open(request, timeout=15) as response:
            status = response.status
            payload = response.read(max_body + 1)
    except HTTPError as exc:
        with exc:
            status = exc.code
            payload = exc.read(max_body + 1)
    except (URLError, OSError):
        status = None
    if len(payload) > max_body:
        status = None
    else:
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                detail = parsed.get('detail')
        except (ValueError, UnicodeError):
            pass
    if expected == 503:
        reason_verified = detail == expected_not_ready
    statuses.append({'method': method, 'path': path, 'body': body,
                     'status': status, 'expected_status': expected,
                     'detail': detail, 'reason_verified': reason_verified})
with open(sys.argv[1], 'w') as output:
    json.dump(statuses, output, sort_keys=True)
if any(row['status'] != row['expected_status']
       or row['expected_status'] == 503 and row['reason_verified'] is not True
       for row in statuses):
    raise SystemExit('behavioural_probe_pairs_failed')
PY
}

require_manifest_identities() {
  # Compute through the actual builders inside the attested API image.
  timeout --signal=TERM 120 docker run --rm -i --network none --cpus 2 --memory 4g \
    --read-only --tmpfs /tmp --env PYTHONPATH=/work --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --mount "type=bind,src=${RUN_DIR}/products.json,dst=/input/products.json,readonly" \
    --entrypoint /app/.venv/bin/python "$IMAGE_DIGEST" - \
    > "$RUN_DIR/checkout-identities.json" <<'PY'
import hashlib, json
from pathlib import Path
from scripts import v3_system_search as search, v3_system_archetype as archetype
rows = {row['product_code']: row for row in json.loads(Path('/input/products.json').read_text())}
manifest = rows['system_search']['manifest']
generation = search.Generation(
    identifier=manifest['derived_generation_id'], key=manifest['generation_key'], state='PUBLISHED',
    canonical_generation_id=manifest['canonical_generation_id'],
    canonical_publication_sequence=manifest['canonical_publication_sequence'],
    canonical_schema=manifest['canonical_schema'], expected_systems=manifest['expected_rows'],
)
print(json.dumps({'search_code_sha256': search.product_manifest(generation)['code_sha256'],
                  'archetype_code_sha256': archetype.code_identity(),
                  'model_file_sha256': hashlib.sha256(Path('/work/shared_contracts/v3_system_archetype_model.py').read_bytes()).hexdigest()}))
PY
  local code=$?
  [ "$code" -eq 0 ] || return "$code"
  docker exec "$API" sha256sum /app/shared_contracts/v3_system_archetype_model.py \
    > "$RUN_DIR/api-model.sha256" || return 1
  "$PYTHON_BIN" - "$RUN_DIR" <<'PY'
import json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
rows = {row['product_code']: row for row in json.loads((root / 'products.json').read_text())}
expected = json.loads((root / 'checkout-identities.json').read_text())
model = (root / 'api-model.sha256').read_text().split()
if len(model) != 2 or re.fullmatch(r'[0-9a-f]{64}', model[0]) is None:
    raise SystemExit('API model digest malformed')
if rows['system_search']['manifest'].get('code_sha256') != expected['search_code_sha256']:
    raise SystemExit('Search manifest code identity mismatch')
a = rows['system_archetype']['manifest']
if a.get('code_sha256') != expected['archetype_code_sha256']:
    raise SystemExit('Archetype manifest code identity mismatch')
if a.get('model_file_sha256') != expected['model_file_sha256'] or a.get('model_file_sha256') != model[0]:
    raise SystemExit('Archetype model_file_sha256 mismatch')
(root / 'verified-identities.json').write_text(json.dumps({
    'checkout': expected, 'api_model_file_sha256': model[0], 'matches': True,
}, sort_keys=True) + '\n')
PY
}

require_maintenance() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(json_agg(json_build_object('product_code',relname,'last_vacuum',last_vacuum,'last_analyze',last_analyze) ORDER BY relname),'[]'::json)::text FROM pg_stat_user_tables WHERE schemaname='v3_derived' AND relname IN ('system_search','system_archetype'); COMMIT;" > "$RUN_DIR/live-maintenance.json" || return 1
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$RUN_DIR" "$SEARCH_FINAL_RECEIPT" \
    "$ARCHETYPE_FINAL_RECEIPT" "$TARGET_GENERATION_ID" "$F2D_IDENTITY" <<'PY'
from datetime import datetime
import json, sys
from pathlib import Path
from scripts.operator.lib.f2d_evidence import load_sealed
root, search, archetype, identifier, identity = sys.argv[1:]
root = Path(root)
products = {row['product_code']: row for row in json.loads((root / 'products.json').read_text())}
live = {row['product_code']: row for row in json.loads((root / 'live-maintenance.json').read_text())}
def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('maintenance timestamp lacks timezone')
    return result
checked = []
for path, product in ((search, 'system_search'), (archetype, 'system_archetype')):
    receipt = load_sealed(path)
    required = {'schema_version': 'ed-finder/v3-build-final-receipt/v1',
                'product_code': product, 'derived_generation_id': identifier,
                'manifest_sha256': products[product]['manifest_sha256'],
                'lifecycle_state': 'READY', 'validation_status': 'VERIFIED',
                'f2d_operator_code_sha256': identity}
    if any(receipt.get(key) != value for key, value in required.items()):
        raise SystemExit(product + '_build_final_receipt_identity_mismatch')
    final = timestamp(receipt['final_insert_at'])
    for field in ('last_vacuum', 'last_analyze'):
        if timestamp(receipt[field]) <= final:
            raise SystemExit(product + '_' + field + '_predates_final_insert')
        if timestamp(live[product][field]) < timestamp(receipt[field]):
            raise SystemExit(product + '_' + field + '_live_older_than_receipt')
    checked.append({'product_code': product, 'receipt': receipt, 'live': live[product]})
(root / 'maintenance.json').write_text(json.dumps(checked, sort_keys=True) + '\n')
print('\t'.join(item['receipt']['final_insert_at'] for item in checked))
PY
}

validate_ready() {
  "$PYTHON_BIN" - "$RUN_DIR/ready-to-commit.json" "$TARGET_GENERATION_KEY" \
    "$TARGET_GENERATION_ID" "$TARGET_PUBLICATION_SEQUENCE" <<'PY'
from datetime import datetime
import json, re, sys
from pathlib import Path
path = Path(sys.argv[1])
if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
    raise SystemExit('ready handshake file is unsafe')
value = json.loads(path.read_text())
if value.get('generation') != {'generation_key': sys.argv[2], 'derived_generation_id': sys.argv[3], 'publication_sequence': int(sys.argv[4]), 'lifecycle_state': 'PUBLISHED', 'is_current': True}:
    raise SystemExit('ready generation mismatch')
if value.get('products') != ['system_search', 'system_archetype']:
    raise SystemExit('ready products mismatch')
published = value.get('published_at') or {}
if set(published) != {'system_search', 'system_archetype'}:
    raise SystemExit('ready timestamps missing')
times = [datetime.fromisoformat(item.replace('Z', '+00:00')) for item in published.values()]
if times[0] != times[1] or any(item.tzinfo is None for item in times):
    raise SystemExit('ready timestamps mismatch')
if re.fullmatch(r'[0-9a-f]{64}', str(value.get('plan_probe_receipt_sha256', ''))) is None:
    raise SystemExit('ready probe seal missing')
PY
}

# Recover an acknowledged COMMIT even if writing the program receipt failed.
# Refusals without a host commit decision never claim this launch wrote data.
detect_commit() {
  [ -f "$RUN_DIR/ready-to-commit.json" ] && [ -f "$RUN_DIR/commit-decision.json" ] || return 1
  db_query "BEGIN READ ONLY; SELECT COALESCE(json_agg(json_build_object('product_code',p.product_code,'published_at',p.published_at,'audit_published_at',a.published_at,'actor',a.actor) ORDER BY p.product_code),'[]'::json)::text FROM v3_meta.derived_product p JOIN v3_meta.derived_product_publication_audit a USING (derived_generation_id,product_code) WHERE p.derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND p.product_code IN ('system_search','system_archetype'); COMMIT;" > "$RUN_DIR/commit-recovery.json" || return 1
  "$PYTHON_BIN" - "$RUN_DIR" "$ACTOR" <<'PY' || return 1
from datetime import datetime
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
if json.loads((root / 'commit-decision.json').read_text()) != {'decision': 'commit'}:
    raise SystemExit(1)
ready = json.loads((root / 'ready-to-commit.json').read_text())
rows = json.loads((root / 'commit-recovery.json').read_text())
if len(rows) != 2 or {row['product_code'] for row in rows} != {'system_search', 'system_archetype'}:
    raise SystemExit(1)
def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))
for row in rows:
    if row['actor'] != sys.argv[2] or stamp(row['published_at']) != stamp(row['audit_published_at']) or stamp(row['published_at']) != stamp(ready['published_at'][row['product_code']]):
        raise SystemExit(1)
PY
  COMMITTED=true
}

write_decision() {
  "$PYTHON_BIN" - "$RUN_DIR" "$1" "${2:-}" <<'PY'
import json, os, sys
from pathlib import Path
root, decision, reason = sys.argv[1:]
path = Path(root) / 'commit-decision.json'
temporary = path.with_name('.commit-decision.tmp')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    json.dump({'decision': 'commit'} if decision == 'commit' else {'decision': 'abort', 'reason': reason}, output)
    output.flush()
    os.fsync(output.fileno())
os.replace(temporary, path)
PY
}

verify_postcommit() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(json_agg(json_build_object('product_code',p.product_code,'published_at',p.published_at,'audit_published_at',a.published_at,'actor',a.actor,'product_version',a.product_version,'manifest_sha256',encode(a.manifest_sha256,'hex'),'matches',p.published_at=a.published_at AND p.product_version=a.product_version AND p.manifest_sha256=a.manifest_sha256) ORDER BY p.product_code),'[]'::json)::text FROM v3_meta.derived_product p LEFT JOIN v3_meta.derived_product_publication_audit a USING (derived_generation_id,product_code) WHERE p.derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND p.product_code IN ('system_search','system_archetype'); COMMIT;" > "$RUN_DIR/postcommit.json" || return 1
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$RUN_DIR" "$ACTOR" <<'PY'
import json, sys
from pathlib import Path
from scripts.operator.lib.f2d_evidence import load_sealed
root = Path(sys.argv[1])
rows = json.loads((root / 'postcommit.json').read_text())
try:
    program = load_sealed(root / 'receipt.json')
except ValueError:
    program = load_sealed(root / 'program-output.json')
probe = program.get('plan_probe_receipt') or {}
if program.get('status') != 'published' or program.get('publication_performed') is not True or probe.get('status') != 'passed':
    raise SystemExit('program publication receipt invalid')
if {row['product_code'] for row in rows} != {'system_search', 'system_archetype'} or len(rows) != 2:
    raise SystemExit('postcommit product rows missing')
if any(row['published_at'] is None or row['matches'] is not True or row['actor'] != sys.argv[2] for row in rows):
    raise SystemExit('postcommit audit mismatch')
if len({row['published_at'] for row in rows}) != 1:
    raise SystemExit('postcommit timestamp mismatch')
PY
}

verify_live_finder() {
  "$PYTHON_BIN" - "$RUN_DIR" "$TARGET_GENERATION_KEY" "$TARGET_GENERATION_ID" \
    "$TARGET_PUBLICATION_SEQUENCE" <<'PY'
from http.client import HTTPException
import json, sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
root = Path(sys.argv[1])
attestation = json.loads((root / 'attestation.json').read_text())
products = {row['product_code']: row for row in json.loads((root / 'products.json').read_text())}
published = {row['product_code']: row for row in json.loads((root / 'postcommit.json').read_text())}
archetype = published['system_archetype']
expected = {
    'derived_generation_id': sys.argv[3], 'publication_sequence': int(sys.argv[4]),
    'ranking_version': attestation['ranking_version'], 'ranking_sha256': attestation['ranking_sha256'],
    'archetype_version': archetype['product_version'],
    'archetype_manifest_sha256': archetype['manifest_sha256'],
    'archetype_model_sha256': products['system_archetype']['manifest']['archetype_model_sha256'],
}
# RankingIdentity has UUID and sequence, not generation_key. The pinned key's
# UUID/sequence were checked before publication and are compared here.
opener = build_opener(ProxyHandler({}), NoRedirect())
origin = 'http://127.0.0.1:58080'
max_body = 64 * 1024
pairs = [
    ('rankings', 'GET', '/api/archetypes/rankings?archetype=paradise&offset=0&limit=1', None),
    ('search', 'POST', '/api/local/search', {'galaxy_wide': True, 'sort_by': 'development', 'from': 0, 'size': 1}),
]
responses, failures = [], []
for name, method, path, body in pairs:
    status, payload, parsed = None, b'', None
    request = Request(origin + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'}, method=method)
    try:
        with opener.open(request, timeout=15) as response:
            status = response.status
            payload = response.read(max_body + 1)
    except HTTPError as exc:
        with exc:
            status = exc.code
            try:
                payload = exc.read(max_body + 1)
            except (OSError, HTTPException):
                pass
    except (URLError, OSError, HTTPException):
        pass
    bounded = len(payload) <= max_body
    if bounded:
        try:
            parsed = json.loads(payload)
        except (ValueError, UnicodeError):
            pass
    envelope = parsed if isinstance(parsed, dict) else {}
    ranking = envelope.get('ranking')
    identity = {field: ranking.get(field) if isinstance(ranking, dict) else None for field in expected}
    results = envelope.get('results')
    checks = {'http_200': status == 200, 'bounded_body': bounded,
              'json_envelope': isinstance(parsed, dict),
              'results_served': isinstance(results, list) and len(results) == 1}
    checks.update({field: type(identity[field]) is type(value) and identity[field] == value
                   for field, value in expected.items()})
    failures.extend(name + ':' + field for field, passed in checks.items() if not passed)
    responses.append({'method': method, 'path': path, 'body': body, 'status': status,
                      'expected_status': 200, 'identity': identity, 'checks': checks})
evidence = {'generation': {'generation_key': sys.argv[2], 'derived_generation_id': sys.argv[3],
                           'publication_sequence': int(sys.argv[4])},
            'expected_identity': expected, 'responses': responses, 'failures': failures}
(root / 'live-finder.json').write_text(json.dumps(evidence, sort_keys=True) + '\n')
if failures:
    raise SystemExit(80)
PY
}

run_operation() {
  require_target
  require_stage
  require_generation
  umask 077
  RUN_DIR="$STATE_ROOT/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/runs" "$RUN_DIR"
  trap cleanup EXIT
  trap 'exit 143' HUP INT TERM
  acquire_deployment_lock
  require_products
  load_attestation || refuse 73 accepted_release_attestation_missing_or_invalid
  read_image > "$RUN_DIR/image-first.json" || refuse 73 active_api_image_identity
  check_image "$RUN_DIR/image-first.json" || refuse 73 active_api_digest_not_attested
  local image_values
  image_values="$("$PYTHON_BIN" - "$RUN_DIR/image-first.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1]))
print(value['container'] + '\t' + value['image_digest'])
PY
)" || refuse 73 active_api_image_identity
  IFS=$'\t' read -r API IMAGE_DIGEST <<< "$image_values"
  [ -n "$API" ] && [ -n "$IMAGE_DIGEST" ] || refuse 73 active_api_image_identity
  probe_pairs || refuse 74 behavioural_probe_pairs
  require_manifest_identities || refuse 75 product_manifest_code_or_model_identity
  local receipt_values search_final archetype_final dense_cell dense_x dense_y dense_z statements_sha
  receipt_values="$(require_maintenance)" || refuse 76 build_final_receipts_or_live_maintenance
  IFS=$'\t' read -r search_final archetype_final <<< "$receipt_values"
  dense_cell="$(dense_anchor)" || refuse 21 dense_anchor_unavailable
  local dense_values
  dense_values="$(DENSE_CELL="$dense_cell" "$PYTHON_BIN" - <<'PY'
import json, os
value = json.loads(os.environ['DENSE_CELL'])['coordinates']
print(f"{value['x']}\t{value['y']}\t{value['z']}")
PY
)" || refuse 21 dense_anchor_coordinates
  IFS=$'\t' read -r dense_x dense_y dense_z <<< "$dense_values"
  [ -n "$dense_x" ] && [ -n "$dense_y" ] && [ -n "$dense_z" ] || refuse 21 dense_anchor_coordinates
  docker exec -i "$API" /app/.venv/bin/python - \
    --dense-anchor "$dense_x" "$dense_y" "$dense_z" \
    < "$REPO_ROOT/scripts/v3_plan_probe_statements.py" > "$RUN_DIR/statements.json" \
    || refuse 21 plan_probe_statement_generation
  statements_sha="$(PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$RUN_DIR/statements.json" <<'PY'
import json, sys
from scripts.operator.lib.f2d_evidence import canonical_sha256
value = json.load(open(sys.argv[1], encoding='utf-8'))
if len(value.get('statements', [])) != 80:
    raise SystemExit('statement count mismatch')
print(canonical_sha256(value))
PY
)" || refuse 21 plan_probe_statement_identity
  printf '"%s"\n' "$statements_sha" > "$RUN_DIR/statements-identity.json"
  local dsn
  dsn="$(api_database_url "$API")" || refuse 79 database_target_identity_mismatch
  ENV_FILE="$RUN_DIR/publish.env"
  printf 'V3_PUBLISH_DERIVED_PRODUCTS_DATABASE_URL=%s\n' "$dsn" > "$ENV_FILE"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$ENV_FILE"
  printf 'V3_PUBLISH_ACTOR=%s\nV3_PLAN_PROBE_STATEMENTS_SHA256=%s\n' "$ACTOR" "$statements_sha" >> "$ENV_FILE"
  printf 'V3_PLAN_PROBE_IMAGE_DIGEST=%s\n' "$IMAGE_DIGEST" >> "$ENV_FILE"
  printf 'V3_PLAN_PROBE_SEARCH_FINAL_INSERT_AT=%s\nV3_PLAN_PROBE_ARCHETYPE_FINAL_INSERT_AT=%s\n' "$search_final" "$archetype_final" >> "$ENV_FILE"
  printf 'V3_PLAN_PROBE_DENSE_CELL=%s\nPYTHONDONTWRITEBYTECODE=1\n' "$dense_cell" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  unset dsn
  WORKER="edfinder-v3-publish-${SOURCE_SHA:0:12}-$$"
  timeout --signal=TERM --kill-after=30s 1800 docker run --rm --name "$WORKER" --label "$OPERATION_LABEL" \
    --network "$WORKER_NETWORK" --cpus 2 --memory 4g --memory-swap 4g --pids-limit 128 \
    --read-only --tmpfs /tmp --env-file "$ENV_FILE" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --mount "type=bind,src=${RUN_DIR},dst=/publish" \
    --entrypoint /bin/sh "$IMAGE_DIGEST" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-probe-wheelhouse --target /tmp/v3-publish-deps "psycopg[binary]==3.3.4" 1>&2
      export PYTHONPATH="/tmp/v3-publish-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_publish_derived_products.py \
        --actor "$V3_PUBLISH_ACTOR" --publish-dir /publish \
        --statements /publish/statements.json --statements-sha256 "$V3_PLAN_PROBE_STATEMENTS_SHA256" \
        --image-digest "$V3_PLAN_PROBE_IMAGE_DIGEST" \
        --generation-key ratings_v4_prod_p4_parallel_v1 \
        --generation-id cfc25d36-3bc7-4011-a465-d6460eaaf826 --publication-sequence 1 \
        --search-final-insert-at "$V3_PLAN_PROBE_SEARCH_FINAL_INSERT_AT" \
        --archetype-final-insert-at "$V3_PLAN_PROBE_ARCHETYPE_FINAL_INSERT_AT" \
        --dense-anchor-cell "$V3_PLAN_PROBE_DENSE_CELL"
    ' > "$RUN_DIR/program-output.json" &
  WORKER_PID=$!
  local host_abort=0 code=0 deadline=$((SECONDS + 1800))
  while [ ! -f "$RUN_DIR/ready-to-commit.json" ]; do
    kill -0 "$WORKER_PID" 2>/dev/null || break
    if [ "$SECONDS" -ge "$deadline" ]; then host_abort=78; break; fi
    sleep 1
  done
  if [ -f "$RUN_DIR/ready-to-commit.json" ]; then
    if validate_ready && read_image > "$RUN_DIR/image-last.json" && check_image "$RUN_DIR/image-last.json"; then
      write_decision commit || host_abort=77
    else
      host_abort=77
      write_decision abort active_api_digest_changed || true
    fi
  elif [ "$host_abort" -eq 78 ]; then
    write_decision abort host_ready_handshake_timeout || true
    docker stop --time 10 "$WORKER" >/dev/null 2>&1 || true
  fi
  wait "$WORKER_PID" || code=$?
  if [ "$code" -ne 0 ]; then
    # A killed Docker client is not proof that its database session stopped.
    docker stop --time 10 "$WORKER" >/dev/null 2>&1 || true
  fi
  WORKER_PID=""
  rm -f -- "$ENV_FILE"
  ENV_FILE=""
  # Exit zero is proof of COMMIT, even if postcommit receipt verification fails.
  if [ "$code" -eq 0 ]; then COMMITTED=true; else detect_commit || true; fi
  [ "$host_abort" -eq 0 ] || refuse "$host_abort" host_commit_handshake_abort
  [ "$code" -eq 0 ] || refuse "$code" publication_program_refused_or_failed
  # COMMIT is irreversible here: failures report committed writes and never
  # request rollback. The protected workflow propagates this nonzero exit.
  verify_postcommit || refuse 80 postcommit_audit_verification
  verify_live_finder || refuse 80 postcommit_live_finder_verification
  write_result 0 ""
}

case "$ACTION" in
  run) run_operation ;;
  *) fail "expected run <REPO_ROOT> <SOURCE_SHA> <ACTOR>" ;;
esac
