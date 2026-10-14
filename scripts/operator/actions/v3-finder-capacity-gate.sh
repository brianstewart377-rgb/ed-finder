#!/usr/bin/env bash
# Runs the combined Finder capacity gate against the pinned published Ratings
# generation. The database and checkout mounts are read-only; the only writes
# are sealed operation evidence under the operator's local state directory.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

# This identity check deliberately precedes every target, stage, generation,
# database, volume, and API-container check.
IDENTITY_HELPER="$REPO_ROOT/scripts/operator/lib/f2d_operator_identity.sh"
[ -f "$IDENTITY_HELPER" ] && [ ! -L "$IDENTITY_HELPER" ] || {
  printf '%s\n' 'v3 finder capacity gate: identity helper is missing or symlinked' >&2
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
OPERATION_LABEL="ed-finder.operation=v3-finder-capacity-gate"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-finder-capacity-gate"
COMPLETE_STATE_ROOT="${HOME}/.local/state/ed-finder/v3-archetype-calibration-complete"
SEARCH_STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-search"
ARCHETYPE_STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-archetype"
PYTHON_BIN=""

fail() {
  printf 'v3 finder capacity gate: %s\n' "$*" >&2
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
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] \
    || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  # The gate runs standalone from its own stage, or as the fail-closed
  # precondition inside the Search and Archetype build actions from THEIR
  # staged checkouts (design 8.4/8.5). Each stage namespace carries its own
  # source-SHA marker; every other path is refused.
  local marker
  case "$REPO_ROOT" in
    /var/tmp/edfinder-v3-capacity-gate-"$SOURCE_SHA") marker=".v3-capacity-gate-source-sha" ;;
    /var/tmp/edfinder-v3-search-"$SOURCE_SHA") marker=".v3-search-source-sha" ;;
    /var/tmp/edfinder-v3-archetype-build-"$SOURCE_SHA") marker=".v3-archetype-build-source-sha" ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ ! -L "$REPO_ROOT/$marker" ] || fail "trusted main bundle SHA marker is a symlink"
  [ "$(cat "$REPO_ROOT/$marker" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_finder_capacity_gate.py" ] \
    || fail "Finder capacity gate program is missing"
  [ -d "$REPO_ROOT/.v3-probe-wheelhouse" ] \
    || fail "offline capacity gate dependency wheelhouse is missing"
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

write_volume_reading() {
  local output="$1" mount_rows mount_source="" mount_destination=""
  local fallback_source="" fallback_destination=""
  local df_output filesystem filesystem_type size_bytes used_bytes avail_bytes read_at
  mount_rows="$(docker inspect -f $'{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}' "$POSTGRES_CONTAINER")" \
    || fail "postgres data mount inspection failed"
  # Same resolution as the step 0 action (v3-derived-lifecycle-status.sh): the
  # exact /var/lib/postgresql/data destination wins; otherwise the first mount
  # under /var/lib/postgresql (the PostgreSQL 18 image mounts the volume there,
  # and the step 0 receipt records mount_destination=/var/lib/postgresql).
  while IFS=$'\t' read -r source destination; do
    [ -n "$source" ] && [ -n "$destination" ] || continue
    if [ "$destination" = "/var/lib/postgresql/data" ]; then
      [ -z "$mount_source" ] || fail "postgres data mount is ambiguous"
      mount_source="$source"
      mount_destination="$destination"
    elif [[ "$destination" == /var/lib/postgresql* ]] && [ -z "$fallback_source" ]; then
      fallback_source="$source"
      fallback_destination="$destination"
    fi
  done <<< "$mount_rows"
  if [ -z "$mount_source" ]; then
    mount_source="$fallback_source"
    mount_destination="$fallback_destination"
  fi
  [ -n "$mount_source" ] || fail "postgres data mount is unresolved"

  df_output="$(df -B1 --output=source,fstype,size,used,avail "$mount_source")" \
    || fail "postgres data volume reading failed"
  IFS=' ' read -r filesystem filesystem_type size_bytes used_bytes avail_bytes \
    <<< "$(printf '%s\n' "$df_output" | awk 'NF {line=$0} END {print line}')"
  [[ "$size_bytes" =~ ^[0-9]+$ && "$used_bytes" =~ ^[0-9]+$ && "$avail_bytes" =~ ^[0-9]+$ ]] \
    || fail "postgres data volume reading is invalid"
  read_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$PYTHON_BIN" - "$output" "$filesystem" "$filesystem_type" "$size_bytes" \
    "$used_bytes" "$avail_bytes" "$read_at" "$mount_source" "$mount_destination" <<'PY'
import json
from pathlib import Path
import sys

(path, filesystem, filesystem_type, size_bytes, used_bytes, avail_bytes,
 read_at, mount_source, mount_destination) = sys.argv[1:]
payload = {
    "filesystem": filesystem,
    "filesystem_type": filesystem_type,
    "size_bytes": int(size_bytes),
    "used_bytes": int(used_bytes),
    "avail_bytes": int(avail_bytes),
    "read_at": read_at,
    "mount_source": mount_source,
    "mount_destination": mount_destination,
}
Path(path).write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
  chmod 600 "$output"
}

emit_result() {
  local exit_code="$1" run_dir="$2"
  EXIT_CODE_VALUE="$exit_code" RUN_DIR_VALUE="$run_dir" \
  F2D_IDENTITY_VALUE="$F2D_IDENTITY" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

exit_code = int(os.environ["EXIT_CODE_VALUE"])
run_dir = Path(os.environ["RUN_DIR_VALUE"])

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

def read_sealed(path: Path):
    value = read_json(path)
    if not isinstance(value, dict):
        return None
    seal = value.get("content_sha256")
    body = dict(value)
    body.pop("content_sha256", None)
    try:
        canonical = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError):
        return None
    if not isinstance(seal, str) or hashlib.sha256(canonical).hexdigest() != seal:
        return None
    return value

receipt = read_sealed(run_dir / "receipt.json")
volume = read_json(run_dir / "volume-reading.json")
if exit_code == 0:
    status = "passed"
elif exit_code in {2, 3, 10, 11, 12, 13, 14, 15, 16}:
    status = "refused"
else:
    status = "failed"

failures = []
if isinstance(receipt, dict):
    candidate = receipt.get("failures")
    if isinstance(candidate, list):
        failures = candidate
    elif receipt.get("failure") is not None:
        failures = [receipt["failure"]]
if exit_code != 0 and not failures:
    failures = ["capacity_gate_exit_" + str(exit_code)]

payload = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-finder-capacity-gate",
    "status": status,
    "exit_code": exit_code,
    "failures": failures,
    "read_only": True,
    "db_writes_performed": False,
    "publication_performed": False,
    "canonical_writes_performed": False,
    "application_service_changes_performed": False,
    "f2d_operator_code_sha256": os.environ["F2D_IDENTITY_VALUE"],
    "volume_reading": volume,
    "receipt": receipt,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY
}

# The gate's database reads can outlast the program's 15-minute freshness
# window, so keep replacing the reading (atomically, by rename in the same
# directory) while the gate runs; the program re-reads it just before the
# capacity comparison. A failed refresh leaves the older reading in place,
# which the freshness check then refuses.
refresh_volume_reading() {
  local output="$1" next="$1.next"
  while sleep 60; do
    ( write_volume_reading "$next" ) && mv -f -- "$next" "$output" || rm -f -- "$next"
  done
}

run_operation() {
  require_target
  require_stage
  require_generation

  local timestamp run_dir volume_file api api_image dsn env_file output_file worker exit_code
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="$STATE_ROOT/runs/${timestamp}-$$"
  install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/runs" "$run_dir"
  volume_file="$run_dir/volume-reading.json"
  write_volume_reading "$volume_file"

  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"
  env_file="$run_dir/capacity-gate.env"
  output_file="$run_dir/program-output.json"
  worker="edfinder-v3-capacity-gate-${SOURCE_SHA:0:12}-$$"
  umask 077
  printf 'V3_FINDER_CAPACITY_GATE_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$env_file"
  chmod 600 "$env_file"
  local refresher=""
  trap 'rm -f -- "$env_file"; [ -z "$refresher" ] || kill "$refresher" 2>/dev/null || true' EXIT

  local -a state_mounts=()
  if [ -d "$COMPLETE_STATE_ROOT" ]; then
    state_mounts+=(--mount "type=bind,src=${COMPLETE_STATE_ROOT},dst=/state/complete,readonly")
  fi
  if [ -d "$SEARCH_STATE_ROOT" ]; then
    state_mounts+=(--mount "type=bind,src=${SEARCH_STATE_ROOT},dst=/state/search,readonly")
  fi
  if [ -d "$ARCHETYPE_STATE_ROOT" ]; then
    state_mounts+=(--mount "type=bind,src=${ARCHETYPE_STATE_ROOT},dst=/state/archetype,readonly")
  fi

  refresh_volume_reading "$volume_file" &
  refresher=$!

  set +e
  timeout --signal=TERM 2700 docker run --rm \
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
    "${state_mounts[@]}" \
    --entrypoint /bin/sh \
    "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-probe-wheelhouse --target /tmp/v3-capacity-gate-deps \
        "psycopg[binary]==3.3.4" 1>&2
      export PYTHONPATH="/tmp/v3-capacity-gate-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_finder_capacity_gate.py \
        --generation-key ratings_v4_prod_p4_parallel_v1 \
        --generation-id cfc25d36-3bc7-4011-a465-d6460eaaf826 \
        --publication-sequence 1 \
        --volume-reading /gate/volume-reading.json \
        --complete-state /state/complete \
        --search-state /state/search \
        --archetype-state /state/archetype \
        --output /gate/receipt.json
    ' > "$output_file"
  exit_code=$?
  kill "$refresher" 2>/dev/null || true
  wait "$refresher" 2>/dev/null || true
  refresher=""
  rm -f -- "$volume_file.next"
  set -e
  rm -f -- "$env_file"
  trap - EXIT

  emit_result "$exit_code" "$run_dir"
  return "$exit_code"
}

case "$ACTION" in
  run) run_operation ;;
  *) fail "expected run <REPO_ROOT> <SOURCE_SHA>" ;;
esac
