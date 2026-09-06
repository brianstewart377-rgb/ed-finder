from __future__ import annotations

import ast
import re
import tomllib
from itertools import chain
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


def test_psycopg3_sync_tests_run_without_the_temporary_quarantine_boundary():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    coverage = (WORKFLOWS / "coverage.yml").read_text(encoding="utf-8")

    assert not (ROOT / "tests" / "legacy_psycopg2_test_paths.txt").exists()
    assert "--v3-api-only" not in ci
    assert "--v3-api-only" not in coverage
    assert "legacy-tooling:" not in ci
    assert "Synchronous PostgreSQL tooling (CPython 3.14)" in ci
    assert "scripts/checks/requirements.txt" in ci
    assert "tests/test_deploy_main_invariants_gate.py" in ci
    assert "--ignore=tests/test_deploy_main_invariants_gate.py" in ci
    assert "--ignore=tests/test_deploy_main_invariants_gate.py" in coverage


def _imports(path: Path) -> set[str]:
    # A few retained source files carry a UTF-8 BOM. Tokenize them the same way
    # Python's source loader does before applying the import-only AST guard.
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _active_python_files(search_root: Path):
    ignored_parts = {".venv", "__pycache__", "archive", "node_modules"}
    return (
        path
        for path in search_root.rglob("*.py")
        if not ignored_parts.intersection(path.relative_to(search_root).parts)
    )


def test_active_python_has_no_psycopg2_imports():
    active_roots = (
        ROOT / "apps",
        ROOT / "scripts",
        ROOT / "shared_contracts",
        ROOT / "tests",
    )
    violations = sorted(
        path.relative_to(ROOT).as_posix()
        for search_root in active_roots
        for path in _active_python_files(search_root)
        if any(name == "psycopg2" or name.startswith("psycopg2.") for name in _imports(path))
    )

    assert violations == []


def test_active_dependency_authority_has_no_psycopg2_packages():
    ignored_parts = {".git", ".venv", "archive", "artifacts", "node_modules"}
    dependency_authority = (
        path
        for path in chain(
            ROOT.rglob("pyproject.toml"),
            ROOT.rglob("*requirements*.txt"),
            ROOT.rglob("uv.lock"),
            ROOT.rglob("Dockerfile*"),
            (ROOT / ".github").rglob("*.yml"),
        )
        if not ignored_parts.intersection(path.relative_to(ROOT).parts)
    )
    legacy_package = re.compile(r"(?i)(?:types-|py3-)?psycopg2(?:-binary)?")
    violations = sorted(
        path.relative_to(ROOT).as_posix()
        for path in dependency_authority
        if legacy_package.search(path.read_text(encoding="utf-8"))
    )

    assert violations == []


def test_synchronous_pip_authorities_share_the_psycopg_334_pin():
    importer = (ROOT / "apps" / "importer" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    checks = (ROOT / "scripts" / "checks" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert importer.splitlines().count("psycopg[binary]==3.3.4") == 1
    assert checks.splitlines().count("psycopg[binary]==3.3.4") == 1


def test_api_and_eddn_runtime_sources_remain_asyncpg_owned():
    for source_root in (ROOT / "apps" / "api" / "src", ROOT / "apps" / "eddn" / "src"):
        imports = {
            name
            for path in source_root.rglob("*.py")
            for name in _imports(path)
        }
        assert "asyncpg" in imports
        assert not any(name == "psycopg" or name.startswith("psycopg.") for name in imports)


def test_canonical_worker_bootstrap_remains_python312_and_is_not_runtime_evidence():
    worker = (WORKFLOWS / "codex-laptop.yml").read_text(encoding="utf-8")
    assert '- name: Set up Python 3.12' in worker
    assert 'python-version: "3.12"' in worker
    assert "assert_v3_python_runtime.py" not in worker
