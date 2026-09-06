#!/usr/bin/env bash
#
# Idempotent, source-free provisioning for the NON-PRODUCTION Contabo V3
# live-checkpoint. This script owns infrastructure only; it never deploys the
# api/web application and never changes deployment target authority.
set -Eeuo pipefail
umask 077

TARGET_HOSTNAME="vmi3542235"
TARGET_FQDN="vmi3542235.contaboserver.net"
TARGET_ARCH="x86_64"
PROJECT="edfinder-v3-checkpoint"
APP_NETWORK="edfinder-v3-checkpoint-app"
APP_SUBNET="172.30.54.0/24"
APP_GATEWAY="172.30.54.1"
ORIGIN_PORT="18080"
DB_NAME="edfinder_v3_checkpoint"
DB_OWNER="edfinder_checkpoint_db"
DB_APP_ROLE="edfinder_checkpoint_app"
DB_AUTHORITY="contabo-vmi3542235-native-postgresql18-preview-v1"
DOCKER_CONTEXT="edfinder-v3-checkpoint"
STATE_DIR="/var/lib/edfinder-v3-checkpoint-provisioner"
OWNERSHIP_FILE="$STATE_DIR/ownership-v1"
CONFIG_DIR="/etc/ed-finder/v3-checkpoint"
API_ENV_FILE="$CONFIG_DIR/api.env"
RUNTIME_DIR="/var/lib/edfinder-v3-checkpoint"
RECEIPT_DIR="$RUNTIME_DIR/receipts"
DOCKER_CONFIG_DIR="$RUNTIME_DIR/docker-config"
SCHEMA_RECEIPT="$RUNTIME_DIR/schema-identity.json"
NGINX_SITE="/etc/nginx/sites-available/edfinder-v3-checkpoint"
NGINX_ENABLED="/etc/nginx/sites-enabled/edfinder-v3-checkpoint"
RUNNER_SERVICES=(
  "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service"
  "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service"
  "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service"
)

OPERATOR_USER=""
OUTPUT_DIR=""
BACKEND_IMAGE=""
WEB_IMAGE=""
BUNDLE_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
RECEIPT_WRITTEN=0
RUNNERS_BEFORE=false
RUNNERS_AFTER=false
RUNNER_STATE_BEFORE=""
RUNNER_CONTINUITY=false
MUTATION_STARTED=false
GHCR_STATUS="explicit_secret_backed_authority_required"
GHCR_AUTHORITY=""
DB_BUNDLE_DIR=""

usage() {
  printf '%s\n' "usage: $0 --operator-user USER --output-dir DIR [--backend-image GHCR_DIGEST --web-image GHCR_DIGEST]" >&2
  exit 64
}

while (($#)); do
  case "$1" in
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --backend-image) BACKEND_IMAGE="${2:-}"; shift 2 ;;
    --web-image) WEB_IMAGE="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ $EUID -eq 0 ]] || { printf '%s\n' "provisioner requires non-interactive root authority" >&2; exit 77; }
[[ "$OPERATOR_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || usage
[[ -n "$OUTPUT_DIR" && "$OUTPUT_DIR" == /tmp/* ]] || usage
[[ -d "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || usage
operator_uid="$(id -u "$OPERATOR_USER" 2>/dev/null)" || usage
[[ "$(stat -c %u "$OUTPUT_DIR")" == "$operator_uid" ]] || usage
[[ "$(stat -c %a "$OUTPUT_DIR")" == "700" ]] || usage

expected_backend_prefix="ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:"
expected_web_prefix="ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:"
if [[ -n "$BACKEND_IMAGE" || -n "$WEB_IMAGE" ]]; then
  [[ "$BACKEND_IMAGE" =~ ^${expected_backend_prefix}[0-9a-f]{64}$ ]] || usage
  [[ "$WEB_IMAGE" =~ ^${expected_web_prefix}[0-9a-f]{64}$ ]] || usage
fi

receipt_path="$OUTPUT_DIR/provisioning-receipt.json"
candidate_path="$OUTPUT_DIR/target-authority-candidate.json"
private_log="$OUTPUT_DIR/.provisioning.log"
install -m 600 /dev/null "$private_log"

json_array_lines() {
  local first=1 value
  printf '['
  for value in "$@"; do
    ((first)) || printf ','
    printf '"%s"' "$value"
    first=0
  done
  printf ']'
}

write_stopped_artifacts() {
  local failure="${1:-unexpected_provisioning_failure}"
  [[ "$failure" =~ ^[a-z0-9_]+$ ]] || failure="unexpected_provisioning_failure"
  local changed=false
  $MUTATION_STARTED && changed=true
  cat >"$receipt_path.tmp" <<JSON
{"schema_version":"ed-finder/v3-live-checkpoint-provisioning-receipt/v1","operation":"provision-infrastructure","status":"stopped","target":{"provider":"contabo","classification":"live-checkpoint","production":false,"hostname":"$TARGET_HOSTNAME","fqdn":"$TARGET_FQDN","architecture":"$TARGET_ARCH"},"failures":["$failure"],"mutation_started":$changed,"runner_services_verified_before":$RUNNERS_BEFORE,"runner_services_verified_after":$RUNNERS_AFTER,"runner_service_continuity_preserved":$RUNNER_CONTINUITY,"credentials_emitted":false,"production_access_performed":false,"production_data_copied":false,"dns_changes_performed":false,"application_deploy_performed":false}
JSON
  local compose_sha=""
  if [[ -f "$BUNDLE_ROOT/deploy/v3-live-checkpoint/compose.yml" ]]; then
    compose_sha="$(sha256sum "$BUNDLE_ROOT/deploy/v3-live-checkpoint/compose.yml" 2>/dev/null | awk '{print $1}')"
  fi
  cat >"$candidate_path.tmp" <<JSON
{"schema_version":"ed-finder/v3-live-checkpoint-target-authority/v1","status":"stopped","target":{"provider":"contabo","classification":"live-checkpoint","production":false,"hostname":"$TARGET_HOSTNAME","fqdn":"$TARGET_FQDN","architecture":"$TARGET_ARCH"},"observed_at":"$(date -u +%Y-%m-%d)","observed_capacity":{},"observed_runtime":{"container_runtime":null,"compose":null,"alternative_container_clis_present":[],"container_names":[],"docker_networks":[],"docker_volumes":[],"tcp_listeners":[],"runner_services":$(json_array_lines "${RUNNER_SERVICES[@]}"),"checkpoint_directories_found_under_opt_srv_var_lib":[]},"application_contract":{"compose_project":"$PROJECT","compose_sha256":"$compose_sha","services":{"api":{"container_name":"edfinder-v3-checkpoint-api","cpus":"1.50","memory":"1536m","pids":256},"web":{"container_name":"edfinder-v3-checkpoint-web","cpus":"0.50","memory":"512m","pids":128}},"network":"$APP_NETWORK","network_lifecycle":"externally-provisioned-persistent","named_volumes":[]},"external_authority":{"api_env_file":null,"api_env_owner_uid":null,"api_env_mode":null,"database_source_authority":null,"schema_identity_receipt":null,"schema_identity_receipt_sha256":null,"origin_bind":null,"edge_route_authority":null,"receipt_directory":null,"receipt_owner_uid":null,"receipt_mode":null,"ghcr_pull_authority":null,"docker_config_directory":null,"docker_config_owner_uid":null,"docker_config_mode":null,"docker_context":null},"blockers":["$failure"]}
JSON
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$receipt_path.tmp" "$receipt_path"
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$candidate_path.tmp" "$candidate_path"
  rm -f -- "$receipt_path.tmp" "$candidate_path.tmp"
  RECEIPT_WRITTEN=1
}

stop() {
  local code="$1"
  printf 'Provisioning stopped: %s\n' "$code" >&2
  write_stopped_artifacts "$code"
  exit 78
}

on_exit() {
  local rc=$?
  rm -f -- "$private_log"
  if [[ "$DB_BUNDLE_DIR" == /tmp/edfinder-v3-db-bundle.* ]]; then
    rm -rf -- "$DB_BUNDLE_DIR"
  fi
  if ((rc != 0)) && ((RECEIPT_WRITTEN == 0)); then
    set +e
    if exact_runners_active; then
      RUNNERS_AFTER=true
      [[ -n "$RUNNER_STATE_BEFORE" && "$(runner_state_snapshot)" == "$RUNNER_STATE_BEFORE" ]] && RUNNER_CONTINUITY=true
    fi
    write_stopped_artifacts unexpected_provisioning_failure
  fi
}
trap on_exit EXIT

exact_runners_active() {
  local expected observed
  expected="$(printf '%s\n' "${RUNNER_SERVICES[@]}" | LC_ALL=C sort)"
  observed="$(systemctl list-units --type=service --state=active --plain --no-legend --no-pager 'actions.runner.*.service' 2>/dev/null | awk '{print $1}' | LC_ALL=C sort)"
  [[ "$observed" == "$expected" ]] || return 1
  local service
  for service in "${RUNNER_SERVICES[@]}"; do
    systemctl is-active --quiet "$service" || return 1
  done
}

runner_state_snapshot() {
  local service
  for service in "${RUNNER_SERVICES[@]}"; do
    printf '%s:' "$service"
    systemctl show "$service" --property=MainPID --property=ActiveEnterTimestampMonotonic --value 2>/dev/null | paste -sd: -
  done
}

run_logged() {
  timeout --signal=TERM --kill-after=30s "$1" "${@:2}" >>"$private_log" 2>&1
}

# Nothing above this line mutates the target except the private output log in
# the caller-owned temporary directory.
[[ "$(hostname -s 2>/dev/null)" == "$TARGET_HOSTNAME" ]] || stop hostname_mismatch
[[ "$(hostname -f 2>/dev/null)" == "$TARGET_FQDN" ]] || stop fqdn_mismatch
[[ "$(uname -m)" == "$TARGET_ARCH" ]] || stop architecture_mismatch
[[ "$(dpkg --print-architecture 2>/dev/null)" == "amd64" ]] || stop package_architecture_mismatch
[[ -r /etc/os-release ]] || stop unsupported_operating_system
# shellcheck source=/dev/null
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || stop unsupported_operating_system
[[ "${VERSION_CODENAME:-}" =~ ^(jammy|noble|resolute)$ ]] || stop unsupported_operating_system
command -v systemctl >/dev/null 2>&1 || stop systemd_unavailable
command -v timeout >/dev/null 2>&1 || stop timeout_unavailable
command -v flock >/dev/null 2>&1 || stop flock_unavailable
exact_runners_active || stop runner_service_set_mismatch
RUNNERS_BEFORE=true
RUNNER_STATE_BEFORE="$(runner_state_snapshot)" || stop runner_service_state_unavailable
[[ "$(nproc)" -ge 8 ]] || stop host_capacity_below_recorded_target
[[ "$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)" -ge 24608576 ]] || stop host_capacity_below_recorded_target

if [[ -e "$OWNERSHIP_FILE" ]]; then
  [[ -f "$OWNERSHIP_FILE" && ! -L "$OWNERSHIP_FILE" ]] || stop unsafe_ownership_marker
  [[ "$(stat -c '%U:%G:%a' "$OWNERSHIP_FILE")" == "root:root:600" ]] || stop unsafe_ownership_marker
  [[ "$(<"$OWNERSHIP_FILE")" == "ed-finder-v3-checkpoint-provisioner-v1" ]] || stop foreign_ownership_marker
else
  [[ ! -e "$STATE_DIR" && ! -e "$CONFIG_DIR" && ! -e "$RUNTIME_DIR" ]] || stop unowned_checkpoint_paths_present
  [[ ! -d /etc/nginx || -z "$(find /etc/nginx -mindepth 1 -print -quit 2>/dev/null)" ]] || stop unowned_checkpoint_edge_present
  dpkg-query -W -f='${db:Status-Status}' nginx 2>/dev/null | grep -qx installed && stop unowned_http_edge_package_present
  [[ ! -d /etc/postgresql || -z "$(find /etc/postgresql -mindepth 1 -print -quit 2>/dev/null)" ]] || stop unowned_postgresql_cluster_present
  [[ ! -d /var/lib/postgresql || -z "$(find /var/lib/postgresql -mindepth 1 -print -quit 2>/dev/null)" ]] || stop unowned_postgresql_data_present
  id "$DB_OWNER" >/dev/null 2>&1 && stop unowned_checkpoint_database_owner_present
  command -v docker >/dev/null 2>&1 && stop unowned_container_runtime_present
  for conflicting_package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    dpkg-query -W -f='${db:Status-Status}' "$conflicting_package" 2>/dev/null | grep -qx installed && stop unowned_docker_conflicting_package_present
  done
  [[ ! -d /var/lib/docker || -z "$(find /var/lib/docker -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]] || stop unowned_container_state_present
  ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)5432$' && stop unowned_postgresql_listener_present
  ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)80$' && stop unowned_http_listener_present
  command -v podman >/dev/null 2>&1 && stop unowned_alternative_container_cli_present
  command -v nerdctl >/dev/null 2>&1 && stop unowned_alternative_container_cli_present
fi

MUTATION_STARTED=true
install -d -o root -g root -m 700 "$STATE_DIR"
if [[ ! -e "$OWNERSHIP_FILE" ]]; then
  printf '%s\n' 'ed-finder-v3-checkpoint-provisioner-v1' >"$OWNERSHIP_FILE.tmp"
  install -o root -g root -m 600 "$OWNERSHIP_FILE.tmp" "$OWNERSHIP_FILE"
  rm -f -- "$OWNERSHIP_FILE.tmp"
fi
install -d -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 700 "$CONFIG_DIR" "$RUNTIME_DIR" "$RECEIPT_DIR" "$DOCKER_CONFIG_DIR"
deployment_lock="$RECEIPT_DIR/deploy.lock"
if [[ -e "$deployment_lock" ]]; then
  [[ -f "$deployment_lock" && ! -L "$deployment_lock" ]] || stop unsafe_deployment_lock
  [[ "$(stat -c '%u:%a' "$deployment_lock")" == "$operator_uid:600" ]] || stop unsafe_deployment_lock
else
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 /dev/null "$deployment_lock"
fi
exec 9<>"$deployment_lock"
flock -n 9 || stop checkpoint_operation_already_running

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
run_logged 900 apt-get update
run_logged 900 apt-get install -y --no-install-recommends ca-certificates curl gnupg jq openssl

install -d -m 755 /etc/apt/keyrings /usr/share/postgresql-common/pgdg
run_logged 120 curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg --output /etc/apt/keyrings/docker.asc
run_logged 120 curl --fail --silent --show-error --location https://www.postgresql.org/media/keys/ACCC4CF8.asc --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
docker_fingerprint="$(gpg --show-keys --with-colons /etc/apt/keyrings/docker.asc 2>/dev/null | awk -F: '$1=="fpr" {print $10; exit}')"
pgdg_fingerprint="$(gpg --show-keys --with-colons /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc 2>/dev/null | awk -F: '$1=="fpr" {print $10; exit}')"
[[ "$docker_fingerprint" == "9DC858229FC7DD38854AE2D88D81803C0EBFCD88" ]] || stop docker_repository_key_mismatch
[[ "$pgdg_fingerprint" == "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8" ]] || stop postgresql_repository_key_mismatch
chmod 644 /etc/apt/keyrings/docker.asc /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc

cat >/etc/apt/sources.list.d/docker.sources <<SOURCES
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $VERSION_CODENAME
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
cat >/etc/apt/sources.list.d/pgdg.sources <<SOURCES
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: ${VERSION_CODENAME}-pgdg
Components: main
Architectures: amd64
Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
SOURCES
chmod 644 /etc/apt/sources.list.d/docker.sources /etc/apt/sources.list.d/pgdg.sources

# Prevent the package's default nginx site from becoming briefly reachable.
systemctl mask nginx.service >>"$private_log" 2>&1 || true
run_logged 900 apt-get update
run_logged 1200 apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin postgresql-18 postgresql-client-18 postgresql-contrib-18 nginx
systemctl unmask nginx.service >>"$private_log" 2>&1 || stop nginx_unmask_failed

command -v docker >/dev/null 2>&1 || stop docker_engine_unavailable
command -v psql >/dev/null 2>&1 || stop psql_unavailable
[[ "$(psql --version | awk '{print $3}' | cut -d. -f1)" == "18" ]] || stop postgresql_client_not_18
systemctl enable --now docker.service >>"$private_log" 2>&1 || stop docker_service_unavailable
systemctl enable --now postgresql.service >>"$private_log" 2>&1 || stop postgresql_service_unavailable
docker compose version >>"$private_log" 2>&1 || stop docker_compose_unavailable

[[ -f "$BUNDLE_ROOT/artifacts/migration-set.json" && ! -L "$BUNDLE_ROOT/artifacts/migration-set.json" ]] || stop migration_identity_missing
migration_identity="$(jq -er '.identity | select(test("^sha256:[0-9a-f]{64}$"))' "$BUNDLE_ROOT/artifacts/migration-set.json")" || stop migration_identity_invalid
migration_entries="$(jq -ce '.entries' "$BUNDLE_ROOT/artifacts/migration-set.json")" || stop migration_entries_invalid
manifest_hash="$(jq -er '.manifest_sha256 | select(test("^[0-9a-f]{64}$"))' "$BUNDLE_ROOT/artifacts/migration-set.json")" || stop migration_manifest_identity_invalid
[[ "$(sha256sum "$BUNDLE_ROOT/sql/migration-manifest.txt" | awk '{print $1}')" == "$manifest_hash" ]] || stop migration_manifest_checksum_mismatch
while IFS=$'\t' read -r relative expected_hash; do
  [[ "$relative" =~ ^sql/[0-9]{3}_[a-z0-9_]+\.sql$ && "$expected_hash" =~ ^[0-9a-f]{64}$ ]] || stop migration_entry_invalid
  [[ -f "$BUNDLE_ROOT/$relative" && ! -L "$BUNDLE_ROOT/$relative" ]] || stop migration_file_missing
  [[ "$(sha256sum "$BUNDLE_ROOT/$relative" | awk '{print $1}')" == "$expected_hash" ]] || stop migration_file_checksum_mismatch
done < <(jq -r '.entries[] | [.path,.sha256] | @tsv' "$BUNDLE_ROOT/artifacts/migration-set.json")

# The database owner cannot traverse the SSH user's mode-0700 extraction
# directory. Give it a distinct secret-free temporary bundle containing only
# the canonical database bootstrap inputs, and always remove that bundle.
DB_BUNDLE_DIR="$(mktemp -d /tmp/edfinder-v3-db-bundle.XXXXXX)"
chmod 755 "$DB_BUNDLE_DIR"
install -d -o root -g root -m 755 "$DB_BUNDLE_DIR/scripts" "$DB_BUNDLE_DIR/sql"
install -o root -g root -m 755 "$BUNDLE_ROOT/scripts/apply_migrations.sh" "$BUNDLE_ROOT/scripts/seed_check.sh" "$DB_BUNDLE_DIR/scripts/"
install -o root -g root -m 644 "$BUNDLE_ROOT/sql/"*.sql "$BUNDLE_ROOT/sql/migration-manifest.txt" "$DB_BUNDLE_DIR/sql/"

getent group docker >/dev/null || stop docker_group_unavailable
usermod -aG docker "$OPERATOR_USER"

network_json="$(docker network inspect "$APP_NETWORK" 2>/dev/null || true)"
if [[ -z "$network_json" ]]; then
  run_logged 120 docker network create --driver bridge --subnet "$APP_SUBNET" --gateway "$APP_GATEWAY" "$APP_NETWORK"
  network_json="$(docker network inspect "$APP_NETWORK" 2>/dev/null)" || stop app_network_unavailable
fi
jq -e --arg name "$APP_NETWORK" --arg subnet "$APP_SUBNET" --arg gateway "$APP_GATEWAY" '
  length == 1 and .[0].Name == $name and .[0].Driver == "bridge" and
  .[0].Scope == "local" and .[0].Ingress == false and
  .[0].IPAM.Config == [{"Subnet":$subnet,"Gateway":$gateway}] and
  ((.[0].Containers // {}) | to_entries | all(.value.Name == "edfinder-v3-checkpoint-api" or .value.Name == "edfinder-v3-checkpoint-web"))
' <<<"$network_json" >/dev/null || stop app_network_topology_mismatch
mapfile -t docker_networks < <(docker network ls --format '{{.Name}}' | LC_ALL=C sort)
[[ "$(printf '%s\n' "${docker_networks[@]}")" == $'bridge\nedfinder-v3-checkpoint-app\nhost\nnone' ]] || stop unexpected_docker_network_present
mapfile -t container_names < <(docker ps --all --format '{{.Names}}' | LC_ALL=C sort)
for container_name in "${container_names[@]}"; do
  [[ "$container_name" == "edfinder-v3-checkpoint-api" || "$container_name" == "edfinder-v3-checkpoint-web" ]] || stop unexpected_container_present
done
[[ -z "$(docker volume ls --quiet)" ]] || stop unexpected_docker_volume_present
command -v podman >/dev/null 2>&1 && stop unexpected_alternative_container_cli_present
command -v nerdctl >/dev/null 2>&1 && stop unexpected_alternative_container_cli_present

if [[ ! -s "$DOCKER_CONFIG_DIR/config.json" ]]; then
  printf '%s\n' '{}' >"$DOCKER_CONFIG_DIR/config.json.tmp"
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$DOCKER_CONFIG_DIR/config.json.tmp" "$DOCKER_CONFIG_DIR/config.json"
  rm -f -- "$DOCKER_CONFIG_DIR/config.json.tmp"
fi

run_as_operator() {
  runuser -u "$OPERATOR_USER" -- env HOME="$(getent passwd "$OPERATOR_USER" | cut -d: -f6)" DOCKER_CONFIG="$DOCKER_CONFIG_DIR" "$@"
}
if ! run_as_operator docker context inspect "$DOCKER_CONTEXT" >>"$private_log" 2>&1; then
  run_as_operator docker context create "$DOCKER_CONTEXT" --docker "host=unix:///var/run/docker.sock" >>"$private_log" 2>&1 || stop docker_context_create_failed
fi
context_endpoint="$(run_as_operator docker context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}' 2>/dev/null)" || stop docker_context_unavailable
[[ "$context_endpoint" == "unix:///var/run/docker.sock" ]] || stop docker_context_not_local_rootful
chown -R "$operator_uid:$(id -g "$OPERATOR_USER")" "$DOCKER_CONFIG_DIR"
find "$DOCKER_CONFIG_DIR" -type d -exec chmod 700 {} +
find "$DOCKER_CONFIG_DIR" -type f -exec chmod 600 {} +

if ! id "$DB_OWNER" >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_DIR/db-owner" --create-home --shell /usr/sbin/nologin "$DB_OWNER"
fi
runuser -u postgres -- psql -X --no-password --quiet --set=ON_ERROR_STOP=1 postgres >>"$private_log" 2>&1 <<SQL
SELECT format('CREATE ROLE %I LOGIN', '$DB_OWNER') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_OWNER') \gexec
ALTER ROLE "$DB_OWNER" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD NULL;
SELECT format('CREATE ROLE %I LOGIN', '$DB_APP_ROLE') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_APP_ROLE') \gexec
ALTER ROLE "$DB_APP_ROLE" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SQL
role_memberships="$(runuser -u postgres -- psql -X --no-password --tuples-only --no-align postgres --command "SELECT count(*) FROM pg_auth_members WHERE roleid IN ((SELECT oid FROM pg_roles WHERE rolname='$DB_OWNER'),(SELECT oid FROM pg_roles WHERE rolname='$DB_APP_ROLE')) OR member IN ((SELECT oid FROM pg_roles WHERE rolname='$DB_OWNER'),(SELECT oid FROM pg_roles WHERE rolname='$DB_APP_ROLE'))")"
[[ "$role_memberships" == "0" ]] || stop checkpoint_database_role_membership_present
if ! runuser -u postgres -- psql -X --no-password --tuples-only --no-align postgres --command "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -qx 1; then
  run_logged 120 runuser -u postgres -- createdb --owner "$DB_OWNER" "$DB_NAME"
fi
db_owner_observed="$(runuser -u postgres -- psql -X --no-password --tuples-only --no-align postgres --command "SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname='$DB_NAME'")"
[[ "$db_owner_observed" == "$DB_OWNER" ]] || stop database_owner_mismatch

if [[ ! -s "$API_ENV_FILE" ]]; then
  db_password="$(openssl rand -hex 32)"
  admin_token="$(openssl rand -hex 32)"
  umask 077
  cat >"$API_ENV_FILE.tmp" <<ENV
DATABASE_URL=postgresql://$DB_APP_ROLE:$db_password@$APP_GATEWAY:5432/$DB_NAME
DATABASE_READONLY_URL=postgresql://$DB_APP_ROLE:$db_password@$APP_GATEWAY:5432/$DB_NAME
ADMIN_TOKEN=$admin_token
CORS_ORIGINS=http://$TARGET_FQDN
FRONTIER_REDIRECT_URI=http://$TARGET_FQDN/api/auth/frontier/callback
AUTH_COOKIE_SECURE=false
ENV
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$API_ENV_FILE.tmp" "$API_ENV_FILE"
  rm -f -- "$API_ENV_FILE.tmp"
else
  [[ -f "$API_ENV_FILE" && ! -L "$API_ENV_FILE" ]] || stop unsafe_api_env_file
  [[ "$(stat -c '%u:%a' "$API_ENV_FILE")" == "$operator_uid:600" ]] || stop unsafe_api_env_file
fi
[[ "$(wc -l <"$API_ENV_FILE")" -eq 6 ]] || stop invalid_api_env_file_shape
grep -Eq "^DATABASE_READONLY_URL=postgresql://$DB_APP_ROLE:[0-9a-f]{64}@$APP_GATEWAY:5432/$DB_NAME$" "$API_ENV_FILE" || stop invalid_api_env_file_shape
grep -Eq '^ADMIN_TOKEN=[0-9a-f]{64}$' "$API_ENV_FILE" || stop invalid_api_env_file_shape
grep -Fqx "CORS_ORIGINS=http://$TARGET_FQDN" "$API_ENV_FILE" || stop invalid_api_env_file_shape
grep -Fqx "FRONTIER_REDIRECT_URI=http://$TARGET_FQDN/api/auth/frontier/callback" "$API_ENV_FILE" || stop invalid_api_env_file_shape
grep -Fqx 'AUTH_COOKIE_SECURE=false' "$API_ENV_FILE" || stop invalid_api_env_file_shape
db_password="$(sed -n "s#^DATABASE_URL=postgresql://$DB_APP_ROLE:\([^@]*\)@$APP_GATEWAY:5432/$DB_NAME\$#\1#p" "$API_ENV_FILE")"
[[ "$db_password" =~ ^[0-9a-f]{64}$ ]] || stop invalid_api_database_credential
grep -Fqx "DATABASE_READONLY_URL=postgresql://$DB_APP_ROLE:$db_password@$APP_GATEWAY:5432/$DB_NAME" "$API_ENV_FILE" || stop api_database_credentials_disagree
runuser -u postgres -- psql -X --no-password --quiet --set=ON_ERROR_STOP=1 postgres >>"$private_log" 2>&1 <<SQL
SET password_encryption = 'scram-sha-256';
ALTER ROLE "$DB_APP_ROLE" PASSWORD '$db_password';
ALTER ROLE "$DB_APP_ROLE" IN DATABASE "$DB_NAME" SET default_transaction_read_only = on;
SQL
unset admin_token

postgres_conf="/etc/postgresql/18/main/conf.d/edfinder-v3-checkpoint.conf"
install -d -o postgres -g postgres -m 750 "$(dirname "$postgres_conf")"
cat >"$postgres_conf.tmp" <<CONF
# Managed by the bounded ED-Finder non-production checkpoint provisioner.
listen_addresses = '127.0.0.1,$APP_GATEWAY'
password_encryption = 'scram-sha-256'
CONF
install -o postgres -g postgres -m 640 "$postgres_conf.tmp" "$postgres_conf"
rm -f -- "$postgres_conf.tmp"
hba_file="/etc/postgresql/18/main/pg_hba.conf"
if ! grep -Fqx "host $DB_NAME $DB_APP_ROLE $APP_SUBNET scram-sha-256" "$hba_file"; then
  printf '\n# ED-Finder V3 checkpoint app network only\nhost %s %s %s scram-sha-256\n' "$DB_NAME" "$DB_APP_ROLE" "$APP_SUBNET" >>"$hba_file"
fi
systemctl restart postgresql.service >>"$private_log" 2>&1 || stop postgresql_restart_failed
runuser -u postgres -- psql -X --no-password --tuples-only --no-align --command 'SHOW server_version_num' "$DB_NAME" | grep -Eq '^18[0-9]{4}$' || stop postgresql_server_not_18

seed_marker="$STATE_DIR/seed-complete-v1"
if [[ ! -e "$seed_marker" ]]; then
  # Canonical seed_check invokes apply_migrations.sh --include-manual, applies
  # sql/seed_preview.sql, and runs its established preview invariants.
  run_logged 3600 runuser -u "$DB_OWNER" -- env DATABASE_URL="postgresql:///$DB_NAME?host=/var/run/postgresql" ENV_FILE="$STATE_DIR/no-env-file" SQL_DIR="$DB_BUNDLE_DIR/sql" bash "$DB_BUNDLE_DIR/scripts/seed_check.sh"
  install -o root -g root -m 600 /dev/null "$seed_marker"
fi

runuser -u postgres -- psql -X --no-password --quiet --set=ON_ERROR_STOP=1 "$DB_NAME" >>"$private_log" 2>&1 <<SQL
REVOKE ALL ON DATABASE "$DB_NAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE "$DB_NAME" TO "$DB_APP_ROLE";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO "$DB_APP_ROLE";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "$DB_APP_ROLE";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO "$DB_APP_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "$DB_OWNER" IN SCHEMA public GRANT SELECT ON TABLES TO "$DB_APP_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "$DB_OWNER" IN SCHEMA public GRANT SELECT ON SEQUENCES TO "$DB_APP_ROLE";
SQL

seed_counts="$(PGPASSWORD="$db_password" PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=10000' psql -X --no-password --tuples-only --no-align --quiet -h "$APP_GATEWAY" -U "$DB_APP_ROLE" -d "$DB_NAME" --command "SELECT json_build_object('systems',(SELECT count(*) FROM systems),'ratings',(SELECT count(*) FROM ratings),'bodies',(SELECT count(*) FROM bodies),'stations',(SELECT count(*) FROM stations),'galaxy_regions',(SELECT count(*) FROM galaxy_regions),'unrated_systems',(SELECT count(*) FROM systems s LEFT JOIN ratings r ON r.system_id64=s.id64 WHERE r.system_id64 IS NULL),'transaction_read_only',current_setting('transaction_read_only'))")" || stop seed_acceptance_read_failed
jq -e '.systems >= 40 and .ratings >= 40 and .bodies >= 10 and .stations >= 5 and .galaxy_regions >= 42 and .unrated_systems == 0 and .transaction_read_only == "on"' <<<"$seed_counts" >/dev/null || stop seed_acceptance_failed

observed_db="$(PGPASSWORD="$db_password" PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=10000' psql -X --no-password --tuples-only --no-align --quiet -h "$APP_GATEWAY" -U "$DB_APP_ROLE" -d "$DB_NAME" --command "SELECT json_build_object('database_name',current_database(),'server_address',inet_server_addr()::text,'server_port',inet_server_port(),'transaction_read_only',current_setting('transaction_read_only'),'migrations',COALESCE((SELECT json_agg(json_build_object('filename',filename,'checksum_sha256',checksum_sha256) ORDER BY filename) FROM schema_migrations),'[]'::json))")" || stop schema_readonly_proof_failed
expected_ledger="$(jq -cS '[.entries[] | {filename:(.path | sub("^sql/";"")),checksum_sha256:.sha256}] | sort_by(.filename)' "$BUNDLE_ROOT/artifacts/migration-set.json")"
observed_ledger="$(jq -cS '.migrations | sort_by(.filename)' <<<"$observed_db")" || stop schema_readonly_proof_invalid
jq -e --arg db "$DB_NAME" --arg address "$APP_GATEWAY" '.database_name == $db and .server_address == $address and .server_port == 5432 and .transaction_read_only == "on"' <<<"$observed_db" >/dev/null || stop schema_database_identity_mismatch
[[ "$observed_ledger" == "$expected_ledger" ]] || stop schema_migration_ledger_mismatch

captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n --arg authority "$DB_AUTHORITY" --arg database "$DB_NAME" --arg address "$APP_GATEWAY" --arg identity "$migration_identity" --arg captured "$captured_at" --argjson entries "$migration_entries" '{schema_version:"ed-finder/v3-live-checkpoint-schema-identity/v2",database_source_authority:$authority,database_identity:{database_name:$database,server_address:$address,server_port:5432},migration_set_identity:$identity,migration_set_entries:$entries,captured_at:$captured}' >"$SCHEMA_RECEIPT.tmp"
[[ ! -e "$SCHEMA_RECEIPT" || ( -f "$SCHEMA_RECEIPT" && ! -L "$SCHEMA_RECEIPT" ) ]] || stop unsafe_schema_receipt
chown "$operator_uid:$(id -g "$OPERATOR_USER")" "$SCHEMA_RECEIPT.tmp"
chmod 600 "$SCHEMA_RECEIPT.tmp"
mv -fT "$SCHEMA_RECEIPT.tmp" "$SCHEMA_RECEIPT"
schema_receipt_sha="$(sha256sum "$SCHEMA_RECEIPT" | awk '{print $1}')"

cat >"$NGINX_SITE.tmp" <<NGINX
# HTTP-only, provider-FQDN-only NON-PRODUCTION checkpoint edge. No DNS or TLS.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 404;
}
server {
    listen 80;
    listen [::]:80;
    server_name $TARGET_FQDN;
    add_header X-EDFinder-Checkpoint-Edge v1 always;
    location / {
        proxy_pass http://127.0.0.1:$ORIGIN_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }
}
NGINX
install -o root -g root -m 644 "$NGINX_SITE.tmp" "$NGINX_SITE"
rm -f -- "$NGINX_SITE.tmp" /etc/nginx/sites-enabled/default
ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
find /etc/nginx/sites-enabled -mindepth 1 -maxdepth 1 ! -name 'edfinder-v3-checkpoint' -print -quit | grep -q . && stop unexpected_nginx_site_enabled
find /etc/nginx/conf.d -type f -print -quit 2>/dev/null | grep -q . && stop unexpected_nginx_conf_enabled
run_logged 120 nginx -t
systemctl enable --now nginx.service >>"$private_log" 2>&1 || stop nginx_service_unavailable
systemctl reload nginx.service >>"$private_log" 2>&1 || stop nginx_reload_failed
curl --silent --output /dev/null --max-time 5 --header 'Host: rejected.invalid' --write-out '%{http_code}' http://127.0.0.1/ | grep -qx 404 || stop edge_default_route_not_rejected
edge_headers="$(curl --silent --show-error --dump-header - --output /dev/null --max-time 5 --header "Host: $TARGET_FQDN" http://127.0.0.1/ 2>/dev/null)" || stop checkpoint_edge_route_unavailable
grep -Eiq '^X-EDFinder-Checkpoint-Edge: v1\r?$' <<<"$edge_headers" || stop checkpoint_edge_route_not_selected

if [[ -n "$BACKEND_IMAGE" ]]; then
  probe_config="$(mktemp -d "$OUTPUT_DIR/.anonymous-docker.XXXXXX")"
  chmod 700 "$probe_config"
  printf '%s\n' '{}' >"$probe_config/config.json"
  chmod 600 "$probe_config/config.json"
  if runuser -u "$OPERATOR_USER" -- env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/nonexistent DOCKER_CONFIG="$probe_config" docker --host unix:///var/run/docker.sock pull "$BACKEND_IMAGE" >>"$private_log" 2>&1 &&
     runuser -u "$OPERATOR_USER" -- env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/nonexistent DOCKER_CONFIG="$probe_config" docker --host unix:///var/run/docker.sock pull "$WEB_IMAGE" >>"$private_log" 2>&1; then
    GHCR_STATUS="anonymous_public_digest_pull_proven"
    GHCR_AUTHORITY="anonymous-public-digest-pull:${BACKEND_IMAGE},${WEB_IMAGE}"
  fi
  rm -rf -- "$probe_config"
fi

exact_runners_active || stop runner_service_set_changed
[[ "$(runner_state_snapshot)" == "$RUNNER_STATE_BEFORE" ]] || stop runner_service_continuity_changed
RUNNERS_AFTER=true
RUNNER_CONTINUITY=true
docker_version="$(docker version --format '{{.Server.Version}}' 2>/dev/null)" || stop docker_version_unavailable
compose_version="$(docker compose version --short 2>/dev/null)" || stop compose_version_unavailable
postgres_version="$(runuser -u postgres -- psql -X --no-password --tuples-only --no-align --command 'SHOW server_version' "$DB_NAME")" || stop postgresql_version_unavailable
compose_sha="$(sha256sum "$BUNDLE_ROOT/deploy/v3-live-checkpoint/compose.yml" | awk '{print $1}')"
cpu_count="$(nproc)"
memory_total="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
memory_available="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
read -r root_bytes root_available < <(df -B1 --output=size,avail / | awk 'NR==2 {print $1,$2}')
cpu_model="$(awk -F: '/model name/ {sub(/^[[:space:]]+/,"",$2); print $2; exit}' /proc/cpuinfo | tr -cd '[:alnum:] ._()+/-' | cut -c1-120)"
swap_total="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
root_filesystem="$(findmnt --noheadings --output FSTYPE / | tr -cd '[:alnum:]_.-')"
mapfile -t tcp_listeners < <(ss -H -ltn | awk '{print $4}' | LC_ALL=C sort -u)

blockers='[]'
candidate_status="authorized"
if [[ "$GHCR_STATUS" != "anonymous_public_digest_pull_proven" ]]; then
  blockers='["explicit_secret_backed_ghcr_pull_authority_required"]'
  candidate_status="stopped"
fi

jq -n \
  --arg status "$candidate_status" --arg observed "$(date -u +%Y-%m-%d)" --arg docker "$docker_version" --arg compose "$compose_version" \
  --arg compose_sha "$compose_sha" --arg cpu_model "$cpu_model" --arg root_filesystem "$root_filesystem" --argjson cpus "$cpu_count" --argjson mem_total "$memory_total" --argjson mem_available "$memory_available" \
  --argjson swap_total "$swap_total" --argjson root_bytes "$root_bytes" --argjson root_available "$root_available" --argjson owner_uid "$operator_uid" --arg schema_sha "$schema_receipt_sha" \
  --arg ghcr "$GHCR_AUTHORITY" --argjson blockers "$blockers" --argjson docker_networks "$(json_array_lines "${docker_networks[@]}")" --argjson container_names "$(json_array_lines "${container_names[@]}")" --argjson tcp_listeners "$(json_array_lines "${tcp_listeners[@]}")" '
  {schema_version:"ed-finder/v3-live-checkpoint-target-authority/v1",status:$status,
   target:{provider:"contabo",classification:"live-checkpoint",production:false,hostname:"vmi3542235",fqdn:"vmi3542235.contaboserver.net",architecture:"x86_64"},observed_at:$observed,
   observed_capacity:{logical_cpus:$cpus,cpu_model:$cpu_model,memory_total_kib:$mem_total,memory_available_kib:$mem_available,swap_total_kib:$swap_total,root_bytes:$root_bytes,root_available_bytes:$root_available,root_filesystem:$root_filesystem},
   observed_runtime:{container_runtime:$docker,compose:$compose,alternative_container_clis_present:[],container_names:$container_names,docker_networks:$docker_networks,docker_volumes:[],tcp_listeners:$tcp_listeners,runner_services:["actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service","actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service","actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service"],checkpoint_directories_found_under_opt_srv_var_lib:["/var/lib/edfinder-v3-checkpoint"]},
   application_contract:{compose_project:"edfinder-v3-checkpoint",compose_sha256:$compose_sha,services:{api:{container_name:"edfinder-v3-checkpoint-api",cpus:"1.50",memory:"1536m",pids:256},web:{container_name:"edfinder-v3-checkpoint-web",cpus:"0.50",memory:"512m",pids:128}},network:"edfinder-v3-checkpoint-app",network_lifecycle:"externally-provisioned-persistent",named_volumes:[],resource_derivation:"The fixed app limits remain 2 CPUs and 2 GiB combined, preserving the recorded runner capacity boundary."},
   external_authority:{api_env_file:"/etc/ed-finder/v3-checkpoint/api.env",api_env_owner_uid:$owner_uid,api_env_mode:"0600",database_source_authority:"contabo-vmi3542235-native-postgresql18-preview-v1",schema_identity_receipt:"/var/lib/edfinder-v3-checkpoint/schema-identity.json",schema_identity_receipt_sha256:$schema_sha,origin_bind:"http://127.0.0.1:18080",edge_route_authority:"http-only-provider-fqdn-vmi3542235.contaboserver.net-to-loopback-18080-no-dns",receipt_directory:"/var/lib/edfinder-v3-checkpoint/receipts",receipt_owner_uid:$owner_uid,receipt_mode:"0700",ghcr_pull_authority:(if $ghcr == "" then null else $ghcr end),docker_config_directory:"/var/lib/edfinder-v3-checkpoint/docker-config",docker_config_owner_uid:$owner_uid,docker_config_mode:"0700",docker_context:"edfinder-v3-checkpoint"},blockers:$blockers}' >"$candidate_path.tmp"

jq -n --arg status "$( [[ "$candidate_status" == authorized ]] && printf provisioned || printf provisioned_with_blocker )" --arg created "$captured_at" --arg docker "$docker_version" --arg compose "$compose_version" --arg postgres "$postgres_version" --arg migration "$migration_identity" --arg schema_sha "$schema_receipt_sha" --arg ghcr "$GHCR_STATUS" --argjson owner_uid "$operator_uid" --argjson runners "$(json_array_lines "${RUNNER_SERVICES[@]}")" --argjson probe_images "$(if [[ -n "$BACKEND_IMAGE" ]]; then json_array_lines "$BACKEND_IMAGE" "$WEB_IMAGE"; else printf '[]'; fi)" '
  {schema_version:"ed-finder/v3-live-checkpoint-provisioning-receipt/v1",operation:"provision-infrastructure",status:$status,created_at:$created,
   target:{provider:"contabo",classification:"live-checkpoint",production:false,hostname:"vmi3542235",fqdn:"vmi3542235.contaboserver.net",architecture:"x86_64"},runner_services:{expected:$runners,verified_before:true,verified_after:true,continuity_preserved:true,managed:false},
   runtime:{docker_engine:$docker,docker_compose:$compose,context:"edfinder-v3-checkpoint",endpoint:"unix:///var/run/docker.sock",external_network:"edfinder-v3-checkpoint-app"},
   database:{major:18,server_version:$postgres,source_authority:"contabo-vmi3542235-native-postgresql18-preview-v1",database_name:"edfinder_v3_checkpoint",owner_role:"edfinder_checkpoint_db",application_role:"edfinder_checkpoint_app",persistent:true,non_production:true,production_data_copied:false,canonical_apply_migrations_include_manual:true,preview_seed_applied:true,seed_acceptance_passed:true,read_only_schema_proof_passed:true,migration_set_identity:$migration,schema_receipt_sha256:$schema_sha},
   files:{api_env:{path:"/etc/ed-finder/v3-checkpoint/api.env",owner_uid:$owner_uid,mode:"0600",credentials_emitted:false},schema_receipt:{path:"/var/lib/edfinder-v3-checkpoint/schema-identity.json",owner_uid:$owner_uid,mode:"0600"},receipt_directory:{path:"/var/lib/edfinder-v3-checkpoint/receipts",owner_uid:$owner_uid,mode:"0700"},docker_config_directory:{path:"/var/lib/edfinder-v3-checkpoint/docker-config",owner_uid:$owner_uid,mode:"0700"}},
   routing:{origin:"http://127.0.0.1:18080",edge:"http://vmi3542235.contaboserver.net",http_only:true,dns_changes_performed:false,production_route_touched:false},
   ghcr:{status:$ghcr,probe_images:$probe_images,credentials_used:false},application_deploy_performed:false,production_access_performed:false,redis_provisioned:false,valkey_provisioned:false,nats_provisioned:false}' >"$receipt_path.tmp"

install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$candidate_path.tmp" "$candidate_path"
install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$receipt_path.tmp" "$receipt_path"
rm -f -- "$candidate_path.tmp" "$receipt_path.tmp"
durable_copy="$RECEIPT_DIR/provisioning-${captured_at//[:\-]/}.json"
if [[ ! -e "$durable_copy" ]]; then
  install -o "$operator_uid" -g "$(id -g "$OPERATOR_USER")" -m 600 "$receipt_path" "$durable_copy"
fi
RECEIPT_WRITTEN=1
