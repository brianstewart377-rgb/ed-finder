"""Contracts for the request-only V3 checkpoint workflow dispatcher."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "operator" / "v3_checkpoint_request.py"
WORKFLOW = ROOT / ".github" / "workflows" / "v3-checkpoint-request-dispatch.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "v3-application-release.yml"
DEPLOY_WORKFLOW = (
    ROOT / ".github" / "workflows" / "v3-application-live-checkpoint-preflight.yml"
)
OPERATIONS_NOTE = ROOT / "docs" / "operations" / "v3-application-checkpoint-release.md"
REQUEST_SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("v3_checkpoint_request", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _release_request(**input_overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "source_sha": "b" * 40,
        "schema_compatibility": "exact",
        "compatibility_evidence": "review-record:checkpoint-42",
        "reviewed_compatible_migration_sets": "",
        "rollback_eligible": True,
    }
    inputs.update(input_overrides)
    return {
        "operation": "v3-application-immutable-release",
        "inputs": inputs,
    }


def _deploy_request(**input_overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "deployment_mode": "bootstrap",
        "release_run_id": "1234567890",
    }
    inputs.update(input_overrides)
    return {
        "operation": "v3-application-live-checkpoint-deploy",
        "inputs": inputs,
    }


def _write_request(tmp_path: Path, value: object) -> tuple[Path, str]:
    root = tmp_path / "checkout"
    relative = ".github/v3-checkpoint-requests/request-001.json"
    request = root / relative
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps(value), encoding="utf-8")
    return root, relative


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _request_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "request"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Checkpoint Contract Test")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run_resolve_step(
    tmp_path: Path, repo: Path, before_sha: str
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    step = next(
        item
        for item in workflow["jobs"]["dispatch"]["steps"]
        if item.get("id") == "request"
    )
    trusted_tool = (
        tmp_path / "trusted-main" / "scripts" / "operator" / TOOL.name
    )
    trusted_tool.parent.mkdir(parents=True)
    trusted_tool.write_text(TOOL.read_text(encoding="utf-8"), encoding="utf-8")
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=repo,
        env={
            **os.environ,
            "BEFORE_SHA": before_sha,
            "CURRENT_SHA": _git(repo, "rev-parse", "HEAD"),
            "REQUEST_REF": "chatgpt-v3-checkpoint-requests",
            "PAYLOAD_FILE": str(tmp_path / "payload.json"),
            "GITHUB_OUTPUT": str(github_output),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_request_serializes_only_the_exact_canonical_inputs(tmp_path: Path):
    module = _load_module()
    root, relative = _write_request(tmp_path, _release_request())

    request_id, workflow, payload = module.prepare_request(
        request_root=root,
        request_relative=relative,
        request_sha=REQUEST_SHA,
    )

    assert request_id.startswith("v3cp-aaaaaaaaaaaa-")
    assert workflow == "v3-application-release.yml"
    assert payload == {
        "ref": "main",
        "inputs": _release_request()["inputs"],
        "return_run_details": True,
    }
    assert type(payload["inputs"]["rollback_eligible"]) is bool


def test_deploy_request_serializes_only_the_exact_canonical_inputs(tmp_path: Path):
    module = _load_module()
    root, relative = _write_request(
        tmp_path, _deploy_request(deployment_mode="upgrade")
    )

    _, workflow, payload = module.prepare_request(
        request_root=root,
        request_relative=relative,
        request_sha=REQUEST_SHA,
    )

    assert workflow == "v3-application-live-checkpoint-preflight.yml"
    assert payload == {
        "ref": "main",
        "inputs": {"deployment_mode": "upgrade", "release_run_id": "1234567890"},
        "return_run_details": True,
    }


def test_backward_compatible_request_accepts_unique_lowercase_migration_sets():
    module = _load_module()
    first = "sha256:" + "1" * 64
    second = "sha256:" + "2" * 64
    request = _release_request(
        schema_compatibility="backward-compatible",
        reviewed_compatible_migration_sets=f"{first}\n{second}",
    )

    operation, inputs = module.validate_request(request)

    assert operation == "v3-application-immutable-release"
    assert inputs["reviewed_compatible_migration_sets"] == f"{first}\n{second}"


@pytest.mark.parametrize(
    "request_document",
    [
        [],
        {"operation": "v3-application-immutable-release"},
        {**_release_request(), "extra": False},
        {"operation": "release", "inputs": {}},
        {**_release_request(), "inputs": None},
        _release_request(source_sha="B" * 40),
        _release_request(source_sha=1),
        _release_request(schema_compatibility="compatible"),
        _release_request(compatibility_evidence=""),
        _release_request(compatibility_evidence="password=do-not-store-this"),
        _release_request(reviewed_compatible_migration_sets="sha256:" + "1" * 64),
        _release_request(rollback_eligible=1),
        _release_request(
            schema_compatibility="unknown",
            compatibility_evidence="positive-evidence",
            rollback_eligible=False,
        ),
        _release_request(
            schema_compatibility="incompatible",
            compatibility_evidence="",
            rollback_eligible=True,
        ),
        _release_request(
            schema_compatibility="backward-compatible",
            reviewed_compatible_migration_sets="sha256:ABC",
        ),
        _release_request(
            schema_compatibility="backward-compatible",
            reviewed_compatible_migration_sets=("sha256:" + "1" * 64 + "\n") * 2,
        ),
        _deploy_request(deployment_mode="production"),
        _deploy_request(release_run_id=123),
        _deploy_request(release_run_id="0"),
        _deploy_request(release_run_id="01"),
        _deploy_request(release_run_id="1" * 21),
        {
            "operation": "v3-application-live-checkpoint-deploy",
            "inputs": {
                "deployment_mode": "bootstrap",
                "release_run_id": "1",
                "extra": "not-allowed",
            },
        },
    ],
)
def test_request_validation_fails_closed_on_keys_types_and_values(
    request_document: object,
):
    module = _load_module()

    with pytest.raises(module.RequestError):
        module.validate_request(request_document)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"operation":"x","operation":"y","inputs":{}}',
        b'{"operation":"x","inputs":{"value":NaN}}',
        b"\xff",
        b"not-json",
    ],
)
def test_json_loader_rejects_duplicates_extensions_and_invalid_encoding(raw: bytes):
    module = _load_module()

    with pytest.raises(module.RequestError):
        module._load_json_bytes(raw)


def test_request_path_must_be_bounded_regular_and_one_level(tmp_path: Path):
    module = _load_module()
    root, relative = _write_request(tmp_path, _deploy_request())

    for invalid in (
        ".github/v3-checkpoint-requests/nested/request.json",
        ".github/v3-checkpoint-requests/UPPER.json",
        ".github/other/request.json",
    ):
        with pytest.raises(module.RequestError):
            module.prepare_request(
                request_root=root,
                request_relative=invalid,
                request_sha=REQUEST_SHA,
            )

    target = root / relative
    target.unlink()
    target.symlink_to(root / "missing")
    with pytest.raises(module.RequestError):
        module.prepare_request(
            request_root=root,
            request_relative=relative,
            request_sha=REQUEST_SHA,
        )


def test_dispatch_response_is_bound_to_the_repository_and_numeric_run_id():
    module = _load_module()
    repository = "owner/repository"
    response = {
        "workflow_run_id": 123456789,
        "run_url": "https://api.github.com/repos/owner/repository/actions/runs/123456789",
        "html_url": "https://github.com/owner/repository/actions/runs/123456789",
    }

    assert module.validate_dispatch_response(response, repository) == 123456789
    for invalid in (
        {**response, "workflow_run_id": True},
        {**response, "workflow_run_id": "123456789"},
        {**response, "html_url": "https://example.invalid/run"},
    ):
        with pytest.raises(module.RequestError):
            module.validate_dispatch_response(invalid, repository)


def test_dispatch_workflow_is_push_only_narrow_and_uses_trusted_main():
    source = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(source, Loader=yaml.BaseLoader)

    assert workflow["on"] == {
        "push": {
            "branches": ["chatgpt-v3-checkpoint-requests"],
            "paths": [".github/v3-checkpoint-requests/*.json"],
        }
    }
    assert workflow["permissions"] == {"actions": "write", "contents": "read"}
    assert "workflow_dispatch" not in workflow["on"]
    assert "environment" not in source
    assert "secrets." not in source
    assert "persist-credentials: false" in source
    assert "ref: main" in source
    assert "trusted-main/scripts/operator/v3_checkpoint_request.py" in source
    assert "git diff --name-only -z --no-renames" in source
    assert "git diff --diff-filter=A --name-only -z --no-renames" in source
    assert '"${tree_entry%% *}" = "100644"' in source


def test_resolve_step_accepts_one_new_regular_request_file(tmp_path: Path):
    repo, before_sha = _request_repo(tmp_path)
    request = repo / ".github/v3-checkpoint-requests/request-001.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps(_deploy_request()), encoding="utf-8")
    _git(repo, "add", ".github/v3-checkpoint-requests/request-001.json")
    _git(repo, "commit", "-qm", "request")

    result = _run_resolve_step(tmp_path, repo, before_sha)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "payload.json").is_file()
    output = (tmp_path / "github-output").read_text(encoding="utf-8")
    assert "request_id=v3cp-" in output
    assert "workflow_file=v3-application-live-checkpoint-preflight.yml" in output
    assert "release_run_id" not in output


def test_resolve_step_rejects_request_push_with_any_other_changed_path(
    tmp_path: Path,
):
    repo, before_sha = _request_repo(tmp_path)
    request = repo / ".github/v3-checkpoint-requests/request-001.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps(_deploy_request()), encoding="utf-8")
    (repo / "seed.txt").write_text("changed too\n", encoding="utf-8")
    _git(repo, "add", ".github/v3-checkpoint-requests/request-001.json", "seed.txt")
    _git(repo, "commit", "-qm", "mixed request")

    result = _run_resolve_step(tmp_path, repo, before_sha)

    assert result.returncode == 64
    assert "exactly one file" in result.stderr
    assert not (tmp_path / "payload.json").exists()


def test_resolve_step_rejects_modified_or_symlink_requests(tmp_path: Path):
    modified_root = tmp_path / "modified"
    modified_root.mkdir()
    modified_repo, _ = _request_repo(modified_root)
    request = modified_repo / ".github/v3-checkpoint-requests/request-001.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps(_deploy_request()), encoding="utf-8")
    _git(modified_repo, "add", ".github/v3-checkpoint-requests/request-001.json")
    _git(modified_repo, "commit", "-qm", "existing request")
    before_sha = _git(modified_repo, "rev-parse", "HEAD")
    request.write_text(
        json.dumps(_deploy_request(release_run_id="2")), encoding="utf-8"
    )
    _git(modified_repo, "commit", "-qam", "modify request")

    modified = _run_resolve_step(modified_root, modified_repo, before_sha)

    assert modified.returncode == 64
    assert "newly added file" in modified.stderr

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    symlink_repo, before_sha = _request_repo(symlink_root)
    request = symlink_repo / ".github/v3-checkpoint-requests/request-001.json"
    request.parent.mkdir(parents=True)
    request.symlink_to("payload.json")
    _git(symlink_repo, "add", ".github/v3-checkpoint-requests/request-001.json")
    _git(symlink_repo, "commit", "-qm", "symlink request")

    symlink = _run_resolve_step(symlink_root, symlink_repo, before_sha)

    assert symlink.returncode == 64
    assert "regular non-executable file" in symlink.stderr


def test_dispatch_api_uses_exact_run_details_without_logging_request_data():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/workflows/$TARGET_WORKFLOW/dispatches" in source
    assert "--data-binary \"@$PAYLOAD_FILE\"" in source
    assert "X-GitHub-Api-Version: 2022-11-28" in source
    assert '"$http_code" = "200"' in source
    assert "V3_CHECKPOINT_REQUEST_ID=" in source
    assert "V3_CHECKPOINT_TARGET_RUN_ID=" in source
    assert "V3_CHECKPOINT_TARGET_RUN_URL=" in source
    assert "cat \"$RESPONSE_FILE\"" not in source
    assert "cat \"$PAYLOAD_FILE\"" not in source
    assert "compatibility_evidence" not in source
    assert "reviewed_compatible_migration_sets" not in source


def test_dispatch_targets_only_the_existing_canonical_workflow_input_contracts():
    module = _load_module()
    release = yaml.load(RELEASE_WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    deploy = yaml.load(DEPLOY_WORKFLOW.read_text(), Loader=yaml.BaseLoader)

    assert set(release["on"]["workflow_dispatch"]["inputs"]) == module.RELEASE_INPUTS
    assert set(deploy["on"]["workflow_dispatch"]["inputs"]) == module.DEPLOY_INPUTS
    assert set(module.WORKFLOWS.values()) == {
        RELEASE_WORKFLOW.name,
        DEPLOY_WORKFLOW.name,
    }
    for target in (release, deploy):
        assert set(target["on"]) == {"workflow_dispatch"}


def test_operations_note_records_request_boundary_and_non_authority():
    note = OPERATIONS_NOTE.read_text(encoding="utf-8")

    assert "## Request-triggered dispatch" in note
    assert "chatgpt-v3-checkpoint-requests" in note
    assert "A successful dispatcher run means GitHub accepted" in note
    assert "currently\nstopped target authority still prevents host mutation" in note
