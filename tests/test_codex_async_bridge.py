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
