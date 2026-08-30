from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / ".github" / "workflows" / "codex-dispatch.yml"
WORKER = ROOT / ".github" / "workflows" / "codex-laptop.yml"


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
    text = WORKER.read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, Linux, X64]" in text
    assert "group: codex-worker" not in text
    assert "cancel-in-progress:" not in text


def test_privileged_workflow_push_token_is_isolated_from_codex() -> None:
    text = WORKER.read_text(encoding="utf-8")

    checkout = text.split("- name: Checkout main", 1)[1].split(
        "- name: Resolve request", 1
    )[0]
    implementation = text.split("- name: Run Codex implementation", 1)[1].split(
        "- name: Push implementation branch", 1
    )[0]
    push_wrapper = text.split("- name: Push implementation branch", 1)[1].split(
        "- name: Implementation branch summary", 1
    )[0]

    assert "persist-credentials: false" in checkout
    assert "CODEX_WORKER_GIT_TOKEN" not in implementation
    assert "git push" not in implementation
    assert "CODEX_WORKER_GIT_TOKEN: ${{ secrets.CODEX_WORKER_GIT_TOKEN }}" in push_wrapper
    assert "^\\.github/workflows/" in push_wrapper
    assert "Contents: read/write and Workflows: read/write" in push_wrapper
    assert "GIT_ASKPASS" in push_wrapper
    assert "git -c credential.helper= push --force-with-lease origin \"$CODEX_BRANCH\"" in push_wrapper
