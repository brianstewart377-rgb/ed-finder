#!/usr/bin/env bash
set -euo pipefail

stage="${1:-}"
artifact_stage="${2:-stage-18j}"

case "$stage" in
  context)
    exec bash scripts/operator/actions/context.sh
    ;;
  git-clean-check)
    exec bash scripts/operator/actions/git-clean-check.sh
    ;;
  latest-artifacts)
    exec bash scripts/operator/actions/latest-artifacts.sh "$artifact_stage"
    ;;
  latest-artifact-summary)
    exec bash scripts/operator/actions/latest-artifact-summary.sh "$artifact_stage"
    ;;
  latest-stage18j-summary)
    exec bash scripts/operator/actions/latest-artifact-summary.sh "stage-18j"
    ;;
  *)
    echo "STOP: unsupported operator stage: $stage" >&2
    exit 1
    ;;
esac
