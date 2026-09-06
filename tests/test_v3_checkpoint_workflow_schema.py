"""GitHub's schema distinguishes step.shell from job.defaults.run.shell.

Runner schema: actions/runner src/Sdk/DTPipelines/workflow-v1.0.json,
run-step shell=non-empty-string vs job-defaults-run context=github,needs,...
"""
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTEXTS = {"github", "needs", "strategy", "matrix", "env", "vars", "inputs"}


def check_shell_contexts(workflow):
    # Workflow-level defaults do not support expressions either.
    assert "${{" not in str(workflow.get("defaults", {}))
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            assert "${{" not in step.get("shell", ""), "step.shell is literal-only"
        shell = job.get("defaults", {}).get("run", {}).get("shell", "")
        for context in re.findall(r"\$\{\{\s*(\w+)\.", shell):
            assert context in CONTEXTS, f"Unavailable job-default context: {context}"


def test_every_workflow_uses_only_supported_shell_expression_locations():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        check_shell_contexts(yaml.safe_load(path.read_text()) or {})


@pytest.mark.parametrize("workflow", [
    {"jobs": {"x": {"steps": [{"shell": "${{ github.sha }}"}]}}},
    {"jobs": {"x": {"defaults": {"run": {"shell": "${{ runner.temp }}"}}}}},
    {"defaults": {"run": {"shell": "${{ github.sha }}"}}},
])
def test_regression_rejects_the_previously_merged_invalid_schema(workflow):
    with pytest.raises(AssertionError):
        check_shell_contexts(workflow)


def test_native_schema_probe_is_hosted_unprivileged_and_requires_success():
    path = ROOT / ".github/workflows/checkpoint-workflow-validation.yml"
    workflow = yaml.safe_load(path.read_text())
    job = workflow["jobs"]["custom-shell"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["needs"] == "values"
    shell = job["defaults"]["run"]["shell"]
    assert "${{ github.sha }}" in shell
    assert "${{ needs.values.outputs.marker }}" in shell
    assert shell.endswith(" {0}") and "-I -S -c" in shell
    assert "sudo" not in shell
    assert job["steps"][-1]["run"].startswith("raise RuntimeError")
    assert all("continue-on-error" not in step for step in job["steps"])
