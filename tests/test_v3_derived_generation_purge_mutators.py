"""Production mutator entry contracts; no production calls or credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "scripts/operator/actions"
HELPER = ROOT / "scripts/operator/lib/v3-purge-state.sh"
MUTATORS = (
    ("ratings-v4-generation", "start"),
    ("v3-system-search-f1", "start"),
    ("v3-system-search-f1", "finalize"),
    ("v3-system-archetype", "start"),
    ("v3-system-archetype", "finalize"),
    ("v3-archetype-calibration-complete", "start"),
    ("v3-archetype-calibration-probe", "run"),
    ("v3-archetype-plan-probe", "run"),
    ("v3-finder-capacity-gate", "run"),
    ("v3-spatial-pyramid", "build"),
    ("v3-spatial-pyramid", "publish"),
)
FAILURES = (
    "purge_unresolved_BATCH_STARTED",
    "purge_unresolved_REWRITE_STARTED",
    "purge_unresolved_SERVICES_QUIESCED",
    "purge_unresolved_WRITER_FENCE_ENABLED",
    "purge_unresolved_AUTOVACUUM_DISABLED",
    "purge_unresolved_FAILED_STOP",
    "purge_host_lease_held",
)


@pytest.mark.parametrize(("name", "mode"), MUTATORS)
@pytest.mark.parametrize("failure", FAILURES)
def test_mutator_refuses_before_any_operation_side_effect(
    name: str, mode: str, failure: str, tmp_path: Path,
) -> None:
    source = (ACTIONS / f"{name}.sh").read_text()
    gate = f'  require_purge_clear "{name}-{mode}"\n'
    # This is the actual entry prefix, including the target check, before any
    # stage, mutation, lock, credential lookup or worker launch is possible.
    entry = source.split(f"{mode}_operation() {{\n", 1)[1].split(gate, 1)[0]
    assert entry == "  require_target\n"
    require = source.split("require_purge_clear() {\n", 1)[1].split(
        "\nrequire_target() {", 1,
    )[0]
    report = json.dumps({"status": "refused", "failures": [failure]})
    stage = tmp_path / "stage"
    library = stage / "scripts/operator/lib"
    library.mkdir(parents=True)
    (library / HELPER.name).write_text(HELPER.read_text())
    marker = tmp_path / "mutation"
    harness = (
        'set -euo pipefail\nREPO_ROOT="$1"\n'
        'v3_purge_state_check() { printf "%s\\n" "$REPORT"; return 78; }\n'
        'require_target() { :; }\n'
        f"require_purge_clear() {{\n{require}\n"
        f"operation() {{\n{entry}{gate}touch -- \"$2\"; }}\n"
        'operation "$1" "$2"\n'
    )
    result = subprocess.run(
        ["bash", "-c", harness, "purge-test", str(stage), str(marker)],
        capture_output=True, text=True, check=False,
        env={**os.environ, "REPORT": report},
    )
    assert result.returncode == 78, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["schema_version"] == "ed-finder/operator-operation-result/v1"
    assert receipt["operation"] == f"{name}-{mode}"
    assert receipt["failures"] == [failure]
    assert receipt["db_writes_performed"] is False
    assert not marker.exists()


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("name", (
    "v3-system-search-validate-constraints", "octopus-qdrant-healthcheck-repair",
))
def test_streamed_mutators_preserve_refusal_receipts(name: str, failure: str) -> None:
    source = (ACTIONS / f"{name}.sh").read_text()
    report = json.dumps({"status": "refused", "failures": [failure]})
    if name == "v3-system-search-validate-constraints":
        prefix = source.rsplit('\ncase "$ACTION" in', 1)[0]
        harness = prefix + '\nrequire_target() { :; }\nstart_operation\n'
    else:
        prefix = source.split('host_identity_matches "$(hostname -s)"', 1)[0]
        gate = source.split('# Trusted-main streaming supplies this helper', 1)[1].split(
            'docker compose version', 1,
        )[0]
        harness = prefix + '\n# Trusted-main streaming supplies this helper' + gate
    harness = (
        'v3_purge_state_check() { printf "%s\\n" "$REPORT"; return 78; }\n'
        + harness
    )
    result = subprocess.run(
        ["bash", "-c", harness, "purge-test", "start"],
        capture_output=True, text=True, check=False,
        env={**os.environ, "REPORT": report},
    )
    assert result.returncode != 0
    receipt = json.loads(result.stdout or result.stderr)
    assert receipt["status"] == "stopped"
    assert receipt["failures"] == [failure]
    assert receipt["db_writes_performed"] is False
    if name == "v3-system-search-validate-constraints":
        assert receipt["catalog_validation_launched"] is False
    else:
        assert receipt["qdrant_recreated"] is False
        assert receipt["web_started"] is False


@pytest.mark.parametrize("name", (
    "octopus-edge-status", "v3-app-status", "v3-spatial-status",
    "v3-derived-lifecycle-status", "v3-disk-inventory", "v3-host-storage-detail",
))
def test_read_only_inventory_status_actions_do_not_take_purge_fence(name: str) -> None:
    source = (ACTIONS / f"{name}.sh").read_text()
    assert "v3_purge_state_check" not in source
    assert "require_purge_clear" not in source


@pytest.mark.parametrize("name", (
    "ratings-v4-generation", "v3-system-search-f1", "v3-system-archetype",
    "v3-archetype-calibration-complete", "v3-system-search-validate-constraints",
))
def test_read_only_status_modes_remain_available_during_purge(name: str) -> None:
    source = (ACTIONS / f"{name}.sh").read_text()
    body = source.split("status_operation() {\n", 1)[1].split("\n}", 1)[0]
    assert "require_purge_clear" not in body
    assert "v3_purge_state_check" not in body
