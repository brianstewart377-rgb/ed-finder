from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REQUIRES_PYTHON = ">=3.14,<3.15"


def _active_execution_surfaces() -> list[Path]:
    surfaces = {
        ROOT / "Makefile",
        ROOT / "pyproject.toml",
        ROOT / "apps" / "api" / "pyproject.toml",
    }
    surfaces.update(ROOT.glob("docker-compose*.yml"))
    surfaces.update((ROOT / ".github" / "workflows").glob("*.yml"))
    surfaces.update((ROOT / ".github" / "workflows").glob("*.yaml"))
    surfaces.update(
        path
        for path in (ROOT / "apps").rglob("*")
        if path.is_file() and path.name.startswith("Dockerfile")
    )
    surfaces.update(
        path
        for base in (ROOT / "apps", ROOT / "scripts", ROOT / "frontend" / "scripts")
        for path in base.rglob("*")
        if path.is_file()
        and "archive" not in path.relative_to(ROOT).parts
        and path.suffix.lower()
        in {".js", ".mjs", ".ps1", ".py", ".sh", ".toml", ".yaml", ".yml"}
    )
    return sorted(surfaces)


PYTHON_SELECTORS = (
    re.compile(r"\b(?:CPython|Python)\s+3\.(?P<minor>\d{1,2})\b"),
    re.compile(r"\bpython-version\s*:\s*['\"]?3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bFROM\s+python:3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bpython3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bpy\s+-3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\b(?:py|cp)3(?P<minor>\d{2})\b", re.I),
)


def test_active_execution_surfaces_only_select_python314() -> None:
    violations: list[str] = []
    for path in _active_execution_surfaces():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            # Ruff's py313 setting is a documented grammar-only exception,
            # not an interpreter/runtime selection.
            if path == ROOT / "pyproject.toml" and "py313" in line:
                continue
            for pattern in PYTHON_SELECTORS:
                for match in pattern.finditer(line):
                    if int(match.group("minor")) != 14:
                        relative = path.relative_to(ROOT).as_posix()
                        violations.append(f"{relative}:{line_number}: {match.group(0)}")

    assert not violations, "non-3.14 Python selectors found:\n" + "\n".join(violations)


def test_all_python_workflow_jobs_setup_exact_cpython314_before_use() -> None:
    python_command = re.compile(
        r"(?<![\w.-])python(?:3(?:\.(?P<minor>\d+))?)?(?![\w.-])"
    )
    workflow_paths = (
        *(ROOT / ".github" / "workflows").glob("*.yml"),
        *(ROOT / ".github" / "workflows").glob("*.yaml"),
    )
    for path in sorted(workflow_paths):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            setup_indexes = [
                index
                for index, step in enumerate(steps)
                if str(step.get("uses", "")).startswith("actions/setup-python@")
            ]
            for setup_index in setup_indexes:
                assert steps[setup_index].get("with", {}).get("python-version") == "3.14", (
                    path.name,
                    job_name,
                )

            python_indexes: list[int] = []
            for index, step in enumerate(steps):
                matches = list(python_command.finditer(str(step.get("run", ""))))
                if not matches:
                    continue
                python_indexes.append(index)
                assert all(match.group("minor") in (None, "14") for match in matches), (
                    path.name,
                    job_name,
                )

            matrix_languages = job.get("strategy", {}).get("matrix", {}).get("language", [])
            configures_python_analysis = "python" in matrix_languages
            if python_indexes or configures_python_analysis:
                assert setup_indexes, (path.name, job_name)
            if python_indexes:
                assert min(setup_indexes) < min(python_indexes), (path.name, job_name)


def test_python_projects_publish_exact_314_and_lint_exception_is_non_runtime() -> None:
    root_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    repository_authority = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    root_project = tomllib.loads(root_text)
    api_project = tomllib.loads(
        (ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    )

    for project in (root_project, api_project):
        assert project["project"]["requires-python"] == EXPECTED_REQUIRES_PYTHON
    assert root_project["project"]["classifiers"] == [
        "Programming Language :: Python :: 3.14"
    ]
    assert root_project["tool"]["ruff"]["target-version"] == "py313"
    assert "It does not select a runtime" in root_text
    assert "grammar-compatibility exception only" in repository_authority
    assert "does not\nselect an interpreter or runtime" in repository_authority
