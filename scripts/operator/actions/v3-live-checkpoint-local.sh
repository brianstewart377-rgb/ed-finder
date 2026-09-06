#!/usr/bin/env bash
# Executed ONLY inside the root-owned, checksum-verified operation bundle.
set -euo pipefail
umask 077
export PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[ "$(id -u)" = 0 ] || { echo 'Immutable root bootstrap required' >&2; exit 78; }
[ "$(stat -c %u .)" = 0 ] && [ "$(stat -c %a .)" = 755 ] || exit 78
[ "$(hostname -s)" = vmi3542235 ] && [ "$(uname -m)" = x86_64 ] || exit 78
OP_UID="$(id -u codex)"
OP_GID="$(id -g codex)"
[ "$OP_UID" -gt 0 ] && [ "$OP_GID" -gt 0 ] || exit 78
actual="$(systemctl list-units --type=service --state=active --no-legend --plain 'actions.runner.*.service' | awk '{print $1}' | sort)"
expected="$(printf '%s\n' \
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service \
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service \
  actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service | sort)"
[ "$actual" = "$expected" ] || { echo 'Unexpected checkpoint runner topology' >&2; exit 78; }
# OS Python is used only to parse sealed bootstrap data before provisioning 3.14.
operation="$(/usr/bin/python3 -I -S -c 'import json; print(json.load(open("operation.json"))["operation"])')"
if [ "$operation" = provision ]; then
  exec env -i PATH="$PATH" HOME=/root \
    CHECKPOINT_OPERATOR_UID="$OP_UID" CHECKPOINT_OPERATOR_GID="$OP_GID" CHECKPOINT_OPERATOR_USER=codex \
    /bin/bash scripts/operator/actions/v3-live-checkpoint-provision.sh
fi
[ "$operation" = deploy ] || exit 64
python3.14 -I -S -c 'import platform,sys; assert platform.python_implementation()=="CPython" and sys.version_info[:2]==(3,14)'
mode="$(python3.14 -I -S -c 'import json; print(json.load(open("operation.json"))["mode"])')"
run_id="$(python3.14 -I -S -c 'import json; print(json.load(open("operation.json"))["release_run_id"])')"
[[ "$mode" = bootstrap || "$mode" = upgrade ]] && [[ "$run_id" =~ ^[1-9][0-9]{0,19}$ ]] || exit 64
test -n "${GHCR_TOKEN:-}" || exit 78
logged_in=false
cleanup() {
  result="$?"
  if [ "$logged_in" = true ]; then
    runuser -u codex -- env -i PATH="$PATH" HOME=/home/codex \
      DOCKER_CONFIG=/var/lib/edfinder-v3-checkpoint/docker-config \
      DOCKER_CONTEXT=edfinder-v3-checkpoint-local docker logout ghcr.io >/dev/null 2>&1 || result=78
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
logged_in=true
printf '%s' "$GHCR_TOKEN" | runuser -u codex -- env -i PATH="$PATH" HOME=/home/codex \
  DOCKER_CONFIG=/var/lib/edfinder-v3-checkpoint/docker-config \
  DOCKER_CONTEXT=edfinder-v3-checkpoint-local \
  docker login ghcr.io -u brianstewart377-rgb --password-stdin >/dev/null
unset GHCR_TOKEN
# Fresh non-root child obtains current supplementary groups without restarting runners.
runuser -u codex -- env -i PATH="$PATH" HOME=/home/codex \
  /bin/bash scripts/operator/actions/v3-app-live-checkpoint-preflight.sh \
  --mode "$mode" --candidate-run-id "$run_id" \
  --candidate artifacts/candidate/v3-application-release.json \
  --candidate-checksum artifacts/candidate/v3-application-release.json.sha256
