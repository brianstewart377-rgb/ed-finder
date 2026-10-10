#!/usr/bin/env bash
# Runs the bounded archetype coefficient-calibration probe over at most 200,000
# systems for 25 minutes. It is read-only: the database connection is READ ONLY,
# every operator query is SELECT-only, and no lifecycle calls are made. Record the
# coefficient decision informed by its receipt before the system_archetype build.
# Config.Env is inspected only to pass the active API's database URL through a
# mode-0600 temporary env-file; that file is removed as soon as the container exits.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
COMPOSE_PROJECT="edfinder-v3-production"
WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"
OPERATION_LABEL="ed-finder.operation=v3-archetype-calibration-probe"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-archetype-probe"
PYTHON_BIN=""

fail() {
  printf 'v3 archetype calibration probe: %s\n' "$*" >&2
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
  docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || fail "retained postgres container is unavailable"
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER")" = "true" ] \
    || fail "retained postgres container is not running"
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

active_api_container() {
  local -a matches=()
  local container service
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")"
    case "$service" in
      api-*) matches+=("$container") ;;
    esac
  done < <(docker ps --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --format '{{.Names}}')
  [ "${#matches[@]}" -eq 1 ] || fail "expected exactly one running production API slot, found ${#matches[@]}"
  printf '%s\n' "${matches[0]}"
}

api_database_url() {
  local api="$1" value count
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')"
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || fail "active API does not expose exactly one DATABASE_URL"
  case "$value" in
    postgresql://*|postgres://*) ;;
    *) fail "active API DATABASE_URL is not a PostgreSQL DSN" ;;
  esac
  printf '%s' "$value"
}

require_generation() {
  local row key state current
  row="$(db_query "BEGIN READ ONLY; SELECT g.generation_key || E'\\t' || g.lifecycle_state || E'\\t' || (p.derived_generation_id IS NOT NULL)::text FROM v3_meta.derived_generation g LEFT JOIN v3_meta.current_derived_generation p ON p.singleton AND p.derived_generation_id=g.derived_generation_id WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r key state current <<< "$row"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  [ "$state" = "PUBLISHED" ] || fail "target generation is not PUBLISHED"
  [ "$current" = "true" ] || fail "target generation is not the current published pointer"
}

run_operation() {
  require_target
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in /var/tmp/edfinder-v3-probe-"$SOURCE_SHA") ;; *) fail "trusted main bundle path is outside reviewed staging namespace" ;; esac
  [ "$(cat "$REPO_ROOT/.v3-probe-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_archetype_calibration_probe.py" ] || fail "archetype calibration probe is missing"
  [ -f "$REPO_ROOT/scripts/v3_system_archetype.py" ] || fail "system archetype reader is missing"
  [ -f "$REPO_ROOT/scripts/v3_system_archetype_model.py" ] || fail "system archetype model is missing"
  [ -d "$REPO_ROOT/.v3-probe-wheelhouse" ] || fail "offline probe dependency wheelhouse is missing"
  require_generation

  install -d -m 700 "$STATE_ROOT"
  local api api_image cleanup_command dsn env_file output_file exit_code worker
  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"
  worker="edfinder-v3-archetype-probe-${SOURCE_SHA:0:12}"
  env_file="$STATE_ROOT/probe.envfile"
  output_file="$(mktemp "$STATE_ROOT/probe-output.XXXXXX")"
  printf -v cleanup_command 'rm -f -- %q %q' "$env_file" "$output_file"
  trap "$cleanup_command" EXIT
  umask 077
  printf 'V3_ARCHETYPE_PROBE_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  chmod 600 "$env_file"

  set +e
  timeout --signal=TERM 1500 docker run --rm \
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
    --entrypoint /bin/sh \
    "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-probe-wheelhouse --target /tmp/v3-probe-deps \
        "psycopg[binary]==3.3.4" 1>&2
      export PYTHONPATH="/tmp/v3-probe-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_archetype_calibration_probe.py --generation-key ratings_v4_prod_p4_parallel_v1 --max-systems 200000
    ' > "$output_file"
  exit_code=$?
  set -e
  rm -f "$env_file"
  local output_valid=true
  if ! "$PYTHON_BIN" -c 'import json,sys; json.load(open(sys.argv[1]))' "$output_file"; then
    output_valid=false
    exit_code=65
  fi
  printf 'operation=v3-archetype-calibration-probe\n'
  if [ "$output_valid" = true ] && [ "$exit_code" -eq 0 ]; then
    printf 'result=completed\n'
  else
    printf 'result=failed\n'
  fi
  printf 'source_sha=%s\n' "$SOURCE_SHA"
  printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
  printf 'exit_code=%s\n' "$exit_code"
  printf 'read_only=true\n'
  printf 'publication_performed=false\n'
  printf 'canonical_writes_performed=false\n'
  printf 'db_writes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
  if [ "$output_valid" = true ]; then
    printf 'probe_json=\n'
  else
    printf 'failure=invalid_probe_output\n'
    printf 'probe_output_raw=\n'
  fi
  cat "$output_file"
  return "$exit_code"
}

case "$ACTION" in
  run) run_operation ;;
  *) fail "expected run <REPO_ROOT> <SOURCE_SHA>" ;;
esac
