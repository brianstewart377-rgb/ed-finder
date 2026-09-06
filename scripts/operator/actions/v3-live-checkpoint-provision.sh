#!/usr/bin/env bash
set -euo pipefail
umask 077

EXPECTED_HOST="vmi3542235"
EXPECTED_FQDN="vmi3542235.contaboserver.net"
APP_NETWORK="edfinder-v3-checkpoint-app"
ORIGIN_PORT="18080"
STATE_ROOT="/var/lib/edfinder-v3-checkpoint"
API_ENV="/etc/edfinder-v3-checkpoint/api.env"
RECEIPT_DIR="$STATE_ROOT/receipts"
SCHEMA_RECEIPT="$STATE_ROOT/schema-identity.json"
DOCKER_CONFIG_DIR="$STATE_ROOT/docker-config"
DOCKER_CONTEXT="edfinder-v3-checkpoint-local"
DB_NAME="edfinder_checkpoint"
DB_APP_ROLE="edfinder_checkpoint_app"
DB_AUTHORITY="contabo-local-postgresql18-preview-seed-v1"
RUNNERS=(
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service
)
PW_SQL=""
LEDGER_FILE=""

cleanup_sensitive_temps() {
  [ -z "$PW_SQL" ] || rm -f -- "$PW_SQL"
  [ -z "$LEDGER_FILE" ] || rm -f -- "$LEDGER_FILE"
}
trap cleanup_sensitive_temps EXIT HUP INT TERM

fail() { echo "checkpoint provisioning stopped: $*" >&2; exit 78; }

verify_exact_runners() {
  local -a active=()
  local -a expected=()
  mapfile -t active < <(
    systemctl list-units --type=service --state=active --no-legend --plain 'actions.runner.*.service' |
      awk '{print $1}' | sort
  )
  mapfile -t expected < <(printf '%s\n' "${RUNNERS[@]}" | sort)
  [ "${#active[@]}" -eq "${#expected[@]}" ] || fail "unexpected active runner service count"
  local i
  for i in "${!expected[@]}"; do
    [ "${active[$i]}" = "${expected[$i]}" ] || fail "unexpected active runner topology"
  done
}

verify_origin_authority() {
  local listener=""
  listener="$(ss -lntH "sport = :$ORIGIN_PORT" 2>/dev/null || true)"
  if [ -z "$listener" ]; then
    return 0
  fi
  docker inspect edfinder-v3-checkpoint-web >/dev/null 2>&1 ||
    fail "checkpoint origin port is occupied by an unauthorized process"
  [ "$(docker inspect -f '{{.State.Running}}' edfinder-v3-checkpoint-web)" = true ] ||
    fail "checkpoint origin port occupant is not a running checkpoint web container"
  docker port edfinder-v3-checkpoint-web 8080/tcp 2>/dev/null |
    grep -qx "127.0.0.1:$ORIGIN_PORT" ||
    fail "checkpoint web container does not own the authorized loopback origin"
}

[ "$(id -u)" -eq 0 ] || fail "root authority required"
[ "$(hostname -s)" = "$EXPECTED_HOST" ] || fail "unexpected host"
[ "$(uname -m)" = "x86_64" ] || fail "unexpected architecture"

OP_UID="${CHECKPOINT_OPERATOR_UID:-}"
OP_GID="${CHECKPOINT_OPERATOR_GID:-}"
OP_USER="${CHECKPOINT_OPERATOR_USER:-}"
[[ "$OP_UID" =~ ^[1-9][0-9]*$ ]] || fail "checkpoint operator uid missing or invalid"
[[ "$OP_GID" =~ ^[0-9]+$ ]] || fail "checkpoint operator gid missing or invalid"
[[ "$OP_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "checkpoint operator user missing or invalid"
[ "$(id -u "$OP_USER")" = "$OP_UID" ] || fail "checkpoint operator uid mismatch"
[ "$(id -g "$OP_USER")" = "$OP_GID" ] || fail "checkpoint operator gid mismatch"

verify_exact_runners

. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || fail "checkpoint provisioner requires Ubuntu"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg jq nginx openssl software-properties-common >/dev/null

if ! command -v python3.14 >/dev/null 2>&1; then
  add-apt-repository -y ppa:deadsnakes/ppa >/dev/null
  apt-get update -qq
  apt-get install -y -qq python3.14 >/dev/null
fi
python3.14 -c 'import platform,sys; raise SystemExit(0 if platform.python_implementation()=="CPython" and sys.version_info[:2]==(3,14) else 1)' ||
  fail "checkpoint target requires exact CPython 3.14"
ACTUAL_FQDN="$(python3.14 -c 'import socket; print(socket.getfqdn())')"
[ "$ACTUAL_FQDN" = "$EXPECTED_FQDN" ] || fail "unexpected checkpoint FQDN"

install -d -m 0755 /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
fi
chmod 0644 /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
  "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list

if [ ! -s /etc/apt/keyrings/postgresql.asc ]; then
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/postgresql.asc
fi
chmod 0644 /etc/apt/keyrings/postgresql.asc
printf 'deb [signed-by=/etc/apt/keyrings/postgresql.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
  "$VERSION_CODENAME" > /etc/apt/sources.list.d/pgdg.list

apt-get update -qq
apt-get install -y -qq \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  postgresql-18 postgresql-client-18 >/dev/null

systemctl enable --now docker >/dev/null
usermod -aG docker "$OP_USER"
verify_origin_authority

if ! docker network inspect "$APP_NETWORK" >/dev/null 2>&1; then
  docker network create --driver bridge "$APP_NETWORK" >/dev/null
fi
NETWORK_DRIVER="$(docker network inspect "$APP_NETWORK" --format '{{.Driver}}')"
NETWORK_SCOPE="$(docker network inspect "$APP_NETWORK" --format '{{.Scope}}')"
[ "$NETWORK_DRIVER" = bridge ] && [ "$NETWORK_SCOPE" = local ] || \
  fail "checkpoint app network is not a local bridge"
NETWORK_GATEWAY="$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Gateway}}')"
NETWORK_SUBNET="$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Subnet}}')"
python3.14 - "$NETWORK_GATEWAY" "$NETWORK_SUBNET" <<'PY' || fail "invalid checkpoint network"
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
network = ipaddress.ip_network(sys.argv[2], strict=False)
assert address in network and not network.is_loopback
PY

if ! pg_lsclusters --no-header 2>/dev/null | awk '$1=="18" && $2=="main" {found=1} END{exit !found}'; then
  pg_createcluster 18 main --start >/dev/null
fi
systemctl enable --now postgresql@18-main >/dev/null
PG_HBA="$(runuser -u postgres -- psql -X -Atqc 'show hba_file')"
PG_PORT="$(runuser -u postgres -- psql -X -Atqc 'show port')"
[ "$PG_PORT" = 5432 ] || fail "unexpected PostgreSQL port"

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q <<SQL
ALTER SYSTEM SET listen_addresses = '127.0.0.1,$NETWORK_GATEWAY';
ALTER SYSTEM SET password_encryption = 'scram-sha-256';
SQL
sed -i '/# edfinder-v3-checkpoint$/d' "$PG_HBA"
printf 'host %s %s %s scram-sha-256 # edfinder-v3-checkpoint\n' \
  "$DB_NAME" "$DB_APP_ROLE" "$NETWORK_SUBNET" >> "$PG_HBA"
systemctl restart postgresql@18-main

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" \
  /etc/edfinder-v3-checkpoint "$STATE_ROOT" "$RECEIPT_DIR" "$DOCKER_CONFIG_DIR"

DB_EXISTS="$(runuser -u postgres -- psql -X -Atqc \
  "select 1 from pg_database where datname='$DB_NAME'")"
DB_CREATED=false
if [ "$DB_EXISTS" != 1 ]; then
  [ ! -e "$SCHEMA_RECEIPT" ] || fail "schema receipt exists while checkpoint database is missing"
  runuser -u postgres -- createdb "$DB_NAME"
  ADMIN_DATABASE_URL="postgresql:///$DB_NAME?host=/var/run/postgresql"
  runuser -u postgres -- env DATABASE_URL="$ADMIN_DATABASE_URL" bash scripts/seed_check.sh >&2
  DB_CREATED=true
else
  [ -f "$SCHEMA_RECEIPT" ] || fail "existing checkpoint database lacks trusted schema receipt"
  [ "$(stat -c '%u' "$SCHEMA_RECEIPT")" = "$OP_UID" ] || fail "schema receipt owner changed"
  [ "$(stat -c '%a' "$SCHEMA_RECEIPT")" = 600 ] || fail "schema receipt mode changed"
fi

DB_PASSWORD=""
if [ -f "$API_ENV" ]; then
  DB_PASSWORD="$(python3.14 - "$API_ENV" <<'PY'
import pathlib, sys, urllib.parse
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        parsed = urllib.parse.urlsplit(line.split("=", 1)[1].strip())
        print(urllib.parse.unquote(parsed.password or ""))
        break
PY
)"
fi
if [ -z "$DB_PASSWORD" ]; then
  DB_PASSWORD="$(openssl rand -hex 24)"
fi
[[ "$DB_PASSWORD" =~ ^[0-9a-f]{48}$ ]] || fail "checkpoint database password format is invalid"

ROLE_EXISTS="$(runuser -u postgres -- psql -X -Atqc \
  "select 1 from pg_roles where rolname='$DB_APP_ROLE'")"
if [ "$ROLE_EXISTS" != 1 ]; then
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE $DB_APP_ROLE LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
SQL
fi

PW_SQL="$(mktemp)"
printf "ALTER ROLE %s PASSWORD '%s';\n" "$DB_APP_ROLE" "$DB_PASSWORD" > "$PW_SQL"
chown postgres:postgres "$PW_SQL"
chmod 0600 "$PW_SQL"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -f "$PW_SQL"
rm -f -- "$PW_SQL"
PW_SQL=""

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q <<SQL
ALTER ROLE $DB_APP_ROLE NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE $DB_APP_ROLE SET default_transaction_read_only = on;
REVOKE ALL ON DATABASE $DB_NAME FROM PUBLIC;
REVOKE TEMP ON DATABASE $DB_NAME FROM $DB_APP_ROLE;
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_APP_ROLE;
SQL
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB_NAME" <<SQL
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM $DB_APP_ROLE;
GRANT USAGE ON SCHEMA public TO $DB_APP_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $DB_APP_ROLE;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $DB_APP_ROLE;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM $DB_APP_ROLE;
SQL

DATABASE_URL="postgresql://$DB_APP_ROLE:$DB_PASSWORD@$NETWORK_GATEWAY:5432/$DB_NAME"
cat > "$API_ENV" <<EOF
DATABASE_URL=$DATABASE_URL
CORS_ORIGINS=http://$EXPECTED_FQDN
REDIS_URL=redis://127.0.0.1:1/0
ADMIN_OPERATION_STARTUP_REAP_ENABLED=false
EDDN_SIMULATION_INGEST_ENABLED=false
AUTH_COOKIE_SECURE=false
FRONTIER_REDIRECT_URI=http://$EXPECTED_FQDN/api/auth/frontier/callback
EOF
chown "$OP_UID:$OP_GID" "$API_ENV"
chmod 0600 "$API_ENV"

READONLY="$(env PGDATABASE="$DATABASE_URL" psql -X -Atqc \
  "select current_setting('transaction_read_only')")"
[ "$READONLY" = on ] || fail "checkpoint app database session is not read-only"
PREVIEW_COUNTS="$(env PGDATABASE="$DATABASE_URL" psql -X -At -F '|' -qc \
  'select (select count(*) from systems),(select count(*) from ratings),(select count(*) from bodies),(select count(*) from stations),(select count(*) from galaxy_regions)')"
[ "$PREVIEW_COUNTS" = "40|40|129|10|42" ] || fail "checkpoint preview dataset identity mismatch"
if env PGDATABASE="$DATABASE_URL" psql -X -v ON_ERROR_STOP=1 -q \
    -c 'update systems set name=name where false' >/dev/null 2>&1; then
  fail "checkpoint app database role unexpectedly permits writes"
fi

DB_IDENTITY="$(env PGDATABASE="$DATABASE_URL" psql -X -Atqc \
  "select current_database() || '|' || inet_server_addr()::text || '|' || inet_server_port()::text")"
IFS='|' read -r OBSERVED_DB OBSERVED_ADDRESS OBSERVED_PORT <<<"$DB_IDENTITY"
[ "$OBSERVED_DB" = "$DB_NAME" ] || fail "checkpoint database identity mismatch"
[ "$OBSERVED_PORT" = 5432 ] || fail "checkpoint database port mismatch"
[ "$OBSERVED_ADDRESS" = "$NETWORK_GATEWAY" ] || fail "checkpoint database address mismatch"

LEDGER_FILE="$(mktemp)"
env PGDATABASE="$DATABASE_URL" psql -X -At -F '|' -q \
  -c 'select filename, checksum_sha256 from public.schema_migrations order by filename' \
  > "$LEDGER_FILE"

RECEIPT_MODE=verify
[ "$DB_CREATED" = false ] || RECEIPT_MODE=create
python3.14 - "$RECEIPT_MODE" "$DB_AUTHORITY" "$OBSERVED_DB" "$OBSERVED_ADDRESS" "$OBSERVED_PORT" \
  "$LEDGER_FILE" "$SCHEMA_RECEIPT" <<'PY'
import datetime, hashlib, json, pathlib, sys

receipt_mode, source, dbname, address, port, ledger_path, receipt_path = sys.argv[1:]
root = pathlib.Path(".")
entries = []
for raw in (root / "sql/migration-manifest.txt").read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("|", 1)
    name = parts[0]
    mode_name = parts[1] if len(parts) == 2 else "auto"
    entries.append({
        "path": f"sql/{name}",
        "mode": mode_name,
        "sha256": hashlib.sha256((root / "sql" / name).read_bytes()).hexdigest(),
    })

expected_ledger = sorted(
    [(entry["path"].removeprefix("sql/"), entry["sha256"]) for entry in entries]
)
observed_ledger = []
for raw in pathlib.Path(ledger_path).read_text(encoding="utf-8").splitlines():
    if not raw:
        continue
    name, checksum = raw.split("|", 1)
    observed_ledger.append((name, checksum))
if observed_ledger != expected_ledger:
    raise SystemExit("checkpoint migration ledger does not match source")

identity = "sha256:" + hashlib.sha256(
    json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
database_identity = {
    "database_name": dbname,
    "server_address": address,
    "server_port": int(port),
}
receipt = pathlib.Path(receipt_path)
captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

if receipt_mode == "create":
    document = {
        "schema_version": "ed-finder/v3-live-checkpoint-schema-identity/v2",
        "database_source_authority": source,
        "database_identity": database_identity,
        "migration_set_identity": identity,
        "migration_set_entries": entries,
        "captured_at": captured_at,
    }
elif receipt_mode == "verify":
    document = json.loads(receipt.read_text(encoding="utf-8"))
    expected = {
        "schema_version": "ed-finder/v3-live-checkpoint-schema-identity/v2",
        "database_source_authority": source,
        "database_identity": database_identity,
        "migration_set_identity": identity,
        "migration_set_entries": entries,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise SystemExit(f"trusted schema receipt mismatch: {key}")
    document["captured_at"] = captured_at
else:
    raise SystemExit("unknown schema receipt mode")

receipt.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
rm -f -- "$LEDGER_FILE"
LEDGER_FILE=""

chown "$OP_UID:$OP_GID" "$SCHEMA_RECEIPT"
chmod 0600 "$SCHEMA_RECEIPT"
SCHEMA_SHA="$(sha256sum "$SCHEMA_RECEIPT" | awk '{print $1}')"

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" "$DOCKER_CONFIG_DIR"
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" \
  docker context inspect "$DOCKER_CONTEXT" >/dev/null 2>&1 || \
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" \
  docker context create "$DOCKER_CONTEXT" --docker host=unix:///var/run/docker.sock >/dev/null
chown -R "$OP_UID:$OP_GID" "$DOCKER_CONFIG_DIR"
chmod 0700 "$DOCKER_CONFIG_DIR"
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" \
  docker context inspect "$DOCKER_CONTEXT" --format '{{json .Endpoints.docker.Host}}' |
  grep -qx '"unix:///var/run/docker.sock"' || fail "local Docker context verification failed"

cat > /etc/nginx/sites-available/edfinder-v3-checkpoint <<EOF
server {
  listen 80;
  listen [::]:80;
  server_name $EXPECTED_FQDN;
  location / {
    proxy_pass http://127.0.0.1:$ORIGIN_PORT;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
  }
}
EOF
ln -sfn /etc/nginx/sites-available/edfinder-v3-checkpoint \
  /etc/nginx/sites-enabled/edfinder-v3-checkpoint
rm -f /etc/nginx/sites-enabled/default
nginx -t >/dev/null
systemctl enable --now nginx >/dev/null
systemctl reload nginx

verify_exact_runners
verify_origin_authority
docker version >/dev/null
docker compose version >/dev/null

AUTHORITY_SOURCE="deploy/v3-live-checkpoint/target-authority.json"
python3.14 - "$AUTHORITY_SOURCE" "$OP_UID" "$SCHEMA_SHA" <<'PY'
import datetime, json, pathlib, subprocess, sys

source, uid, schema_sha = sys.argv[1:]
uid = int(uid)
authority = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
authority["status"] = "authorized"
authority["blockers"] = []
authority["observed_at"] = datetime.date.today().isoformat()
runtime = authority["observed_runtime"]
runtime["container_runtime"] = subprocess.check_output(
    ["docker", "--version"], text=True
).strip()
runtime["compose"] = subprocess.check_output(
    ["docker", "compose", "version"], text=True
).strip()
runtime["container_names"] = subprocess.check_output(
    ["docker", "ps", "-a", "--format", "{{.Names}}"], text=True
).splitlines()
runtime["docker_networks"] = subprocess.check_output(
    ["docker", "network", "ls", "--format", "{{.Name}}"], text=True
).splitlines()
runtime["docker_volumes"] = subprocess.check_output(
    ["docker", "volume", "ls", "--format", "{{.Name}}"], text=True
).splitlines()
runtime["tcp_listeners"] = sorted(
    line.split()[3]
    for line in subprocess.check_output(["ss", "-lntH"], text=True).splitlines()
)
runtime["checkpoint_directories_found_under_opt_srv_var_lib"] = [
    "/var/lib/edfinder-v3-checkpoint"
]
authority["external_authority"] = {
    "api_env_file": "/etc/edfinder-v3-checkpoint/api.env",
    "api_env_owner_uid": uid,
    "api_env_mode": "0600",
    "database_source_authority": "contabo-local-postgresql18-preview-seed-v1",
    "schema_identity_receipt": "/var/lib/edfinder-v3-checkpoint/schema-identity.json",
    "schema_identity_receipt_sha256": schema_sha,
    "origin_bind": "http://127.0.0.1:18080",
    "edge_route_authority": "nginx-vmi3542235-http80-to-loopback-18080",
    "receipt_directory": "/var/lib/edfinder-v3-checkpoint/receipts",
    "receipt_owner_uid": uid,
    "receipt_mode": "0700",
    "ghcr_pull_authority": "per-deploy-github-actions-packages-read-token",
    "docker_config_directory": "/var/lib/edfinder-v3-checkpoint/docker-config",
    "docker_config_owner_uid": uid,
    "docker_config_mode": "0700",
    "docker_context": "edfinder-v3-checkpoint-local",
}
print(json.dumps(authority, sort_keys=True, indent=2))
PY
