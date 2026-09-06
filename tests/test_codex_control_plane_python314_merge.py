from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / ".github" / "workflows" / "codex-dispatch.yml"
WORKER = ROOT / ".github" / "workflows" / "codex-laptop.yml"
CONTROL_PLANE_DOC = ROOT / "docs" / "development" / "chatgpt-ops-control-plane.md"


def test_merged_dispatcher_uses_selected_python314_not_runner_default() -> None:
    text = DISPATCH.read_text(encoding="utf-8")
    setup_position = text.index("- name: Set up Python 3.14")
    resolve_position = text.index("- name: Resolve request")
    setup = text[setup_position:resolve_position]

    assert setup_position < resolve_position
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in setup
    assert 'python-version: "3.14"' in setup
    assert "python3" not in text
    assert text.count("$(python -c ") == 3
    assert text.count("$(python -") == 5


def test_merged_control_plane_keeps_exact_cpython314_worker_authority() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    dispatch = DISPATCH.read_text(encoding="utf-8")
    documentation = CONTROL_PLANE_DOC.read_text(encoding="utf-8")

    assert "Set up CPython 3.14" in worker
    assert 'python-version: "3.14"' in worker
    assert "platform.python_implementation()" in worker
    assert "sys.version_info[:2] == (3, 14)" in worker
    assert "The dispatcher and worker select exactly CPython 3.14" in documentation
    for authority in (worker, dispatch, documentation):
        assert "3.12" not in authority
