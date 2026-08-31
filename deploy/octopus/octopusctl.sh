#!/usr/bin/env bash
set -Eeuo pipefail

readonly TARGET=/opt/octopus
readonly PROJECT=edfinder_octopus_fresh_10122
readonly RELEASE=1.0.122
readonly UPSTREAM_COMMIT=55583ac832472ad8b535f1f678f9c11837f7cfdb
readonly NETWORK=edfinder-octopus-fresh-10122-network
readonly PG_VOLUME=edfinder-octopus-fresh-10122-postgres-data
readonly QDRANT_VOLUME=edfinder-octopus-fresh-10122-qdrant-data
readonly WEB_CONTAINER=edfinder-octopus-fresh-10122-web
readonly PG_CONTAINER=edfinder-octopus-fresh-10122-postgres
readonly QDRANT_CONTAINER=edfinder-octopus-fresh-10122-qdrant
readonly SOURCE_DIR="$TARGET/upstream-v$RELEASE"
readonly COMPOSE_FILE="$TARGET/docker-compose.yml"
readonly ENV_FILE="$TARGET/.env"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"; }
compose() { docker compose --project-name "$PROJECT" --project-directory "$TARGET" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

assert_port_free() {
  if command -v ss >/dev/null 2>&1 && ss -H -ltn | awk '{print $4}' | grep -Eq '(^|:)43300$'; then
    die 'TCP port 43300 is already listening'
  fi
}

assert_absent_docker_objects() {
  local item
  for item in "$WEB_CONTAINER" "$PG_CONTAINER" "$QDRANT_CONTAINER"; do
    [[ -z "$(docker ps -aq --filter "name=^/${item}$")" ]] || die "container already exists: $item"
  done
  for item in "$PG_VOLUME" "$QDRANT_VOLUME"; do
    ! docker volume inspect "$item" >/dev/null 2>&1 || die "volume already exists: $item"
  done
  ! docker network inspect "$NETWORK" >/dev/null 2>&1 || die "network already exists: $NETWORK"
}

assert_owned_object() {
  local kind=$1 name=$2 label
  label=$(docker "$kind" inspect --format '{{ index .Labels "com.docker.compose.project" }}' "$name" 2>/dev/null) || die "$kind missing: $name"
  [[ "$label" == "$PROJECT" ]] || die "$kind $name is not owned by $PROJECT"
}

assert_prepared() {
  [[ -d "$TARGET" && -f "$COMPOSE_FILE" && -f "$ENV_FILE" ]] || die 'bundle is not prepared'
  [[ $(stat -c '%a' "$ENV_FILE") == 600 ]] || die '.env must have mode 0600'
  ! grep -q '__REQUIRED_' "$ENV_FILE" || die '.env still contains required placeholders'
  [[ $(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null) == "$UPSTREAM_COMMIT" ]] || die 'upstream checkout does not match v1.0.122'
  [[ -z "$(git -C "$SOURCE_DIR" status --porcelain)" ]] || die 'upstream checkout is dirty'
}

assert_owned_stack() {
  assert_owned_object container "$PG_CONTAINER"
  assert_owned_object container "$QDRANT_CONTAINER"
  assert_owned_object volume "$PG_VOLUME"
  assert_owned_object volume "$QDRANT_VOLUME"
  assert_owned_object network "$NETWORK"
}

wait_dependencies() {
  local tries=60
  until docker exec "$PG_CONTAINER" pg_isready -U octopus_app -d octopus_fresh >/dev/null 2>&1 &&
        docker exec "$QDRANT_CONTAINER" wget -q --spider http://127.0.0.1:6333/readyz; do
    ((--tries > 0)) || die 'PostgreSQL or Qdrant readiness timed out'
    sleep 2
  done
}

preflight() {
  need docker; need git; need install; need awk; need grep
  docker info >/dev/null
  docker compose version >/dev/null
  [[ ! -e "$TARGET" ]] || die "$TARGET already exists"
  assert_absent_docker_objects
  assert_port_free
  printf 'preflight ok: target, named Docker objects, and loopback port are free\n'
}

prepare() {
  preflight
  local source_root
  source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  install -d -m 0700 "$TARGET" "$TARGET/receipts"
  install -m 0644 "$source_root/docker-compose.yml" "$COMPOSE_FILE"
  install -m 0600 "$source_root/env.example" "$ENV_FILE"
  install -m 0755 "$source_root/octopusctl.sh" "$TARGET/octopusctl.sh"
  git clone --depth 1 --branch "v$RELEASE" https://github.com/octopusreview/octopus.git "$SOURCE_DIR"
  [[ $(git -C "$SOURCE_DIR" rev-parse HEAD) == "$UPSTREAM_COMMIT" ]] || die 'cloned tag commit mismatch'
  printf '%s  v%s\n' "$UPSTREAM_COMMIT" "$RELEASE" >"$TARGET/receipts/upstream-source.txt"
  printf 'prepared %s; populate %s and keep it mode 0600\n' "$TARGET" "$ENV_FILE"
}

migrate() {
  assert_prepared
  assert_absent_docker_objects
  assert_port_free
  compose up -d postgres qdrant
  assert_owned_stack
  wait_dependencies
  local DATABASE_URL
  DATABASE_URL=$(sed -n 's/^OCTOPUS_DATABASE_URL=//p' "$ENV_FILE")
  [[ -n "$DATABASE_URL" ]] || die 'OCTOPUS_DATABASE_URL is missing'
  export DATABASE_URL
  # Runtime image has no migrations. Copy the immutable matching checkout into
  # a disposable Bun container; no host dependency tree or mutable toolchain is used.
  docker run --rm --network "$NETWORK" \
    -e DATABASE_URL \
    -v "$SOURCE_DIR:/source:ro" oven/bun:1.3.4-alpine@sha256:7608db4aeb44f1fe8169cc8ec7055376b3013557b106407ccf092b00e426407d \
    sh -euc 'cp -a /source /work && cd /work && bun install --frozen-lockfile && cd packages/db && bunx prisma migrate deploy' \
    2>&1 | tee "$TARGET/receipts/migration-v$RELEASE.txt"
  printf '%s\n' "$UPSTREAM_COMMIT" >"$TARGET/receipts/migration-source-commit.txt"
}

start() {
  assert_prepared
  assert_owned_stack
  [[ -f "$TARGET/receipts/migration-source-commit.txt" ]] || die 'matching migrations have no receipt'
  [[ $(<"$TARGET/receipts/migration-source-commit.txt") == "$UPSTREAM_COMMIT" ]] || die 'migration receipt version mismatch'
  assert_port_free
  compose up -d web
  assert_owned_object container "$WEB_CONTAINER"
  health
}

health() {
  assert_prepared
  need curl; need python3
  assert_owned_stack
  assert_owned_object container "$WEB_CONTAINER"
  wait_dependencies
  local health='' version='' tries=60
  until health=$(curl --fail --silent --show-error http://127.0.0.1:43300/api/health 2>/dev/null) &&
        version=$(curl --fail --silent --show-error http://127.0.0.1:43300/api/version 2>/dev/null); do
    ((--tries > 0)) || die 'Octopus API health/version timed out'
    sleep 2
  done
  printf '%s\n' "$health" | tee "$TARGET/receipts/api-health.json"
  printf '%s\n' "$version" | tee "$TARGET/receipts/api-version.json"
  python3 - "$TARGET/receipts/api-health.json" "$TARGET/receipts/api-version.json" <<'PY'
import json
import sys

health = json.load(open(sys.argv[1], encoding='utf-8'))
version = json.load(open(sys.argv[2], encoding='utf-8'))
if health.get('status') != 'ok':
    raise SystemExit('API health is not ok')
if version.get('version') != '1.0.122' or version.get('selfHosted') is not True:
    raise SystemExit('API version is not exact self-hosted 1.0.122')
PY
  compose ps | tee "$TARGET/receipts/container-health.txt"
  docker inspect --format '{{.Name}} {{.Config.Image}} {{.Image}} {{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    "$WEB_CONTAINER" "$PG_CONTAINER" "$QDRANT_CONTAINER" | tee "$TARGET/receipts/image-version-health.txt"
}

activate() {
  assert_prepared
  [[ ${OCTOPUS_OLD_WORKER_STOPPED:-} == yes ]] || die 'set OCTOPUS_OLD_WORKER_STOPPED=yes only after independently stopping the old worker/webhook'
  grep -qx 'ENABLE_REVIEW_WORKERS=false' "$ENV_FILE" || die 'worker setting is not exactly false'
  health
  local tmp="$TARGET/.env.activate.$$"
  sed 's/^ENABLE_REVIEW_WORKERS=false$/ENABLE_REVIEW_WORKERS=true/' "$ENV_FILE" >"$tmp"
  chmod 0600 "$tmp"
  cmp -s <(grep -v '^ENABLE_REVIEW_WORKERS=' "$ENV_FILE") <(grep -v '^ENABLE_REVIEW_WORKERS=' "$tmp") || die 'activation changed more than the worker setting'
  mv "$tmp" "$ENV_FILE"
  compose up -d --no-deps --force-recreate web
  health
  printf '%s activation: ENABLE_REVIEW_WORKERS false -> true\n' "$(date -u +%FT%TZ)" | tee -a "$TARGET/receipts/activation.log"
}

stop_stack() {
  assert_prepared
  assert_owned_stack
  compose stop
  printf 'stopped only project %s; volumes and network retained\n' "$PROJECT"
}

case ${1:-} in
  preflight) preflight ;;
  prepare) prepare ;;
  migrate) migrate ;;
  start) start ;;
  health) health ;;
  activate) activate ;;
  stop) stop_stack ;;
  *) die 'usage: octopusctl.sh {preflight|prepare|migrate|start|health|activate|stop}' ;;
esac
