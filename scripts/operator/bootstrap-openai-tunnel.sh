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
RELEASE="v0.0.10"
ASSET="tunnel-client-${RELEASE}-linux-amd64.zip"

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
ss -ltn | grep -q '127.0.0.1:8765' || stop "operator MCP is not listening on 127.0.0.1:8765"

printf '== Installing tunnel-client prerequisites ==\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates

if [[ -x "$BIN" ]] && "$BIN" --version 2>/dev/null | grep -q '^0\.0\.10+'; then
  printf '\n== Reusing installed tunnel-client %s ==\n' "$RELEASE"
  "$BIN" --version
else
  printf '\n== Downloading official tunnel-client %s ==\n' "$RELEASE"
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  base="https://github.com/openai/tunnel-client/releases/download/${RELEASE}"
  curl -fL --retry 3 --retry-delay 2 "$base/$ASSET" -o "$tmpdir/$ASSET"
  curl -fL --retry 3 --retry-delay 2 "$base/SHA256SUMS.txt" -o "$tmpdir/SHA256SUMS.txt"
  expected="$(awk -v asset="$ASSET" '$2==asset || $2=="*"asset {print $1; exit}' "$tmpdir/SHA256SUMS.txt")"
  [[ -n "$expected" ]] || stop "$ASSET checksum not found in release manifest"
  actual="$(sha256sum "$tmpdir/$ASSET" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || stop "tunnel-client checksum mismatch"
  unzip -q "$tmpdir/$ASSET" -d "$tmpdir/unpacked"
  client_path="$(find "$tmpdir/unpacked" -type f -name tunnel-client -print -quit)"
  [[ -n "$client_path" ]] || stop "tunnel-client binary not found in archive"
  install -o root -g root -m 0755 "$client_path" "$BIN"
  "$BIN" --version
fi

install -d -o root -g root -m 0700 "$SECRET_DIR"
if [[ -s "$SECRET_FILE" ]] && grep -q '^CONTROL_PLANE_API_KEY=.' "$SECRET_FILE"; then
  printf '\n== Runtime API key ==\n'
  printf 'Reusing existing root-only runtime API key from %s.\n' "$SECRET_FILE"
else
  printf '\n== Runtime API key ==\n'
  printf 'Paste the OpenAI Runtime API key with Tunnels Read + Use. Input will not be echoed.\n'
  IFS= read -r -s -p 'Runtime API key: ' runtime_key
  printf '\n'
  [[ -n "$runtime_key" ]] || stop "runtime API key was empty"
  umask 077
  printf 'CONTROL_PLANE_API_KEY=%s\n' "$runtime_key" > "$SECRET_FILE"
  unset runtime_key
  chmod 0600 "$SECRET_FILE"
  chown root:root "$SECRET_FILE"
fi

printf '\n== Running tunnel-client preflight ==\n'
set -a
# shellcheck disable=SC1090
source "$SECRET_FILE"
set +a
export CONTROL_PLANE_TUNNEL_ID="$TUNNEL_ID"
export MCP_SERVER_URL="$MCP_URL"
export HEALTH_LISTEN_ADDR="$HEALTH_ADDR"
set +e
doctor_output="$("$BIN" doctor --explain 2>&1)"
doctor_rc=$?
set -e
printf '%s\n' "$doctor_output"
if (( doctor_rc != 0 )); then
  if printf '%s\n' "$doctor_output" | grep -qx 'FAILED_CHECKS oauth_metadata' \
     && printf '%s\n' "$doctor_output" | grep -q 'HTTP 404'; then
    printf '\nNOTE: OAuth metadata 404 is expected for this intentionally no-auth localhost MCP.\n'
    printf 'The official no-auth tunnel profile allows readiness when PRMD candidates return 404.\n'
  else
    unset CONTROL_PLANE_API_KEY CONTROL_PLANE_TUNNEL_ID MCP_SERVER_URL HEALTH_LISTEN_ADDR
    stop "tunnel-client preflight failed for a reason other than the expected no-auth OAuth 404"
  fi
fi
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
