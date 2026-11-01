"""Keep the V3 journal flows on their own required, disposable CI database."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    "sql/v3/migrations/001_v3_baseline.sql",
    "sql/v3/migrations/002_v3_accounts_identity.sql",
    "sql/v3/migrations/005_v3_journal_intelligence.sql",
    "sql/v3/migrations/008_v3_journal_commander_ownership.sql",
    "sql/v3/migrations/009_v3_journal_galaxy_contributions.sql",
]
FLOW_MODULES = [
    "tests/integration/test_v3_journal_research_flow.py",
    "tests/integration/test_v3_journal_import_flow.py",
]


def _workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def _step(name: str) -> dict:
    return next(
        step for step in _workflow()["jobs"]["journal-flows"]["steps"]
        if step.get("name") == name
    )


def test_lane_uses_mirrored_pg18_and_redis_with_pinned_actions_and_read_permissions() -> None:
    workflow = _workflow()
    lane = workflow["jobs"]["journal-flows"]
    assert lane["name"] == "V3 journal flows (PG18+Redis)"
    assert lane["runs-on"] == "ubuntu-latest"
    assert lane["timeout-minutes"] == 15
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in lane
    assert "if" not in lane
    assert not lane.get("continue-on-error", False)
    postgres = lane["services"]["postgres"]
    assert postgres["image"] == (
        workflow["jobs"]["journal-contributions"]["services"]["postgres"]["image"]
    ) == "ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine"
    assert postgres["env"]["POSTGRES_DB"] == "journal_flow_test"
    assert postgres["ports"] == ["5432:5432"]
    assert "--health-cmd pg_isready" in postgres["options"]
    assert lane["services"]["redis"] == workflow["jobs"]["integration"]["services"]["redis"]
    uses = [step["uses"] for step in lane["steps"] if "uses" in step]
    assert uses == [
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    ]
    assert all(not step.get("continue-on-error", False) for step in lane["steps"])


@pytest.mark.parametrize("fail_migration", [None, MIGRATIONS[2]])
def test_migration_step_applies_only_journal_schema_in_order_and_stops_on_error(
    tmp_path: Path, fail_migration: str | None,
) -> None:
    step = _step("Apply V3 journal fixture migrations")
    capture = tmp_path / "psql-args.jsonl"
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['PSQL_CAPTURE'], 'a', encoding='utf-8') as capture:\n"
        "    capture.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(1 if os.environ.get('FAIL_MIGRATION') in sys.argv[1:] else 0)\n",
        encoding="utf-8",
    )
    fake_psql.chmod(0o755)
    completed = subprocess.run(
        ["bash", "-c", step["run"]], cwd=ROOT, capture_output=True, text=True,
        env={
            **os.environ, **step["env"], "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "PSQL_CAPTURE": str(capture), "FAIL_MIGRATION": fail_migration or "",
        },
    )
    calls = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    expected_migrations = MIGRATIONS if fail_migration is None else MIGRATIONS[:3]
    assert [args[args.index("-f") + 1] for args in calls] == expected_migrations
    for args in calls:
        assert args[args.index("-h") + 1] == "localhost"
        assert args[args.index("-d") + 1] == "journal_flow_test"
        assert args[args.index("-v") + 1] == "ON_ERROR_STOP=1"
        assert "-X" in args
    assert completed.returncode == (0 if fail_migration is None else 1), completed.stderr


def test_lane_runs_both_modules_after_migrations_with_required_database_and_skip_check() -> None:
    lane = _workflow()["jobs"]["journal-flows"]
    migration_step = _step("Apply V3 journal fixture migrations")
    run_step = _step("Run V3 journal research and import flows")
    assert lane["steps"].index(migration_step) < lane["steps"].index(run_step)
    env = run_step["env"]
    assert env["DATABASE_URL"] == "postgresql://edfinder:edfinder@localhost:5432/journal_flow_test"
    assert env["REDIS_URL"] == "redis://localhost:6379/15"
    assert env["CORS_ORIGINS"] == "http://test"
    assert env["ADMIN_TOKEN"] == "test-admin-token"
    assert env["EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET"] == "yes"
    assert env["EDF_DB_TESTS_REQUIRED"] == "1"
    assert env["EDDN_SIMULATION_INGEST_ENABLED"] == "false"
    assert env["PYTHONPATH"] == "apps/api/src:."
    run = run_step["run"]
    command = run.split("apps/api/.venv/bin/python -m pytest", 1)[1].split("\n#", 1)[0]
    args = shlex.split(command.replace("\\\n", ""))
    assert [arg for arg in args if arg.startswith("tests/")] == FLOW_MODULES
    assert "-q" in args
    assert "--junitxml=$RUNNER_TEMP/journal-flows.xml" in args
    assert 'apps/api/.venv/bin/python - "$RUNNER_TEMP/journal-flows.xml"' in run
    assert "set -euo pipefail" in run


@pytest.mark.parametrize(
    ("report", "accepted"),
    [
        ('<testsuites><testsuite><testcase name="passed"/></testsuite></testsuites>', True),
        ('<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>', False),
        ('<testsuites><testsuite/></testsuites>', False),
        ('<testsuites><testsuite><testcase/></testsuite>', False),
    ],
)
def test_lane_rejects_skipped_empty_or_malformed_test_reports(
    tmp_path: Path, report: str, accepted: bool,
) -> None:
    run = _step("Run V3 journal research and import flows")["run"]
    guard = re.search(r"<<'PY'\n(.*?)\nPY(?:\n|$)", run, re.DOTALL)
    assert guard is not None
    report_path = tmp_path / "journal-flows.xml"
    report_path.write_text(report, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-c", guard.group(1), str(report_path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert (completed.returncode == 0) is accepted, completed.stdout + completed.stderr
