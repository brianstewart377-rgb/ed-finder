#!/usr/bin/env bash
# Governed bootstrap for the single non-production Contabo V3 checkpoint.
# This script never checks out, pulls, or builds repository/application code.
set -Eeuo pipefail
umask 077

# Reserve stdout for the one sanitized JSON receipt consumed by the workflow.
exec 3>&1
exec 1>&2

MODE=""
BUNDLE_ROOT=""
OUTPUT_DIR=""
SOURCE_SHA=""
POSTGRES_IMAGE=""
GHCR_PROOF_IMAGE=""
GHCR_USERNAME_FILE=""
GHCR_TOKEN_FILE=""
FAILED=1
schema_candidate=""
OPERATOR_UID="${SUDO_UID:-$(id -u)}"
OPERATOR_GID="${SUDO_GID:-$(id -g)}"

usage() {
  printf '%s\n' 'usage: host-bootstrap.sh --mode check|provision --bundle-root PATH --output-dir PATH [--source-sha SHA] [--postgres-image IMAGE] [--ghcr-proof-image IMAGE] [--ghcr-username-file FILE --ghcr-token-file FILE]'
}

while (($#)); do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --bundle-root) BUNDLE_ROOT="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --source-sha) SOURCE_SHA="${2:-}"; shift 2 ;;
    --postgres-image) POSTGRES_IMAGE="${2:-}"; shift 2 ;;
    --ghcr-proof-image) GHCR_PROOF_IMAGE="${2:-}"; shift 2 ;;
    --ghcr-username-file) GHCR_USERNAME_FILE="${2:-}"; shift 2 ;;
    --ghcr-token-file) GHCR_TOKEN_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

if [[ "$MODE" != "check" && "$MODE" != "provision" ]]; then
  printf '%s\n' 'bootstrap stopped: mode must be check or provision' >&2
  exit 64
fi
if [[ -z "$SOURCE_SHA" && -f "$BUNDLE_ROOT/trusted-source-sha" ]]; then
  SOURCE_SHA="$(<"$BUNDLE_ROOT/trusted-source-sha")"
fi
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' 'bootstrap stopped: invalid or missing trusted source SHA' >&2; exit 64; }
if [[ -n "$GHCR_PROOF_IMAGE" && ! "$GHCR_PROOF_IMAGE" =~ ^ghcr\.io/brianstewart377-rgb/ed-finder/v3-(backend|web)@sha256:[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'bootstrap stopped: GHCR proof must be an allowlisted exact-digest application image' >&2
  exit 64
fi
if [[ -n "$POSTGRES_IMAGE" && "$POSTGRES_IMAGE" != "postgres:18" ]]; then
  printf '%s\n' 'bootstrap stopped: PostgreSQL image contract must be postgres:18' >&2
  exit 64
fi
if [[ -n "$GHCR_USERNAME_FILE" || -n "$GHCR_TOKEN_FILE" ]]; then
  [[ -n "$GHCR_USERNAME_FILE" && -n "$GHCR_TOKEN_FILE" ]] || {
    printf '%s\n' 'bootstrap stopped: both GHCR credential files are required' >&2
    exit 64
  }
fi

BUNDLE_ROOT="$(realpath -e -- "$BUNDLE_ROOT")"
[[ -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/compose.yml" \
   && -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/target-authority.json" \
   && -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/synthetic-checkpoint-fixture.sql" \
   && -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/bootstrap_receipt.py" \
   && -f "$BUNDLE_ROOT/scripts/apply_migrations.sh" \
   && -f "$BUNDLE_ROOT/scripts/release/v3_release_manifest.py" \
   && -f "$BUNDLE_ROOT/sql/migration-manifest.txt" ]] || {
  printf '%s\n' 'bootstrap stopped: bundle is incomplete' >&2
  exit 64
}
[[ "$OUTPUT_DIR" = /* ]] || OUTPUT_DIR="$PWD/$OUTPUT_DIR"
install -d -m 0700 -- "$OUTPUT_DIR"

failure_receipt() {
  local rc="$?"
  if ((FAILED)); then
    [[ -z "$schema_candidate" ]] || rm -f -- "$schema_candidate"
    rm -f -- "$OUTPUT_DIR/target-authority-candidate.json" \
      "$OUTPUT_DIR/schema-identity-receipt.json" \
      "$OUTPUT_DIR/schema-identity-receipt.json.sha256"
    if command -v systemctl >/dev/null 2>&1 && declare -F assert_runners >/dev/null; then
      assert_runners >/dev/null 2>&1 || printf '%s\n' 'bootstrap stopped: runner preservation re-check failed' >&2
    fi
    python3.14 - "$MODE" "$SOURCE_SHA" >"$OUTPUT_DIR/provisioning-receipt.json" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({
    "schema_version": "ed-finder/v3-live-checkpoint-provisioning-receipt/v1",
    "operation": "v3-live-checkpoint-host-bootstrap",
    "status": "stopped",
    "mode": sys.argv[1],
    "source_sha": sys.argv[2],
    "target": {"provider": "contabo", "classification": "live-checkpoint", "production": False, "hostname": "vmi3542235"},
    "failures": ["bounded_host_bootstrap_failed"],
    "secret_values_emitted": False,
    "production_mutations_performed": False,
    "production_data_accessed": False,
}, sort_keys=True))
PY
    chmod 0600 "$OUTPUT_DIR/provisioning-receipt.json" 2>/dev/null || true
    chown "$OPERATOR_UID:$OPERATOR_GID" "$OUTPUT_DIR" "$OUTPUT_DIR/provisioning-receipt.json" 2>/dev/null || true
    if [[ -s "$OUTPUT_DIR/provisioning-receipt.json" ]]; then
      cat "$OUTPUT_DIR/provisioning-receipt.json" >&3
    fi
  fi
  exit "$rc"
}
trap failure_receipt EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || { printf 'bootstrap stopped: required command unavailable: %s\n' "$1" >&2; return 1; }
}

EXPECTED_HOST="vmi3542235"
EXPECTED_FQDN="vmi3542235.contaboserver.net"
EXPECTED_ARCH="x86_64"
APP_NETWORK="edfinder-v3-checkpoint-app"
DATA_NETWORK="edfinder-v3-checkpoint-data"
APP_SUBNET="172.30.53.0/24"
APP_GATEWAY="172.30.53.1"
DATA_SUBNET="172.30.54.0/24"
DATA_GATEWAY="172.30.54.1"
POSTGRES_ADDRESS="172.30.54.2"
POSTGRES_HOST_PORT="55432"
POSTGRES_CONTAINER="edfinder-v3-checkpoint-postgres"
POSTGRES_IMAGE_DEFAULT="postgres:18"
POSTGRES_VOLUME="edfinder_v3_checkpoint_postgres_data"
DATABASE_NAME="edfinder_v3_checkpoint"
DATABASE_OWNER="edfinder_checkpoint_owner"
DATABASE_API_USER="edfinder_checkpoint_api"
STATE_ROOT="/var/lib/edfinder-v3-checkpoint"
CONFIG_ROOT="/etc/edfinder-v3-checkpoint"
API_ENV="$STATE_ROOT/api.env"
OWNER_ENV="$CONFIG_ROOT/postgres-owner.env"
API_PASSWORD_FILE="$CONFIG_ROOT/api-role-password"
DOCKER_CONFIG_DIR="$STATE_ROOT/docker-config"
RECEIPT_DIR="$STATE_ROOT/deployment-receipts"
PROVISION_RECEIPT_DIR="$STATE_ROOT/provisioning-receipts"
SCHEMA_DIR="$STATE_ROOT/schema"
SCHEMA_PATH="$SCHEMA_DIR/schema-identity.json"
DOCKER_CONTEXT="v3-live-checkpoint-local"
GHCR_AUTHORITY_PATH="$STATE_ROOT/ghcr-authority.json"
ORIGIN="http://127.0.0.1:18080"
NGINX_SITE="/etc/nginx/sites-available/edfinder-v3-checkpoint"
NGINX_ENABLED="/etc/nginx/sites-enabled/edfinder-v3-checkpoint"
RUNNERS=(
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service
)

[[ "$(hostname -s)" == "$EXPECTED_HOST" && "$(hostname -f)" == "$EXPECTED_FQDN" && "$(uname -m)" == "$EXPECTED_ARCH" ]] || {
  printf '%s\n' 'bootstrap stopped: target host identity mismatch' >&2
  exit 78
}
[[ "$(id -u)" == "0" ]] || { printf '%s\n' 'bootstrap stopped: bounded provisioning requires root' >&2; exit 78; }
[[ "$OPERATOR_UID" =~ ^[0-9]+$ && "$OPERATOR_GID" =~ ^[0-9]+$ ]] || { printf '%s\n' 'bootstrap stopped: operator identity is invalid' >&2; exit 78; }
((OPERATOR_UID > 0 && OPERATOR_GID > 0)) || { printf '%s\n' 'bootstrap stopped: invoking operator must be unprivileged' >&2; exit 78; }
require_command flock
exec 9>/run/lock/edfinder-v3-checkpoint-bootstrap.lock
flock -n 9 || { printf '%s\n' 'bootstrap stopped: provisioning lock is unavailable' >&2; exit 75; }

active_runners() {
  systemctl list-units --type=service --state=active --plain --no-legend 'actions.runner.*.service' \
    | awk '$1 ~ /^actions[.]runner[.].*[.]service$/ {print $1}' | sort
}
expected_runners() { printf '%s\n' "${RUNNERS[@]}" | sort; }
assert_runners() {
  diff -u <(expected_runners) <(active_runners) >/dev/null || {
    printf '%s\n' 'bootstrap stopped: exact three-runner active set is not preserved' >&2
    return 1
  }
  local runner
  for runner in "${RUNNERS[@]}"; do
    systemctl is-active --quiet "$runner" || return 1
  done
}
assert_runners

if [[ "$MODE" == "provision" ]]; then
  require_command apt-get
  # This provisioning authority is deliberately bounded to the audited Ubuntu
  # host and official Docker/PGDG package sources. It does not curl a shell.
  # shellcheck source=/dev/null
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" && "${VERSION_CODENAME:-}" =~ ^[a-z]+$ ]] || {
    printf '%s\n' 'bootstrap stopped: only a supported Ubuntu target is authorized' >&2
    exit 78
  }
  timeout 600 apt-get update
  DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y ca-certificates curl gnupg
  install -d -m 0755 /etc/apt/keyrings
  curl --fail --silent --show-error --location --max-time 60 \
    https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor --yes --output /etc/apt/keyrings/docker.gpg
  chmod 0644 /etc/apt/keyrings/docker.gpg
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "$VERSION_CODENAME" >/etc/apt/sources.list.d/docker.list
  curl --fail --silent --show-error --location --max-time 60 \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor --yes --output /etc/apt/keyrings/postgresql.gpg
  chmod 0644 /etc/apt/keyrings/postgresql.gpg
  printf 'deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "$VERSION_CODENAME" >/etc/apt/sources.list.d/pgdg.list
  timeout 600 apt-get update
  DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    postgresql-client-18 nginx openssl
  systemctl enable --now docker
  operator_name="$(getent passwd "$OPERATOR_UID" | cut -d: -f1)"
  [[ -n "$operator_name" ]] || { printf '%s\n' 'bootstrap stopped: invoking operator account is unavailable' >&2; exit 78; }
  if [[ "$OPERATOR_UID" != "0" ]]; then
    usermod -aG docker "$operator_name"
  fi
  assert_runners
fi

require_command docker
require_command psql
require_command python3.14
require_command systemctl
require_command ss
require_command findmnt
require_command cmp
python3.14 -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)' || {
  printf '%s\n' 'bootstrap stopped: exact CPython 3.14 is required' >&2
  exit 78
}
docker version >/dev/null
docker compose version >/dev/null
[[ "$(psql --version)" =~ ^psql\ \(PostgreSQL\)\ 18([.]|\ ) ]] || { printf '%s\n' 'bootstrap stopped: exact PostgreSQL 18 psql client is required' >&2; exit 78; }

ensure_network() {
  local name="$1" subnet="$2" gateway="$3"
  if ! docker network inspect "$name" >/dev/null 2>&1; then
    [[ "$MODE" == "provision" ]] || { printf 'bootstrap stopped: network missing: %s\n' "$name" >&2; return 1; }
    docker network create --driver bridge --subnet "$subnet" --gateway "$gateway" \
      --label com.edfinder.checkpoint=non-production --label com.edfinder.checkpoint.role="$name" "$name" >/dev/null
  fi
  local observed
  observed="$(docker network inspect "$name" --format '{{.Driver}}|{{.Scope}}|{{.Internal}}|{{.Attachable}}|{{.Ingress}}|{{.IPAM.Driver}}|{{range .IPAM.Config}}{{.Subnet}}|{{.Gateway}}{{end}}|{{index .Labels "com.edfinder.checkpoint"}}|{{index .Labels "com.edfinder.checkpoint.role"}}')"
  [[ "$observed" == "bridge|local|false|false|false|default|$subnet|$gateway|non-production|$name" ]] || {
    printf 'bootstrap stopped: network authority mismatch: %s\n' "$name" >&2
    return 1
  }
}
ensure_network "$APP_NETWORK" "$APP_SUBNET" "$APP_GATEWAY"
ensure_network "$DATA_NETWORK" "$DATA_SUBNET" "$DATA_GATEWAY"

network_peers() {
  docker network inspect "$1" --format '{{range .Containers}}{{println .Name}}{{end}}' | sort
}
while IFS= read -r peer; do
  [[ -z "$peer" || "$peer" == "edfinder-v3-checkpoint-api" || "$peer" == "edfinder-v3-checkpoint-web" ]] || {
    printf '%s\n' 'bootstrap stopped: application network has an unexpected attachment' >&2
    exit 78
  }
done < <(network_peers "$APP_NETWORK")
mapfile -t app_peers < <(network_peers "$APP_NETWORK")
if [[ "${#app_peers[@]}" -eq 1 || "${#app_peers[@]}" -gt 2 ]]; then
  printf '%s\n' 'bootstrap stopped: application network must be empty or contain exact api and web peers' >&2
  exit 78
fi
if [[ "${#app_peers[@]}" -eq 2 && "${app_peers[*]}" != "edfinder-v3-checkpoint-api edfinder-v3-checkpoint-web" ]]; then
  printf '%s\n' 'bootstrap stopped: application network peer set is not exact' >&2
  exit 78
fi

if [[ "$MODE" == "provision" ]]; then
  for directory in "$STATE_ROOT" "$DOCKER_CONFIG_DIR" "$RECEIPT_DIR" "$PROVISION_RECEIPT_DIR" "$SCHEMA_DIR"; do
    if [[ -e "$directory" || -L "$directory" ]]; then
      [[ -d "$directory" && ! -L "$directory" \
         && "$(stat -c '%u:%g:%a' "$directory")" == "$OPERATOR_UID:$OPERATOR_GID:700" ]] || {
        printf '%s\n' 'bootstrap stopped: unsafe existing checkpoint directory' >&2
        exit 78
      }
    else
      install -d -m 0700 -o "$OPERATOR_UID" -g "$OPERATOR_GID" "$directory"
    fi
  done
  if [[ -e "$CONFIG_ROOT" || -L "$CONFIG_ROOT" ]]; then
    [[ -d "$CONFIG_ROOT" && ! -L "$CONFIG_ROOT" \
       && "$(stat -c '%u:%g:%a' "$CONFIG_ROOT")" == "0:0:700" ]] || {
      printf '%s\n' 'bootstrap stopped: unsafe existing root config directory' >&2
      exit 78
    }
  else
    install -d -m 0700 -o root -g root "$CONFIG_ROOT"
  fi
else
  for directory in "$STATE_ROOT" "$DOCKER_CONFIG_DIR" "$RECEIPT_DIR" "$PROVISION_RECEIPT_DIR" "$SCHEMA_DIR"; do
    [[ -d "$directory" && ! -L "$directory" && "$(stat -c '%u:%g:%a' "$directory")" == "$OPERATOR_UID:$OPERATOR_GID:700" ]] || {
      printf 'bootstrap stopped: directory ownership/mode mismatch: %s\n' "$directory" >&2
      exit 78
    }
  done
  [[ -d "$CONFIG_ROOT" && ! -L "$CONFIG_ROOT" && "$(stat -c '%u:%g:%a' "$CONFIG_ROOT")" == "0:0:700" ]] || {
    printf '%s\n' 'bootstrap stopped: root config directory ownership/mode mismatch' >&2
    exit 78
  }
fi

if ! DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" >/dev/null 2>&1; then
  [[ "$MODE" == "provision" ]] || { printf '%s\n' 'bootstrap stopped: Docker context missing' >&2; exit 78; }
  DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context create "$DOCKER_CONTEXT" --docker host=unix:///var/run/docker.sock >/dev/null
fi
context_host="$(DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" --format '{{json .Endpoints.docker.Host}}')"
[[ "$context_host" == '"unix:///var/run/docker.sock"' ]] || { printf '%s\n' 'bootstrap stopped: Docker context is not local rootful daemon' >&2; exit 78; }
chmod 0700 "$DOCKER_CONFIG_DIR"
chown -R "$OPERATOR_UID:$OPERATOR_GID" "$DOCKER_CONFIG_DIR"

if [[ "$MODE" == "check" && -z "$GHCR_USERNAME_FILE" && -f "$GHCR_AUTHORITY_PATH" ]]; then
  GHCR_PROOF_MODE="$(python3.14 -c 'import json,sys; print(json.load(open(sys.argv[1]))["mode"])' "$GHCR_AUTHORITY_PATH")"
  if [[ -z "$GHCR_PROOF_IMAGE" ]]; then
    GHCR_PROOF_IMAGE="$(python3.14 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("image") or "")' "$GHCR_AUTHORITY_PATH")"
  fi
elif [[ -n "$GHCR_USERNAME_FILE" ]]; then
  for secret_file in "$GHCR_USERNAME_FILE" "$GHCR_TOKEN_FILE"; do
    [[ -f "$secret_file" && ! -L "$secret_file" && -s "$secret_file" ]] || { printf '%s\n' 'bootstrap stopped: GHCR credential file is unsafe' >&2; exit 78; }
    (( (8#$(stat -c '%a' "$secret_file") & 8#077) == 0 )) || { printf '%s\n' 'bootstrap stopped: GHCR credential file is too permissive' >&2; exit 78; }
  done
  GHCR_PROOF_MODE="secret-backed"
  if [[ "$MODE" == "provision" ]]; then
    ghcr_username="$(<"$GHCR_USERNAME_FILE")"
    [[ "$ghcr_username" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || { printf '%s\n' 'bootstrap stopped: GHCR username format is invalid' >&2; exit 78; }
    DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker --context "$DOCKER_CONTEXT" login ghcr.io --username "$ghcr_username" --password-stdin <"$GHCR_TOKEN_FILE" >/dev/null
    unset ghcr_username
    chown "$OPERATOR_UID:$OPERATOR_GID" "$DOCKER_CONFIG_DIR/config.json"
    chmod 0600 "$DOCKER_CONFIG_DIR/config.json"
    printf '%s\n' '{"mode":"secret-backed","image":null}' >"$GHCR_AUTHORITY_PATH"
    chmod 0600 "$GHCR_AUTHORITY_PATH"
    chown "$OPERATOR_UID:$OPERATOR_GID" "$GHCR_AUTHORITY_PATH"
  else
    [[ -s "$DOCKER_CONFIG_DIR/config.json" ]] || { printf '%s\n' 'bootstrap stopped: target-local GHCR config missing' >&2; exit 78; }
  fi
else
  GHCR_PROOF_MODE="anonymous"
fi
if [[ "$GHCR_PROOF_MODE" == "anonymous" && -z "$GHCR_PROOF_IMAGE" ]]; then
  printf '%s\n' 'bootstrap stopped: anonymous GHCR authority requires an allowlisted exact-digest proof image' >&2
  exit 78
fi
if [[ "$MODE" == "provision" && "$GHCR_PROOF_MODE" == "anonymous" ]]; then
  DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker --context "$DOCKER_CONTEXT" pull "$GHCR_PROOF_IMAGE" >/dev/null
  printf '{"mode":"anonymous","image":"%s"}\n' "$GHCR_PROOF_IMAGE" >"$GHCR_AUTHORITY_PATH"
  chmod 0600 "$GHCR_AUTHORITY_PATH"
  chown "$OPERATOR_UID:$OPERATOR_GID" "$GHCR_AUTHORITY_PATH"
fi
[[ -f "$GHCR_AUTHORITY_PATH" && ! -L "$GHCR_AUTHORITY_PATH" \
   && "$(stat -c '%u:%g:%a' "$GHCR_AUTHORITY_PATH")" == "$OPERATOR_UID:$OPERATOR_GID:600" ]] || {
  printf '%s\n' 'bootstrap stopped: GHCR authority receipt ownership/mode mismatch' >&2
  exit 78
}
if [[ "$GHCR_PROOF_MODE" == "anonymous" ]]; then
  docker image inspect "$GHCR_PROOF_IMAGE" >/dev/null
  docker image inspect "$GHCR_PROOF_IMAGE" --format '{{json .RepoDigests}}' | grep -Fq "\"$GHCR_PROOF_IMAGE\"" || {
    printf '%s\n' 'bootstrap stopped: exact GHCR digest is not locally proven' >&2
    exit 78
  }
else
  [[ -f "$DOCKER_CONFIG_DIR/config.json" && ! -L "$DOCKER_CONFIG_DIR/config.json" && -s "$DOCKER_CONFIG_DIR/config.json" \
     && "$(stat -c '%u:%g:%a' "$DOCKER_CONFIG_DIR/config.json")" == "$OPERATOR_UID:$OPERATOR_GID:600" ]] || {
    printf '%s\n' 'bootstrap stopped: secret-backed Docker config is missing or unsafe' >&2
    exit 78
  }
fi

if docker container inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
  existing_postgres_image="$(docker container inspect "$POSTGRES_CONTAINER" --format '{{.Config.Image}}')"
  [[ "$existing_postgres_image" == "$POSTGRES_IMAGE_DEFAULT" ]] || {
    printf '%s\n' 'bootstrap stopped: existing PostgreSQL container image authority is invalid' >&2
    exit 78
  }
  if [[ -n "$POSTGRES_IMAGE" && "$POSTGRES_IMAGE" != "$existing_postgres_image" ]]; then
    printf '%s\n' 'bootstrap stopped: requested PostgreSQL digest differs from persistent data source' >&2
    exit 78
  fi
  POSTGRES_IMAGE="$existing_postgres_image"
  [[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Name}}{{end}}{{end}}')" == "$POSTGRES_VOLUME" \
     && "$(docker volume inspect "$POSTGRES_VOLUME" --format '{{index .Labels "com.edfinder.checkpoint"}}|{{index .Labels "com.edfinder.checkpoint.role"}}')" == "non-production|postgres-data" ]] || {
    printf '%s\n' 'bootstrap stopped: PostgreSQL persistent-volume ownership mismatch' >&2
    exit 78
  }
else
  [[ "$MODE" == "provision" ]] || { printf '%s\n' 'bootstrap stopped: PostgreSQL data source is missing' >&2; exit 78; }
  POSTGRES_IMAGE="${POSTGRES_IMAGE:-$POSTGRES_IMAGE_DEFAULT}"
  if docker volume inspect "$POSTGRES_VOLUME" >/dev/null 2>&1; then
    printf '%s\n' 'bootstrap stopped: orphaned PostgreSQL volume exists without its owned container' >&2
    exit 78
  fi
  [[ ! -e "$OWNER_ENV" && ! -e "$API_ENV" && ! -e "$API_PASSWORD_FILE" ]] || {
    printf '%s\n' 'bootstrap stopped: orphaned database credentials exist without the data source' >&2
    exit 78
  }
  owner_password="$(openssl rand -hex 32)"
  api_password="$(openssl rand -hex 32)"
  admin_token="$(openssl rand -hex 32)"
  {
    printf 'POSTGRES_DB=%s\n' "$DATABASE_NAME"
    printf 'POSTGRES_USER=%s\n' "$DATABASE_OWNER"
    printf 'POSTGRES_PASSWORD=%s\n' "$owner_password"
  } >"$OWNER_ENV"
  printf '%s\n' "$api_password" >"$API_PASSWORD_FILE"
  {
    printf 'DATABASE_URL=postgresql://%s:%s@%s:%s/%s\n' "$DATABASE_API_USER" "$api_password" "$APP_GATEWAY" "$POSTGRES_HOST_PORT" "$DATABASE_NAME"
    printf 'CORS_ORIGINS=http://%s\n' "$EXPECTED_FQDN"
    printf 'FRONTIER_REDIRECT_URI=http://%s/api/auth/frontier/callback\n' "$EXPECTED_FQDN"
    printf 'AUTH_COOKIE_SECURE=false\n'
    printf 'ADMIN_TOKEN=%s\n' "$admin_token"
    printf 'LOG_LEVEL=INFO\n'
    printf 'EXPOSE_ERROR_DETAIL=false\n'
  } >"$API_ENV"
  chmod 0600 "$OWNER_ENV" "$API_ENV" "$API_PASSWORD_FILE"
  chown root:root "$OWNER_ENV" "$API_PASSWORD_FILE"
  chown "$OPERATOR_UID:$OPERATOR_GID" "$API_ENV"

  docker pull "$POSTGRES_IMAGE" >/dev/null
  docker volume create --label com.edfinder.checkpoint=non-production \
    --label com.edfinder.checkpoint.role=postgres-data "$POSTGRES_VOLUME" >/dev/null
  docker container create --name "$POSTGRES_CONTAINER" \
    --label com.edfinder.checkpoint=non-production \
    --label com.edfinder.checkpoint.role=postgres-data-source \
    --restart unless-stopped --cpus 1.0 --memory 1536m --pids-limit 256 \
    --network "$DATA_NETWORK" --ip "$POSTGRES_ADDRESS" \
    --publish "$APP_GATEWAY:$POSTGRES_HOST_PORT:5432" \
    --env-file "$OWNER_ENV" --volume "$POSTGRES_VOLUME:/var/lib/postgresql" \
    "$POSTGRES_IMAGE" >/dev/null
  docker container start "$POSTGRES_CONTAINER" >/dev/null
  unset owner_password api_password admin_token
fi

[[ -f "$OWNER_ENV" && ! -L "$OWNER_ENV" && "$(stat -c '%u:%a' "$OWNER_ENV")" == "0:600" \
   && -f "$API_ENV" && ! -L "$API_ENV" && "$(stat -c '%u:%g:%a' "$API_ENV")" == "$OPERATOR_UID:$OPERATOR_GID:600" \
   && -f "$API_PASSWORD_FILE" && ! -L "$API_PASSWORD_FILE" && "$(stat -c '%u:%a' "$API_PASSWORD_FILE")" == "0:600" ]] || {
  printf '%s\n' 'bootstrap stopped: target-local credential ownership/mode mismatch' >&2
  exit 78
}
[[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{index .Config.Labels "com.edfinder.checkpoint"}}|{{index .Config.Labels "com.edfinder.checkpoint.role"}}')" == "non-production|postgres-data-source" ]] || {
  printf '%s\n' 'bootstrap stopped: PostgreSQL container ownership label mismatch' >&2
  exit 78
}
[[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{json .HostConfig.PortBindings}}')" == '{"5432/tcp":[{"HostIp":"172.30.53.1","HostPort":"55432"}]}' ]] || {
  printf '%s\n' 'bootstrap stopped: PostgreSQL port publication is not exact' >&2
  exit 78
}
[[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{.HostConfig.RestartPolicy.Name}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.PidsLimit}}')" == 'unless-stopped|1000000000|1610612736|256' ]] || {
  printf '%s\n' 'bootstrap stopped: PostgreSQL resource/restart policy is not exact' >&2
  exit 78
}
[[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{.HostConfig.NetworkMode}}|{{(index .NetworkSettings.Networks "edfinder-v3-checkpoint-data").IPAddress}}')" == "$DATA_NETWORK|$POSTGRES_ADDRESS" ]] || {
  printf '%s\n' 'bootstrap stopped: PostgreSQL network isolation mismatch' >&2
  exit 78
}
[[ "$(network_peers "$DATA_NETWORK")" == "$POSTGRES_CONTAINER" ]] || {
  printf '%s\n' 'bootstrap stopped: database network attachments are not exactly the owned PostgreSQL container' >&2
  exit 78
}
if [[ "$(docker container inspect "$POSTGRES_CONTAINER" --format '{{.State.Running}}')" != "true" ]]; then
  [[ "$MODE" == "provision" ]] || { printf '%s\n' 'bootstrap stopped: PostgreSQL is not running' >&2; exit 78; }
  docker container start "$POSTGRES_CONTAINER" >/dev/null
fi

ready=0
for _attempt in $(seq 1 60); do
  if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$DATABASE_OWNER" -d "$DATABASE_NAME" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
((ready)) || { printf '%s\n' 'bootstrap stopped: PostgreSQL readiness timed out' >&2; exit 78; }
postgres_version="$(docker exec "$POSTGRES_CONTAINER" psql -XAt -U "$DATABASE_OWNER" -d "$DATABASE_NAME" -c 'SHOW server_version')"
[[ "$postgres_version" =~ ^18([.]|$) ]] || { printf '%s\n' 'bootstrap stopped: PostgreSQL 18 is required' >&2; exit 78; }

owner_password="$(sed -n 's/^POSTGRES_PASSWORD=//p' "$OWNER_ENV")"
api_password="$(<"$API_PASSWORD_FILE")"
[[ "$owner_password" =~ ^[0-9a-f]{64}$ && "$api_password" =~ ^[0-9a-f]{64}$ ]] || {
  printf '%s\n' 'bootstrap stopped: persisted database credential format is invalid' >&2
  exit 78
}
OWNER_DATABASE_URL="postgresql://$DATABASE_OWNER@$APP_GATEWAY:$POSTGRES_HOST_PORT/$DATABASE_NAME"

fixture_present="no"
if [[ "$(docker exec "$POSTGRES_CONTAINER" psql -XAt -U "$DATABASE_OWNER" -d "$DATABASE_NAME" -c \
  "SELECT CASE WHEN to_regclass('public.checkpoint_fixture_metadata') IS NULL THEN 'no' ELSE 'yes' END")" == "yes" ]]; then
  fixture_present="$(docker exec "$POSTGRES_CONTAINER" psql -XAt -U "$DATABASE_OWNER" -d "$DATABASE_NAME" -c \
    "SELECT CASE WHEN EXISTS (SELECT 1 FROM checkpoint_fixture_metadata WHERE fixture_id='checkpoint-synthetic-v1' AND classification='synthetic_non_production' AND source='repository_owned') THEN 'yes' ELSE 'no' END")"
fi
if [[ "$MODE" == "provision" && "$fixture_present" == "no" ]]; then
  ((${#app_peers[@]} == 0)) || {
    printf '%s\n' 'bootstrap stopped: initial schema/fixture creation requires application absence' >&2
    exit 78
  }
  PGPASSWORD="$owner_password" DATABASE_URL="$OWNER_DATABASE_URL" ENV_FILE=/dev/null MIGRATION_STATEMENT_TIMEOUT=10min \
    bash "$BUNDLE_ROOT/scripts/apply_migrations.sh" --include-manual
  PGPASSWORD="$owner_password" psql -X --no-password --set ON_ERROR_STOP=1 \
    -h "$APP_GATEWAY" -p "$POSTGRES_HOST_PORT" -U "$DATABASE_OWNER" -d "$DATABASE_NAME" \
    -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/synthetic-checkpoint-fixture.sql" >/dev/null
fi
if [[ "$MODE" == "provision" ]]; then
  # Keep role creation outside the fixture guard so an interrupted first run
  # can safely resume after the fixture transaction commits.
  PGPASSWORD="$owner_password" psql -X --no-password --set ON_ERROR_STOP=1 \
    -h "$APP_GATEWAY" -p "$POSTGRES_HOST_PORT" -U "$DATABASE_OWNER" -d "$DATABASE_NAME" >/dev/null <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DATABASE_API_USER') THEN
    CREATE ROLE $DATABASE_API_USER LOGIN PASSWORD '$api_password';
  END IF;
END \$\$;
ALTER ROLE $DATABASE_API_USER LOGIN PASSWORD '$api_password';
ALTER ROLE $DATABASE_API_USER SET default_transaction_read_only = on;
REVOKE ALL ON DATABASE $DATABASE_NAME FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE $DATABASE_NAME TO $DATABASE_API_USER;
GRANT USAGE ON SCHEMA public TO $DATABASE_API_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $DATABASE_API_USER;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $DATABASE_API_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $DATABASE_OWNER IN SCHEMA public GRANT SELECT ON TABLES TO $DATABASE_API_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $DATABASE_OWNER IN SCHEMA public GRANT SELECT ON SEQUENCES TO $DATABASE_API_USER;
SQL
fi
unset owner_password api_password OWNER_DATABASE_URL

fixture_identity="$(docker exec "$POSTGRES_CONTAINER" psql -XAt -U "$DATABASE_OWNER" -d "$DATABASE_NAME" -c \
  "SELECT fixture_id || '|' || (SELECT count(*) FROM systems) || '|' || (SELECT count(*) FROM bodies) || '|' || (SELECT count(*) FROM stations) FROM checkpoint_fixture_metadata WHERE fixture_id='checkpoint-synthetic-v1' AND classification='synthetic_non_production' AND source='repository_owned'")"
[[ "$fixture_identity" == 'checkpoint-synthetic-v1|4|9|1' ]] || {
  printf '%s\n' 'bootstrap stopped: synthetic fixture scope is missing or has drifted' >&2
  exit 78
}

write_nginx_site() {
  cat >"$1" <<'NGINX'
# NON-PRODUCTION ED-Finder V3 checkpoint only.
server {
    listen 80;
    listen [::]:80;
    server_name vmi3542235.contaboserver.net;

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
NGINX
}
if [[ "$MODE" == "provision" ]]; then
  install -m 0644 /dev/null "$NGINX_SITE"
  write_nginx_site "$NGINX_SITE"
  ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
fi
[[ -f "$NGINX_SITE" && ! -L "$NGINX_SITE" && "$(readlink -f "$NGINX_ENABLED")" == "$NGINX_SITE" ]] || {
  printf '%s\n' 'bootstrap stopped: non-production edge route is missing' >&2
  exit 78
}
expected_nginx_site="$(mktemp)"
write_nginx_site "$expected_nginx_site"
cmp --silent "$expected_nginx_site" "$NGINX_SITE" || {
  rm -f -- "$expected_nginx_site"
  printf '%s\n' 'bootstrap stopped: non-production edge route has drifted' >&2
  exit 78
}
rm -f -- "$expected_nginx_site"
nginx -t
systemctl is-active --quiet nginx
getent ahostsv4 "$EXPECTED_FQDN" >/dev/null || { printf '%s\n' 'bootstrap stopped: checkpoint FQDN does not resolve' >&2; exit 78; }

captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
refresh_schema=()
schema_verify_path="$SCHEMA_PATH"
if [[ "$MODE" == "provision" ]]; then
  schema_candidate="$(mktemp "$SCHEMA_DIR/.schema-identity.candidate.XXXXXX")"
  refresh_schema=(--refresh-schema --schema-write-path "$schema_candidate")
  schema_verify_path="$schema_candidate"
else
  [[ -f "$SCHEMA_PATH" && ! -L "$SCHEMA_PATH" ]] || { printf '%s\n' 'bootstrap stopped: schema receipt missing' >&2; exit 78; }
  captured_at="$(python3.14 -c 'import json,sys; print(json.load(open(sys.argv[1]))["captured_at"])' "$SCHEMA_PATH")"
fi
facts_file="$(mktemp)"
postgres_image_digest="$(docker image inspect "$POSTGRES_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}' | awk '/(^|\/)postgres@sha256:/{print; exit}')"
[[ "$postgres_image_digest" =~ postgres@sha256:[0-9a-f]{64}$ ]] || { printf '%s\n' 'bootstrap stopped: PostgreSQL repository digest is unavailable' >&2; exit 78; }
export BOOTSTRAP_MODE="$MODE" BOOTSTRAP_CAPTURED_AT="$captured_at" BOOTSTRAP_POSTGRES_VERSION="$postgres_version"
export BOOTSTRAP_OPERATOR_UID="$OPERATOR_UID"
export BOOTSTRAP_POSTGRES_IMAGE="$POSTGRES_IMAGE" BOOTSTRAP_POSTGRES_IMAGE_DIGEST="$postgres_image_digest"
export BOOTSTRAP_GHCR_PROOF_IMAGE="$GHCR_PROOF_IMAGE" BOOTSTRAP_GHCR_PROOF_MODE="$GHCR_PROOF_MODE"
python3.14 - "$facts_file" <<'PY'
import json, os, platform, shutil, socket, subprocess, sys
from pathlib import Path

def output(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()

meminfo = {
    line.split(":", 1)[0]: int(line.split()[1])
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:"))
}
filesystem = os.statvfs("/")
cpu_model = "unknown"
for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
    if line.startswith("model name"):
        cpu_model = line.split(":", 1)[1].strip()
        break

facts = {
    "mode": os.environ["BOOTSTRAP_MODE"],
    "hostname": socket.gethostname().split(".")[0],
    "fqdn": socket.getfqdn(),
    "architecture": platform.machine(),
    "captured_at": os.environ["BOOTSTRAP_CAPTURED_AT"],
    "docker_version": output("docker", "version", "--format", "{{.Server.Version}}"),
    "compose_version": output("docker", "compose", "version", "--short"),
    "psql_version": output("psql", "--version"),
    "postgres_version": os.environ["BOOTSTRAP_POSTGRES_VERSION"],
    "postgres_image": os.environ["BOOTSTRAP_POSTGRES_IMAGE"],
    "postgres_image_digest": os.environ["BOOTSTRAP_POSTGRES_IMAGE_DIGEST"],
    "postgres_image_id": output("docker", "image", "inspect", "--format", "{{.Id}}", os.environ["BOOTSTRAP_POSTGRES_IMAGE"]),
    "ghcr_proof_image": os.environ["BOOTSTRAP_GHCR_PROOF_IMAGE"],
    "ghcr_proof_mode": os.environ["BOOTSTRAP_GHCR_PROOF_MODE"],
    "runner_services": sorted(line.split()[0] for line in output("systemctl", "list-units", "--type=service", "--state=active", "--plain", "--no-legend", "actions.runner.*.service").splitlines() if line.strip()),
    "alternative_container_clis_present": sorted(name for name in ("incus", "lxc", "nerdctl", "podman") if shutil.which(name)),
    "docker_networks": sorted(output("docker", "network", "ls", "--format", "{{.Name}}").splitlines()),
    "docker_volumes": sorted(output("docker", "volume", "ls", "--format", "{{.Name}}").splitlines()),
    "container_names": sorted(output("docker", "container", "ls", "-a", "--format", "{{.Names}}").splitlines()),
    "tcp_listeners": sorted({line.split()[3] for line in output("ss", "-H", "-ltn").splitlines() if len(line.split()) >= 4}),
    "observed_capacity": {
        "logical_cpus": os.cpu_count() or 0,
        "cpu_model": cpu_model,
        "memory_total_kib": meminfo["MemTotal"],
        "memory_available_kib": meminfo["MemAvailable"],
        "swap_total_kib": meminfo["SwapTotal"],
        "root_bytes": filesystem.f_frsize * filesystem.f_blocks,
        "root_available_bytes": filesystem.f_frsize * filesystem.f_bavail,
        "root_filesystem": output("findmnt", "--noheadings", "--output", "FSTYPE", "/"),
    },
    "api_env_file": "/var/lib/edfinder-v3-checkpoint/api.env",
    "owner_uid": int(os.environ["BOOTSTRAP_OPERATOR_UID"]),
    "receipt_directory": "/var/lib/edfinder-v3-checkpoint/deployment-receipts",
    "docker_config_directory": "/var/lib/edfinder-v3-checkpoint/docker-config",
    "docker_context": "v3-live-checkpoint-local",
    "origin_bind": "http://127.0.0.1:18080",
    "edge_route_authority": "non-production HTTP vhost vmi3542235.contaboserver.net proxies only to http://127.0.0.1:18080",
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(facts, handle, sort_keys=True)
PY

python3.14 "$BUNDLE_ROOT/deploy/v3-live-checkpoint/bootstrap_receipt.py" \
  --bundle-root "$BUNDLE_ROOT" --facts "$facts_file" --output-dir "$OUTPUT_DIR" \
  --source-sha "$SOURCE_SHA" --schema-path "$SCHEMA_PATH" "${refresh_schema[@]}"
chown "$OPERATOR_UID:$OPERATOR_GID" "$OUTPUT_DIR" "$OUTPUT_DIR"/*
if [[ "$MODE" == "check" ]]; then
  [[ "$(stat -c '%u:%g:%a' "$SCHEMA_PATH")" == "$OPERATOR_UID:$OPERATOR_GID:600" ]] || {
    printf '%s\n' 'bootstrap stopped: schema receipt ownership/mode mismatch' >&2
    exit 78
  }
fi

# Reuse the canonical deployment verifier's read-only schema/identity query.
PYTHONDONTWRITEBYTECODE=1 python3.14 - "$BUNDLE_ROOT" "$API_ENV" "$schema_verify_path" <<'PY'
import importlib.util, json, sys
from pathlib import Path
root, env_path, schema_path = map(Path, sys.argv[1:])
path = root / "scripts/operator/v3_checkpoint_deploy.py"
spec = importlib.util.spec_from_file_location("checkpoint_deploy", path)
if spec is None or spec.loader is None:
    raise SystemExit(78)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
schema = json.loads(schema_path.read_text(encoding="utf-8"))
module.verify_database_schema(env_path, schema, module.run_command)
PY

if [[ "$MODE" == "provision" ]]; then
  chown "$OPERATOR_UID:$OPERATOR_GID" "$schema_candidate"
  chmod 0600 "$schema_candidate"
  mv -f -- "$schema_candidate" "$SCHEMA_PATH"
  schema_candidate=""
fi

assert_runners
stamp="${captured_at//[:]/-}"
if [[ "$MODE" == "provision" ]]; then
  install -m 0600 -o "$OPERATOR_UID" -g "$OPERATOR_GID" "$OUTPUT_DIR/provisioning-receipt.json" "$PROVISION_RECEIPT_DIR/$stamp-$SOURCE_SHA.json"
fi
rm -f -- "$facts_file"
FAILED=0
trap - EXIT
cat "$OUTPUT_DIR/provisioning-receipt.json" >&3
