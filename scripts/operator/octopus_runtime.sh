#!/usr/bin/env bash
set -euo pipefail
readonly DIR=/opt/octopus
readonly UPSTREAM_COMMIT=55583ac832472ad8b535f1f678f9c11837f7cfdb
readonly VERSION=1.0.122
readonly PUBLIC_URL=https://octopus.ed-finder.app
die(){ printf 'error: %s\n' "$*" >&2; exit 64; }
dc(){ docker compose --project-name octopus-selfhost --env-file "$DIR/octopus.env" -f "$DIR/compose.yaml" "$@"; }
wait_healthy(){
  local service id state attempt
  for service in "$@"; do
    id=$(dc ps -q "$service"); [[ -n $id ]] || die "service did not start: $service"
    for attempt in $(seq 1 60); do
      state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")
      [[ $state == healthy ]] && break
      [[ $state != unhealthy && $state != exited && $state != dead ]] || die "service failed health: $service"
      sleep 2
    done
    [[ $state == healthy ]] || die "service health timed out: $service"
  done
}
env_value(){ sed -n "s/^$1=//p" "$DIR/octopus.env" | tail -1; }
workers_false(){ [[ $(env_value ENABLE_REVIEW_WORKERS) == false ]] || die 'ENABLE_REVIEW_WORKERS must be false'; }
receipt(){ [[ -f "$DIR/receipts/$1" ]] || die "required receipt missing: $1"; }
set_env_literal_file(){
  local path=$1 key=$2 value=$3 tmp
  [[ $key =~ ^[A-Z][A-Z0-9_]*$ ]] || die 'invalid environment key'
  [[ $value != *$'\n'* && $value != *$'\r'* ]] || die 'invalid environment value'
  [[ -f $path ]] || die 'environment file is absent'
  tmp=$(mktemp "$(dirname "$path")/.octopus-env.XXXXXX")
  awk -v key="$key" -v value="$value" 'BEGIN{found=0} $0 ~ ("^" key "="){if(!found) print key "=" value; found=1; next} {print} END{if(!found) print key "=" value}' "$path" > "$tmp"
  chmod 0600 "$tmp"; mv "$tmp" "$path"
}
set_workers_file(){
  local path=$1 value=$2
  [[ $value == true || $value == false ]] || die 'invalid worker value'
  set_env_literal_file "$path" ENABLE_REVIEW_WORKERS "$value"
}
set_workers(){ set_workers_file "$DIR/octopus.env" "$1"; }
legacy_env_path(){
  local candidate found='' count=0
  for candidate in "$DIR/octopus.env" "$DIR/.env"; do
    if [[ -f $candidate ]]; then
      found=$candidate
      count=$((count + 1))
    fi
  done
  [[ $count -eq 1 ]] || {
    if [[ $count -eq 0 ]]; then
      die 'no supported legacy env file found under /opt/octopus'
    fi
    die 'multiple supported legacy env files found under /opt/octopus'
  }
  printf '%s\n' "$found"
}
legacy_worker_state(){
  docker inspect octopus-web >/dev/null 2>&1 || die 'legacy octopus-web container is absent'
  local state
  state=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' octopus-web | sed -n 's/^ENABLE_REVIEW_WORKERS=//p' | tail -1)
  [[ $state == true || $state == false ]] || die 'legacy worker state is not explicit'
  printf '%s\n' "$state"
}
legacy_dc(){
  local container=octopus-web project config workdir env_file
  docker inspect "$container" >/dev/null 2>&1 || die 'legacy octopus-web container is absent'
  project=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
  config=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container")
  workdir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container")
  env_file=$(legacy_env_path)
  [[ $project =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die 'invalid legacy Compose project label'
  [[ $config == /opt/octopus/* && $config != *,* && -f $config ]] || die 'legacy Compose config is not a single /opt/octopus file'
  [[ $workdir == /opt/octopus ]] || die 'legacy Compose working directory mismatch'
  docker compose --project-name "$project" --env-file "$env_file" -f "$config" "$@"
}
case "${1:-}" in
  private-install)
    workers_false; cd "$DIR"; dc pull
    dc up -d postgres qdrant
    wait_healthy postgres qdrant
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
    git -c advice.detachedHead=false clone --quiet --depth 1 --branch v1.0.122 https://github.com/octopusreview/octopus.git "$tmp/source"
    [[ $(git -C "$tmp/source" rev-parse HEAD) == "$UPSTREAM_COMMIT" ]] || die 'upstream tag commit mismatch'
    umask 077; db_env=$(mktemp); trap 'rm -rf "$tmp"; rm -f "$db_env"' EXIT
    printf 'DATABASE_URL=postgresql://octopus:%s@postgres:5432/octopus\n' "$(env_value OCTOPUS_POSTGRES_PASSWORD)" > "$db_env"
    docker run --rm --network octopus-selfhost-backend --env-file "$db_env" -v "$tmp/source:/src" -w /src oven/bun:1.3.4 sh -c 'bun install --frozen-lockfile && cd packages/db && bunx prisma migrate deploy'
    rm -f "$db_env"; rm -rf "$tmp"; trap - EXIT
    dc up -d web
    ;;
  private-verify)
    workers_false; cd "$DIR"; dc ps --status running | grep -q web || die 'web is not running'
    curl --fail --silent http://127.0.0.1:43300/api/health >/dev/null
    [[ $(curl --fail --silent http://127.0.0.1:43300/api/version | tr -d '"[:space:]') == "$VERSION" ]] || die 'unexpected Octopus version'
    for port in 43332 43333 43334; do ! ss -H -ltn "sport = :$port" | grep -q . || die "forbidden listener: $port"; done
    before=$(docker ps --filter 'name=edfinder|name=v3' --format '{{.ID}} {{.State}}' | sort | sha256sum)
    dc restart; wait_healthy postgres qdrant web; curl --fail --silent http://127.0.0.1:43300/api/health >/dev/null
    after=$(docker ps --filter 'name=edfinder|name=v3' --format '{{.ID}} {{.State}}' | sort | sha256sum); [[ $before == "$after" ]] || die 'ED-Finder/V3 runtime changed'
    install -d -m 0700 "$DIR/receipts"; printf 'version=%s\nworkers=false\n' "$VERSION" | install -m 0600 /dev/stdin "$DIR/receipts/private-proof"
    ;;
  status)
    printf 'workers_enabled: %s\n' "$(env_value ENABLE_REVIEW_WORKERS)"; [[ -f "$DIR/receipts/private-proof" ]] && printf 'private_proof: true\n' || printf 'private_proof: false\n'
    ;;
  set-public-url)
    receipt private-proof; receipt public-edge-proof; workers_false
    set_env_literal_file "$DIR/octopus.env" BETTER_AUTH_URL "$PUBLIC_URL"
    set_env_literal_file "$DIR/octopus.env" NEXT_PUBLIC_APP_URL "$PUBLIC_URL"
    cd "$DIR"; dc up -d --no-deps web; wait_healthy web
    [[ $(env_value BETTER_AUTH_URL) == "$PUBLIC_URL" ]] || die 'BETTER_AUTH_URL transition failed'
    [[ $(env_value NEXT_PUBLIC_APP_URL) == "$PUBLIC_URL" ]] || die 'NEXT_PUBLIC_APP_URL transition failed'
    printf 'public_auth_url_configured: true\nworkers_enabled: false\n'
    ;;
  cutover-verify)
    receipt private-proof; receipt public-edge-proof
    [[ $(env_value ENABLE_REVIEW_WORKERS) == true ]] || die 'new review worker is not enabled'
    [[ $(env_value BETTER_AUTH_URL) == "$PUBLIC_URL" ]] || die 'public BETTER_AUTH_URL is not configured'
    [[ $(env_value NEXT_PUBLIC_APP_URL) == "$PUBLIC_URL" ]] || die 'public NEXT_PUBLIC_APP_URL is not configured'
    curl --fail --silent http://127.0.0.1:43300/api/health >/dev/null
    [[ $(curl --fail --silent http://127.0.0.1:43300/api/version | tr -d '"[:space:]') == "$VERSION" ]] || die 'unexpected private Octopus version'
    code=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --resolve octopus.ed-finder.app:443:127.0.0.1 https://octopus.ed-finder.app/)
    [[ $code == 401 ]] || die 'local TLS edge did not route to the protected Octopus origin'
    printf 'local_edge_tls_routes_to_new_octopus: true\nexternal_dns_webhook_proof_pending: true\n'
    ;;
  legacy-env-path)
    legacy_env_path
    ;;
  legacy-preflight)
    env_file=$(legacy_env_path)
    [[ $(dirname "$env_file") == /opt/octopus ]] || die 'legacy env escaped expected directory'
    docker inspect octopus-web >/dev/null 2>&1 || die 'legacy octopus-web container is absent'
    legacy_dc config --quiet
    python3 "$(dirname "$0")/octopus_credentials.py" check --source "$env_file"
    printf 'legacy_env_file: %s\n' "$(basename "$env_file")"
    printf 'legacy_workers_enabled: %s\n' "$(legacy_worker_state)"
    printf 'legacy_compose_valid: true\n'
    ;;
  legacy-status)
    legacy_env_path >/dev/null
    printf 'legacy_workers_enabled: %s\n' "$(legacy_worker_state)"
    [[ -f "$DIR/receipts/old-quiesced" ]] && printf 'old_quiesce_receipt: true\n' || printf 'old_quiesce_receipt: false\n'
    ;;
  quiesce-old)
    env_file=$(legacy_env_path); cd /opt/octopus; set_workers_file "$env_file" false
    legacy_dc up -d --no-deps web
    [[ $(legacy_worker_state) == false ]] || die 'legacy worker did not quiesce'
    install -d -m 0700 receipts; printf 'workers=false\nlegacy_preserved=true\n' | install -m 0600 /dev/stdin receipts/old-quiesced
    ;;
  restore-old)
    env_file=$(legacy_env_path); cd /opt/octopus; set_workers_file "$env_file" true
    legacy_dc up -d --no-deps web
    [[ $(legacy_worker_state) == true ]] || die 'legacy worker did not restore'
    rm -f "$DIR/receipts/old-quiesced"
    printf 'legacy_workers_restored: true\nold_quiesce_receipt_invalidated: true\n'
    ;;
  enable-worker)
    receipt private-proof; receipt old-quiesced; receipt public-edge-proof
    [[ $(env_value BETTER_AUTH_URL) == "$PUBLIC_URL" ]] || die 'final BETTER_AUTH_URL required'
    [[ $(env_value NEXT_PUBLIC_APP_URL) == "$PUBLIC_URL" ]] || die 'final NEXT_PUBLIC_APP_URL required'
    set_workers true; cd "$DIR"; dc up -d --no-deps web
    ;;
  disable-worker)
    set_workers false; cd "$DIR"; dc up -d --no-deps web
    ;;
  *) die 'unsupported runtime operation' ;;
esac
