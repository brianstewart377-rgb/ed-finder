#!/usr/bin/env bash
set -euo pipefail

readonly VERSION="1.0.122"
readonly PROJECT="octopus-selfhost"
readonly PROD_CONFIRM="PREPARE FRESH OCTOPUS ON ED-FINDER-PROD"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
readonly PACKAGE_DIR="${OCTOPUS_PACKAGE_DIR:-$REPO_ROOT/deploy/octopus-selfhost}"

die() { printf 'error: %s\n' "$*" >&2; exit 64; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  printf '%s\n' \
    'Usage:' \
    '  octopus_selfhost.sh preflight [--host-root PATH] [--expected-hostname NAME]' \
    '  octopus_selfhost.sh prepare --target-root PATH --admin-email EMAIL [--confirm PHRASE]' \
    '  octopus_selfhost.sh validate --deployment-dir PATH'
}

preflight() {
  local host_root=/ expected=ed-finder-prod
  while (($#)); do
    case "$1" in
      --host-root) (($# >= 2)) || die 'missing --host-root value'; host_root=$2; shift 2 ;;
      --expected-hostname) (($# >= 2)) || die 'missing --expected-hostname value'; expected=$2; shift 2 ;;
      *) die "unknown preflight argument: $1" ;;
    esac
  done
  local actual
  actual=$(hostname -s 2>/dev/null || printf unknown)
  printf 'expected_hostname: %s\nactual_hostname: %s\nhostname_match: %s\n' \
    "$expected" "$actual" "$([[ $actual == "$expected" ]] && printf true || printf false)"
  printf 'kernel_architecture: '; uname -srm 2>/dev/null || printf 'unavailable\n'
  printf 'cpu_count: '; (getconf _NPROCESSORS_ONLN 2>/dev/null || printf unavailable)
  printf 'memory: '; (free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || printf unavailable)
  printf 'root_disk: '; (df -hP "$host_root" 2>/dev/null | awk 'NR==2 {print $2 " total, " $4 " available"}' || printf unavailable)
  if have docker; then
    printf 'docker_version: '; docker version --format '{{.Server.Version}}' 2>/dev/null || printf 'unavailable\n'
    printf 'compose_version: '; docker compose version --short 2>/dev/null || printf 'unavailable\n'
    printf 'docker_networks:\n'; docker network ls --format '  {{.Name}}' 2>/dev/null || printf '  unavailable\n'
    printf 'public_edge_containers (name|networks|bind_mount_sources):\n'
    while IFS= read -r container; do
      [[ -n $container ]] || continue
      docker inspect --format '{{.Name}}|{{range $k, $_ := .NetworkSettings.Networks}}{{$k}} {{end}}|{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}} {{end}}{{end}}' "$container" 2>/dev/null || true
    done < <(docker ps --filter publish=80 --filter publish=443 --format '{{.Names}}' 2>/dev/null | sort -u)
  else
    printf 'docker_version: unavailable\ncompose_version: unavailable\ndocker_networks: unavailable\npublic_edge_containers: unavailable\n'
  fi
  printf 'listeners:\n'
  for port in 43300 43332 43333 43334 80 443; do
    if have ss && ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .; then
      printf '  %s: occupied\n' "$port"
    else
      printf '  %s: free_or_unknown\n' "$port"
    fi
  done
  if [[ -e "${host_root%/}/opt/octopus" ]]; then printf '/opt/octopus: exists\n'; else printf '/opt/octopus: absent\n'; fi
  printf 'read_only: true\n'
}

valid_email() { [[ $1 =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; }
hex_secret() { openssl rand -hex "$1"; }

prepare() {
  local target_root= admin_email= confirm=
  while (($#)); do
    case "$1" in
      --target-root) (($# >= 2)) || die 'missing --target-root value'; target_root=$2; shift 2 ;;
      --admin-email) (($# >= 2)) || die 'missing --admin-email value'; admin_email=$2; shift 2 ;;
      --confirm) (($# >= 2)) || die 'missing --confirm value'; confirm=$2; shift 2 ;;
      *) die "unknown prepare argument: $1" ;;
    esac
  done
  [[ -n $target_root && $target_root == /* ]] || die '--target-root must be an absolute path'
  valid_email "$admin_email" || die '--admin-email must be supplied and look like an email address'
  have openssl || die 'openssl is required'
  local destination="${target_root%/}/opt/octopus"
  if [[ $destination == /opt/octopus ]]; then
    [[ ${EUID:-$(id -u)} -eq 0 ]] || die 'production /opt/octopus preparation requires root'
    [[ $confirm == "$PROD_CONFIRM" ]] || die "production preparation requires confirmation phrase: $PROD_CONFIRM"
    [[ $(hostname -s 2>/dev/null) == ed-finder-prod ]] || die 'production preparation requires hostname ed-finder-prod'
  fi
  [[ ! -e $destination ]] || die "destination already exists; refusing to alter content: $destination"
  local parent staging
  parent=$(dirname -- "$destination")
  mkdir -p -- "$parent"
  umask 077
  staging=$(mktemp -d "$parent/.octopus.prepare.XXXXXX")
  trap 'rm -rf -- "$staging"' EXIT
  install -m 0600 "$PACKAGE_DIR/compose.yaml" "$staging/compose.yaml"
  : > "$staging/octopus.env"
  chmod 0600 "$staging/octopus.env"
  {
    printf 'OCTOPUS_POSTGRES_PASSWORD=%s\n' "$(hex_secret 32)"
    printf 'BETTER_AUTH_SECRET=%s\n' "$(hex_secret 32)"
    printf 'OCTOPUS_DATA_KEY=%s\n' "$(hex_secret 32)"
    printf 'OCTOPUS_ADMIN_EMAIL=%s\n' "$admin_email"
    printf 'OCTOPUS_ADMIN_PASSWORD=%s\n' "$(hex_secret 24)"
    printf '%s\n' \
      'BETTER_AUTH_URL=http://127.0.0.1:43300' \
      'NEXT_PUBLIC_APP_URL=http://127.0.0.1:43300' \
      'OCTOPUS_EMBED_PROVIDER=openai' \
      'OCTOPUS_EMBED_MODEL=text-embedding-3-large' \
      'ENABLE_REVIEW_WORKERS=false' \
      'ENABLE_INTERNAL_CLI=false'
  } >> "$staging/octopus.env"
  printf 'managed_by=ed-finder-octopus-preparation\nversion=%s\ncompose_project=%s\n' "$VERSION" "$PROJECT" > "$staging/.managed"
  chmod 0600 "$staging/.managed"
  mv -- "$staging" "$destination"
  trap - EXIT
  printf 'prepared: %s\nversion: %s\ncontainers_started: false\nmigrations_applied: false\n' "$destination" "$VERSION"
}

validate() {
  local deployment_dir=
  while (($#)); do
    case "$1" in
      --deployment-dir) (($# >= 2)) || die 'missing --deployment-dir value'; deployment_dir=$2; shift 2 ;;
      *) die "unknown validate argument: $1" ;;
    esac
  done
  [[ -f $deployment_dir/compose.yaml && -f $deployment_dir/octopus.env ]] || die 'deployment directory is incomplete'
  local compose=$deployment_dir/compose.yaml
  grep -q 'octopus-selfhost:1.0.122' "$compose" || die 'application image is not pinned to 1.0.122'
  ! grep -Eq '(^|:)latest([[:space:]]|$)' "$compose" || die 'latest tag is forbidden'
  grep -q '127.0.0.1:43300:3000' "$compose" || die 'web listener is not loopback-only'
  ! grep -Eq '^[[:space:]]*-[[:space:]]*"?([^"[:space:]]*:)?(43332|43333|43334):' "$compose" || die 'database/vector host ports are forbidden'
  grep -q 'octopus-selfhost-backend' "$compose" || die 'dedicated backend network is missing'
  grep -q 'octopus-selfhost-egress' "$compose" || die 'dedicated web egress network is missing'
  grep -q 'internal: true' "$compose" || die 'internal backend network is missing'
  grep -q 'octopus-selfhost-postgres-1-0-122' "$compose" || die 'dedicated PostgreSQL volume is missing'
  grep -q 'octopus-selfhost-qdrant-1-0-122' "$compose" || die 'dedicated Qdrant volume is missing'
  if have docker && docker compose version >/dev/null 2>&1; then
    (cd -- "$deployment_dir" && docker compose --project-name "$PROJECT" --env-file octopus.env -f compose.yaml config --quiet)
    printf 'compose_config: passed\n'
  else
    printf 'compose_config: skipped (Docker Compose unavailable)\n'
  fi
  printf 'static_validation: passed\n'
}

(($#)) || { usage; exit 64; }
command_name=$1; shift
case "$command_name" in
  preflight) preflight "$@" ;;
  prepare) prepare "$@" ;;
  validate) validate "$@" ;;
  -h|--help|help) usage ;;
  *) usage >&2; die "unknown command: $command_name" ;;
esac
