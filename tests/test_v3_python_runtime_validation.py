from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
EXPECTED_SYNC = (
    "python -m uv sync --project apps/api --frozen --group test "
    "--no-install-project"
)


def _workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))


def _assert_v3_job(filename: str, job_name: str) -> None:
    job = _workflow(filename)["jobs"][job_name]
    steps = job["steps"]
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.14"

    commands = "\n".join(str(step.get("run", "")) for step in steps)
    assert "python -m pip install uv==0.11.33" in commands
    assert '"uv 0.11.33"' in commands
    assert "python -m uv lock --project apps/api --check" in commands
    assert EXPECTED_SYNC in commands
    assert "apps/api/.venv/bin/python scripts/checks/assert_v3_python_runtime.py" in commands


def test_all_v3_application_validation_jobs_fail_closed_on_cpython314_and_frozen_uv():
    for filename, job_name in (
        ("ci.yml", "backend"),
        ("ci.yml", "integration"),
        ("ci.yml", "openapi-types"),
        ("coverage.yml", "backend-coverage"),
        ("cypress-parity.yml", "cypress-release-gate"),
        ("review-lab.yml", "review-lab"),
    ):
        _assert_v3_job(filename, job_name)


def test_browser_lanes_keep_separate_authority_while_sharing_python314_api_contract():
    product = (WORKFLOWS / "cypress-parity.yml").read_text(encoding="utf-8")
    review = (WORKFLOWS / "review-lab.yml").read_text(encoding="utf-8")
    review_lifecycle = (
        ROOT / "scripts" / "dev" / "review_lab" / "lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "browser: [chrome, firefox]" in product
    assert "edfinder_api.main:app" in product
    assert "review_main.py" not in product
    assert "scripts/dev/review_environment.py verify" in review
    assert "product-journey.cy.ts" not in review
    assert "'review-api', '/proc/1/exe'" in review_lifecycle
    assert "sys.version_info[:2] == (3, 14)" in review_lifecycle


def test_api_test_dependencies_are_locked_beside_but_excluded_from_release_runtime():
    project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "apps" / "api" / "uv.lock").read_text())
    release_dockerfile = (ROOT / "apps" / "api" / "Dockerfile.release").read_text()

    assert project["project"]["requires-python"] == ">=3.14,<3.15"
    assert project["tool"]["uv"]["required-version"] == "==0.11.33"
    assert {dependency.split("==", 1)[0].lower() for dependency in project["dependency-groups"]["test"]} >= {
        "coverage",
        "pytest",
        "pytest-asyncio",
        "ruff",
    }
    assert lock["requires-python"] == "==3.14.*"
    api_package = next(package for package in lock["package"] if package["name"] == "ed-finder-api")
    assert "test" in api_package["dev-dependencies"]
    assert "--no-group test" in release_dockerfile


def test_canonical_worker_bootstrap_remains_python312_and_is_not_runtime_evidence():
    worker = (WORKFLOWS / "codex-laptop.yml").read_text(encoding="utf-8")
    assert '- name: Set up Python 3.12' in worker
    assert 'python-version: "3.12"' in worker
    assert "assert_v3_python_runtime.py" not in worker
