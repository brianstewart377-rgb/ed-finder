#!/usr/bin/env bash
set -euo pipefail

stage="${1:-}"

case "$stage" in
  context)
    exec bash scripts/operator/targets/mevspace/actions/context.sh
    ;;
  docker-status)
    exec bash scripts/operator/targets/mevspace/actions/docker-status.sh
    ;;
  pg18-lab-status)
    exec bash scripts/operator/targets/mevspace/actions/pg18-lab-status.sh
    ;;
  pg18-lab-logs)
    exec bash scripts/operator/targets/mevspace/actions/pg18-lab-logs.sh
    ;;
  pg18-lab-settings)
    exec bash scripts/operator/targets/mevspace/actions/pg18-lab-settings.sh
    ;;
  *)
    echo "STOP: unsupported MevSpace operator stage: ${stage:-<missing>}" >&2
    echo "Allowed stages: context, docker-status, pg18-lab-status, pg18-lab-logs, pg18-lab-settings" >&2
    exit 1
    ;;
esac
