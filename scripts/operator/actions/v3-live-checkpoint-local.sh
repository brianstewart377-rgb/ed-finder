#!/usr/bin/env bash
# Fixed operations on the already-connected Contabo runner; never a remote shell.
set -euo pipefail
umask 077

verify_local_identity() {
  [ "$(hostname -s)" = vmi3542235 ] || { echo 'Unexpected checkpoint host' >&2; return 78; }
  [ "$(uname -m)" = x86_64 ] || { echo 'Unexpected checkpoint architecture' >&2; return 78; }
  [ "$(id -un)" = codex ] && [ "$(id -u)" = 1001 ] && [ "$(id -g)" = 1001 ] || {
    echo 'Unexpected checkpoint operator' >&2; return 78;
  }
  python3.14 - <<'PY'
import platform, socket, sys
assert platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 14)
assert socket.getfqdn() == 'vmi3542235.contaboserver.net'
PY
  local actual expected
  actual="$(systemctl list-units --type=service --state=active --no-legend --plain 'actions.runner.*.service' | awk '{print $1}' | sort)"
  expected="$(printf '%s\n' \
    actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service \
    actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service \
    actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service | sort)"
  [ "$actual" = "$expected" ] || { echo 'Unexpected checkpoint runner topology' >&2; return 78; }
}

verify_local_request() {
  [ "${GITHUB_REPOSITORY:-}" = brianstewart377-rgb/ed-finder ] && [ "${GITHUB_REF:-}" = refs/heads/main ] || {
    echo 'Local checkpoint operations require trusted main' >&2; return 78;
  }
  [[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || return 78
  [ "$(git rev-parse HEAD)" = "$GITHUB_SHA" ] || { echo 'Checkpoint checkout SHA changed' >&2; return 78; }
  case "${1:-}" in
    provision) [ "$#" = 1 ] && [ "${GITHUB_EVENT_NAME:-}" = issue_comment ] || return 64 ;;
    deploy)
      [ "$#" = 3 ] && [ "${GITHUB_EVENT_NAME:-}" = workflow_dispatch ] || return 64
      [[ "$2" = bootstrap || "$2" = upgrade ]] && [[ "$3" =~ ^[1-9][0-9]{0,19}$ ]] || return 64
      ;;
    *) echo 'Unsupported local checkpoint operation' >&2; return 64 ;;
  esac
}

# Function definitions above are exercised with stubs by the regression tests.
export PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset BASH_ENV ENV PYTHONPATH PYTHONHOME
verify_local_request "$@"
verify_local_identity
work="$(mktemp -d /tmp/edfinder-v3-checkpoint.XXXXXXXXXX)"
logged_in=false
cleanup() {
  local result="$?"
  if [ "$logged_in" = true ]; then
    if ! sudo -n -u codex -- env -i PATH="$PATH" HOME=/home/codex \
      DOCKER_CONFIG=/var/lib/edfinder-v3-checkpoint/docker-config \
      DOCKER_CONTEXT=edfinder-v3-checkpoint-local docker logout ghcr.io >/dev/null 2>&1; then
      echo 'Unable to clear ephemeral checkpoint registry authentication' >&2
      result=78
    fi
  fi
  rm -rf -- "$work"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

if [ "$1" = provision ]; then
  # Archive immutable committed objects, not the mutable coding worktree.
  git archive "$GITHUB_SHA" \
    scripts/operator/actions/v3-live-checkpoint-provision.sh \
    scripts/apply_migrations.sh scripts/seed_check.sh sql \
    deploy/v3-live-checkpoint/target-authority.json | tar -x -C "$work"
  chmod -R a+rX "$work"
  cd "$work"
  sudo -n env -i PATH="$PATH" HOME=/root \
    CHECKPOINT_OPERATOR_UID=1001 CHECKPOINT_OPERATOR_GID=1001 CHECKPOINT_OPERATOR_USER=codex \
    bash scripts/operator/actions/v3-live-checkpoint-provision.sh
else
  test -n "${GHCR_TOKEN:-}" || { echo 'Missing ephemeral registry token' >&2; exit 78; }
  git archive "$GITHUB_SHA" \
    deploy/v3-live-checkpoint/compose.yml deploy/v3-live-checkpoint/target-authority.json \
    scripts/operator/v3_checkpoint_deploy.py \
    scripts/operator/actions/v3-app-live-checkpoint-preflight.sh \
    scripts/release/v3_release_manifest.py | tar -x -C "$work"
  install -d -m 700 "$work/artifacts/candidate"
  install -m 600 "$RUNNER_TEMP/candidate/v3-application-release.json" \
    "$RUNNER_TEMP/candidate/v3-application-release.json.sha256" "$work/artifacts/candidate/"
  # A fresh non-root process obtains the Docker group added by provisioning.
  # None of the three existing runner services is restarted or reconfigured.
  logged_in=true
  printf '%s' "$GHCR_TOKEN" | sudo -n -u codex -- env -i PATH="$PATH" HOME=/home/codex \
    DOCKER_CONFIG=/var/lib/edfinder-v3-checkpoint/docker-config \
    DOCKER_CONTEXT=edfinder-v3-checkpoint-local \
    docker login ghcr.io -u brianstewart377-rgb --password-stdin >/dev/null
  unset GHCR_TOKEN
  cd "$work"
  sudo -n -u codex -- env -i PATH="$PATH" HOME=/home/codex \
    bash scripts/operator/actions/v3-app-live-checkpoint-preflight.sh \
    --mode "$2" --candidate-run-id "$3" \
    --candidate artifacts/candidate/v3-application-release.json \
    --candidate-checksum artifacts/candidate/v3-application-release.json.sha256
fi
