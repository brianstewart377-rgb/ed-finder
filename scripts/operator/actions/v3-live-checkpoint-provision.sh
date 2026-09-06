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
NGINX_SITE="/etc/nginx/sites-available/edfinder-v3-checkpoint"
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

# Read and replace state through no-follow descriptors; never chown a link target.
atomic_checkpoint_file() {
  python3.14 -c '
import os, secrets, stat, sys
path, uid, gid, mode = sys.argv[1:]
uid, gid, mode = int(uid), int(gid), int(mode, 8)
data = sys.stdin.buffer.read()
if not data:
    raise SystemExit("refusing an empty checkpoint state file")
parent, name = os.path.split(path)
dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
temporary = "." + name + "." + secrets.token_hex(16) + ".tmp"
created = False
def check_target():
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SystemExit("checkpoint state target must be a single-link regular file")
try:
    check_target()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=dir_fd)
    created = True
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fchown(handle.fileno(), uid, gid)
        os.fchmod(handle.fileno(), mode)
        os.fsync(handle.fileno())
    check_target()
    os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    os.fsync(dir_fd)
finally:
    try:
        if created:
            os.unlink(temporary, dir_fd=dir_fd)
    except FileNotFoundError:
        pass
    os.close(dir_fd)
' "$1" "$2" "$3" "${4:-600}"
}

read_checkpoint_password() {
  python3.14 - "$API_ENV" "$OP_UID" "$DB_EXISTS" "$NETWORK_GATEWAY" "$DB_NAME" "$DB_APP_ROLE" <<'PY'
import os, re, stat, sys, urllib.parse
path, uid, exists, gateway, database, role = sys.argv[1:]
parent, name = os.path.split(path)
dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except FileNotFoundError:
        if exists == "1":
            raise SystemExit("existing checkpoint database lacks a complete API environment")
        raise SystemExit(0)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != int(uid) or stat.S_IMODE(info.st_mode) != 0o600):
            raise SystemExit("checkpoint API environment has unsafe type, owner or mode")
        if exists != "1":
            raise SystemExit("API environment exists while checkpoint database is missing")
        values = [line.split("=", 1)[1] for line in handle.read().splitlines()
                  if line.startswith("DATABASE_URL=")]
finally:
    os.close(dir_fd)
if len(values) != 1:
    raise SystemExit("existing checkpoint database lacks one complete DATABASE_URL")
try:
    parsed = urllib.parse.urlsplit(values[0])
    password = urllib.parse.unquote(parsed.password or "")
    valid = (parsed.scheme == "postgresql" and parsed.username == role
             and parsed.hostname == gateway and parsed.port == 5432
             and parsed.path == "/" + database and not parsed.query and not parsed.fragment
             and re.fullmatch(r"[0-9a-f]{48}", password) is not None)
except ValueError:
    valid = False
if not valid:
    raise SystemExit("checkpoint DATABASE_URL identity or password is invalid")
print(password)
PY
}

checkpoint_hba_document() {
  python3.14 - "$PG_HBA" "$DB_NAME" "$DB_APP_ROLE" "$NETWORK_SUBNET" <<'PY'
import ipaddress, pathlib, sys
path, database, role, subnet = sys.argv[1:]
subnet = str(ipaddress.ip_network(subnet, strict=True))
lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
retained = [line for line in lines if not line.rstrip().endswith("# edfinder-v3-checkpoint")]
# This must precede every broad rule and include directive: HBA is first-match.
print(f"host {database} {role} {subnet} scram-sha-256 # edfinder-v3-checkpoint")
print("".join(retained), end="")
PY
}

verify_checkpoint_password_rejection() {
  local diagnostic=""
  # This deliberately differs from every valid 48-character hexadecimal password.
  if diagnostic="$(env LC_ALL=C PGHOST="$NETWORK_GATEWAY" PGPORT=5432 \
      PGUSER="$DB_APP_ROLE" PGDATABASE="$DB_NAME" PGPASSWORD=invalid-checkpoint-password \
      PGCONNECT_TIMEOUT=5 psql -X -w -Atqc 'select 1' 2>&1)"; then
    fail "checkpoint database accepted an incorrect password"
  fi
  printf '%s\n' "$diagnostic" | grep -Fq "password authentication failed for user \"$DB_APP_ROLE\"" ||
    fail "checkpoint negative authentication probe did not prove password rejection"
}

verify_checkpoint_nginx_ownership() {
  # Inspect every included config (not just sites-enabled). Do not print the dump.
  local dump=""
  dump="$(nginx -T 2>&1)" || fail "cannot inspect enabled nginx configuration"
  printf '%s\n' "$dump" | python3.14 -c '
import os, re, shlex, sys
fqdn, managed, required = sys.argv[1:]
fqdn = fqdn.lower().rstrip(".")
managed = os.path.realpath(managed)
dump = sys.stdin.read()
if re.search(r"conflicting server name \"" + re.escape(fqdn) + r"\.?\"", dump, re.I):
    raise SystemExit("conflicting nginx ownership of checkpoint FQDN")
sections = re.split(r"^# configuration file (.+):\s*$", dump, flags=re.M)
if len(sections) < 3:
    raise SystemExit("nginx did not return an inspectable configuration dump")
owned = 0
for index in range(1, len(sections), 2):
    source, body = sections[index:index + 2]
    lexer = shlex.shlex(body, posix=True, punctuation_chars=";{}")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    directive = []
    for token in lexer:
        if token and all(char in ";{}" for char in token):
            if token.startswith(";") and directive and directive[0] == "server_name":
                names = [value.lower().rstrip(".") for value in directive[1:]]
                if fqdn in names:
                    if os.path.realpath(source) != managed:
                        raise SystemExit("competing nginx site owns checkpoint FQDN")
                    owned += names.count(fqdn)
            directive = []
        else:
            directive.append(token)
if owned > 1 or (required == "required" and owned != 1):
    raise SystemExit("checkpoint nginx FQDN must have exactly one managed declaration")
' "$EXPECTED_FQDN" "$NGINX_SITE" "${1:-optional}"
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

# Serialize provisioning with the canonical deployer using its durable host lock.
install -d -m 0700 -o "$OP_UID" -g "$OP_GID" "$STATE_ROOT" "$RECEIPT_DIR"
touch "$RECEIPT_DIR/deploy.lock"
chown "$OP_UID:$OP_GID" "$RECEIPT_DIR/deploy.lock"
chmod 0600 "$RECEIPT_DIR/deploy.lock"
exec 9<>"$RECEIPT_DIR/deploy.lock"
flock -n 9 || fail "live-checkpoint deployment lock is unavailable"

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
HBA_DOCUMENT="$(checkpoint_hba_document)"
printf '%s\n' "$HBA_DOCUMENT" | atomic_checkpoint_file "$PG_HBA" \
  "$(stat -c '%u' "$PG_HBA")" "$(stat -c '%g' "$PG_HBA")" "$(stat -c '%a' "$PG_HBA")"
systemctl restart postgresql@18-main
HBA_VERIFIED="$(runuser -u postgres -- psql -X -At -v ON_ERROR_STOP=1 \
  -v checkpoint_db="$DB_NAME" -v checkpoint_role="$DB_APP_ROLE" \
  -v checkpoint_subnet="$NETWORK_SUBNET" <<'SQL'
SELECT count(*) = 1 FROM pg_hba_file_rules
WHERE rule_number = 1 AND type = 'host'
  AND database = ARRAY[:'checkpoint_db'] AND user_name = ARRAY[:'checkpoint_role']
  AND address = host(network(:'checkpoint_subnet'::cidr))
  AND netmask = host(netmask(:'checkpoint_subnet'::cidr))
  AND auth_method = 'scram-sha-256' AND error IS NULL
  AND NOT EXISTS (SELECT 1 FROM pg_hba_file_rules WHERE error IS NOT NULL);
SQL
)"
[ "$HBA_VERIFIED" = t ] || fail "checkpoint SCRAM rule is not the first effective HBA rule"

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" \
  /etc/edfinder-v3-checkpoint "$STATE_ROOT" "$RECEIPT_DIR" "$DOCKER_CONFIG_DIR"

DB_EXISTS="$(runuser -u postgres -- psql -X -Atqc \
  "select 1 from pg_database where datname='$DB_NAME'")"
DB_PASSWORD="$(read_checkpoint_password)"
if [ "$DB_EXISTS" != 1 ]; then
  DB_PASSWORD="$(openssl rand -hex 24)"
fi
[[ "$DB_PASSWORD" =~ ^[0-9a-f]{48}$ ]] || fail "checkpoint database password format is invalid"
DB_CREATED=false
if [ "$DB_EXISTS" != 1 ]; then
  [ ! -e "$SCHEMA_RECEIPT" ] || fail "schema receipt exists while checkpoint database is missing"
  runuser -u postgres -- createdb "$DB_NAME"
  ADMIN_DATABASE_URL="postgresql:///$DB_NAME?host=/var/run/postgresql"
  runuser -u postgres -- env DATABASE_URL="$ADMIN_DATABASE_URL" bash scripts/seed_check.sh >&2
  DB_CREATED=true
else
  [ ! -L "$SCHEMA_RECEIPT" ] || fail "schema receipt must not be a symlink"
  [ -f "$SCHEMA_RECEIPT" ] || fail "existing checkpoint database lacks trusted schema receipt"
  [ "$(stat -c '%u' "$SCHEMA_RECEIPT")" = "$OP_UID" ] || fail "schema receipt owner changed"
  [ "$(stat -c '%a' "$SCHEMA_RECEIPT")" = 600 ] || fail "schema receipt mode changed"
fi

ROLE_EXISTS="$(runuser -u postgres -- psql -X -Atqc \
  "select 1 from pg_roles where rolname='$DB_APP_ROLE'")"
if [ "$ROLE_EXISTS" != 1 ]; then
  [ "$DB_CREATED" = true ] || fail "existing checkpoint database lacks its application role"
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE $DB_APP_ROLE LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
SQL
fi

# A verification rerun must never rotate the credential held by a live container.
if [ "$DB_CREATED" = true ]; then
  PW_SQL="$(mktemp)"
  printf "ALTER ROLE %s PASSWORD '%s';\n" "$DB_APP_ROLE" "$DB_PASSWORD" > "$PW_SQL"
  chown postgres:postgres "$PW_SQL"
  chmod 0600 "$PW_SQL"
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -f "$PW_SQL"
  rm -f -- "$PW_SQL"
  PW_SQL=""
fi

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
if [ "$DB_CREATED" = true ]; then
  atomic_checkpoint_file "$API_ENV" "$OP_UID" "$OP_GID" <<EOF
DATABASE_URL=$DATABASE_URL
CORS_ORIGINS=http://$EXPECTED_FQDN
REDIS_URL=redis://127.0.0.1:1/0
ADMIN_OPERATION_STARTUP_REAP_ENABLED=false
EDDN_SIMULATION_INGEST_ENABLED=false
AUTH_COOKIE_SECURE=false
FRONTIER_REDIRECT_URI=http://$EXPECTED_FQDN/api/auth/frontier/callback
EOF
fi

READONLY="$(env PGDATABASE="$DATABASE_URL" psql -X -Atqc \
  "select current_setting('transaction_read_only')")"
[ "$READONLY" = on ] || fail "checkpoint app database session is not read-only"
verify_checkpoint_password_rejection
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
SCHEMA_DOCUMENT="$(python3.14 - "$RECEIPT_MODE" "$DB_AUTHORITY" "$OBSERVED_DB" "$OBSERVED_ADDRESS" "$OBSERVED_PORT" \
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

print(json.dumps(document, sort_keys=True, indent=2))
PY
)"
printf '%s\n' "$SCHEMA_DOCUMENT" | atomic_checkpoint_file "$SCHEMA_RECEIPT" "$OP_UID" "$OP_GID"
rm -f -- "$LEDGER_FILE"
LEDGER_FILE=""

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

verify_checkpoint_nginx_ownership
cat > "$NGINX_SITE" <<EOF
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
verify_checkpoint_nginx_ownership required
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
