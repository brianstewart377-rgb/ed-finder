"""Contract for the Finder derived-data CI lane and its fixture-module discovery."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
FIXTURE_PATTERN = r"RATINGS_V4_VALIDATION_DATABASE_URL|ratings_v4_pg_fixture|canonical_database"

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


def _discover_with_the_lane_command() -> list[str]:
    run = next(
        step["run"] for step in _lane()["steps"]
        if step.get("name") == "Run every validation-fixture-backed Finder test module"
    )
    discovery = re.search(r"grep -lE '([^']+)' tests/test_\*\.py \\\n\s*\| grep -v '([^']+)'", run)
    assert discovery is not None, run
    assert discovery.group(1) == FIXTURE_PATTERN
    assert discovery.group(2) == "^tests/test_ratings_v4"
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
