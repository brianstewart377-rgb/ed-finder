"""Governed Octopus upgrade routing and trusted streaming, without remote calls."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
INPUTS = (
    ("OCTOPUS_PACKAGE_JSON_B64", "package.json"),
    ("OCTOPUS_PACKAGE_LOCK_B64", "package-lock.json"),
    ("OCTOPUS_MODELS_SQL_B64", "openai-models.sql"),
)


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def _step(name):
    return next(step for step in _workflow()["jobs"]["execute"]["steps"] if step["name"] == name)


@pytest.mark.parametrize(("operation", "event", "ref", "accepted"), [
    ("octopus-upgrade-apply", "workflow_dispatch", "refs/heads/main", True),
    ("octopus-upgrade-apply", "workflow_dispatch", "refs/heads/other", False),
    ("octopus-upgrade-apply", "push", "refs/heads/chatgpt-ed-new-ops-requests", False),
    ("octopus-upgrade-preflight", "workflow_dispatch", "refs/heads/other", True),
    ("octopus-upgrade-preflight", "push", "refs/heads/chatgpt-ed-new-ops-requests", True),
])
def test_upgrade_resolver_restricts_apply_to_manual_main(tmp_path, operation, event, ref, accepted):
    binary = tmp_path / "bin"
    binary.mkdir()
    git = binary / "git"
    git.write_text("#!/bin/sh\nprintf '%s\\n' '.github/ed-new-ops-requests/upgrade.json'\n")
    git.chmod(0o755)
    (binary / "python").symlink_to(sys.executable)
    request = tmp_path / ".github/ed-new-ops-requests/upgrade.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({"operation": operation}))
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-c", _step("Resolve request")["run"]], cwd=tmp_path,
        capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
             "EVENT_NAME": event, "CURRENT_REF": ref, "INPUT_OPERATION": operation,
             "BEFORE_SHA": "a" * 40, "CURRENT_SHA": "b" * 40, "GITHUB_OUTPUT": str(output)},
    )
    assert result.returncode == (0 if accepted else 64), result.stderr
    assert output.exists() == accepted
    if accepted:
        assert output.read_text() == f"operation={operation}\n"


def test_both_choices_are_exposed_once_and_receipts_are_retained():
    options = _workflow()[True]["workflow_dispatch"]["inputs"]["operation"]["options"]
    for mode in ("preflight", "apply"):
        assert options.count(f"octopus-upgrade-{mode}") == 1
    upload = _step("Upload Octopus upgrade receipt")
    assert upload["if"].startswith("always() &&")
    assert "octopus-upgrade-preflight" in upload["if"]
    assert "octopus-upgrade-apply" in upload["if"]
    assert upload["with"] == {
        "name": "octopus-upgrade-receipt",
        "path": "${{ runner.temp }}/octopus-upgrade-receipt.json",
        "if-no-files-found": "error", "retention-days": 30,
    }


def test_prepared_script_carries_fence_and_exact_reviewed_input_bytes(tmp_path):
    prepare = _step("Prepare trusted purge-fenced streamed actions")
    assert all(f"octopus-upgrade-{mode}" in prepare["if"] for mode in ("preflight", "apply"))
    trusted = tmp_path / "trusted-main/scripts/operator"
    library = trusted / "lib"
    library.mkdir(parents=True)
    for name in ("v3_purge_state.py", "v3-purge-state.sh"):
        shutil.copyfile(ROOT / "scripts/operator/lib" / name, library / name)
    actions = trusted / "actions"
    actions.mkdir()
    for name in ("v3-backup-wrapper-install", "octopus-qdrant-healthcheck-repair", "v3-system-search-validate-constraints"):
        (actions / f"{name}.sh").write_text(":\n")
    # Only this harmless body executes. The real action is never invoked here.
    (actions / "octopus-upgrade.sh").write_text(
        "declare -F v3_purge_state_check >/dev/null || exit 1\n"
        + "".join(f'printf \'%s\\n\' "${name}"\n' for name, _ in INPUTS),
    )
    source = trusted / "octopus-upgrade"
    source.mkdir()
    for _, filename in INPUTS:
        shutil.copyfile(ROOT / "scripts/operator/octopus-upgrade" / filename, source / filename)
    temporary = tmp_path / "runner-temp"
    temporary.mkdir()
    result = subprocess.run(
        ["bash", "-c", prepare["run"]], cwd=tmp_path,
        capture_output=True, text=True, check=False,
        env={**os.environ, "RUNNER_TEMP": str(temporary)},
    )
    assert result.returncode == 0, result.stderr
    prepared = temporary / "v3-purge-fenced-actions/octopus-upgrade.sh"
    assert (library / "v3_purge_state.py").read_text() in prepared.read_text()
    payloads = subprocess.run(
        ["bash", str(prepared)], capture_output=True, text=True, check=False,
    )
    assert payloads.returncode == 0, payloads.stderr
    for payload, (_, filename) in zip(payloads.stdout.splitlines(), INPUTS, strict=True):
        assert base64.b64decode(payload, validate=True) == (source / filename).read_bytes()


@pytest.mark.parametrize("mode", ("preflight", "apply"))
def test_upgrade_ssh_routes_only_literal_modes_and_keeps_pinned_trust(tmp_path, mode):
    step = _step(f"Run Octopus upgrade {mode}")
    assert step["if"] == f"steps.request.outputs.operation == 'octopus-upgrade-{mode}'"
    binary = tmp_path / "bin"
    binary.mkdir()
    ssh = binary / "ssh"
    ssh.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$SSH_LOG\"\nprintf '{}\\n'\n")
    ssh.chmod(0o755)
    prepared = tmp_path / "v3-purge-fenced-actions/octopus-upgrade.sh"
    prepared.parent.mkdir()
    prepared.write_text(":\n")
    log = tmp_path / "ssh-log"
    result = subprocess.run(
        ["bash", "-c", step["run"]], capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
             "RUNNER_TEMP": str(tmp_path), "SSH_HOST": "stub.invalid", "SSH_PORT": "22",
             "SSH_USER": "stub", "SSH_LOG": str(log), "OPERATION": "injected-command"},
    )
    assert result.returncode == 0, result.stderr
    arguments = log.read_text().splitlines()
    assert arguments[-1] == f"cd /opt/ed-finder && bash -s -- {mode}"
    assert "StrictHostKeyChecking=yes" in arguments
    assert f"UserKnownHostsFile={Path.home()}/.ssh/known_hosts" in arguments
    assert "injected-command" not in log.read_text()
    assert (tmp_path / "octopus-upgrade-receipt.json").read_text() == "{}\n"


def test_upgrade_modes_are_classified_separately_in_purge_entry_table():
    document = (ROOT / "docs/operations/v3-governed-derived-purge.md").read_text()
    assert "| `octopus-upgrade.sh apply` | Mutator, fenced |" in document
    assert "| `octopus-upgrade.sh preflight` | Read-only |" in document
