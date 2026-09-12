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
APPLICATION_NETWORK="edfinder-v3-production"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"
TARGET_CANONICAL_SEQUENCE="4"
TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
MIGRATION_NAME="006_v3_derived_product_lifecycle.sql"
MIGRATION_SHA="85f38fe5f0251bf3d5f81485a8a5b7de439750b4cc12ef9449755454898767f4"
WORKER="edfinder-v3-system-search-p4-opt1"
OPERATION_LABEL="ed-finder.operation=v3-system-search-f1"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-search"
TARGET_CPUS="8"
TARGET_MEMORY="32g"

fail() {
  printf 'v3 system search f1: %s\n' "$*" >&2
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
  done < <(docker ps --filter "label=com.docker.compose.project=${APPLICATION_NETWORK}" --format '{{.Names}}')
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
  local row key state canonical sequence expected
  row="$(db_query "BEGIN READ ONLY; SELECT generation_key || E'\\t' || lifecycle_state || E'\\t' || canonical_generation_id::text || E'\\t' || canonical_publication_sequence::text || E'\\t' || expected_systems::text FROM v3_meta.derived_generation WHERE generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r key state canonical sequence expected <<< "$row"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  case "$state" in BUILDING|VALIDATING|READY) ;; *) fail "target generation cannot accept Search in state $state" ;; esac
  [ "$canonical" = "$TARGET_CANONICAL_GENERATION" ] || fail "target canonical generation mismatch"
  [ "$sequence" = "$TARGET_CANONICAL_SEQUENCE" ] || fail "target canonical publication sequence mismatch"
  [ "$expected" = "198528286" ] || fail "target expected system count mismatch"
}

latest_status() {
  db_query "BEGIN READ ONLY; SELECT json_build_object(
    'generation_key',g.generation_key,
    'generation_state',g.lifecycle_state,
    'ratings_completed_chunks',(SELECT count(*) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
    'ratings_completed_systems',(SELECT COALESCE(sum(b.systems),0) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
    'ratings_source_receipt_present',g.source_receipt IS NOT NULL,
    'ratings_validation_status',g.validation_receipt->>'status',
    'search_product_state',(SELECT p.lifecycle_state FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_expected_rows',(SELECT p.expected_rows FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_validation_status',(SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_validated_at',(SELECT p.validated_at FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_completed_chunks',(SELECT count(*) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
    'search_completed_systems',(SELECT COALESCE(sum(s.systems),0) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
    'search_rows',(SELECT count(*) FROM v3_derived.system_search s WHERE s.derived_generation_id=g.derived_generation_id),
    'published_at',g.published_at
  )::text FROM v3_meta.derived_generation g WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;"
}

install_target_schema_identity() {
  local api_image="$1" identity_file expected_sha actual_sha authority
  authority="$REPO_ROOT/deploy/v3-production/target-authority.json"
  identity_file="$STATE_ROOT/schema-identity-${SOURCE_SHA}.json"
  python3.14 "$REPO_ROOT/scripts/operator/v3_schema_identity.py" --output "$identity_file" >/dev/null
  expected_sha="$(python3.14 - "$authority" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text())
print(value['external_authority']['schema_identity_sha256'])
PY
)"
  actual_sha="$(sha256sum "$identity_file" | awk '{print $1}')"
  [[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || fail "target authority schema identity pin is invalid"
  [ "$actual_sha" = "$expected_sha" ] || fail "derived schema identity does not match target authority pin"
  [ -d /etc/ed-finder/v3-production ] || fail "production authority directory is missing"

  docker run --rm -i --network none --user 0:0 \
    --mount type=bind,src=/etc/ed-finder/v3-production,dst=/target \
    --entrypoint /bin/sh "$api_image" -c '
      set -eu
      umask 077
      temp=/target/.schema-identity.json.new
      cat > "$temp"
      chmod 0600 "$temp"
      chown 0:0 "$temp"
      mv -f "$temp" /target/schema-identity.json
    ' < "$identity_file" >/dev/null

  [ "$(sha256sum /etc/ed-finder/v3-production/schema-identity.json | awk '{print $1}')" = "$expected_sha" ] \
    || fail "installed production schema identity checksum mismatch"
  printf '%s' "$expected_sha"
}

apply_pending_migration() {
  local plan_file apply_file pending_count pending_name
  plan_file="$STATE_ROOT/migration-plan-${SOURCE_SHA}.json"
  apply_file="$STATE_ROOT/migration-apply-${SOURCE_SHA}.json"
  python3.14 "$REPO_ROOT/scripts/operator/v3_production_migrate.py" \
    --operation plan --authority "$REPO_ROOT/deploy/v3-production/target-authority.json" \
    --root "$REPO_ROOT" > "$plan_file"
  read -r pending_count pending_name < <(python3.14 - "$plan_file" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text())
p=value.get('pending') or []
print(len(p), p[0]['ledger_name'] if len(p)==1 else '-')
PY
)
  if [ "$pending_count" = "1" ]; then
    [ "$pending_name" = "$MIGRATION_NAME" ] || fail "unexpected pending production migration: $pending_name"
    python3.14 "$REPO_ROOT/scripts/operator/v3_production_migrate.py" \
      --operation apply --authority "$REPO_ROOT/deploy/v3-production/target-authority.json" \
      --root "$REPO_ROOT" > "$apply_file"
  elif [ "$pending_count" != "0" ]; then
    fail "expected only migration 006 to be pending, found $pending_count"
  fi
  python3.14 "$REPO_ROOT/scripts/operator/v3_production_migrate.py" \
    --operation authority-gate --authority "$REPO_ROOT/deploy/v3-production/target-authority.json" \
    --root "$REPO_ROOT" | grep -F '"pending": 0' >/dev/null \
    || fail "production migration authority still reports pending migrations"
  local ledger_sha
  ledger_sha="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${MIGRATION_NAME}'; COMMIT;")"
  [ "$ledger_sha" = "$MIGRATION_SHA" ] || fail "migration 006 live ledger hash mismatch"
}

start_operation() {
  require_target
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in /var/tmp/edfinder-v3-search-"$SOURCE_SHA") ;; *) fail "trusted main bundle path is outside reviewed staging namespace" ;; esac
  [ "$(cat "$REPO_ROOT/.v3-search-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_system_search.py" ] || fail "Search builder is missing"
  [ -f "$REPO_ROOT/sql/v3/migrations/006_v3_derived_product_lifecycle.sql" ] || fail "migration 006 is missing"

  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/start.lock"
  flock -n 9 || fail "another V3 Search start is in progress"

  local api api_image dsn identity_sha worker_state env_file
  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  identity_sha="$(install_target_schema_identity "$api_image")"
  apply_pending_migration
  require_generation
  dsn="$(api_database_url "$api")"

  if docker inspect "$WORKER" >/dev/null 2>&1; then
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$worker_state" = "running" ]; then
      printf 'operation=v3-system-search-f1-start\nresult=already-running\nworker=%s\nschema_identity_sha256=%s\n' "$WORKER" "$identity_sha"
      printf 'latest_status=%s\n' "$(latest_status)"
      printf 'publication_performed=false\ncanonical_writes_performed=false\n'
      exit 0
    fi
    docker rm "$WORKER" >/dev/null
  fi

  env_file="$STATE_ROOT/search.env"
  umask 077
  printf 'V3_SYSTEM_SEARCH_DATABASE_URL=%s\n' "$dsn" > "$env_file"
  chmod 600 "$env_file"
  docker run -d \
    --name "$WORKER" \
    --label "$OPERATION_LABEL" \
    --label "ed-finder.generation-key=${TARGET_GENERATION_KEY}" \
    --label "ed-finder.source-sha=${SOURCE_SHA}" \
    --network "$APPLICATION_NETWORK" \
    --cpus "$TARGET_CPUS" \
    --memory "$TARGET_MEMORY" \
    --memory-swap "$TARGET_MEMORY" \
    --pids-limit 256 \
    --restart no \
    --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --entrypoint /bin/sh \
    "$api_image" -lc '
      set -eu
      export PYTHONPATH="/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_system_search.py \
        --generation-key ratings_v4_prod_p4_opt1 --follow --poll-seconds 5
    ' >/dev/null
  rm -f "$env_file"

  sleep 3
  worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  if [ "$worker_state" != "running" ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    fail "Search worker did not remain running"
  fi

  local proof=0
  for _ in $(seq 1 30); do
    proof="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.search_build_chunk s JOIN v3_meta.derived_generation g USING(derived_generation_id) WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
    [[ "$proof" =~ ^[0-9]+$ ]] || fail "Search proof query was invalid"
    [ "$proof" -ge 1 ] && break
    sleep 2
  done
  [ "$proof" -ge 1 ] || { docker logs --tail 80 "$WORKER" >&2 || true; fail "Search worker did not prove a committed chunk"; }

  printf 'operation=v3-system-search-f1-start\n'
  printf 'result=launched\n'
  printf 'source_sha=%s\n' "$SOURCE_SHA"
  printf 'schema_identity_sha256=%s\n' "$identity_sha"
  printf 'migration_006_verified=true\n'
  printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
  printf 'worker=%s\n' "$WORKER"
  printf 'worker_state=%s\n' "$worker_state"
  printf 'proof_chunks=%s\n' "$proof"
  printf 'cpu_limit=%s\n' "$TARGET_CPUS"
  printf 'memory_limit=%s\n' "$TARGET_MEMORY"
  printf 'latest_status=%s\n' "$(latest_status)"
  printf 'publication_performed=false\n'
  printf 'canonical_writes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
}

status_operation() {
  require_target
  require_generation
  printf 'operation=v3-system-search-f1-status\n'
  printf 'worker_containers:\n'
  docker ps -a --filter "label=${OPERATION_LABEL}" --format '  {{.Names}}\t{{.Status}}\t{{.Image}}' || true
  printf 'latest_status=%s\n' "$(latest_status)"
  if docker inspect "$WORKER" >/dev/null 2>&1; then
    printf 'latest_worker_log_tail:\n'
    docker logs --tail 40 "$WORKER" 2>&1 | sed 's/^/  /' || true
  fi
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

case "$ACTION" in
  start) start_operation ;;
  status) status_operation ;;
  *) fail "expected start or status" ;;
esac
