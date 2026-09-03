#!/usr/bin/env bash
# =============================================================================
# RETIRED — V2 single-host deployment entrypoint
# =============================================================================
#
# This filename is retained as a fail-closed tombstone because historical
# documentation and tests refer to the former deployment path. The Hetzner/V2
# single-host environment is decommissioned. This script intentionally performs
# no git operations, database migrations, Docker actions, frontend builds,
# nginx reloads, health checks, rollback actions, or production deployment.
#
# Current production actions require an explicitly current V3 runbook/workflow
# that identifies the replacement environment and its safety boundary. Start at:
#
#   docs/operations/infrastructure-status.md
#   docs/operations/operator-command-contexts.md
#
# Do not add a compatibility/bypass flag that re-enables the V2 behaviour.
set -euo pipefail

cat >&2 <<'EOF'
[RETIRED] scripts/deploy_main.sh was the V2/Hetzner single-host deployment entrypoint.
It intentionally performs no deployment or production mutation.
Use docs/operations/infrastructure-status.md and an explicitly current V3 operator workflow/runbook.
EOF

exit 64
