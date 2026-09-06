from __future__ import annotations

from pathlib import Path

import pytest


_INTEGRATION_DIR = Path(__file__).resolve().parent / 'integration'
_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_PSYCOPG2_TEST_PATHS = frozenset(
    line
    for raw_line in (_ROOT / 'tests' / 'legacy_psycopg2_test_paths.txt').read_text(encoding='utf-8').splitlines()
    if (line := raw_line.strip()) and not line.startswith('#')
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--v3-api-only',
        action='store_true',
        help='Ignore bounded psycopg2-backed legacy tooling tests before collection.',
    )


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if not config.getoption('--v3-api-only'):
        return None
    try:
        relative_path = collection_path.resolve().relative_to(_ROOT).as_posix()
    except (OSError, ValueError):
        return None
    if relative_path in _LEGACY_PSYCOPG2_TEST_PATHS:
        return True
    return None


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

        root = Path(__file__).resolve().parent.parent
        api_src = root / 'apps' / 'api' / 'src'
        if str(api_src) not in sys.path:
            sys.path.insert(0, str(api_src))

        for module_name in ('config', 'edfinder_api.config'):
            try:
                # Reset API state when an API test already imported it during
                # collection. Do not make every repository/tooling-only pytest
                # invocation import V3 application code as a side effect.
                module = sys.modules.get(module_name)
                if module is None:
                    continue
                limiter = module.limiter
                limiter._storage.reset()  # pyright: ignore[reportPrivateUsage]
            except Exception:
                continue
    except Exception:
        pass
    yield
