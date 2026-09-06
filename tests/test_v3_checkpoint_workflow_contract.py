"""Workflow-only contracts for the bounded V3 live-checkpoint deploy."""

import hashlib
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "v3-application-live-checkpoint-preflight.yml"
)


def _workflow_step(name: str) -> dict[str, str]:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    return next(
        step for step in workflow["jobs"]["deploy"]["steps"] if step.get("name") == name
    )


def _run_checksum_step(candidate_dir: Path) -> subprocess.CompletedProcess[str]:
    step = _workflow_step("Verify downloaded artifact checksum")
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=ROOT,
        env={**os.environ, "CANDIDATE_DIR": str(candidate_dir)},
        check=False,
        text=True,
        capture_output=True,
    )


def test_checkpoint_workflow_ceiling_covers_bounded_deploy_and_rollback_budget():
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    deploy = workflow["jobs"]["deploy"]

    assert int(deploy["timeout-minutes"]) == 75

    source = WORKFLOW.read_text()
    assert "each command at 120 seconds" in source
    assert "readiness window at 120 seconds" in source
    assert "candidate apply/smoke, rollback" in source


def test_upgrade_uses_durable_host_rollback_state_not_expiring_artifact():
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    step_names = [step.get("name") for step in workflow["jobs"]["deploy"]["steps"]]

    assert set(inputs) == {"deployment_mode", "release_run_id", "transport"}
    assert inputs["transport"]["default"] == "local"
    assert inputs["transport"]["options"] == ["local", "ssh"]
    assert "Download candidate release manifest" in step_names
    assert "Download accepted rollback manifest" not in step_names

    source = WORKFLOW.read_text()
    for stale_artifact_path in (
        "rollback_run_id",
        "artifacts/rollback",
        "--rollback-run-id",
        "--rollback-manifest",
        "--rollback-checksum",
        "--purpose rollback-candidate",
    ):
        assert stale_artifact_path not in source


def test_untrusted_release_run_stops_before_artifact_checksum_processing():
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["deploy"]["steps"]
    step_names = [step.get("name") for step in steps]
    provenance_index = step_names.index("Authenticate release workflow run provenance")
    checksum_index = step_names.index("Verify downloaded artifact checksum")

    assert provenance_index < checksum_index
    provenance = steps[provenance_index]
    assert provenance.get("continue-on-error") is None
    assert provenance.get("if") is None
    assert "scripts/release/v3_release_run.py" in provenance["run"]


def test_candidate_checksum_verifier_accepts_only_the_expected_basename(tmp_path):
    manifest = tmp_path / "v3-application-release.json"
    manifest.write_bytes(b'{"trusted": true}\n')
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (tmp_path / "v3-application-release.json.sha256").write_text(
        f"{digest}  v3-application-release.json\n"
    )

    result = _run_checksum_step(tmp_path)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("path_kind", ["absolute", "parent"])
def test_candidate_checksum_verifier_rejects_absolute_and_parent_paths(
    tmp_path, path_kind
):
    manifest = tmp_path / "v3-application-release.json"
    manifest.write_bytes(b'{"trusted": true}\n')
    outside = tmp_path.parent / f"{tmp_path.name}-attacker-controlled"
    outside.write_bytes(manifest.read_bytes())
    hostile_path = str(outside) if path_kind == "absolute" else f"../{outside.name}"
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (tmp_path / "v3-application-release.json.sha256").write_text(
        f"{digest}  {hostile_path}\n"
    )

    result = _run_checksum_step(tmp_path)

    assert result.returncode == 64
    assert "must name only v3-application-release.json" in result.stderr


def test_candidate_checksum_step_never_executes_gnu_checksum_lists():
    source = _workflow_step("Verify downloaded artifact checksum")["run"]

    assert "sha256sum" not in source
    assert "--check" not in source
    assert 'manifest_basename = "v3-application-release.json"' in source
