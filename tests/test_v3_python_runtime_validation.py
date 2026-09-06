from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import yaml

from tests.test_v3_checkpoint_validator_runtime import is_verified_checkpoint_preinstall_job


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
EXPECTED_SYNC = (
    "python -m uv sync --project apps/api --frozen --group test "
    "--no-install-project"
)
LEGACY_DRIVER = "psycopg" + "2"
OLD_PYTHON = re.compile(
    r"(?i)(?:(?:cpython|python)\s+3\.(?:11|12|13)\b|"
    r"python-version\s*:\s*['\"]?3\.(?:11|12|13)\b|"
    r"FROM\s+python:3\.(?:11|12|13)\b|"
    r"python3\.(?:11|12|13)\b|py\s+-3\.(?:11|12|13)\b|"
    r"\b(?:py|cp)3(?:11|12|13)\b)"
)


def _workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _repository_text_files():
    text_suffixes = {
        ".css", ".html", ".js", ".json", ".lock", ".md", ".mjs", ".ps1",
        ".py", ".sh", ".svg", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "node_modules", ".pytest_cache"} or part.startswith(".venv") for part in path.parts):
            continue
        if path.suffix in text_suffixes or path.name.startswith(("Dockerfile", "requirements")):
            yield path


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


def test_every_active_workflow_python_selection_and_label_is_cpython314():
    setup_steps: list[tuple[Path, dict]] = []
    for path in WORKFLOWS.glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in workflow.get("jobs", {}).items():
            if is_verified_checkpoint_preinstall_job(path, job_name, job):
                continue
            steps = job.get("steps", [])
            job_setup_steps = []
            for step in steps:
                if str(step.get("uses", "")).startswith("actions/setup-python@"):
                    setup_steps.append((path, step))
                    job_setup_steps.append(step)
            commands = "\n".join(str(step.get("run", "")) for step in steps)
            if re.search(r"(?:^|[\s/])python(?:3)?(?:\s|$)|\.py(?:\s|$)", commands):
                assert job_setup_steps, path

    assert setup_steps
    for path, step in setup_steps:
        assert step.get("with", {}).get("python-version") == "3.14", path
        assert not OLD_PYTHON.search(str(step.get("name", ""))), path


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


def test_python_project_and_container_authorities_are_exactly_314():
    root_project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    api_project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8"))

    assert root_project["project"]["requires-python"] == ">=3.14,<3.15"
    assert root_project["project"]["classifiers"] == ["Programming Language :: Python :: 3.14"]
    assert root_project["tool"]["ruff"]["target-version"] == "py314"
    assert api_project["project"]["requires-python"] == ">=3.14,<3.15"

    for path in (
        ROOT / "apps" / "api" / "Dockerfile",
        ROOT / "apps" / "api" / "Dockerfile.release",
        ROOT / "apps" / "eddn" / "Dockerfile",
        ROOT / "apps" / "importer" / "Dockerfile",
        ROOT / "apps" / "maintenance" / "Dockerfile",
    ):
        text = path.read_text(encoding="utf-8")
        python_bases = re.findall(r"^FROM python:([^\s@]+)", text, flags=re.MULTILINE)
        assert python_bases, path
        assert all(version.startswith("3.14-") for version in python_bases), path
        assert not OLD_PYTHON.search(text), path


def test_api_test_dependencies_are_locked_beside_but_excluded_from_release_runtime():
    project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "apps" / "api" / "uv.lock").read_text())
    release_dockerfile = (ROOT / "apps" / "api" / "Dockerfile.release").read_text()

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


def test_driver_ownership_and_dependency_pins_are_explicit():
    api_project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text())
    api_runtime = api_project["project"]["dependencies"]
    api_tests = api_project["dependency-groups"]["test"]
    importer = (ROOT / "apps" / "importer" / "requirements.txt").read_text(encoding="utf-8")
    eddn = (ROOT / "apps" / "eddn" / "requirements.txt").read_text(encoding="utf-8")
    root_tests = (ROOT / "tests" / "requirements-ci.txt").read_text(encoding="utf-8")

    assert "asyncpg==0.31.0" in api_runtime
    assert all(not dependency.startswith("psycopg") for dependency in api_runtime)
    assert "psycopg[binary]==3.3.4" in api_tests
    assert "psycopg[binary]==3.3.4" in importer
    assert "asyncpg" not in importer
    assert "asyncpg==0.31.0" in eddn
    assert "psycopg[binary]==3.3.4" in root_tests
    assert "import asyncpg" in (ROOT / "apps" / "api" / "src" / "state.py").read_text()
    assert "import asyncpg" in (ROOT / "apps" / "eddn" / "src" / "eddn_listener.py").read_text()


def test_api_and_eddn_runtime_sources_remain_asyncpg_owned():
    for source_root in (ROOT / "apps" / "api" / "src", ROOT / "apps" / "eddn" / "src"):
        imports = {
            name
            for path in source_root.rglob("*.py")
            for name in _imports(path)
        }
        assert "asyncpg" in imports
        assert not any(name == "psycopg" or name.startswith("psycopg.") for name in imports)


def test_no_active_dependency_or_python_source_reintroduces_legacy_driver():
    dependency_paths = [
        *ROOT.glob("**/requirements*.txt"),
        *ROOT.glob("**/pyproject.toml"),
        ROOT / "apps" / "api" / "uv.lock",
        *WORKFLOWS.glob("*.yml"),
        *ROOT.glob("apps/**/Dockerfile*"),
    ]
    dependency_paths = [
        path for path in dependency_paths
        if not any(part.startswith(".venv") for part in path.parts)
    ]
    for path in dependency_paths:
        assert LEGACY_DRIVER not in path.read_text(encoding="utf-8").lower(), path

    for source_root in (ROOT / "apps", ROOT / "scripts", ROOT / "shared_contracts", ROOT / "tests"):
        for path in source_root.rglob("*.py"):
            if any(part.startswith(".venv") for part in path.parts):
                continue
            assert LEGACY_DRIVER not in path.read_text(encoding="utf-8").lower(), path


def test_repository_legacy_strings_are_only_historical_or_non_python_data():
    driver_hits = set()
    old_version_hits = set()
    for path in _repository_text_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        if LEGACY_DRIVER in text.lower():
            driver_hits.add(relative)
        if OLD_PYTHON.search(text):
            old_version_hits.add(relative)

    assert driver_hits == {
        "docs/development/code-quality-findings.md",
        "docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md",
        "docs/superpowers/plans/2026-08-10-scoring-cleanup-migration.md",
    }
    for relative in driver_hits:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "Historical implementation evidence only" in text or "RESOLVED" in text

    assert old_version_hits == {
        "apps/api/uv.lock",  # platform-specific wheel filenames for dependencies
    }


def test_importer_tooling_is_validated_on_314_without_collection_quarantine():
    manifest = ROOT / "tests" / "synchronous_tooling_test_paths.txt"
    paths = [
        line.strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    coverage = (WORKFLOWS / "coverage.yml").read_text(encoding="utf-8")
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert len(paths) == len(set(paths))
    assert all((ROOT / path).is_file() for path in paths)
    assert "Importer and synchronous tooling (CPython 3.14)" in ci
    assert "tests/synchronous_tooling_test_paths.txt" in ci
    assert "legacy-tooling" not in ci
    assert "--v3-api-only" not in ci
    assert "--v3-api-only" not in coverage
    assert "pytest_ignore_collect" not in conftest


def test_dev_python_launchers_do_not_select_retired_interpreters():
    launcher_paths = (
        ROOT / "scripts" / "dev" / "bootstrap-windows.ps1",
        ROOT / "scripts" / "dev" / "doctor.ps1",
        ROOT / "frontend" / "scripts" / "types-gen.mjs",
        ROOT / "scripts" / "checks" / "local-ci-parity.sh",
        ROOT / "scripts" / "checks" / "openapi-drift.sh",
        ROOT / "scripts" / "run_canonical_safety_tests.sh",
        ROOT / "scripts" / "run_data_invariants_receipted.sh",
    )
    for path in launcher_paths:
        text = path.read_text(encoding="utf-8")
        assert not OLD_PYTHON.search(text), path
        assert "3.14" in text, path
