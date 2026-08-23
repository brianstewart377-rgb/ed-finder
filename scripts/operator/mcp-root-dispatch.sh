#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="ed-finder-prod"
REPO_DIR="/opt/ed-finder"
stage="${1:-}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  exit 1
}

[[ "$(hostname 2>/dev/null || true)" == "$EXPECTED_HOSTNAME" ]] || \
  stop "wrong host; expected $EXPECTED_HOSTNAME"
[[ -d "$REPO_DIR/.git" ]] || stop "repo missing at $REPO_DIR"

case "$stage" in
  context|docker-status|pg18-lab-status|pg18-lab-settings)
    [[ "$#" -eq 1 ]] || stop "$stage accepts no arguments"
    ;;
  pg18-lab-logs)
    [[ "$#" -le 2 ]] || stop "pg18-lab-logs accepts at most one line-count argument"
    lines="${2:-100}"
    case "$lines" in
      ''|*[!0-9]*) stop "log line count must be an integer" ;;
    esac
    (( lines >= 1 && lines <= 500 )) || stop "log line count must be between 1 and 500"
    export PG18_LOG_LINES="$lines"
    ;;
  *)
    stop "unsupported MCP operator stage: ${stage:-<missing>}"
    ;;
esac

cd "$REPO_DIR"
exec /bin/bash scripts/operator/dispatch-target.sh mevspace "$stage"
