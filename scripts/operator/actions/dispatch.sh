#!/usr/bin/env bash
set -euo pipefail

stage="${1:-}"

case "$stage" in
  context)
    exec bash scripts/operator/actions/context.sh
    ;;
  git-clean-check)
    exec bash scripts/operator/actions/git-clean-check.sh
    ;;
  latest-artifacts)
    exec bash scripts/operator/actions/latest-artifacts.sh
    ;;
  latest-stage18j-summary)
    exec bash scripts/operator/actions/latest-stage18j-summary.sh
    ;;
  *)
    echo "STOP: unsupported operator stage: $stage" >&2
    exit 1
    ;;
esac
