#!/usr/bin/env bash
set -euo pipefail
readonly DIR=/opt/octopus
readonly UPSTREAM_COMMIT=55583ac832472ad8b535f1f678f9c11837f7cfdb
readonly VERSION=1.0.122
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
set_workers(){
  local value=$1 tmp; [[ $value == true || $value == false ]] || die 'invalid worker value'
  tmp=$(mktemp "$DIR/.octopus.env.XXXXXX")
  awk -v value="$value" 'BEGIN{found=0} /^ENABLE_REVIEW_WORKERS=/{if(!found) print "ENABLE_REVIEW_WORKERS=" value; found=1; next} {print} END{if(!found) print "ENABLE_REVIEW_WORKERS=" value}' "$DIR/octopus.env" > "$tmp"
  chmod 0600 "$tmp"; mv "$tmp" "$DIR/octopus.env"
}
legacy_dc(){
  local container=octopus-web project config workdir
  docker inspect "$container" >/dev/null 2>&1 || die 'legacy octopus-web container is absent'
  project=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
  config=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container")
  workdir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container")
  [[ $project =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die 'invalid legacy Compose project label'
  [[ $config == /opt/octopus/* && $config != *,* && -f $config ]] || die 'legacy Compose config is not a single /opt/octopus file'
  [[ $workdir == /opt/octopus && -f /opt/octopus/octopus.env ]] || die 'legacy Compose working directory/env mismatch'
  docker compose --project-name "$project" --env-file /opt/octopus/octopus.env -f "$config" "$@"
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
  quiesce-old)
    # Legacy deployment path is explicit; preserve web, databases, volumes and files.
    cd /opt/octopus; set_workers false
    legacy_dc up -d --no-deps web
    [[ $(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' octopus-web | sed -n 's/^ENABLE_REVIEW_WORKERS=//p' | tail -1) == false ]] || die 'legacy worker did not quiesce'
    install -d -m 0700 receipts; printf 'workers=false\nlegacy_preserved=true\n' | install -m 0600 /dev/stdin receipts/old-quiesced
    ;;
  enable-worker)
    receipt private-proof; receipt old-quiesced; receipt public-edge-proof
    [[ $(env_value BETTER_AUTH_URL) == https://octopus.ed-finder.app ]] || die 'final BETTER_AUTH_URL required'
    [[ $(env_value NEXT_PUBLIC_APP_URL) == https://octopus.ed-finder.app ]] || die 'final NEXT_PUBLIC_APP_URL required'
    set_workers true; cd "$DIR"; dc up -d --no-deps web
    ;;
  disable-worker)
    set_workers false; cd "$DIR"; dc up -d --no-deps web
    ;;
  *) die 'unsupported runtime operation' ;;
esac
