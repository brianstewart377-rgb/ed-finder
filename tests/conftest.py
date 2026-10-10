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
    message = _escape_github_command(message)
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
                    '\n::warning title=pytest annotations::more than 50 failures; '
                    'see job log',
                    flush=True,
                )
                _github_annotation_limit_warning_emitted = True
            return

        longrepr = getattr(report, 'longrepr', None)
        crash = getattr(longrepr, 'reprcrash', None)
        head = (
            str(crash.message)
            if crash is not None and getattr(crash, 'message', None)
            else ''
        )
        full = getattr(report, 'longreprtext', None) or str(longrepr or '')
        tail = full[-700:] if len(full) > 700 else full
        longrepr_text = head + '\n' + tail if head and head not in tail else tail or head

        location = report.location
        crash_path = getattr(crash, 'path', None)
        crash_lineno = getattr(crash, 'lineno', None)
        if isinstance(crash_path, str) and crash_path and isinstance(crash_lineno, int):
            annotation_path = Path(crash_path)
            if annotation_path.is_absolute():
                try:
                    annotation_path = annotation_path.resolve().relative_to(
                        Path(__file__).resolve().parent.parent
                    )
                except (OSError, ValueError):
                    annotation_path = None
            if annotation_path is not None:
                location = (
                    str(annotation_path),
                    crash_lineno - 1,
                    report.location[2] if report.location else '',
                )
        print(
            '\n'
            + github_failure_annotation(
                report.nodeid,
                location,
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
