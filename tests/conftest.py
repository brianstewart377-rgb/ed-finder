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


@pytest.fixture(autouse=True)
def reset_rate_limiter_state():
    try:
        import sys
        import importlib

        root = Path(__file__).resolve().parent.parent
        api_src = root / 'apps' / 'api' / 'src'
        if str(api_src) not in sys.path:
            sys.path.insert(0, str(api_src))

        for module_name in ('config', 'edfinder_api.config'):
            try:
                limiter = importlib.import_module(module_name).limiter
                limiter._storage.reset()  # pyright: ignore[reportPrivateUsage]
            except Exception:
                continue
    except Exception:
        pass
    yield
