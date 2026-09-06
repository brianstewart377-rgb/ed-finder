"""Workflow-only contracts for the bounded V3 live-checkpoint deploy."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "v3-application-live-checkpoint-preflight.yml"
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

    assert set(inputs) == {"deployment_mode", "release_run_id"}
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
