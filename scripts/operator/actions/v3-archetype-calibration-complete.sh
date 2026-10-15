#!/usr/bin/env bash
# Detached, read-only complete calibration pass over the pinned published Ratings
# generation. The worker can resume only a checkpoint bound to that generation
# and to the same attested F2d operator-code identity. State under STATE_ROOT:
# checkpoint.json (small, cumulative), per-chunk.jsonl (append-only per-chunk
# tier counts bound to the receipt by digest), receipt.json / failure-receipt.json
# (sealed). status only reads these files and the worker container state.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

if [ -z "$REPO_ROOT" ] || [ ! -d "$REPO_ROOT" ]; then
  printf '%s\n' 'v3 archetype calibration complete: trusted main bundle path is required' >&2
  exit 64
fi
IDENTITY_HELPER="$REPO_ROOT/scripts/operator/lib/f2d_operator_identity.sh"
[ -f "$IDENTITY_HELPER" ] && [ ! -L "$IDENTITY_HELPER" ] || {
  printf '%s\n' 'v3 archetype calibration complete: identity helper is missing or symlinked' >&2
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
WORKER="edfinder-v3-archetype-calibration-complete"
OPERATION_LABEL="ed-finder.operation=v3-archetype-calibration-complete"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-archetype-calibration-complete"
TARGET_CPUS="8"
TARGET_MEMORY="16g"
PYTHON_BIN=""

fail() {
  printf 'v3 archetype calibration complete: %s\n' "$*" >&2
  exit 64
}

# Read-only preflight precedes every operation lock, host write and container change.
require_purge_clear() {
  local helper="$REPO_ROOT/scripts/operator/lib/v3-purge-state.sh"
  if [ ! -f "$helper" ] || [ -L "$helper" ]; then
    printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"%s","status":"stopped","read_only":false,"db_writes_performed":false,"failures":["purge_state_helper_missing"]}\n' "$1"
    exit 78
  fi
  # shellcheck source=../lib/v3-purge-state.sh
  source "$helper"
  v3_purge_require_clear "$1"
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
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in
    /var/tmp/edfinder-v3-archetype-complete-"$SOURCE_SHA") ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ "$(cat "$REPO_ROOT/.v3-archetype-complete-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_archetype_calibration_complete.py" ] \
    || fail "complete calibration program is missing"
  [ -d "$REPO_ROOT/.v3-probe-wheelhouse" ] \
    || fail "offline calibration dependency wheelhouse is missing"
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
  local api="$1" value count
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')"
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || fail "active API does not expose exactly one DATABASE_URL"
  case "$value" in postgresql://*|postgres://*) ;; *) fail "active API DATABASE_URL is not a PostgreSQL DSN" ;; esac
  printf '%s' "$value"
}

require_checkpoint_identity() {
  local checkpoint="$STATE_ROOT/checkpoint.json"
  [ -e "$checkpoint" ] || return 0
  [ -f "$checkpoint" ] && [ ! -L "$checkpoint" ] || fail "checkpoint is not a regular file"
  "$PYTHON_BIN" - "$checkpoint" "$TARGET_GENERATION_KEY" "$TARGET_GENERATION_ID" \
    "$TARGET_PUBLICATION_SEQUENCE" "$F2D_IDENTITY" <<'PY' \
    || fail "checkpoint belongs to another generation or operator identity"
import json
import sys

path, key, identifier, sequence, identity = sys.argv[1:]
try:
    checkpoint = json.load(open(path, encoding='utf-8'))
except (OSError, ValueError):
    raise SystemExit(1)
expected = {
    'generation_key': key,
    'derived_generation_id': identifier,
    'publication_sequence': int(sequence),
    'f2d_operator_code_sha256': identity,
}
raise SystemExit(0 if all(checkpoint.get(k) == v for k, v in expected.items()) else 1)
PY
}

emit_status() {
  local operation="$1" worker_status="missing" worker_exit=""
  if docker inspect "$WORKER" >/dev/null 2>&1; then
    worker_status="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    worker_exit="$(docker inspect -f '{{.State.ExitCode}}' "$WORKER")"
  fi
  WORKER_STATUS="$worker_status" WORKER_EXIT="$worker_exit" \
  OPERATION="$operation" STATE_ROOT_VALUE="$STATE_ROOT" \
  F2D_IDENTITY_VALUE="$F2D_IDENTITY" "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

state_root = Path(os.environ['STATE_ROOT_VALUE'])
def read(name):
    path = state_root / name
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'invalid': True}
    return value

def sealed_read(name):
    value = read(name)
    if value is None:
        return value
    if not isinstance(value, dict):
        return {'invalid': True}
    if value.get('invalid') is True:
        return value
    seal = value.get('content_sha256')
    body = dict(value)
    body.pop('content_sha256', None)
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True, allow_nan=False).encode()
    import hashlib
    if not isinstance(seal, str) or hashlib.sha256(canonical).hexdigest() != seal:
        return {'invalid': True, 'failure': 'content_sha256_mismatch'}
    return value

def per_chunk_log():
    path = state_root / 'per-chunk.jsonl'
    if path.is_symlink() or not path.is_file():
        return None
    import hashlib
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
                size += len(block)
    except OSError:
        return {'invalid': True}
    return {'bytes': size, 'sha256': digest.hexdigest()}

receipt = sealed_read('receipt.json')
failure = sealed_read('failure-receipt.json')
checkpoint = read('checkpoint.json')
worker = os.environ['WORKER_STATUS']
progress = None
if isinstance(checkpoint, dict) and checkpoint.get('invalid') is not True:
    progress = {
        'chunks_done': checkpoint.get('next_chunk_index'),
        'chunk_count': checkpoint.get('chunk_count'),
        'systems_scored': checkpoint.get('system_count'),
        'started_at': checkpoint.get('started_at'),
        'updated_at': checkpoint.get('updated_at'),
    }
if isinstance(receipt, dict) and receipt.get('status') == 'completed':
    status = 'completed'
elif isinstance(failure, dict) or (
    isinstance(receipt, dict) and receipt.get('invalid') is True
):
    status = 'failed'
elif worker == 'running':
    status = 'running'
else:
    status = 'stopped'
payload = {
    'schema_version': 'ed-finder/operator-operation-result/v1',
    'operation': os.environ['OPERATION'],
    'status': status,
    'failures': (
        failure.get('failures', ['invalid_failure_receipt'])
        if isinstance(failure, dict)
        else ['invalid_complete_receipt']
        if isinstance(receipt, dict) and receipt.get('invalid') is True
        else []
    ),
    'read_only': True,
    'db_writes_performed': False,
    'publication_performed': False,
    'canonical_writes_performed': False,
    'application_service_changes_performed': False,
    'f2d_operator_code_sha256': os.environ['F2D_IDENTITY_VALUE'],
    'worker': {'name': 'edfinder-v3-archetype-calibration-complete', 'status': worker,
               'exit_code': int(os.environ['WORKER_EXIT']) if os.environ['WORKER_EXIT'] else None},
    'progress': progress,
    'checkpoint': checkpoint,
    'per_chunk_log': per_chunk_log(),
    'receipt': receipt,
    'failure_receipt': failure,
}
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY
}

start_operation() {
  require_target
  require_purge_clear "v3-archetype-calibration-complete-start"
  require_stage
  require_checkpoint_identity
  require_generation
  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/start.lock"
  flock -n 9 || fail "another complete calibration start is in progress"

  local worker_state api api_image dsn env_file
  if docker inspect "$WORKER" >/dev/null 2>&1; then
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$worker_state" = "running" ]; then
      emit_status "v3-archetype-calibration-complete-start"
      return 0
    fi
    docker rm "$WORKER" >/dev/null
  fi

  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"

  # A restart after a transient failure resumes the checkpoint; the earlier
  # failure receipt describes the previous run, not this one. Keep it as
  # history under a unique name so status reports the live worker rather
  # than a stale failure for the whole resumed run.
  if [ -e "$STATE_ROOT/failure-receipt.json" ] || [ -L "$STATE_ROOT/failure-receipt.json" ]; then
    mv -- "$STATE_ROOT/failure-receipt.json" \
      "$STATE_ROOT/failure-receipt.$(date -u +%Y%m%dT%H%M%SZ).$$.json"
  fi

  local launch_id
  launch_id="$("$PYTHON_BIN" -c 'import uuid; print(uuid.uuid4().hex)')"
  [[ "$launch_id" =~ ^[0-9a-f]{32}$ ]] || fail "could not generate a launch identifier"
  env_file="$STATE_ROOT/complete.env"
  umask 077
  printf 'V3_ARCHETYPE_COMPLETE_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$env_file"
  printf 'V3_ARCHETYPE_COMPLETE_LAUNCH_ID=%s\n' "$launch_id" >> "$env_file"
  chmod 600 "$env_file"
  # The DSN file must not outlive a failed launch (set -e exits before the
  # explicit removal below when docker run fails).
  trap 'rm -f -- "$env_file"' EXIT

  docker run -d \
    --name "$WORKER" \
    --label "$OPERATION_LABEL" \
    --label "ed-finder.generation-key=${TARGET_GENERATION_KEY}" \
    --label "ed-finder.generation-id=${TARGET_GENERATION_ID}" \
    --label "ed-finder.source-sha=${SOURCE_SHA}" \
    --label "ed-finder.f2d-operator-code-sha256=${F2D_IDENTITY}" \
    --network "$WORKER_NETWORK" \
    --cpus "$TARGET_CPUS" \
    --memory "$TARGET_MEMORY" \
    --memory-swap "$TARGET_MEMORY" \
    --pids-limit 256 \
    --restart no \
    --read-only \
    --tmpfs /tmp:rw,nosuid,size=2g \
    --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --mount "type=bind,src=${STATE_ROOT},dst=/state" \
    --entrypoint /bin/sh \
    "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-probe-wheelhouse --target /tmp/v3-complete-deps \
        --require-hashes -r /work/deploy/v3-production/f2d-wheels.txt 1>&2
      export PYTHONPATH="/tmp/v3-complete-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_archetype_calibration_complete.py \
        --generation-key ratings_v4_prod_p4_parallel_v1 \
        --generation-id cfc25d36-3bc7-4011-a465-d6460eaaf826 \
        --publication-sequence 1 --state-dir /state \
        --image-model-file /app/shared_contracts/v3_system_archetype_model.py
    ' >/dev/null
  rm -f -- "$env_file"
  trap - EXIT

  sleep 3
  worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  if [ "$worker_state" != "running" ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    fail "complete calibration worker did not remain running"
  fi

  # Proof of life: after its identity, image-model, generation and
  # checkpoint-state checks pass, the worker writes this launch's identifier
  # into the checkpoint. A checkpoint left by an earlier run does not carry
  # it, so a resume is proven by this worker, not by the file existing. Wait
  # for it so a worker that refuses inside the container fails this start,
  # not a later status read.
  local proof=false
  for _ in $(seq 1 45); do
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$worker_state" = "running" ] && [ -f "$STATE_ROOT/checkpoint.json" ] \
      && [ ! -L "$STATE_ROOT/checkpoint.json" ] \
      && "$PYTHON_BIN" - "$STATE_ROOT/checkpoint.json" "$launch_id" <<'PY'
import json
import sys

try:
    checkpoint = json.load(open(sys.argv[1], encoding='utf-8'))
except (OSError, ValueError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(checkpoint, dict) and checkpoint.get('launch_id') == sys.argv[2] else 1)
PY
    then
      proof=true
      break
    fi
    [ "$worker_state" = "running" ] || break
    sleep 2
  done
  if [ "$proof" != true ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    # A failed start must not leave an unproven worker running.
    if [ "$(docker inspect -f '{{.State.Status}}' "$WORKER" 2>/dev/null || true)" = "running" ]; then
      docker stop --time 60 "$WORKER" >/dev/null 2>&1 || true
      [ "$(docker inspect -f '{{.State.Status}}' "$WORKER" 2>/dev/null || echo unknown)" != "running" ] \
        || fail "unproven complete calibration worker could not be stopped"
    fi
    emit_status "v3-archetype-calibration-complete-start"
    fail "complete calibration worker did not prove this launch while running; the worker was stopped"
  fi
  emit_status "v3-archetype-calibration-complete-start"
}

status_operation() {
  require_target
  require_stage
  require_checkpoint_identity
  emit_status "v3-archetype-calibration-complete-status"
}

case "$ACTION" in
  start) start_operation ;;
  status) status_operation ;;
  *) fail "expected start or status" ;;
esac
