#!/usr/bin/env bash
set -euo pipefail

PRODUCTION_REPO_DIR="${PRODUCTION_REPO_DIR:-/opt/ed-finder}"
REVIEW_REPO_DIR="${REVIEW_REPO_DIR:-/opt/ed-finder-review}"
REVIEW_PROJECT="${REVIEW_PROJECT:-edfinder-review-hosted}"
REVIEW_EDGE_NETWORK="${REVIEW_EDGE_NETWORK:-edfinder-review-edge}"
REVIEW_HOSTNAME="${REVIEW_HOSTNAME:-review.ed-finder.app}"
REVIEW_AUTH_FILE="${REVIEW_AUTH_FILE:-$REVIEW_REPO_DIR/.secrets/review.htpasswd}"
REVIEW_METADATA_FILE="${REVIEW_METADATA_FILE:-$REVIEW_REPO_DIR/.review/deployment.json}"
REVIEW_NGINX_LOG_DIR="${REVIEW_NGINX_LOG_DIR:-$REVIEW_REPO_DIR/.review/nginx-logs}"
CONFIRM=0
REMOVE_VOLUMES=0
COMMAND=""
DEPLOY_REF=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/ops/deploy_hosted_review.sh deploy --ref REF --confirm-hosted-review
  scripts/ops/deploy_hosted_review.sh teardown --confirm-hosted-review [--remove-volumes]

Deploys one branch/ref to the isolated hosted review stack at review.ed-finder.app.
The script never switches branches in /opt/ed-finder and never runs production
compose down. It starts only the review compose project.

Environment overrides:
  PRODUCTION_REPO_DIR=/opt/ed-finder
  REVIEW_REPO_DIR=/opt/ed-finder-review
  REVIEW_PROJECT=edfinder-review-hosted
  REVIEW_EDGE_NETWORK=edfinder-review-edge
  REVIEW_AUTH_FILE=/opt/ed-finder-review/.secrets/review.htpasswd
  REVIEW_NGINX_LOG_DIR=/opt/ed-finder-review/.review/nginx-logs
USAGE
}

say() { printf '\n[INFO] %s\n' "$*"; }
ok() { printf '[OK]   %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    deploy|teardown)
      COMMAND="$1"
      shift
      ;;
    --ref)
      DEPLOY_REF="$2"
      shift 2
      ;;
    --confirm-hosted-review)
      CONFIRM=1
      shift
      ;;
    --remove-volumes)
      REMOVE_VOLUMES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ "$CONFIRM" -eq 1 ]] || die 'mutating hosted review commands require --confirm-hosted-review'
[[ -n "$COMMAND" ]] || die 'command is required: deploy or teardown'

require_tool() {
  command -v "$1" >/dev/null || die "$1 is required"
}

compose_args=(
  -f "$REVIEW_REPO_DIR/docker-compose.review.yml"
  -f "$REVIEW_REPO_DIR/docker-compose.review-hosted.yml"
  -p "$REVIEW_PROJECT"
)

run_review_compose() {
  docker compose "${compose_args[@]}" "$@"
}

require_auth_file() {
  [[ -f "$REVIEW_AUTH_FILE" ]] || die "missing review auth file: $REVIEW_AUTH_FILE"
  local mode other_digit
  mode="$(stat -c '%a' "$REVIEW_AUTH_FILE")"
  other_digit="${mode: -1}"
  if (( other_digit & 4 )); then
    die "review auth file must not be world-readable: $REVIEW_AUTH_FILE has mode $mode"
  fi
}

ensure_edge_network() {
  docker network inspect "$REVIEW_EDGE_NETWORK" >/dev/null || die "missing Docker edge network $REVIEW_EDGE_NETWORK; create it with: docker network create $REVIEW_EDGE_NETWORK"
}

ensure_review_nginx_log_dir() {
  umask 027
  mkdir -p "$REVIEW_NGINX_LOG_DIR"
  chmod 750 "$REVIEW_REPO_DIR/.review" "$REVIEW_NGINX_LOG_DIR"
}

ensure_review_checkout() {
  [[ -d "$PRODUCTION_REPO_DIR/.git" ]] || die "$PRODUCTION_REPO_DIR is not the production git checkout"
  mkdir -p "$REVIEW_REPO_DIR"
  local remote_url
  remote_url="$(git -C "$PRODUCTION_REPO_DIR" remote get-url origin)"
  if [[ ! -d "$REVIEW_REPO_DIR/.git" ]]; then
    git -C "$REVIEW_REPO_DIR" init
    git -C "$REVIEW_REPO_DIR" remote add origin "$remote_url"
  else
    git -C "$REVIEW_REPO_DIR" remote set-url origin "$remote_url"
  fi
}

dirty_review_paths() {
  git -C "$REVIEW_REPO_DIR" status --porcelain=v1 --untracked-files=all \
    | grep -Ev '^(\?\? )?(\.secrets/|\.review/)' || true
}

require_clean_review_checkout() {
  local dirty
  dirty="$(dirty_review_paths)"
  [[ -z "$dirty" ]] || die "review checkout contains uncommitted changes outside .secrets/.review:$'\n'$dirty"
}

require_hosted_review_infrastructure() {
  local -a missing=()
  local required_path
  for required_path in \
    docker-compose.review.yml \
    docker-compose.review-hosted.yml \
    scripts/dev/review_environment_seed.py
  do
    [[ -f "$REVIEW_REPO_DIR/$required_path" ]] || missing+=("$required_path")
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf '[ERROR] Selected review ref does not contain hosted review infrastructure.\n' >&2
    printf '[ERROR] Missing required path(s): %s\n' "${missing[*]}" >&2
    printf '[ERROR] Rebase this branch onto current main after the hosted review environment has been merged, then deploy it again.\n' >&2
    exit 1
  fi
}

resolve_ref() {
  local requested_ref="$1"
  if git -C "$REVIEW_REPO_DIR" fetch --tags origin "$requested_ref" >/dev/null 2>&1; then
    git -C "$REVIEW_REPO_DIR" rev-parse --verify 'FETCH_HEAD^{commit}'
    return
  fi
  git -C "$REVIEW_REPO_DIR" fetch --tags origin >/dev/null
  git -C "$REVIEW_REPO_DIR" rev-parse --verify "$requested_ref^{commit}" 2>/dev/null \
    || git -C "$REVIEW_REPO_DIR" rev-parse --verify "origin/$requested_ref^{commit}"
}

write_deployment_metadata() {
  local requested_ref="$1"
  local resolved_commit="$2"
  mkdir -p "$(dirname "$REVIEW_METADATA_FILE")"
  python3 - "$REVIEW_METADATA_FILE" "$requested_ref" "$resolved_commit" "$REVIEW_HOSTNAME" "$REVIEW_PROJECT" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, requested_ref, resolved_commit, hostname, project = sys.argv[1:6]
payload = {
    "review_hostname": hostname,
    "requested_ref": requested_ref,
    "resolved_commit": resolved_commit,
    "deployed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "compose_project": project,
    "compose_files": [
        "docker-compose.review.yml",
        "docker-compose.review-hosted.yml",
    ],
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

verify_compose_targets() {
  local config_text
  config_text="$(run_review_compose config)"
  for forbidden in \
    'postgresql://edfinder:' \
    '@postgres:5432/edfinder' \
    'redis://redis:6379' \
    'ed-postgres' \
    'ed-redis' \
    'env_file:' \
    '/opt/ed-finder/.env'
  do
    if grep -Fq "$forbidden" <<<"$config_text"; then
      die "hosted review compose contains forbidden production reference: $forbidden"
    fi
  done
  grep -Fq 'CORS_ORIGINS: https://review.ed-finder.app' <<<"$config_text" \
    || die 'hosted review CORS origin is not constrained to https://review.ed-finder.app'
}

capture_production_container_state() {
  for container in ed-api ed-postgres ed-redis; do
    docker inspect -f "${container} {{.Id}} {{.RestartCount}}" "$container" 2>/dev/null || true
  done
}

wait_for_postgres() {
  for _ in {1..60}; do
    if run_review_compose exec -T review-postgres pg_isready -U review_user -d edfinder_local_review >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done
  die 'review Postgres did not become ready'
}

wait_for_redis() {
  for _ in {1..60}; do
    if [[ "$(run_review_compose exec -T review-redis redis-cli ping 2>/dev/null || true)" == "PONG" ]]; then
      return
    fi
    sleep 2
  done
  die 'review Redis did not become ready'
}

wait_for_api() {
  for _ in {1..60}; do
    if run_review_compose exec -T review-api curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done
  die 'review API health did not become ready internally'
}

bootstrap_schema() {
  run_review_compose exec -T review-postgres sh -lc \
    'set -eu; for f in $(ls -1 /workspace/sql/*.sql | sort); do case "$f" in */seed_preview.sql) continue ;; esac; psql -h 127.0.0.1 -U review_user -d edfinder_local_review -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null; done'
}

verify_runtime_targets() {
  run_review_compose exec -T review-api sh -lc \
    'test "$DATABASE_URL" = "postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review" && test "$REDIS_URL" = "redis://review-redis:6379/0"'
}

verify_edge_network_membership() {
  local names unexpected=()
  names="$(docker network inspect -f '{{range .Containers}}{{println .Name}}{{end}}' "$REVIEW_EDGE_NETWORK")"
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    case "$name" in
      ed-nginx|"$REVIEW_PROJECT"-review-api-*)
        ;;
      *)
        unexpected+=("$name")
        ;;
    esac
  done <<<"$names"
  if [[ "${#unexpected[@]}" -gt 0 ]]; then
    die "unexpected container(s) on $REVIEW_EDGE_NETWORK: ${unexpected[*]}"
  fi
}

reset_hosted_review_project() {
  run_review_compose down -v --remove-orphans
}

deploy_review() {
  [[ -n "$DEPLOY_REF" ]] || die 'deploy requires --ref REF'
  require_tool git
  require_tool docker
  require_tool corepack
  require_tool python3
  require_auth_file
  ensure_edge_network
  ensure_review_checkout
  require_clean_review_checkout

  say "Resolve review ref $DEPLOY_REF"
  local resolved_commit
  resolved_commit="$(resolve_ref "$DEPLOY_REF")"
  git -C "$REVIEW_REPO_DIR" checkout --detach "$resolved_commit"
  require_clean_review_checkout
  require_hosted_review_infrastructure
  ok "review checkout at $resolved_commit"

  say "Build review frontend at root path"
  (
    cd "$REVIEW_REPO_DIR/frontend"
    corepack yarn install --frozen-lockfile
    VITE_PUBLIC_BASE=/ corepack yarn build
  )
  ok 'review frontend built'

  say "Validate hosted review compose targets"
  verify_compose_targets
  ensure_review_nginx_log_dir
  local production_before production_after
  production_before="$(capture_production_container_state)"

  say "Reset hosted review project to clean synthetic volumes"
  reset_hosted_review_project

  say "Start isolated review data services"
  run_review_compose up -d review-postgres review-redis
  wait_for_postgres
  wait_for_redis
  bootstrap_schema

  say "Build, seed, and start isolated review API"
  run_review_compose build review-api
  run_review_compose run --rm review-api python /workspace/scripts/dev/review_environment_seed.py
  run_review_compose up -d review-api
  wait_for_api
  verify_runtime_targets
  verify_edge_network_membership

  production_after="$(capture_production_container_state)"
  [[ "$production_before" == "$production_after" ]] || die 'production API/Postgres/Redis container state changed during hosted review deploy'
  write_deployment_metadata "$DEPLOY_REF" "$resolved_commit"

  ok "hosted review deploy complete for $REVIEW_HOSTNAME"
  printf '[OK]   metadata: %s\n' "$REVIEW_METADATA_FILE"
}

teardown_review() {
  require_tool docker
  [[ -f "$REVIEW_REPO_DIR/docker-compose.review.yml" ]] || die "missing review compose file in $REVIEW_REPO_DIR"
  [[ -f "$REVIEW_REPO_DIR/docker-compose.review-hosted.yml" ]] || die "missing hosted review overlay in $REVIEW_REPO_DIR"
  local down_args=(down --remove-orphans)
  if [[ "$REMOVE_VOLUMES" -eq 1 ]]; then
    down_args+=(-v)
  fi
  run_review_compose "${down_args[@]}"
  ok "stopped hosted review compose project $REVIEW_PROJECT"
}

case "$COMMAND" in
  deploy)
    deploy_review
    ;;
  teardown)
    teardown_review
    ;;
  *)
    die "unsupported command: $COMMAND"
    ;;
esac
