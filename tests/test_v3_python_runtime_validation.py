from __future__ import annotations

import re
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


def test_v3_api_graph_uses_asyncpg_and_psycopg3_without_legacy_driver():
    project_text = (ROOT / "apps" / "api" / "pyproject.toml").read_text()
    lock_text = (ROOT / "apps" / "api" / "uv.lock").read_text()
    project = tomllib.loads(project_text)

    assert "asyncpg==0.31.0" in project["project"]["dependencies"]
    assert all(not dependency.startswith("psycopg") for dependency in project["project"]["dependencies"])
    assert "psycopg[binary]==3.3.4" in project["dependency-groups"]["test"]
    assert "psycopg2" not in project_text
    assert "psycopg2" not in lock_text


def test_v3_api_and_legacy_psycopg2_test_lanes_are_explicitly_separated():
    manifest = ROOT / "tests" / "legacy_psycopg2_test_paths.txt"
    paths = [
        line.strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    coverage = (WORKFLOWS / "coverage.yml").read_text(encoding="utf-8")

    assert len(paths) == len(set(paths))
    assert all((ROOT / path).is_file() for path in paths)
    assert "--v3-api-only" in ci
    assert "--v3-api-only" in coverage
    assert "Legacy importer/tooling tests (non-runtime)" in ci
    assert "tests/legacy_psycopg2_test_paths.txt" in ci
    assert "Synchronous PostgreSQL tooling (CPython 3.14)" in ci
    assert "scripts/checks/requirements.txt" in ci
    assert "tests/test_deploy_main_invariants_gate.py" in ci
    assert "--ignore=tests/test_deploy_main_invariants_gate.py" in ci
    assert "--ignore=tests/test_deploy_main_invariants_gate.py" in coverage


def test_remaining_psycopg2_source_debt_is_explicit_and_outside_v3_checks():
    debt = (ROOT / "docs" / "development" / "psycopg3-migration-debt.md").read_text()
    remaining_paths = sorted(
        path.relative_to(ROOT).as_posix()
        for search_root in (ROOT / "apps" / "importer" / "src", ROOT / "scripts")
        for path in search_root.rglob("*.py")
        if any(
            marker in path.read_text(encoding="utf-8")
            for marker in ("import psycopg2", "from psycopg2")
        )
    )

    assert remaining_paths
    assert all(f"`{path}`" in debt for path in remaining_paths)
    assert not any(path.startswith("scripts/checks/") for path in remaining_paths)


def test_canonical_worker_bootstrap_fails_closed_on_cpython314():
    worker = (WORKFLOWS / "codex-laptop.yml").read_text(encoding="utf-8")
    assert '- name: Set up CPython 3.14' in worker
    assert 'python-version: "3.14"' in worker
    assert 'platform.python_implementation() == "CPython"' in worker
    assert "sys.version_info[:2] == (3, 14)" in worker


def test_every_active_workflow_python_job_selects_exact_cpython314():
    python_command = re.compile(
        r"(?<![\w.-])python(?:3(?:\.(?P<minor>\d+))?)?(?![\w.-])"
    )

    workflow_paths = (*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))
    for workflow_path in sorted(workflow_paths):
        workflow_text = workflow_path.read_text(encoding="utf-8")
        assert "3.11" not in workflow_text
        assert "3.12" not in workflow_text

        for job_name, job in _workflow(workflow_path.name)["jobs"].items():
            steps = job.get("steps", [])
            setup_indexes = [
                index
                for index, step in enumerate(steps)
                if step.get("uses", "").startswith("actions/setup-python@")
            ]
            for setup_index in setup_indexes:
                assert steps[setup_index]["with"]["python-version"] == "3.14", (
                    workflow_path.name,
                    job_name,
                )

            python_indexes = []
            for index, step in enumerate(steps):
                matches = list(python_command.finditer(str(step.get("run", ""))))
                if not matches:
                    continue
                python_indexes.append(index)
                assert all(
                    match.group("minor") in (None, "14") for match in matches
                ), (workflow_path.name, job_name)
            matrix_languages = (
                job.get("strategy", {}).get("matrix", {}).get("language", [])
            )
            configures_python_analysis = "python" in matrix_languages
            if python_indexes or configures_python_analysis:
                assert setup_indexes, (workflow_path.name, job_name)
            if python_indexes:
                assert min(setup_indexes) < min(python_indexes), (
                    workflow_path.name,
                    job_name,
                )
