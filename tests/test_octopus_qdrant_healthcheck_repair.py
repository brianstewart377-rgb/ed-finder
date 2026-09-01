import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ops.yml"
DISPATCH = ROOT / "scripts" / "operator" / "actions" / "dispatch.sh"
ACTION = ROOT / "scripts" / "operator" / "actions" / "octopus-qdrant-healthcheck-repair.sh"
OPERATION = "octopus-qdrant-healthcheck-repair"


def _editor_source():
    source = ACTION.read_text(encoding="utf-8")
    marker = 'if ! python3 - "$COMPOSE_FILE" "$replacement_file" <<\'PY\'\n'
    return source.split(marker, 1)[1].split("\nPY\nthen", 1)[0]


def _run_editor(tmp_path, healthcheck):
    compose = tmp_path / "docker-compose.selfhost.yml"
    output = tmp_path / "edited.yml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: ghcr.io/octopusreview/octopus-selfhost:1.0.122\n"
        "    depends_on:\n"
        "      qdrant:\n"
        "        condition: service_healthy\n"
        "  qdrant:\n"
        "    image: qdrant/qdrant:v1.17.0\n"
        "    healthcheck:\n"
        f"      {healthcheck}\n"
        "      interval: 5s\n"
        "    restart: unless-stopped\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-", str(compose), str(output)],
        input=_editor_source(),
        text=True,
        capture_output=True,
        check=False,
    )
    return result, compose, output


def test_chatgpt_ops_allowlists_and_routes_repair_operation():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(f"          - {OPERATION}\n") == 1
    assert f"{OPERATION}) stage={OPERATION} ;;" in source


def test_dispatcher_uses_dedicated_repair_action():
    source = DISPATCH.read_text(encoding="utf-8")
    assert f"{OPERATION})" in source
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in source


def test_repair_action_has_fail_closed_scope_and_guards():
    source = ACTION.read_text(encoding="utf-8")
    required = (
        'EXPECTED_HOST="ed-finder-prod"',
        'COMPOSE_FILE="$OCTOPUS_DIR/docker-compose.selfhost.yml"',
        'EXPECTED_IMAGE="qdrant/qdrant:v1.17.0"',
        'ghcr.io/octopusreview/octopus-selfhost:1.0.122',
        'test_line.strip() != expected',
        '"CMD", "wget", "--no-verbose", "--tries=1", "--spider"',
        "*:18BD) exit 0",
        "cp --preserve=mode,ownership,timestamps",
        "config --quiet",
        "up -d --no-deps --force-recreate qdrant",
        "qdrant_health_timeout",
        "http://127.0.0.1:43333/readyz",
        "http://127.0.0.1:43300",
        'for path in ("/", "/api/health", "/api/version")',
    )
    for guard in required:
        assert guard in source

    assert ".env" not in source
    assert "POSTGRES" not in source
    assert "password" not in source.lower()
    assert '"db_access_performed": False' in source
    assert '"volume_configuration_modified": False' in source


def test_editor_replaces_only_exact_broken_healthcheck(tmp_path):
    broken = ('test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", '
              '"http://localhost:6333/readyz"]')
    result, compose, output = _run_editor(tmp_path, broken)
    assert result.returncode == 0, result.stderr
    before = compose.read_text(encoding="utf-8")
    after = output.read_text(encoding="utf-8")
    assert after.replace(after.split("      test:", 1)[1].split("\n", 1)[0],
                         before.split("      test:", 1)[1].split("\n", 1)[0]) == before
    assert 'test: ["CMD-SHELL"' in after
    assert "*:18BD) exit 0" in after
    assert "wget" not in after


def test_editor_refuses_drifted_healthcheck(tmp_path):
    result, _, output = _run_editor(
        tmp_path,
        'test: ["CMD", "wget", "--spider", "http://localhost:6333/readyz"]',
    )
    assert result.returncode != 0
    assert not output.exists()
