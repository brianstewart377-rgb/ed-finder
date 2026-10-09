from __future__ import annotations

import os
from pathlib import Path

import pytest


_INTEGRATION_DIR = Path(__file__).resolve().parent / 'integration'
_GITHUB_ANNOTATION_LIMIT = 50
_github_failure_annotation_count = 0
_github_annotation_limit_warning_emitted = False


def _escape_github_command(value: str, *, property_value: bool = False) -> str:
    escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    if property_value:
        escaped = escaped.replace(',', '%2C').replace(':', '%3A')
    return escaped


def github_failure_annotation(
    nodeid: str,
    location: tuple[str, int | None, str] | None,
    longrepr_text: str,
    when: str,
) -> str:
    """Format a failed pytest report as one GitHub workflow annotation."""

    message = longrepr_text or 'see job log'
    if len(message) > 1000:
        message = f'{message[:1000]} ...'
    message = _escape_github_command(message).replace(':', '%3A')
    title = _escape_github_command(f'{when}: {nodeid}', property_value=True)

    properties: list[str] = []
    if location is not None:
        properties.append(f'file={location[0]}')
        if location[1] is not None:
            properties.append(f'line={location[1] + 1}')
    properties.append(f'title={title}')
    return f'::error {",".join(properties)}::{message}'


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Expose failed tests through the GitHub Checks annotations API."""

    global _github_annotation_limit_warning_emitted
    global _github_failure_annotation_count

    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or not report.failed:
            return

        if _github_failure_annotation_count >= _GITHUB_ANNOTATION_LIMIT:
            if not _github_annotation_limit_warning_emitted:
                print(
                    '::warning title=pytest annotations::more than 50 failures; '
                    'see job log',
                    flush=True,
                )
                _github_annotation_limit_warning_emitted = True
            return

        longrepr_text = getattr(report, 'longreprtext', None)
        if not longrepr_text:
            longrepr_text = str(getattr(report, 'longrepr', ''))
        print(
            github_failure_annotation(
                report.nodeid,
                report.location,
                longrepr_text,
                report.when,
            ),
            flush=True,
        )
        _github_failure_annotation_count += 1
    except Exception:
        pass


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
