from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.conftest import github_failure_annotation, pytest_runtest_logreport


pytestmark = pytest.mark.unit


def test_call_failure_annotation_includes_location_and_assertion() -> None:
    annotation = github_failure_annotation(
        'tests/test_x.py::test_y',
        ('tests/test_x.py', 41, 'test_y'),
        'AssertionError: boom\nassert 1 == 2',
        'call',
    )

    assert annotation == (
        '::error file=tests/test_x.py,line=42,'
        'title=call%3A tests/test_x.py%3A%3Atest_y::'
        'AssertionError%3A boom%0Aassert 1 == 2'
    )


def test_failure_annotation_omits_unknown_line() -> None:
    annotation = github_failure_annotation(
        'tests/test_x.py::test_y',
        ('tests/test_x.py', None, 'test_y'),
        'failed',
        'setup',
    )

    assert annotation == (
        '::error file=tests/test_x.py,'
        'title=setup%3A tests/test_x.py%3A%3Atest_y::failed'
    )


def test_failure_annotation_escapes_percent_and_newline() -> None:
    annotation = github_failure_annotation(
        'tests/test_x.py::test_y',
        ('tests/test_x.py', 0, 'test_y'),
        '100% failed\nsecond line',
        'call',
    )

    assert '100%25 failed%0Asecond line' in annotation
    assert '\n' not in annotation


def test_failure_annotation_truncates_before_escaping() -> None:
    annotation = github_failure_annotation(
        'tests/test_x.py::test_y',
        ('tests/test_x.py', 0, 'test_y'),
        'x' * 5000,
        'call',
    )

    assert annotation.endswith(f"::{('x' * 1000)} ...")


def test_failure_annotation_uses_fallback_for_empty_longrepr() -> None:
    annotation = github_failure_annotation(
        'tests/test_x.py::test_y',
        ('tests/test_x.py', 0, 'test_y'),
        '',
        'call',
    )

    assert annotation.endswith('::see job log')


def test_failure_hook_is_noop_outside_github_actions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    report = SimpleNamespace(
        failed=True,
        when='call',
        nodeid='tests/test_x.py::test_y',
        location=('tests/test_x.py', 0, 'test_y'),
        longreprtext='failed',
    )

    pytest_runtest_logreport(report)  # type: ignore[arg-type]

    assert capsys.readouterr().out == ''


def test_failure_hook_emits_annotation_in_github_actions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    report = SimpleNamespace(
        failed=True,
        when='call',
        nodeid='tests/test_x.py::test_y',
        location=('tests/test_x.py', 0, 'test_y'),
        longreprtext='failed',
    )

    pytest_runtest_logreport(report)  # type: ignore[arg-type]

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith('::error file=')
