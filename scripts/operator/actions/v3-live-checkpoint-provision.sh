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
DB_USER="edfinder_checkpoint"
DB_AUTHORITY="contabo-local-postgresql18-preview-seed-v1"
RUNNERS=(
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service
)

fail() { echo "checkpoint provisioning stopped: $*" >&2; exit 78; }
[ "$(id -u)" -eq 0 ] || fail "root authority required"
[ "$(hostname -s)" = "$EXPECTED_HOST" ] || fail "unexpected host"
[ "$(uname -m)" = "x86_64" ] || fail "unexpected architecture"
for svc in "${RUNNERS[@]}"; do systemctl is-active --quiet "$svc" || fail "required runner inactive: $svc"; done

OP_UID="${SUDO_UID:-}"
OP_GID="${SUDO_GID:-}"
OP_USER="${SUDO_USER:-}"
if [ -z "$OP_UID" ] || [ -z "$OP_GID" ] || [ -z "$OP_USER" ] || [ "$OP_UID" = 0 ]; then
  fail "provisioning must be invoked through passwordless sudo by the checkpoint SSH operator"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg jq nginx >/dev/null

install -d -m 0755 /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
fi
chmod 0644 /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list

if [ ! -s /etc/apt/keyrings/postgresql.asc ]; then
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/postgresql.asc
fi
chmod 0644 /etc/apt/keyrings/postgresql.asc
printf 'deb [signed-by=/etc/apt/keyrings/postgresql.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/pgdg.list

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin postgresql-18 postgresql-client-18 >/dev/null
systemctl enable --now docker >/dev/null
systemctl enable nginx >/dev/null
usermod -aG docker "$OP_USER"

if ! docker network inspect "$APP_NETWORK" >/dev/null 2>&1; then
  docker network create --driver bridge "$APP_NETWORK" >/dev/null
fi
NETWORK_DRIVER="$(docker network inspect "$APP_NETWORK" --format '{{.Driver}}')"
NETWORK_SCOPE="$(docker network inspect "$APP_NETWORK" --format '{{.Scope}}')"
[ "$NETWORK_DRIVER" = bridge ] && [ "$NETWORK_SCOPE" = local ] || fail "checkpoint app network is not a local bridge"
NETWORK_GATEWAY="$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Gateway}}')"
NETWORK_SUBNET="$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Subnet}}')"
python3 - "$NETWORK_GATEWAY" "$NETWORK_SUBNET" <<'PY' || fail "invalid checkpoint network"
import ipaddress,sys
ip=ipaddress.ip_address(sys.argv[1]); net=ipaddress.ip_network(sys.argv[2], strict=False)
assert ip in net and not net.is_loopback
PY

if ! pg_lsclusters --no-header 2>/dev/null | awk '$1=="18" && $2=="main" {found=1} END{exit !found}'; then
  pg_createcluster 18 main --start >/dev/null
fi
PG_CONF="$(sudo -u postgres psql -X -Atqc 'show config_file')"
PG_HBA="$(sudo -u postgres psql -X -Atqc 'show hba_file')"
PG_PORT="$(sudo -u postgres psql -X -Atqc 'show port')"
[ "$PG_PORT" = 5432 ] || fail "unexpected PostgreSQL port"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -q <<SQL
ALTER SYSTEM SET listen_addresses = '127.0.0.1,$NETWORK_GATEWAY';
ALTER SYSTEM SET password_encryption = 'scram-sha-256';
SQL
sed -i '/# edfinder-v3-checkpoint$/d' "$PG_HBA"
printf 'host %s %s %s scram-sha-256 # edfinder-v3-checkpoint\n' "$DB_NAME" "$DB_USER" "$NETWORK_SUBNET" >> "$PG_HBA"
systemctl restart postgresql@18-main

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" /etc/edfinder-v3-checkpoint "$STATE_ROOT" "$RECEIPT_DIR" "$DOCKER_CONFIG_DIR"
DB_PASSWORD=""
if [ -f "$API_ENV" ]; then
  DB_PASSWORD="$(python3 - "$API_ENV" <<'PY'
import pathlib,sys,urllib.parse
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line.startswith('DATABASE_URL='):
        u=urllib.parse.urlsplit(line.split('=',1)[1].strip())
        print(urllib.parse.unquote(u.password or '')); break
PY
)"
fi
if [ -z "$DB_PASSWORD" ]; then DB_PASSWORD="$(openssl rand -hex 24)"; fi

ROLE_EXISTS="$(sudo -u postgres psql -X -Atqc "select 1 from pg_roles where rolname='$DB_USER'")"
if [ "$ROLE_EXISTS" != 1 ]; then
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE $DB_USER LOGIN;
SQL
fi
PW_SQL="$(mktemp)"; chmod 0600 "$PW_SQL"
printf "ALTER ROLE %s PASSWORD '%s';\n" "$DB_USER" "$DB_PASSWORD" > "$PW_SQL"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -q -f "$PW_SQL"
rm -f "$PW_SQL"
DB_EXISTS="$(sudo -u postgres psql -X -Atqc "select 1 from pg_database where datname='$DB_NAME'")"
if [ "$DB_EXISTS" != 1 ]; then sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"; fi

DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$NETWORK_GATEWAY:5432/$DB_NAME"
cat > "$API_ENV" <<EOF
DATABASE_URL=$DATABASE_URL
CORS_ORIGINS=http://$EXPECTED_FQDN
REDIS_URL=redis://127.0.0.1:1/0
ADMIN_OPERATION_STARTUP_REAP_ENABLED=false
EDDN_SIMULATION_INGEST_ENABLED=false
AUTH_COOKIE_SECURE=false
FRONTIER_REDIRECT_URI=http://$EXPECTED_FQDN/api/auth/frontier/callback
EOF
chown "$OP_UID:$OP_GID" "$API_ENV"; chmod 0600 "$API_ENV"

export DATABASE_URL
bash scripts/seed_check.sh >&2

python3 - "$DB_AUTHORITY" "$DB_NAME" "$NETWORK_GATEWAY" "$SCHEMA_RECEIPT" <<'PY'
import datetime,hashlib,json,pathlib,sys
source,dbname,address,out=sys.argv[1:]
root=pathlib.Path('.')
entries=[]
for raw in (root/'sql/migration-manifest.txt').read_text().splitlines():
    line=raw.strip()
    if not line or line.startswith('#'): continue
    parts=line.split('|',1); name=parts[0]; mode=parts[1] if len(parts)==2 else 'auto'
    data=(root/'sql'/name).read_bytes()
    entries.append({'path':f'sql/{name}','mode':mode,'sha256':hashlib.sha256(data).hexdigest()})
identity='sha256:'+hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()
doc={'schema_version':'ed-finder/v3-live-checkpoint-schema-identity/v1','database_source_authority':source,'database_identity':{'database_name':dbname,'server_address':address,'server_port':5432},'migration_set_identity':identity,'migration_set_entries':entries,'captured_at':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
pathlib.Path(out).write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n')
PY
chown "$OP_UID:$OP_GID" "$SCHEMA_RECEIPT"; chmod 0600 "$SCHEMA_RECEIPT"
SCHEMA_SHA="$(sha256sum "$SCHEMA_RECEIPT" | awk '{print $1}')"

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" "$DOCKER_CONFIG_DIR"
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" >/dev/null 2>&1 || \
  runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context create "$DOCKER_CONTEXT" --docker host=unix:///var/run/docker.sock >/dev/null
chown -R "$OP_UID:$OP_GID" "$DOCKER_CONFIG_DIR"; chmod 0700 "$DOCKER_CONFIG_DIR"

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
ln -sfn /etc/nginx/sites-available/edfinder-v3-checkpoint /etc/nginx/sites-enabled/edfinder-v3-checkpoint
nginx -t >/dev/null
systemctl enable --now nginx >/dev/null
systemctl reload nginx

for svc in "${RUNNERS[@]}"; do systemctl is-active --quiet "$svc" || fail "runner changed during provisioning: $svc"; done
docker version >/dev/null
docker compose version >/dev/null
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" --format '{{json .Endpoints.docker.Host}}' | grep -qx '"unix:///var/run/docker.sock"' || fail "local Docker context verification failed"

AUTHORITY_SOURCE="deploy/v3-live-checkpoint/target-authority.json"
python3 - "$AUTHORITY_SOURCE" "$OP_UID" "$SCHEMA_SHA" "$NETWORK_GATEWAY" <<'PY'
import datetime,json,os,pathlib,subprocess,sys
src,uid,schema_sha,gateway=sys.argv[1:]; uid=int(uid)
a=json.loads(pathlib.Path(src).read_text())
a['status']='authorized'; a['blockers']=[]; a['observed_at']=datetime.date.today().isoformat()
r=a['observed_runtime']
r['container_runtime']=subprocess.check_output(['docker','--version'],text=True).strip()
r['compose']=subprocess.check_output(['docker','compose','version'],text=True).strip()
r['container_names']=subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
r['docker_networks']=subprocess.check_output(['docker','network','ls','--format','{{.Name}}'],text=True).splitlines()
r['docker_volumes']=subprocess.check_output(['docker','volume','ls','--format','{{.Name}}'],text=True).splitlines()
r['checkpoint_directories_found_under_opt_srv_var_lib']=['/var/lib/edfinder-v3-checkpoint']
a['external_authority']={
 'api_env_file':'/etc/edfinder-v3-checkpoint/api.env','api_env_owner_uid':uid,'api_env_mode':'0600',
 'database_source_authority':'contabo-local-postgresql18-preview-seed-v1',
 'schema_identity_receipt':'/var/lib/edfinder-v3-checkpoint/schema-identity.json','schema_identity_receipt_sha256':schema_sha,
 'origin_bind':'http://127.0.0.1:18080','edge_route_authority':'nginx-vmi3542235-http80-to-loopback-18080',
 'receipt_directory':'/var/lib/edfinder-v3-checkpoint/receipts','receipt_owner_uid':uid,'receipt_mode':'0700',
 'ghcr_pull_authority':'ephemeral-github-actions-token-via-v3-live-checkpoint-deploy',
 'docker_config_directory':'/var/lib/edfinder-v3-checkpoint/docker-config','docker_config_owner_uid':uid,'docker_config_mode':'0700',
 'docker_context':'edfinder-v3-checkpoint-local'}
print(json.dumps(a,sort_keys=True,indent=2))
PY
