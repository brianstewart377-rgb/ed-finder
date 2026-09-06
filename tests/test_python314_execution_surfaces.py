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


OLD_PYTHON_SELECTORS = (
    re.compile(r"\b(?:CPython|Python)\s+3\.(?P<minor>\d{1,2})\b"),
    re.compile(r"\bpython-version\s*:\s*['\"]?3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bFROM\s+python:3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bpython3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\bpy\s+-3\.(?P<minor>\d{1,2})\b", re.I),
    re.compile(r"\b(?:py|cp)3(?P<minor>\d{2})\b", re.I),
)


def test_active_execution_surfaces_never_select_pre314_python() -> None:
    violations: list[str] = []
    for path in _active_execution_surfaces():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for pattern in OLD_PYTHON_SELECTORS:
                for match in pattern.finditer(line):
                    if int(match.group("minor")) < 14:
                        relative = path.relative_to(ROOT).as_posix()
                        violations.append(f"{relative}:{line_number}: {match.group(0)}")

    assert not violations, "pre-3.14 Python selectors found:\n" + "\n".join(violations)


def test_all_active_workflow_setup_python_steps_select_exact_cpython314() -> None:
    violations: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/setup-python@"):
                    selected = step.get("with", {}).get("python-version")
                    if str(selected) != "3.14":
                        violations.append(
                            f"{path.name}:{job_name} selects {selected!r}"
                        )

    assert not violations, "non-3.14 setup-python steps found:\n" + "\n".join(violations)


def test_python_projects_publish_only_the_cpython314_support_contract() -> None:
    root_project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    api_project = tomllib.loads(
        (ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    )

    for project in (root_project, api_project):
        assert project["project"]["requires-python"] == EXPECTED_REQUIRES_PYTHON

    assert root_project["project"]["classifiers"] == [
        "Programming Language :: Python :: 3.14"
    ]
    assert root_project["tool"]["ruff"]["target-version"] == "py314"
