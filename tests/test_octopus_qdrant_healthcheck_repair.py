import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ops.yml"
DISPATCH = ROOT / "scripts" / "operator" / "actions" / "dispatch.sh"
ACTION = ROOT / "scripts" / "operator" / "actions" / "octopus-qdrant-healthcheck-repair.sh"
OPERATION = "octopus-qdrant-healthcheck-repair"
BROKEN_HEALTHCHECK = ('test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", '
                      '"http://localhost:6333/readyz"]')
FIXED_HEALTHCHECK = ('test: ["CMD-SHELL", "while read -r _ local _ state _; do if [ $$state = 0A ]; '
                     'then case $$local in *:18BD) exit 0;; esac; fi; done < /proc/net/tcp; '
                     'while read -r _ local _ state _; do if [ $$state = 0A ]; then case $$local '
                     'in *:18BD) exit 0;; esac; fi; done < /proc/net/tcp6; exit 1"]')


def _editor_source():
    source = ACTION.read_text(encoding="utf-8")
    marker = 'if editor_state="$(python3 - "$COMPOSE_FILE" "$replacement_file" "$EXPECTED_HEALTHCHECK" <<\'PY\'\n'
    return source.split(marker, 1)[1].split("\nPY\n)\"; then", 1)[0]


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
        [sys.executable, "-", str(compose), str(output), FIXED_HEALTHCHECK],
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
        'EXPECTED_POSTGRES_IMAGE="postgres:17-alpine"',
        'ghcr.io/octopusreview/octopus-selfhost:1.0.122',
        'test_line.strip() == expected',
        '"CMD", "wget", "--no-verbose", "--tries=1", "--spider"',
        "*:18BD) exit 0",
        "cp --preserve=mode,ownership,timestamps",
        "config --quiet",
        "up -d --no-deps --force-recreate qdrant",
        'ps -q postgres)',
        'postgres_health" = healthy',
        "up -d --no-deps web",
        "qdrant_health_timeout",
        "http://127.0.0.1:43333/readyz",
        "http://127.0.0.1:43300",
        'payload.get("version") == "1.0.122"',
    )
    for guard in required:
        assert guard in source

    assert ".env" not in source
    assert "password" not in source.lower()
    assert '"db_access_performed": False' in source
    assert '"volume_configuration_modified": False' in source


def test_editor_replaces_only_exact_broken_healthcheck(tmp_path):
    result, compose, output = _run_editor(tmp_path, BROKEN_HEALTHCHECK)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "patched"
    before = compose.read_text(encoding="utf-8")
    after = output.read_text(encoding="utf-8")
    assert after.replace(after.split("      test:", 1)[1].split("\n", 1)[0],
                         before.split("      test:", 1)[1].split("\n", 1)[0]) == before
    assert 'test: ["CMD-SHELL"' in after
    assert "*:18BD) exit 0" in after
    assert "wget" not in after


def test_editor_accepts_exact_fixed_healthcheck_for_rerun(tmp_path):
    result, compose, output = _run_editor(tmp_path, FIXED_HEALTHCHECK)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "already_patched"
    assert output.read_text(encoding="utf-8") == compose.read_text(encoding="utf-8")


@pytest.mark.parametrize("healthcheck", [
    'test: ["CMD", "wget", "--spider", "http://localhost:6333/readyz"]',
    BROKEN_HEALTHCHECK.replace("/readyz", "/healthz"),
    FIXED_HEALTHCHECK.replace("*:18BD", "*:18BE", 1),
    'test: ["CMD-SHELL", "exit 0"]',
])
def test_editor_refuses_unexpected_healthcheck_variants(tmp_path, healthcheck):
    result, _, output = _run_editor(tmp_path, healthcheck)
    assert result.returncode != 0
    assert not output.exists()


def test_edit_is_committed_only_after_compose_validation_succeeds():
    source = ACTION.read_text(encoding="utf-8")
    moved = source.index('mv -- "$replacement_file" "$COMPOSE_FILE"')
    validation = source.index(
        'docker compose --project-directory "$OCTOPUS_DIR" -f "$COMPOSE_FILE" config --quiet',
        moved,
    )
    committed = source.index("EDIT_COMMITTED=true", validation)
    assert moved < validation < committed

    trap = source[source.index("on_exit() {"):source.index("trap on_exit EXIT")]
    assert '[ "$rc" -ne 0 ] && [ "$EDIT_COMMITTED" = false ]' in trap
    assert '[ -n "$BACKUP" ] && [ -f "$BACKUP" ]' in trap
    assert 'cp --preserve=mode,ownership,timestamps -- "$BACKUP" "$COMPOSE_FILE"' in trap


def test_web_start_is_dependency_free_after_read_only_postgres_healthcheck():
    source = ACTION.read_text(encoding="utf-8")
    postgres_ps = source.index('ps -q postgres)"')
    postgres_inspect = source.index("postgres_health=", postgres_ps)
    web_start = source.index("up -d --no-deps web")
    assert postgres_ps < postgres_inspect < web_start
    assert "up -d web" not in source


def test_action_never_manages_or_mutates_postgres():
    source = ACTION.read_text(encoding="utf-8")
    forbidden = (
        r"docker compose[^\n]*(?:up|restart|stop|rm|create)[^\n]*postgres",
        r"docker compose[^\n]*exec[^\n]*postgres",
        r"\bpsql\b",
        r"\b(?:migrate|migration|schema)\b[^\n]*(?:apply|deploy|update|alter)",
    )
    for pattern in forbidden:
        assert re.search(pattern, source, re.IGNORECASE) is None


def test_version_probe_requires_exact_octopus_version():
    source = ACTION.read_text(encoding="utf-8")
    function_source = "def version_matches" + source.split("def version_matches", 1)[1].split("\n\n", 1)[0]
    namespace = {}
    exec(function_source, namespace)
    version_matches = namespace["version_matches"]

    assert version_matches({"version": "1.0.122", "buildId": "abc", "server": "selfhost",
                            "selfHosted": True})
    for payload in (
        {"version": "1.0.121"},
        {"version": "v1.0.122"},
        {"release": "1.0.122"},
        {"version": 1.0122},
        [{"version": "1.0.122"}],
        "1.0.122",
    ):
        assert not version_matches(payload)
