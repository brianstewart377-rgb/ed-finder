#!/usr/bin/env bash
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
TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
TARGET_CANONICAL_SEQUENCE="4"
TARGET_EXPECTED_SYSTEMS="198528286"
PYRAMID_VERSION="pyramid_v1"
SPATIAL_MIGRATION_NAME="012_v3_spatial_pyramid_decouple.sql"
SPATIAL_MIGRATION_SHA="5ca6a12e969392fe9562e7b2217d77988f4f2b27258ffa84845cb2c5314680ee"
OPERATION_LABEL="ed-finder.operation=v3-spatial-pyramid-build"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-spatial-pyramid"
TARGET_CPUS="4"
TARGET_MEMORY="16g"

fail() {
  printf 'v3 spatial pyramid: %s\n' "$*" >&2
  exit 64
}

require_target() {
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
  command -v python3.14 >/dev/null 2>&1 || fail "python3.14 is unavailable"
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

# The spatial pyramid is decoupled from the ratings derived_generation
# lifecycle (sql/v3/migrations/012_v3_spatial_pyramid_decouple.sql): this is
# the only migration this action gates on. Verifies the committed source file
# on the trusted staged checkout AND the live v3_meta.schema_migration ledger
# both match the pinned sha256, fail-closed on either mismatch.
require_schema() {
  [ "$(sha256sum "$REPO_ROOT/sql/v3/migrations/$SPATIAL_MIGRATION_NAME" | awk '{print $1}')" = "$SPATIAL_MIGRATION_SHA" ] \
    || fail "trusted migration $SPATIAL_MIGRATION_NAME source hash mismatch"
  local ledger_spatial
  ledger_spatial="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${SPATIAL_MIGRATION_NAME}'; COMMIT;")"
  [ "$ledger_spatial" = "$SPATIAL_MIGRATION_SHA" ] || fail "migration $SPATIAL_MIGRATION_NAME live ledger hash mismatch"
}

# Resolves and pins the single named canonical generation this action ever
# builds/publishes against. Prints TARGET_CANONICAL_GENERATION on stdout only
# after independently confirming: the live current_canonical_generation
# pointer is exactly this id at exactly this publication sequence, and the
# canonical catalogue it names has exactly the expected system count. Fails
# closed on any mismatch -- this action never accepts a caller-supplied
# generation id, and it never trusts the pinned constants alone without a
# live re-check.
resolve_pinned_canonical() {
  local row generation_id sequence schema count
  row="$(db_query "BEGIN READ ONLY; SELECT generation_id::text || E'\\t' || publication_sequence::text FROM v3_meta.current_canonical_generation WHERE singleton; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "current canonical generation is missing or ambiguous"
  IFS=$'\t' read -r generation_id sequence <<< "$row"
  [ "$generation_id" = "$TARGET_CANONICAL_GENERATION" ] || fail "current canonical generation mismatch"
  [ "$sequence" = "$TARGET_CANONICAL_SEQUENCE" ] || fail "current canonical publication sequence mismatch"
  schema="$(db_query "BEGIN READ ONLY; SELECT relation_schema FROM v3_meta.canonical_generation WHERE generation_id='${TARGET_CANONICAL_GENERATION}'; COMMIT;")"
  [[ "$schema" =~ ^v3_gen_[a-z][a-z0-9_]{0,30}$ ]] || fail "canonical relation schema is missing or unsafe"
  count="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM ${schema}.systems; COMMIT;")"
  [ "$count" = "$TARGET_EXPECTED_SYSTEMS" ] || fail "canonical system count mismatch"
  printf '%s' "$TARGET_CANONICAL_GENERATION"
}

# Resolves the (canonical, version)-keyed spatial_generation this build
# targets, creating a fresh BUILDING row when none exists yet. Prints
# "<spatial_generation_id>\t<lifecycle_state>" -- the caller (build_operation,
# NOT this function) is responsible for the idempotent already-ready
# short-circuit, because this function is invoked from a `$(...)` command
# substitution subshell: an `exit` here would only terminate that subshell,
# silently resuming the outer build with the printed receipt text mistaken
# for a spatial_generation_id. Any pre-existing lifecycle state other than
# READY/BUILDING is ambiguous for this action and fails closed.
resolve_or_create_spatial_generation() {
  local canonical="$1" row sgid state
  row="$(db_query "BEGIN READ ONLY; SELECT spatial_generation_id::text || E'\\t' || lifecycle_state FROM v3_spatial.spatial_generation WHERE canonical_generation_id='${canonical}' AND pyramid_version='${PYRAMID_VERSION}'; COMMIT;")"
  if [ -n "$row" ]; then
    [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "spatial generation for canonical+version is ambiguous"
    IFS=$'\t' read -r sgid state <<< "$row"
    case "$state" in
      READY|BUILDING) ;;
      *) fail "existing spatial generation for canonical+version is in unexpected state $state" ;;
    esac
  else
    sgid="$(db_query "INSERT INTO v3_spatial.spatial_generation (canonical_generation_id, pyramid_version, expected_systems) VALUES ('${canonical}','${PYRAMID_VERSION}',${TARGET_EXPECTED_SYSTEMS}) RETURNING spatial_generation_id;")"
    [[ "$sgid" =~ ^[0-9a-f-]{36}$ ]] || fail "spatial generation creation did not return a valid id"
    state="BUILDING"
  fi
  printf '%s\t%s' "$sgid" "$state"
}

build_operation() {
  require_target
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in /var/tmp/edfinder-v3-spatial-pyramid-"$SOURCE_SHA") ;; *) fail "trusted main bundle path is outside reviewed staging namespace" ;; esac
  [ "$(cat "$REPO_ROOT/.v3-spatial-pyramid-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_spatial_pyramid.py" ] || fail "spatial pyramid builder is missing"
  [ -d "$REPO_ROOT/.v3-spatial-pyramid-wheelhouse" ] || fail "offline dependency wheelhouse is missing"

  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/build.lock"
  flock -n 9 || fail "another spatial pyramid build is in progress"

  require_schema
  local canonical resolved sgid state
  canonical="$(resolve_pinned_canonical)"
  resolved="$(resolve_or_create_spatial_generation "$canonical")"
  IFS=$'\t' read -r sgid state <<< "$resolved"
  if [ "$state" = "READY" ]; then
    printf 'operation=v3-spatial-pyramid-build\n'
    printf 'result=already-ready\n'
    printf 'canonical_generation_id=%s\n' "$canonical"
    printf 'spatial_generation_id=%s\n' "$sgid"
    printf 'spatial_pyramid_version=%s\n' "$PYRAMID_VERSION"
    printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
    exit 0
  fi

  local api api_image dsn
  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"

  local driver_file env_file receipt_file
  driver_file="$STATE_ROOT/build_driver.py"
  env_file="$STATE_ROOT/build.env"
  receipt_file="$STATE_ROOT/receipt.json"
  umask 077

  # Static driver source: no shell interpolation into Python. Every varying
  # value (DSN, spatial generation id, pyramid version) crosses the trust
  # boundary only via the container's environment, never as embedded source
  # text.
  cat > "$driver_file" <<'PY'
import json
import os
import sys

sys.path.insert(0, "/work")

import psycopg

from scripts.v3_spatial_pyramid import (
    PYRAMID_VERSION,
    build_all_levels,
    build_receipt,
    canonical_system_count,
    mark_pyramid_ready,
    register_cell_levels,
)

dsn = os.environ["V3_SPATIAL_PYRAMID_DATABASE_URL"]
spatial_generation_id = os.environ["V3_SPATIAL_PYRAMID_SPATIAL_GENERATION_ID"]
version = os.environ.get("V3_SPATIAL_PYRAMID_VERSION") or PYRAMID_VERSION

# No autocommit: the whole build (register -> aggregate every level ->
# reconcile -> receipt -> mark READY) is one transaction. A reconciliation
# failure (or anything else raising) rolls the entire attempt back instead
# of leaving partially-built cell_summary rows behind.
with psycopg.connect(dsn) as conn:
    register_cell_levels(conn, version)

    canonical_count = canonical_system_count(conn, spatial_generation_id)

    per_level = build_all_levels(
        conn, spatial_generation_id=spatial_generation_id, version=version,
    )
    receipt = build_receipt(
        conn, spatial_generation_id=spatial_generation_id, version=version,
        canonical_count=canonical_count, per_level=per_level,
    )
    mark_pyramid_ready(
        conn, spatial_generation_id=spatial_generation_id, version=version, receipt=receipt,
    )

print(json.dumps(receipt, default=str, sort_keys=True))
PY

  printf 'V3_SPATIAL_PYRAMID_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  printf 'V3_SPATIAL_PYRAMID_SPATIAL_GENERATION_ID=%s\n' "$sgid" >> "$env_file"
  printf 'V3_SPATIAL_PYRAMID_VERSION=%s\n' "$PYRAMID_VERSION" >> "$env_file"
  chmod 600 "$env_file"

  docker run --rm -i \
    --name "edfinder-v3-spatial-pyramid-build" \
    --label "$OPERATION_LABEL" \
    --label "ed-finder.canonical-generation-id=${canonical}" \
    --label "ed-finder.spatial-generation-id=${sgid}" \
    --label "ed-finder.source-sha=${SOURCE_SHA}" \
    --network "$WORKER_NETWORK" \
    --cpus "$TARGET_CPUS" \
    --memory "$TARGET_MEMORY" \
    --memory-swap "$TARGET_MEMORY" \
    --pids-limit 256 \
    --restart no \
    --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --entrypoint /bin/sh \
    "$api_image" -c '
      set -eu
      /usr/local/bin/python -m pip install --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-spatial-pyramid-wheelhouse --target /tmp/v3-spatial-pyramid-deps \
        "psycopg[binary]==3.3.4"
      PYTHONPATH="/tmp/v3-spatial-pyramid-deps:/work"
      export PYTHONPATH
      exec /app/.venv/bin/python -
    ' < "$driver_file" > "$receipt_file"

  rm -f "$env_file" "$driver_file"

  cat "$receipt_file"
  printf 'operation=v3-spatial-pyramid-build\n'
  printf 'result=ready\n'
  printf 'source_sha=%s\n' "$SOURCE_SHA"
  printf 'canonical_generation_id=%s\n' "$canonical"
  printf 'spatial_generation_id=%s\n' "$sgid"
  printf 'spatial_pyramid_version=%s\n' "$PYRAMID_VERSION"
  printf 'cpu_limit=%s\n' "$TARGET_CPUS"
  printf 'memory_limit=%s\n' "$TARGET_MEMORY"
  printf 'database_writes_performed=true\n'
  printf 'canonical_writes_performed=false\n'
  printf 'publication_performed=false\n'
  printf 'schema_changes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
}

# Publishes the pinned (canonical, version) spatial generation via the CAS
# v3_spatial.publish_spatial_pyramid function (migration 012). Reads the
# current spatial publish pointer + sequence and the live canonical id in one
# read-only DB session, then passes every expected value back into the
# function so a concurrent publish or canonical rollover between the read and
# the write is rejected by the function itself, not just by this script.
# actor_/reason_ are the only operator-supplied free text this action ever
# passes to the database; they cross the trust boundary as bound psql
# variables (`:'name'`, safely quoted) rather than interpolated SQL text.
publish_operation() {
  require_target
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in /var/tmp/edfinder-v3-spatial-pyramid-"$SOURCE_SHA") ;; *) fail "trusted main bundle path is outside reviewed staging namespace" ;; esac
  [ "$(cat "$REPO_ROOT/.v3-spatial-pyramid-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] || fail "trusted main bundle SHA marker mismatch"

  local actor="${SPATIAL_PYRAMID_ACTOR:-}"
  local reason="${SPATIAL_PYRAMID_REASON:-}"
  [ -n "$(printf '%s' "$actor" | tr -d '[:space:]')" ] || fail "publish requires a non-empty actor"
  [ -n "$(printf '%s' "$reason" | tr -d '[:space:]')" ] || fail "publish requires a non-empty reason"

  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/publish.lock"
  flock -n 9 || fail "another spatial pyramid publish is in progress"

  require_schema
  local canonical
  canonical="$(resolve_pinned_canonical)"

  local row target state
  row="$(db_query "BEGIN READ ONLY; SELECT spatial_generation_id::text || E'\\t' || lifecycle_state FROM v3_spatial.spatial_generation WHERE canonical_generation_id='${canonical}' AND pyramid_version='${PYRAMID_VERSION}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "target spatial generation is missing or ambiguous"
  IFS=$'\t' read -r target state <<< "$row"
  [[ "$target" =~ ^[0-9a-f-]{36}$ ]] || fail "target spatial generation id is invalid"
  case "$state" in
    READY|RETIRED) ;;
    *) fail "target spatial generation must be READY before publishing, got $state" ;;
  esac

  local pointer expected_current expected_sequence
  pointer="$(db_query "BEGIN READ ONLY; SELECT spatial_generation_id::text || E'\\t' || publication_sequence::text FROM v3_spatial.current_spatial_generation WHERE singleton; COMMIT;")"
  if [ -n "$pointer" ]; then
    IFS=$'\t' read -r expected_current expected_sequence <<< "$pointer"
  else
    expected_current=""
    expected_sequence="0"
  fi

  # psql only interpolates client-side :'variables' when it reads the SQL from
  # stdin (or -f), NOT from --command/-c, which passes the string to the server
  # verbatim (a `:` there is a raw syntax error). The bound-variable quoting
  # above is the whole trust-boundary mechanism for actor/reason, so the SQL
  # MUST arrive on stdin: pipe it in via `docker exec -i`. Keep the query as a
  # single static line with no shell interpolation of the operator free text.
  local sequence
  sequence="$(printf '%s\n' \
    "SELECT v3_spatial.publish_spatial_pyramid(:'target'::uuid, NULLIF(:'expected_current','')::uuid, :'expected_sequence'::bigint, :'expected_canonical'::uuid, :'actor', :'reason');" \
    | docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
        --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
        --username "$DATABASE_USER" --dbname "$DATABASE_NAME" \
        -v target="$target" \
        -v expected_current="$expected_current" \
        -v expected_sequence="$expected_sequence" \
        -v expected_canonical="$canonical" \
        -v actor="$actor" \
        -v reason="$reason")"
  [[ "$sequence" =~ ^[0-9]+$ ]] || fail "publish_spatial_pyramid did not return a publication sequence"

  printf 'operation=v3-spatial-pyramid-publish\n'
  printf 'result=published\n'
  printf 'source_sha=%s\n' "$SOURCE_SHA"
  printf 'canonical_generation_id=%s\n' "$canonical"
  printf 'spatial_generation_id=%s\n' "$target"
  printf 'spatial_pyramid_version=%s\n' "$PYRAMID_VERSION"
  printf 'publication_sequence=%s\n' "$sequence"
  printf 'publication_performed=true\n'
  printf 'canonical_writes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
}

case "$ACTION" in
  build) build_operation ;;
  publish) publish_operation ;;
  *) fail "expected build or publish" ;;
esac
