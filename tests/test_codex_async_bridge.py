from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / ".github" / "workflows" / "codex-dispatch.yml"
WORKER = ROOT / ".github" / "workflows" / "codex-laptop.yml"
CONTROL_PLANE = ROOT / "docs" / "development" / "chatgpt-ops-control-plane.md"


def _workflow() -> dict:
    return yaml.load(WORKER.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: str, name: str) -> dict:
    matches = [step for step in _workflow()["jobs"][job]["steps"] if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_codex_request_push_is_acknowledged_by_short_dispatch_workflow() -> None:
    text = DISPATCH.read_text(encoding="utf-8")

    assert "branches:\n      - codex-task-requests" in text
    assert "actions: write" in text
    assert "timeout-minutes: 2" in text
    assert "codex-laptop.yml/dispatches" in text
    assert "CODEX_DISPATCH_ACCEPTED=true" in text
    assert "CODEX_WORKER_RUN_ID=" in text
    assert "Do not wait for it here." in text


def test_long_codex_worker_only_runs_from_explicit_dispatch() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "request_id:" in text
    assert "run-name: Codex Worker · ${{ inputs.request_id }}" in text
    assert "timeout-minutes: 120" in text
    assert "codex exec --sandbox danger-full-access" in text
    assert "codex-task-requests" not in text


def test_codex_workers_are_not_globally_serialized() -> None:
    workflow = _workflow()

    assert "concurrency" not in workflow
    assert workflow["jobs"]["codex"]["runs-on"] == ["self-hosted", "Linux", "X64"]


def test_worker_permissions_are_minimal_and_push_is_separate() -> None:
    workflow = _workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["push"]["runs-on"] == "ubuntu-24.04"
    assert workflow["jobs"]["push"]["permissions"] == {
        "actions": "read",
        "contents": "write",
    }
    assert "pull-requests" not in WORKER.read_text(encoding="utf-8")


def test_privileged_workflow_push_token_is_isolated_from_codex() -> None:
    text = WORKER.read_text(encoding="utf-8")

    checkout = text.split("- name: Checkout main", 1)[1].split(
        "- name: Resolve request", 1
    )[0]
    implementation = _step("codex", "Run Codex implementation")["run"]
    codex_job = text.split("  push:\n", 1)[0]
    ordinary_push = _step("push", "Push ordinary implementation branch")
    workflow_push = _step("push", "Push workflow implementation branch")

    assert "persist-credentials: false" in checkout
    assert "CODEX_WORKER_GIT_TOKEN" not in implementation
    assert "git push" not in implementation
    assert "CODEX_WORKER_GIT_TOKEN" not in codex_job
    assert ordinary_push["env"]["CODEX_PUSH_TOKEN"] == "${{ github.token }}"
    assert workflow_push["env"]["CODEX_PUSH_TOKEN"] == "${{ secrets.CODEX_WORKER_GIT_TOKEN }}"
    assert "CODEX_WORKER_GIT_TOKEN" not in ordinary_push["run"]


def test_workflow_detection_is_fail_closed() -> None:
    run = _step("push", "Reconstruct and inspect trusted push")["run"]

    assert 'if ! git -C "$trusted_root/repo" diff --name-only' in run
    assert "grep_status=$?" in run
    assert '[ "$grep_status" -eq 1 ] ||' in run
    assert "git diff" not in run.split("grep -E", 1)[1]
    assert "|| true" not in run


def test_push_uses_fresh_trusted_git_metadata_and_canonical_remote() -> None:
    reconstruct = _step("push", "Reconstruct and inspect trusted push")["run"]
    pushes = [
        _step("push", "Push ordinary implementation branch")["run"],
        _step("push", "Push workflow implementation branch")["run"],
    ]

    assert "mktemp -d" in reconstruct
    assert 'canonical_remote="https://github.com/${GITHUB_REPOSITORY}.git"' in reconstruct
    assert "GIT_CONFIG_NOSYSTEM=1" in reconstruct
    assert "GIT_CONFIG_GLOBAL=/dev/null" in reconstruct
    assert "GIT_NO_REPLACE_OBJECTS=1" in reconstruct
    assert "core.hooksPath=/dev/null" in reconstruct
    assert "apply --check --index" in reconstruct
    assert "user.name=codex-worker" in reconstruct
    for run in pushes:
        assert 'canonical_remote="https://github.com/${GITHUB_REPOSITORY}.git"' in run
        assert "codex-trusted-repo" in run
        assert "core.hooksPath=/dev/null" in run
        assert "credential.helper=" in run
        assert " push \"$canonical_remote\" " in run
        assert " push origin " not in run


def test_prompts_use_stdin_and_isolated_automation_config() -> None:
    for name in ("Run Codex investigation", "Run Codex implementation"):
        run = _step("codex", name)["run"]
        invocation = next(line for line in run.splitlines() if "codex exec" in line)
        assert "| codex exec" in invocation
        assert invocation.rstrip().endswith("-")
        assert "--ignore-user-config" in invocation
        assert "--ignore-rules" in invocation
        assert "--ephemeral" in invocation
        assert "--disable apps" in invocation
        assert "--disable hooks" in invocation
        assert "--disable plugins" in invocation
        assert '"$prompt"' not in invocation


def test_runner_identity_is_allowlisted_before_any_codex_process() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["codex"]["steps"]
    verify_index = next(i for i, step in enumerate(steps) if step.get("name") == "Verify worker identity")
    run = steps[verify_index]["run"]

    assert "contabo-codex-worker|contabo-codex-worker-2|contabo-codex-worker-3" in run
    assert '*) echo "::error::Refusing to run Codex on unapproved runner: $RUNNER_NAME"; exit 43 ;;' in run
    assert run.index('case "$RUNNER_NAME"') < run.index("codex --version")
    for name in ("Run Codex investigation", "Run Codex implementation"):
        assert verify_index < next(i for i, step in enumerate(steps) if step.get("name") == name)


def test_control_plane_describes_bounded_parallel_pool() -> None:
    text = CONTROL_PLANE.read_text(encoding="utf-8")

    assert "bounded parallel pool" in text
    assert "serial `codex-worker` concurrency group" not in text
    for runner in ("contabo-codex-worker", "contabo-codex-worker-2", "contabo-codex-worker-3"):
        assert runner in text
