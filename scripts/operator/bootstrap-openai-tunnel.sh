#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="ed-finder-prod"
REPO_DIR="/opt/ed-finder"
TUNNEL_ID="tunnel_6a8a41fb68008191a23d08a635a08963"
MCP_URL="http://127.0.0.1:8765/mcp"
HEALTH_ADDR="127.0.0.1:8766"
SERVICE_USER="ed-mcp"
SERVICE_NAME="ed-finder-openai-tunnel.service"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}"
SECRET_DIR="/etc/ed-finder"
SECRET_FILE="${SECRET_DIR}/openai-tunnel.env"
BIN="/usr/local/bin/tunnel-client"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

show_service_failure() {
  printf '\n== Tunnel service failure diagnostics ==\n' >&2
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  printf '\n== Recent tunnel journal ==\n' >&2
  journalctl -u "$SERVICE_NAME" -n 100 --no-pager >&2 || true
}

[[ "$(id -u)" -eq 0 ]] || stop "run as root"
[[ "$(hostname 2>/dev/null || true)" == "$EXPECTED_HOSTNAME" ]] || stop "wrong host; expected $EXPECTED_HOSTNAME"
[[ "$(pwd -P)" == "$REPO_DIR" ]] || stop "run from $REPO_DIR"
[[ -d .git ]] || stop "git repository not found"
[[ "$TUNNEL_ID" =~ ^tunnel_[0-9a-f]{32}$ ]] || stop "invalid tunnel id"

systemctl is-active --quiet ed-finder-operator-mcp.service || stop "operator MCP service is not active"
curl -sS -o /dev/null --max-time 5 "$MCP_URL" || true

printf '== Installing tunnel-client prerequisites ==\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates

printf '\n== Downloading latest official tunnel-client release ==\n'
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
base="https://github.com/openai/tunnel-client/releases/latest/download"
curl -fL "$base/linux-amd64.zip" -o "$tmpdir/linux-amd64.zip"
curl -fL "$base/SHA256SUMS.txt" -o "$tmpdir/SHA256SUMS.txt"
expected="$(awk '$2=="linux-amd64.zip" || $2=="*linux-amd64.zip" {print $1; exit}' "$tmpdir/SHA256SUMS.txt")"
[[ -n "$expected" ]] || stop "linux-amd64.zip checksum not found in release manifest"
actual="$(sha256sum "$tmpdir/linux-amd64.zip" | awk '{print $1}')"
[[ "$actual" == "$expected" ]] || stop "tunnel-client checksum mismatch"
unzip -q "$tmpdir/linux-amd64.zip" -d "$tmpdir/unpacked"
client_path="$(find "$tmpdir/unpacked" -type f -name tunnel-client -print -quit)"
[[ -n "$client_path" ]] || stop "tunnel-client binary not found in archive"
install -o root -g root -m 0755 "$client_path" "$BIN"
"$BIN" --version

printf '\n== Runtime API key ==\n'
printf 'Paste the OpenAI Runtime API key with Tunnels Read + Use. Input will not be echoed.\n'
IFS= read -r -s -p 'Runtime API key: ' runtime_key
printf '\n'
[[ -n "$runtime_key" ]] || stop "runtime API key was empty"

install -d -o root -g root -m 0700 "$SECRET_DIR"
umask 077
printf 'CONTROL_PLANE_API_KEY=%s\n' "$runtime_key" > "$SECRET_FILE"
unset runtime_key
chmod 0600 "$SECRET_FILE"
chown root:root "$SECRET_FILE"

printf '\n== Running tunnel-client preflight ==\n'
set -a
# shellcheck disable=SC1090
source "$SECRET_FILE"
set +a
export CONTROL_PLANE_TUNNEL_ID="$TUNNEL_ID"
export MCP_SERVER_URL="$MCP_URL"
export HEALTH_LISTEN_ADDR="$HEALTH_ADDR"
"$BIN" doctor --explain
unset CONTROL_PLANE_API_KEY CONTROL_PLANE_TUNNEL_ID MCP_SERVER_URL HEALTH_LISTEN_ADDR

printf '\n== Installing tunnel systemd service ==\n'
cat >"$UNIT_FILE" <<EOF
[Unit]
Description=ED-Finder OpenAI Secure MCP Tunnel
After=network-online.target ed-finder-operator-mcp.service
Wants=network-online.target
Requires=ed-finder-operator-mcp.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
EnvironmentFile=${SECRET_FILE}
Environment=CONTROL_PLANE_TUNNEL_ID=${TUNNEL_ID}
Environment=MCP_SERVER_URL=${MCP_URL}
Environment=HEALTH_LISTEN_ADDR=${HEALTH_ADDR}
Environment=LOG_LEVEL=info
Environment=LOG_FORMAT=json
ExecStart=${BIN} run
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

printf '\n== Waiting for tunnel readiness ==\n'
ready=no
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://${HEALTH_ADDR}/readyz" >/tmp/ed-tunnel-ready.out 2>/dev/null; then
    ready=yes
    break
  fi
  sleep 1
done

if [[ "$ready" != yes ]]; then
  show_service_failure
  stop "tunnel did not become ready within 30 seconds"
fi

printf '\n== Tunnel status ==\n'
systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,12p'
printf '\nHealth: '
curl -fsS "http://${HEALTH_ADDR}/healthz"
printf '\nReady: '
curl -fsS "http://${HEALTH_ADDR}/readyz"
printf '\n\nListeners:\n'
ss -ltn | grep -E '127\.0\.0\.1:(8765|8766)' || true

printf '\nOK: OpenAI Secure MCP Tunnel is running.\n'
printf 'Tunnel ID: %s\n' "$TUNNEL_ID"
printf 'MCP backend remains localhost-only: %s\n' "$MCP_URL"
printf 'Tunnel health remains localhost-only: http://%s\n' "$HEALTH_ADDR"
printf 'Next: add a ChatGPT connector using Connection = Tunnel and this tunnel ID.\n'
