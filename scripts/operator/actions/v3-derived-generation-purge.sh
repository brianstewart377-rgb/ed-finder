#!/usr/bin/env bash
# P2b2b local entry point. No workflow/dispatch or deployment authority is added.
set -euo pipefail
if command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
else
  printf '%s\n' '{"schema_version":"ed-finder/derived-generation-purge/v1","operation":"v3-derived-generation-purge","status":"stopped","failures":["python314_required"],"db_writes_performed":false,"canonical_writes_performed":false,"pointer_changes_performed":false,"publication_performed":false,"service_changes_performed":false,"filesystem_reclamation_performed":false,"migration_execution_performed":false,"application_deployment_performed":false}'
  exit 1
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/../lib/v3_generation_purge.py" "$@"
