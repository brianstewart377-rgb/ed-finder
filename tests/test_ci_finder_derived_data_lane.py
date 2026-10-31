"""Contract for the Finder derived-data CI lane and its fixture-module discovery."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
WEIGHTS = ROOT / "scripts/ci/finder_derived_data_weights.json"
FIXTURE_PATTERN = r"RATINGS_V4_VALIDATION_DATABASE_URL|ratings_v4_pg_fixture|canonical_database"
DISCOVERY_COMMAND = (
    f"grep -lE '{FIXTURE_PATTERN}' tests/test_*.py \\\n"
    "    | grep -v '^tests/test_ratings_v4' | sort"
)

# Modules that must keep running on PostgreSQL 18 whatever else the discovery
# finds: the migration-015 publication contract, the builders, the V3 routes and
# the F2d operator programs all skipped silently before this lane existed.
KNOWN_FIXTURE_BACKED_MODULES = (
    "tests/test_archetype_rankings_v3.py",
    "tests/test_archetype_system_v3.py",
    "tests/test_local_search_v3.py",
    "tests/test_ranking_identity_and_no_legacy.py",
    "tests/test_v3_derived_product_publication.py",
    "tests/test_v3_finder_galaxy_window_plan_pg18.py",
    "tests/test_v3_system_archetype_build.py",
    "tests/test_v3_system_archetype_validate.py",
    "tests/test_v3_watchlist_postgres.py",
)


def _lane() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["finder-derived-data"]


def _shard_plugin() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "finder_derived_data_lane_shards", ROOT / "scripts/ci/finder_derived_data_shards.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _discover_with_the_lane_command() -> list[str]:
    run = next(
        step["run"] for step in _lane()["steps"]
        if step.get("name") == "Run every validation-fixture-backed Finder test module"
    )
    discovery = re.search(r"grep -lE '([^']+)' tests/test_\*\.py \\\n\s*\| grep -v '([^']+)'", run)
    assert discovery is not None, run
    assert discovery.group(1) == FIXTURE_PATTERN
    assert discovery.group(2) == "^tests/test_ratings_v4"
    assert DISCOVERY_COMMAND in run
    completed = subprocess.run(
        ["bash", "-c", f"grep -lE '{discovery.group(1)}' tests/test_*.py | grep -v '{discovery.group(2)}' | sort"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return completed.stdout.split()


def test_lane_runs_on_postgresql_18_with_the_validation_fixture_url() -> None:
    lane = _lane()
    assert lane["services"]["postgres"]["image"].endswith("postgres:18-alpine")
    assert lane["services"]["postgres"]["env"]["POSTGRES_DB"] == "ratings_v4_validation"
    assert lane["services"]["postgres"]["ports"] == ["55432:5432"]
    run_step = next(
        step for step in lane["steps"]
        if step.get("name") == "Run every validation-fixture-backed Finder test module"
    )
    env = run_step["env"]
    assert env["RATINGS_V4_VALIDATION_DATABASE_URL"] == (
        "postgresql://edfinder:edfinder@127.0.0.1:55432/ratings_v4_validation"
    )
    assert env["EDFINDER_DISPOSABLE_DSN"] == env["RATINGS_V4_VALIDATION_DATABASE_URL"]
    assert env["EDFINDER_DISPOSABLE_SERVER_ADDRESS"] == "${{ steps.disposable.outputs.address }}"
    assert "-rs" in run_step["run"]
    attest = next(step for step in lane["steps"] if step.get("id") == "disposable")
    assert attest["env"]["SERVICE_ID"] == "${{ job.services.postgres.id }}"
    assert "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'" in attest["run"]
    assert lane["steps"].index(attest) < lane["steps"].index(run_step)


def test_discovery_finds_every_known_fixture_backed_module() -> None:
    discovered = _discover_with_the_lane_command()
    assert len(discovered) >= 10
    for module in KNOWN_FIXTURE_BACKED_MODULES:
        assert module in discovered, module
    assert not any(path.startswith("tests/test_ratings_v4") for path in discovered)
    # Each discovered module really imports or names the fixture it was found by.
    for path in discovered:
        assert re.search(FIXTURE_PATTERN, (ROOT / path).read_text(encoding="utf-8")), path


def test_three_shards_collect_every_discovered_module_and_upload_durations(tmp_path: Path) -> None:
    """Every shard gives the plugin the same collection and its own shard number."""
    lane = _lane()
    assert lane["strategy"]["matrix"]["shard"] == [1, 2, 3]
    assert lane["strategy"]["fail-fast"] is False
    assert lane["name"].endswith("/3)")
    assert lane["timeout-minutes"] == 60
    run_step = next(
        step for step in lane["steps"]
        if step.get("name") == "Run every validation-fixture-backed Finder test module"
    )
    assert run_step["env"]["SHARD"] == "${{ matrix.shard }}"
    assert run_step["env"]["PYTHONPATH"] == (
        "${{ github.workspace }}/apps/api/src:${{ github.workspace }}/scripts/ci"
    )
    run = run_step["run"]
    for expected in (
        DISCOVERY_COMMAND,
        "timeout --signal=INT --kill-after=60s 45m",
        "-p finder_derived_data_shards",
        "--finder-shards 3",
        "--finder-weights scripts/ci/finder_derived_data_weights.json",
        '--finder-durations-out "$RUNNER_TEMP/finder-derived-data-durations-$SHARD.json"',
    ):
        assert expected in run
    upload = lane["steps"][-1]
    assert upload["name"] == "Upload shard durations"
    assert upload["if"] == "always()"
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert upload["with"] == {
        "name": "finder-derived-data-durations-${{ matrix.shard }}",
        "path": "${{ runner.temp }}/finder-derived-data-durations-${{ matrix.shard }}.json",
        "retention-days": 14,
        "if-no-files-found": "ignore",
    }

    fake = tmp_path / "timeout"
    fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    fake.chmod(0o755)
    discovered = _discover_with_the_lane_command()
    for shard in ("1", "2", "3"):
        completed = subprocess.run(
            ["bash", "-c", run], cwd=ROOT, capture_output=True, text=True, check=True,
            env={"PATH": f"{tmp_path}:/usr/bin:/bin", "SHARD": shard, "RUNNER_TEMP": str(tmp_path)},
        )
        argv = completed.stdout.splitlines()
        start = argv.index("pytest") + 1
        modules = [item for item in argv[start:] if item.startswith("tests/")]
        assert modules == discovered, completed.stdout
        assert argv[start:start + len(discovered)] == discovered
        assert argv[argv.index("--finder-shard") + 1] == shard
        assert argv[argv.index("--finder-durations-out") + 1] == str(
            tmp_path / f"finder-derived-data-durations-{shard}.json"
        )
    for shard in ("0", "4", ""):
        refused = subprocess.run(
            ["bash", "-c", run], cwd=ROOT, capture_output=True, text=True,
            env={"PATH": f"{tmp_path}:/usr/bin:/bin", "SHARD": shard, "RUNNER_TEMP": str(tmp_path)},
        )
        assert refused.returncode != 0 and "shard must be 1, 2 or 3" in refused.stderr


def test_real_collection_has_a_complete_balanced_plan() -> None:
    """Collect once without a database; new or renamed modules use the fallback rate."""
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         *_discover_with_the_lane_command()],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    nodeids = [line for line in collected.stdout.splitlines() if "::" in line]
    assert nodeids, collected.stdout
    plugin = _shard_plugin()
    planned = plugin.plan(nodeids, plugin.load_weights(WEIGHTS), 3, lambda path: (ROOT / path).stat().st_size)
    assert len(nodeids) == len(set(nodeids))
    assert set(planned.assignment) == set(nodeids)
    assert set(planned.assignment.values()) == {1, 2, 3}
    assert max(planned.totals) <= 1.3 * min(planned.totals)
    for module in planned.split_modules:
        assert {
            shard for nodeid, shard in planned.assignment.items()
            if nodeid.split("::", 1)[0] == module
        } == {1, 2, 3}, module


def test_weights_file_is_valid_and_uses_the_refresh_format() -> None:
    raw = WEIGHTS.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert _shard_plugin().load_weights(WEIGHTS) == data["seconds"]
    assert raw == json.dumps(data, indent=2, sort_keys=True) + "\n"
