#!/usr/bin/env bash
#
# Highest-value local CI parity checks for Stage 19 work.
#
# This is intentionally fail-fast and non-destructive. It does not connect to
# production DBs, does not run imports, does not run migrations against
# production, and does not enable timers/schedulers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

section() {
  printf '\n==> %s\n' "$1"
}

die() {
  printf 'local-ci-parity: %s\n' "$*" >&2
  exit 1
}

pick_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
  elif [ -x "$ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
  elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
    printf '%s\n' "$ROOT/.venv/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die "missing Python. Create .venv or set PYTHON=/path/to/python."
  fi
}

pick_yarn() {
  if [ -n "${YARN:-}" ]; then
    printf '%s\n' "$YARN"
  elif command -v yarn >/dev/null 2>&1; then
    command -v yarn
  elif command -v yarn.cmd >/dev/null 2>&1; then
    command -v yarn.cmd
  else
    die "missing yarn. Install Node/Yarn before running frontend checks."
  fi
}

require_python_module() {
  "$PYTHON_BIN" - "$1" <<'PY'
import importlib.util
import sys

name = sys.argv[1]
if importlib.util.find_spec(name) is None:
    raise SystemExit(1)
PY
}

PYTHON_BIN="$(pick_python)"
YARN_BIN="$(pick_yarn)"

section "Dependency check"
require_python_module pytest || die "missing Python module pytest. Install test dependencies before running parity checks."
if [ ! -d "$ROOT/frontend-v2/node_modules" ]; then
  die "frontend-v2/node_modules is missing. Run 'cd frontend-v2 && yarn install' first."
fi
printf 'Python: %s\n' "$PYTHON_BIN"
printf 'Yarn:   %s\n' "$YARN_BIN"

section "Backend Python compile"
(
  cd "$ROOT"
  "$PYTHON_BIN" -m compileall -q apps scripts tests
)

section "Stage 19 static safety guardrails"
(
  cd "$ROOT"
  "$PYTHON_BIN" scripts/checks/stage19-safety-guardrails.py
)

section "Stage 19/source-run/operator focused tests"
(
  cd "$ROOT"
  "$PYTHON_BIN" -m pytest \
    tests/test_source_run_compatibility.py \
    tests/test_edsm_station_import.py \
    tests/test_source_run_artifacts.py \
    tests/test_artifact_utils.py \
    tests/test_source_run_ledger.py \
    tests/test_source_runs_migration.py \
    tests/test_stage19ap_operator_visibility.py \
    tests/test_stage19anr_operator_script.py \
    tests/test_stage19as1_disposable_postgres_constraints.py \
    tests/test_stage19as2_operator_script_contract.py \
    tests/test_stage19at_paused_state_next_operator_decision.py \
    tests/test_stage19au_readonly_asau_safety_gate.py \
    tests/test_stage19av_expanded_source_run_staging_pilot.py \
    tests/test_stage19aw_post_av_paused_state_decision.py \
    tests/test_stage19ax_readonly_av_safety_gate.py \
    tests/test_stage19ay_test_environment_closeout.py \
    tests/test_stage20_planning_baseline.py \
    tests/test_stage21_planning_baseline.py \
    tests/test_stage18h1_planner_evidence_contract.py \
    tests/test_stage18h2_warehouse_planner_evidence_endpoint.py \
    tests/test_stage18h3_planner_warehouse_fetch_fallback.py \
    tests/test_stage18h4_warehouse_evidence_ux_clarification.py \
    tests/test_stage18i_canonical_write_design_review.py \
    tests/test_stage18i5_warehouse_database_boundary_review.py \
    tests/test_stage20a_implementation_contract.py \
    tests/test_stage20b_readonly_status_surfaces.py \
    tests/test_stage20c_map_foundation.py \
    tests/test_stage20d_sequence_cp_cockpit.py \
    tests/test_stage20e_export_closeout.py \
    tests/test_stage19aq1_test_fortress_guardrails.py \
    -q
)

section "Frontend operator/API/routing tests"
(
  cd "$ROOT/frontend-v2"
  "$YARN_BIN" test:operator
)

section "Frontend typecheck"
(
  cd "$ROOT/frontend-v2"
  "$YARN_BIN" typecheck
)

section "Frontend build"
(
  cd "$ROOT/frontend-v2"
  "$YARN_BIN" build
)

if [ "${LOCAL_CI_SKIP_OPENAPI:-}" = "1" ]; then
  section "OpenAPI drift check skipped"
  printf 'LOCAL_CI_SKIP_OPENAPI=1 was set. Run scripts/checks/openapi-drift.sh with local PG/Redis before merge when possible.\n'
else
  section "OpenAPI drift check"
  (
    cd "$ROOT"
    bash scripts/checks/openapi-drift.sh
  )
fi

section "Git whitespace check"
(
  cd "$ROOT"
  git diff --check
)

section "Local CI parity passed"
