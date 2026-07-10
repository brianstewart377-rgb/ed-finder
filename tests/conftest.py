from __future__ import annotations

from pathlib import Path

import pytest


_INTEGRATION_DIR = Path(__file__).resolve().parent / 'integration'


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply path-based marks for tests that live in dedicated suites."""

    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except OSError:
            continue

        if _INTEGRATION_DIR in item_path.parents:
            item.add_marker(pytest.mark.integration)
