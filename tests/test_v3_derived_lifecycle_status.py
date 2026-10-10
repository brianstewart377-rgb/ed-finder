from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = (
    ROOT
    / "scripts"
    / "operator"
    / "actions"
    / "v3-derived-lifecycle-status.sh"
)
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ed-new-ops.yml"

WORKERS = (
    "edfinder-ratings-v4-prod-p4",
    "edfinder-ratings-v4-prod-p4-opt1",
    "edfinder-ratings-v4-prod-p4-parallel-v1",
    "edfinder-v3-system-search-p4-opt1",
)

FORBIDDEN = (
    ".env",
    "Config.Env",
    "docker restart",
    "docker compose up",
    "docker compose down",
    "docker stop",
    "docker rm",
    "systemctl",
    "pg_dump",
    "pg_restore",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "ALTER",
    "DROP",
    "CREATE",
    "ADMIN_TOKEN",
    "FRONTIER_CLIENT_SECRET",
    "/root/.ssh",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_python_body(source: str) -> str:
    match = re.search(
        r'^exec "\$PYTHON_BIN" - <<\'PY\'\n(?P<body>.*)^PY\s*$',
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "expected the action's exec Python heredoc"
    return match.group("body")


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def test_v3_derived_lifecycle_status_is_allowlisted_through_trusted_main_path():
    workflow = _read(WORKFLOW)

    assert "          - v3-derived-lifecycle-status\n" in workflow
    assert workflow.index("          - v3-spatial-status\n") < workflow.index(
        "          - v3-derived-lifecycle-status\n"
    )
    assert re.search(
        r"^[ \t]*[^\n]*v3-derived-lifecycle-status[^\n]*\) ;;$",
        workflow,
        flags=re.MULTILINE,
    )
    assert (
        "steps.request.outputs.operation == 'v3-derived-lifecycle-status'"
        in workflow
    )
    assert "- name: Inspect V3 derived lifecycle status" in workflow
    assert (
        "trusted-main/scripts/operator/actions/v3-derived-lifecycle-status.sh"
        in workflow
    )
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow


def test_v3_derived_lifecycle_status_has_fixed_read_only_runtime_targets():
    source = _read(ACTION)

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert (
        'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"'
        in source
    )
    positions = [source.index(f'"{worker}"') for worker in WORKERS]
    assert positions == sorted(positions)
    assert (
        '"{{.State.Status}}\\t{{.State.Running}}\\t{{.State.ExitCode}}\\t'
        '{{.State.FinishedAt}}"'
        in source
    )
    assert "BEGIN READ ONLY" in source
    assert re.search(r"^STATEMENT_TIMEOUT_MS = 20_?000$", source, re.MULTILINE)
    assert "statement_timeout" in source
    assert '"db_writes_performed": False' in source
    assert '"read_only": True' in source
    assert "ON_ERROR_STOP=1" in source


def test_v3_derived_lifecycle_status_excludes_mutation_and_secrets():
    source = _read(ACTION)

    for forbidden in FORBIDDEN:
        assert forbidden not in source


def test_v3_derived_lifecycle_status_shell_syntax_is_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")

    result = subprocess.run(
        [bash, "-n", str(ACTION)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_v3_derived_lifecycle_status_reports_canned_read_only_state(tmp_path: Path):
    body_path = tmp_path / "v3_derived_lifecycle_status_body.py"
    body_path.write_text(_extract_python_body(_read(ACTION)), encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "hostname",
        """#!/bin/sh
if [ "${1:-}" = "-f" ]; then
    printf '%s\\n' 'nb79a3d.mevnode.com'
else
    printf '%s\\n' 'ed-finder-prod'
fi
""",
    )
    _write_executable(
        fake_bin / "pwd",
        """#!/bin/sh
printf '%s\\n' '/opt/ed-finder'
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/bin/sh
postgres='edfinder-v3-phase4c-full-20260827_r5-postgres'

if [ "$1" = "inspect" ] && [ "$2" = "-f" ]; then
    format="$3"
    container="$4"
    if [ "$container" = "$postgres" ] && [ "$format" = '{{.State.Running}}' ]; then
        printf 'true\\n'
        exit 0
    fi
    case "$container" in
        edfinder-ratings-v4-prod-p4|edfinder-ratings-v4-prod-p4-opt1|edfinder-ratings-v4-prod-p4-parallel-v1)
            printf 'exited\\tfalse\\t0\\t2026-10-01T00:00:00Z\\n'
            exit 0
            ;;
        edfinder-v3-system-search-p4-opt1)
            exit 1
            ;;
    esac
    exit 1
fi

if [ "$1" != "exec" ] || [ "$2" != "$postgres" ]; then
    exit 1
fi
if [ "$3" = "sh" ]; then
    printf 'edfinder_v3\\tedfinder_v3_db\\n'
    exit 0
fi
if [ "$3" != "psql" ]; then
    exit 1
fi

sql="$*"
case "$sql" in
    *"to_regclass('v3_meta.derived_product')"*)
        case "$sql" in
            *"IS NOT NULL"*) printf 'true\\n' ;;
            *) printf 'v3_meta.derived_product\\n' ;;
        esac
        ;;
    *"to_regclass('v3_spatial.current_spatial_generation')"*)
        case "$sql" in
            *"IS NOT NULL"*) printf 'true\\n' ;;
            *) printf 'v3_spatial.current_spatial_generation\\n' ;;
        esac
        ;;
    *"FROM v3_meta.schema_migration"*)
        printf '006_v3_derived_product_lifecycle.sql\\t06aa\\t2026-09-01 00:00:00+00\\n'
        printf '011_v3_system_archetype.sql\\t11aa\\t2026-09-02 00:00:00+00\\n'
        printf '013_v3_system_search_parallel.sql\\t13aa\\t2026-09-03 00:00:00+00\\n'
        printf '014_v3_watchlist.sql\\t14aa\\t2026-09-04 00:00:00+00\\n'
        ;;
    *"v3_meta.current_derived_generation"*"v3_meta.derived_product"*|*"v3_meta.derived_product"*"v3_meta.current_derived_generation"*)
        printf 'system_search\\tREADY\\n'
        printf 'system_archetype\\tBUILDING\\n'
        ;;
    *"FROM v3_meta.current_canonical_generation"*)
        printf '10000000-0000-0000-0000-000000000001\\tcanonical-canned\\tv3_canonical\\tPUBLISHED\\t4\\t2026-09-01 00:00:00+00\\n'
        ;;
    *"FROM v3_meta.canonical_generation"*)
        printf '10000000-0000-0000-0000-000000000001\\tcanonical-canned\\tPUBLISHED\\t2026-08-01 00:00:00+00\\t2026-09-01 00:00:00+00\\t\\t\\t\\n'
        ;;
    *"FROM v3_meta.current_derived_generation"*)
        printf '20000000-0000-0000-0000-000000000002\\tderived-canned\\tPUBLISHED\\t10000000-0000-0000-0000-000000000001\\t2\\t2026-09-05 00:00:00+00\\n'
        ;;
    *"FROM v3_meta.derived_product"*)
        printf '20000000-0000-0000-0000-000000000002\\tderived-canned\\tsystem_search\\tv2\\tREADY\\t198528286\\t2026-09-02 00:00:00+00\\t2026-09-04 00:00:00+00\\t\\t\\tabcd\\n'
        ;;
    *"FROM v3_meta.derived_generation"*)
        printf '20000000-0000-0000-0000-000000000002\\tderived-canned\\t10000000-0000-0000-0000-000000000001\\t4\\tmechanics-v4\\tscorer-v4\\tadapter-v1\\tPUBLISHED\\t198528286\\t1200000000\\t2026-09-02 00:00:00+00\\t2026-09-04 00:00:00+00\\t2026-09-05 00:00:00+00\\t\\t\\n'
        ;;
    *"FROM v3_spatial.current_spatial_generation"*)
        printf '30000000-0000-0000-0000-000000000003\\t10000000-0000-0000-0000-000000000001\\tpyramid-v1\\tPUBLISHED\\t1\\t2026-09-06 00:00:00+00\\n'
        ;;
    *"FROM v3_spatial.spatial_generation"*)
        printf '30000000-0000-0000-0000-000000000003\\t10000000-0000-0000-0000-000000000001\\tpyramid-v1\\tPUBLISHED\\t198528286\\t2026-09-03 00:00:00+00\\t2026-09-05 00:00:00+00\\t2026-09-06 00:00:00+00\\t\\t\\n'
        ;;
    *)
        printf 'unmatched SQL: %s\\n' "$sql" >&2
        exit 2
        ;;
esac
""",
    )

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))

    result = subprocess.run(
        [sys.executable, str(body_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["status"] == "success"
    assert receipt["all_named_workers_stopped"] is True
    assert receipt["finder_migrations_applied"][
        "010_v3_system_search_body_type_counts.sql"
    ] is False
    assert receipt["derived"]["generation_key"] == "derived-canned"
    assert any(
        product["product_code"] == "system_search"
        and product["lifecycle_state"] == "READY"
        for product in receipt["derived_products"]
    )
    assert receipt["spatial"]["present"] is True
    assert (
        receipt["spatial"]["current"]["spatial_generation_id"]
        == "30000000-0000-0000-0000-000000000003"
    )
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is True
    assert receipt["direct_db_access_performed"] is True
