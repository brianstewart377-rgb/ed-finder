#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="ed-finder-prod"
REPO_DIR="/opt/ed-finder"
SERVICE_USER="ed-mcp"
SERVICE_NAME="ed-finder-operator-mcp.service"
VENV_DIR="/opt/ed-finder/.venv-operator-mcp"
SUDOERS_FILE="/etc/sudoers.d/ed-finder-operator-mcp"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}"
MCP_PORT="8765"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || stop "run as root"
[[ "$(hostname 2>/dev/null || true)" == "$EXPECTED_HOSTNAME" ]] || \
  stop "wrong host; expected $EXPECTED_HOSTNAME"
[[ "$(pwd -P)" == "$REPO_DIR" ]] || stop "run from $REPO_DIR"
[[ -d .git ]] || stop "git repository not found"
[[ "$(git branch --show-current)" == "infra/multi-target-operator-mcp" ]] || \
  stop "expected branch infra/multi-target-operator-mcp"
[[ -z "$(git status --porcelain)" ]] || stop "working tree is not clean"

printf '== Updating operator branch ==\n'
git pull --ff-only origin infra/multi-target-operator-mcp

printf '\n== Installing host prerequisites ==\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv sudo curl

printf '\n== Creating service account ==\n'
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/ed-mcp --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

printf '\n== Preparing Python environment ==\n'
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r services/operator-mcp/requirements.txt

printf '\n== Installing locked dispatcher permissions ==\n'
chown root:root scripts/operator/mcp-root-dispatch.sh
chmod 0755 scripts/operator/mcp-root-dispatch.sh
cat >"$SUDOERS_FILE" <<EOF
${SERVICE_USER} ALL=(root) NOPASSWD: ${REPO_DIR}/scripts/operator/mcp-root-dispatch.sh
EOF
chmod 0440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE" >/dev/null

printf '\n== Installing systemd service ==\n'
cat >"$UNIT_FILE" <<EOF
[Unit]
Description=ED-Finder read-only MevSpace operator MCP
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
Environment=EDFINDER_REPO_DIR=${REPO_DIR}
Environment=EDFINDER_MCP_PORT=${MCP_PORT}
ExecStart=${VENV_DIR}/bin/python ${REPO_DIR}/services/operator-mcp/server.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=false
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/ed-mcp

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

printf '\n== Smoke tests ==\n'
sleep 2
systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,12p'
printf '\nListening socket:\n'
ss -ltnp | grep "127.0.0.1:${MCP_PORT}" || stop "MCP service is not listening on localhost:${MCP_PORT}"
printf '\nHTTP endpoint probe:\n'
http_code="$(curl -sS -o /tmp/ed-mcp-probe.out -w '%{http_code}' --max-time 5 "http://127.0.0.1:${MCP_PORT}/mcp" || true)"
printf 'GET /mcp -> HTTP %s\n' "$http_code"
case "$http_code" in
  200|400|405|406) ;;
  *)
    cat /tmp/ed-mcp-probe.out 2>/dev/null || true
    stop "unexpected MCP endpoint response"
    ;;
esac

printf '\nRead-only dispatcher smoke test as %s:\n' "$SERVICE_USER"
sudo -u "$SERVICE_USER" sudo -n "$REPO_DIR/scripts/operator/mcp-root-dispatch.sh" pg18-lab-status

printf '\nOK: ED-Finder MevSpace operator MCP bootstrap completed.\n'
printf 'Endpoint is localhost-only: http://127.0.0.1:%s/mcp\n' "$MCP_PORT"
printf 'No firewall or public-listener changes were made.\n'
