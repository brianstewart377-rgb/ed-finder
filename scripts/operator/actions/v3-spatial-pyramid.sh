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
TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"
TARGET_CANONICAL_SEQUENCE="4"
TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
SPATIAL_MIGRATION_NAME="004_v3_search_spatial_clusters.sql"
SPATIAL_MIGRATION_SHA="e1c59def52b6a92a337f1da35c921bd0c135877f7843049ca9dec718aa01a1f2"
LIFECYCLE_MIGRATION_NAME="006_v3_derived_product_lifecycle.sql"
LIFECYCLE_MIGRATION_SHA="85f38fe5f0251bf3d5f81485a8a5b7de439750b4cc12ef9449755454898767f4"
SPATIAL_PYRAMID_VERSION="pyramid_v1"
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

require_schema() {
  [ "$(sha256sum "$REPO_ROOT/sql/v3/migrations/$SPATIAL_MIGRATION_NAME" | awk '{print $1}')" = "$SPATIAL_MIGRATION_SHA" ] \
    || fail "trusted migration $SPATIAL_MIGRATION_NAME source hash mismatch"
  [ "$(sha256sum "$REPO_ROOT/sql/v3/migrations/$LIFECYCLE_MIGRATION_NAME" | awk '{print $1}')" = "$LIFECYCLE_MIGRATION_SHA" ] \
    || fail "trusted migration $LIFECYCLE_MIGRATION_NAME source hash mismatch"
  local ledger_spatial ledger_lifecycle
  ledger_spatial="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${SPATIAL_MIGRATION_NAME}'; COMMIT;")"
  [ "$ledger_spatial" = "$SPATIAL_MIGRATION_SHA" ] || fail "migration $SPATIAL_MIGRATION_NAME live ledger hash mismatch"
  ledger_lifecycle="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${LIFECYCLE_MIGRATION_NAME}'; COMMIT;")"
  [ "$ledger_lifecycle" = "$LIFECYCLE_MIGRATION_SHA" ] || fail "migration $LIFECYCLE_MIGRATION_NAME live ledger hash mismatch"
}

# Resolves and pins the single named target generation this action ever builds
# against. Prints the derived_generation_id on stdout. Fails closed if the
# generation is missing/ambiguous/not READY, or if the canonical lineage it
# is pinned to does not match exactly -- this action never accepts a caller-
# supplied generation id.
resolve_pinned_generation() {
  local row dgid key state canonical sequence expected
  row="$(db_query "BEGIN READ ONLY; SELECT derived_generation_id::text || E'\\t' || generation_key || E'\\t' || lifecycle_state || E'\\t' || canonical_generation_id::text || E'\\t' || canonical_publication_sequence::text || E'\\t' || expected_systems::text FROM v3_meta.derived_generation WHERE generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r dgid key state canonical sequence expected <<< "$row"
  [[ "$dgid" =~ ^[0-9a-f-]{36}$ ]] || fail "derived generation id is invalid"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  [ "$state" = "READY" ] || fail "target generation must be READY before building the spatial pyramid, got $state"
  [ "$canonical" = "$TARGET_CANONICAL_GENERATION" ] || fail "target canonical generation mismatch"
  [ "$sequence" = "$TARGET_CANONICAL_SEQUENCE" ] || fail "target canonical publication sequence mismatch"
  [ "$expected" = "198528286" ] || fail "target expected system count mismatch"
  printf '%s' "$dgid"
}

# The pyramid builder's cheap source path (v3_derived.system_search) must
# already be a complete, READY product for the pinned generation -- the
# canonical-catalogue fallback in scripts/v3_spatial_pyramid.py is not yet
# implemented (raises NotImplementedError by design), so this is a fail-closed
# precondition, not an optimisation.
require_search_product_ready() {
  local dgid="$1" state
  state="$(db_query "BEGIN READ ONLY; SELECT lifecycle_state FROM v3_meta.derived_product WHERE derived_generation_id='${dgid}' AND product_code='system_search'; COMMIT;")"
  [ "$state" = "READY" ] || fail "system_search product must be READY before building the spatial pyramid, got ${state:-missing}"
}

pyramid_product_state() {
  local dgid="$1"
  db_query "BEGIN READ ONLY; SELECT lifecycle_state FROM v3_meta.derived_product WHERE derived_generation_id='${dgid}' AND product_code='spatial_pyramid'; COMMIT;"
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
  local dgid
  dgid="$(resolve_pinned_generation)"
  require_search_product_ready "$dgid"

  local existing_state
  existing_state="$(pyramid_product_state "$dgid")"
  if [ "$existing_state" = "READY" ]; then
    printf 'operation=v3-spatial-pyramid-build\n'
    printf 'result=already-ready\n'
    printf 'derived_generation_id=%s\n' "$dgid"
    printf 'spatial_pyramid_version=%s\n' "$SPATIAL_PYRAMID_VERSION"
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
  # value (DSN, generation id, pyramid version) crosses the trust boundary
  # only via the container's environment, never as embedded source text.
  cat > "$driver_file" <<'PY'
import json
import os
import sys

sys.path.insert(0, "/work")

import psycopg
from psycopg import sql

from scripts.v3_spatial_pyramid import (
    PYRAMID_VERSION,
    _canonical_schema,
    build_all_levels,
    build_receipt,
    mark_pyramid_ready,
    register_cell_levels,
    resolve_source,
)

dsn = os.environ["V3_SPATIAL_PYRAMID_DATABASE_URL"]
derived_generation_id = os.environ["V3_SPATIAL_PYRAMID_DERIVED_GENERATION_ID"]
version = os.environ.get("V3_SPATIAL_PYRAMID_VERSION") or PYRAMID_VERSION

# No autocommit: the whole build (register -> aggregate every level ->
# reconcile -> receipt -> mark READY) is one transaction. A reconciliation
# failure (or anything else raising) rolls the entire attempt back instead
# of leaving partially-built cell_summary rows behind.
with psycopg.connect(dsn) as conn:
    register_cell_levels(conn, version)

    schema = _canonical_schema(conn, derived_generation_id)
    canonical_count = conn.execute(
        sql.SQL("SELECT count(*) FROM {}.systems").format(sql.Identifier(schema))
    ).fetchone()[0]

    source = resolve_source(conn, derived_generation_id)
    per_level = build_all_levels(
        conn, derived_generation_id=derived_generation_id, version=version, source=source,
    )
    receipt = build_receipt(
        conn, derived_generation_id=derived_generation_id, version=version,
        source=source, canonical_count=canonical_count, per_level=per_level,
    )
    mark_pyramid_ready(
        conn, derived_generation_id=derived_generation_id, version=version, receipt=receipt,
    )

print(json.dumps(receipt, default=str, sort_keys=True))
PY

  printf 'V3_SPATIAL_PYRAMID_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  printf 'V3_SPATIAL_PYRAMID_DERIVED_GENERATION_ID=%s\n' "$dgid" >> "$env_file"
  printf 'V3_SPATIAL_PYRAMID_VERSION=%s\n' "$SPATIAL_PYRAMID_VERSION" >> "$env_file"
  chmod 600 "$env_file"

  docker run --rm -i \
    --name "edfinder-v3-spatial-pyramid-build" \
    --label "$OPERATION_LABEL" \
    --label "ed-finder.generation-key=${TARGET_GENERATION_KEY}" \
    --label "ed-finder.derived-generation-id=${dgid}" \
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
  printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
  printf 'derived_generation_id=%s\n' "$dgid"
  printf 'spatial_pyramid_version=%s\n' "$SPATIAL_PYRAMID_VERSION"
  printf 'cpu_limit=%s\n' "$TARGET_CPUS"
  printf 'memory_limit=%s\n' "$TARGET_MEMORY"
  printf 'database_writes_performed=true\n'
  printf 'canonical_writes_performed=false\n'
  printf 'publication_performed=false\n'
  printf 'schema_changes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
}

status_operation() {
  require_target
  local dgid state
  dgid="$(resolve_pinned_generation)"
  state="$(pyramid_product_state "$dgid")"
  printf 'operation=v3-spatial-pyramid-status\n'
  printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
  printf 'derived_generation_id=%s\n' "$dgid"
  printf 'spatial_pyramid_product_state=%s\n' "${state:-none}"
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

case "$ACTION" in
  build) build_operation ;;
  status) status_operation ;;
  *) fail "expected build or status" ;;
esac
