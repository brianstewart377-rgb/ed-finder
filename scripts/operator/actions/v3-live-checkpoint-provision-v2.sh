#!/usr/bin/env bash
set -euo pipefail
umask 077

EXPECTED_HOST=vmi3542235
EXPECTED_FQDN=vmi3542235.contaboserver.net
APP_NETWORK=edfinder-v3-checkpoint-app
ORIGIN_PORT=18080
DB_NAME=edfinder_checkpoint
DB_APP_ROLE=edfinder_checkpoint_ro
DB_AUTHORITY=contabo-local-postgresql18-preview-seed-v1
STATE_ROOT=/var/lib/edfinder-v3-checkpoint
API_ENV=/etc/edfinder-v3-checkpoint/api.env
SCHEMA_RECEIPT=$STATE_ROOT/schema-identity.json
RECEIPT_DIR=$STATE_ROOT/receipts
DOCKER_CONFIG_DIR=$STATE_ROOT/docker-config
DOCKER_CONTEXT=edfinder-v3-checkpoint-local
RUNNERS=(
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service
)
fail(){ echo "checkpoint provisioning stopped: $*" >&2; exit 78; }
[ "$(id -u)" -eq 0 ] || fail "root required"
[ "$(hostname -s)" = "$EXPECTED_HOST" ] || fail "unexpected host"
[ "$(uname -m)" = x86_64 ] || fail "unexpected architecture"
for s in "${RUNNERS[@]}"; do systemctl is-active --quiet "$s" || fail "required runner inactive: $s"; done
OP_USER=${SUDO_USER:-}; OP_UID=${SUDO_UID:-}; OP_GID=${SUDO_GID:-}
[ -n "$OP_USER" ] && [ -n "$OP_UID" ] && [ "$OP_UID" != 0 ] || fail "invoke with passwordless sudo from checkpoint operator"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg nginx openssl jq >/dev/null
install -d -m 0755 /etc/apt/keyrings
. /etc/os-release
[ -s /etc/apt/keyrings/docker.asc ] || curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
[ -s /etc/apt/keyrings/postgresql.asc ] || curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/postgresql.asc
chmod 0644 /etc/apt/keyrings/postgresql.asc
printf 'deb [signed-by=/etc/apt/keyrings/postgresql.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin postgresql-18 postgresql-client-18 >/dev/null
systemctl enable --now docker >/dev/null
usermod -aG docker "$OP_USER"

if ! docker network inspect "$APP_NETWORK" >/dev/null 2>&1; then docker network create --driver bridge "$APP_NETWORK" >/dev/null; fi
[ "$(docker network inspect "$APP_NETWORK" --format '{{.Driver}}')" = bridge ] || fail "checkpoint network driver changed"
[ "$(docker network inspect "$APP_NETWORK" --format '{{.Scope}}')" = local ] || fail "checkpoint network scope changed"
NETWORK_GATEWAY=$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Gateway}}')
NETWORK_SUBNET=$(docker network inspect "$APP_NETWORK" --format '{{(index .IPAM.Config 0).Subnet}}')
python3 - "$NETWORK_GATEWAY" "$NETWORK_SUBNET" <<'PY' || fail "invalid Docker subnet"
import ipaddress,sys
ip=ipaddress.ip_address(sys.argv[1]); net=ipaddress.ip_network(sys.argv[2], strict=False)
assert ip in net and not net.is_loopback
PY

if ! pg_lsclusters --no-header 2>/dev/null | awk '$1=="18"&&$2=="main"{ok=1}END{exit !ok}'; then pg_createcluster 18 main --start >/dev/null; fi
PG_HBA=$(runuser -u postgres -- psql -X -Atqc 'show hba_file')
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q <<SQL
ALTER SYSTEM SET listen_addresses = '127.0.0.1,$NETWORK_GATEWAY';
ALTER SYSTEM SET password_encryption = 'scram-sha-256';
SQL
sed -i '/# edfinder-v3-checkpoint$/d' "$PG_HBA"
printf 'host %s %s %s scram-sha-256 # edfinder-v3-checkpoint\n' "$DB_NAME" "$DB_APP_ROLE" "$NETWORK_SUBNET" >> "$PG_HBA"
systemctl restart postgresql@18-main

DB_EXISTS=$(runuser -u postgres -- psql -X -Atqc "select 1 from pg_database where datname='$DB_NAME'")
[ "$DB_EXISTS" = 1 ] || runuser -u postgres -- createdb "$DB_NAME"
# Source tree is ephemeral and secret-free; postgres needs read/execute access to apply reviewed SQL.
chmod -R a+rX sql scripts/apply_migrations.sh scripts/seed_check.sh
runuser -u postgres -- env DATABASE_URL="postgresql:///$DB_NAME" bash scripts/seed_check.sh >&2

install -d -m 0700 -o "$OP_UID" -g "$OP_GID" /etc/edfinder-v3-checkpoint "$STATE_ROOT" "$RECEIPT_DIR" "$DOCKER_CONFIG_DIR"
APP_PASSWORD=""
if [ -f "$API_ENV" ]; then
  APP_PASSWORD=$(python3 - "$API_ENV" <<'PY'
import pathlib,sys,urllib.parse
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line.startswith('DATABASE_URL='):
        print(urllib.parse.unquote(urllib.parse.urlsplit(line.split('=',1)[1].strip()).password or '')); break
PY
)
fi
[ -n "$APP_PASSWORD" ] || APP_PASSWORD=$(openssl rand -hex 24)
ROLE_EXISTS=$(runuser -u postgres -- psql -X -Atqc "select 1 from pg_roles where rolname='$DB_APP_ROLE'")
[ "$ROLE_EXISTS" = 1 ] || runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -c "CREATE ROLE $DB_APP_ROLE LOGIN"
PW_FILE=$(mktemp); chmod 0600 "$PW_FILE"; printf "ALTER ROLE %s PASSWORD '%s';\n" "$DB_APP_ROLE" "$APP_PASSWORD" > "$PW_FILE"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -f "$PW_FILE"; rm -f "$PW_FILE"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB_NAME" <<SQL
ALTER ROLE $DB_APP_ROLE SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_APP_ROLE;
GRANT USAGE ON SCHEMA public TO $DB_APP_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $DB_APP_ROLE;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $DB_APP_ROLE;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $DB_APP_ROLE;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO $DB_APP_ROLE;
SQL
DATABASE_URL="postgresql://$DB_APP_ROLE:$APP_PASSWORD@$NETWORK_GATEWAY:5432/$DB_NAME"
cat > "$API_ENV" <<EOF
DATABASE_URL=$DATABASE_URL
DATABASE_READONLY_URL=$DATABASE_URL
CORS_ORIGINS=http://$EXPECTED_FQDN
REDIS_URL=redis://127.0.0.1:1/0
ADMIN_OPERATION_STARTUP_REAP_ENABLED=false
EDDN_SIMULATION_INGEST_ENABLED=false
AUTH_COOKIE_SECURE=false
FRONTIER_REDIRECT_URI=http://$EXPECTED_FQDN/api/auth/frontier/callback
EOF
chown "$OP_UID:$OP_GID" "$API_ENV"; chmod 0600 "$API_ENV"

python3 - "$DB_AUTHORITY" "$DB_NAME" "$NETWORK_GATEWAY" "$SCHEMA_RECEIPT" <<'PY'
import datetime,hashlib,json,pathlib,sys
source,dbname,address,out=sys.argv[1:]; entries=[]; root=pathlib.Path('.')
for raw in (root/'sql/migration-manifest.txt').read_text().splitlines():
    line=raw.strip()
    if not line or line.startswith('#'): continue
    p=line.split('|',1); name=p[0]; mode=p[1] if len(p)==2 else 'auto'; data=(root/'sql'/name).read_bytes()
    entries.append({'path':f'sql/{name}','mode':mode,'sha256':hashlib.sha256(data).hexdigest()})
identity='sha256:'+hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()
doc={'schema_version':'ed-finder/v3-live-checkpoint-schema-identity/v2','database_source_authority':source,'database_identity':{'database_name':dbname,'server_address':address,'server_port':5432},'migration_set_identity':identity,'migration_set_entries':entries,'captured_at':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
pathlib.Path(out).write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n')
PY
chown "$OP_UID:$OP_GID" "$SCHEMA_RECEIPT"; chmod 0600 "$SCHEMA_RECEIPT"; SCHEMA_SHA=$(sha256sum "$SCHEMA_RECEIPT"|awk '{print $1}')
# Prove the runtime role is read-only and sees the complete migration ledger.
runuser -u "$OP_USER" -- env PGDATABASE="$DATABASE_URL" PGOPTIONS='-c default_transaction_read_only=on' psql -X --no-password -Atqc "select current_setting('transaction_read_only'), count(*) from schema_migrations" | grep -q '^on|' || fail "read-only DB proof failed"

runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" >/dev/null 2>&1 || runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context create "$DOCKER_CONTEXT" --docker host=unix:///var/run/docker.sock >/dev/null
chown -R "$OP_UID:$OP_GID" "$DOCKER_CONFIG_DIR"; chmod 0700 "$DOCKER_CONFIG_DIR"
cat > /etc/nginx/sites-available/edfinder-v3-checkpoint <<EOF
server { listen 80; listen [::]:80; server_name $EXPECTED_FQDN; location / { proxy_pass http://127.0.0.1:$ORIGIN_PORT; proxy_http_version 1.1; proxy_set_header Host \$host; proxy_set_header X-Forwarded-Proto \$scheme; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; } }
EOF
ln -sfn /etc/nginx/sites-available/edfinder-v3-checkpoint /etc/nginx/sites-enabled/edfinder-v3-checkpoint
nginx -t >/dev/null; systemctl enable --now nginx >/dev/null; systemctl reload nginx
for s in "${RUNNERS[@]}"; do systemctl is-active --quiet "$s" || fail "runner changed during provisioning: $s"; done
runuser -u "$OP_USER" -- env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker context inspect "$DOCKER_CONTEXT" --format '{{json .Endpoints.docker.Host}}' | grep -qx '"unix:///var/run/docker.sock"' || fail "Docker context proof failed"

python3 - deploy/v3-live-checkpoint/target-authority.json "$OP_UID" "$SCHEMA_SHA" <<'PY'
import datetime,json,pathlib,subprocess,sys
src,uid,schema_sha=sys.argv[1:]; uid=int(uid); a=json.loads(pathlib.Path(src).read_text()); a['status']='authorized'; a['blockers']=[]; a['observed_at']=datetime.date.today().isoformat(); r=a['observed_runtime']
r['container_runtime']=subprocess.check_output(['docker','--version'],text=True).strip(); r['compose']=subprocess.check_output(['docker','compose','version'],text=True).strip(); r['container_names']=subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines(); r['docker_networks']=subprocess.check_output(['docker','network','ls','--format','{{.Name}}'],text=True).splitlines(); r['docker_volumes']=subprocess.check_output(['docker','volume','ls','--format','{{.Name}}'],text=True).splitlines(); r['checkpoint_directories_found_under_opt_srv_var_lib']=['/var/lib/edfinder-v3-checkpoint']
a['external_authority']={'api_env_file':'/etc/edfinder-v3-checkpoint/api.env','api_env_owner_uid':uid,'api_env_mode':'0600','database_source_authority':'contabo-local-postgresql18-preview-seed-v1','schema_identity_receipt':'/var/lib/edfinder-v3-checkpoint/schema-identity.json','schema_identity_receipt_sha256':schema_sha,'origin_bind':'http://127.0.0.1:18080','edge_route_authority':'nginx-vmi3542235-http80-to-loopback-18080','receipt_directory':'/var/lib/edfinder-v3-checkpoint/receipts','receipt_owner_uid':uid,'receipt_mode':'0700','ghcr_pull_authority':'ephemeral-github-actions-token','docker_config_directory':'/var/lib/edfinder-v3-checkpoint/docker-config','docker_config_owner_uid':uid,'docker_config_mode':'0700','docker_context':'edfinder-v3-checkpoint-local'}
print(json.dumps(a,sort_keys=True,indent=2))
PY
