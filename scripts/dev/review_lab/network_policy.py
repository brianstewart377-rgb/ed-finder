from __future__ import annotations

from typing import Any, Mapping


def list_unexpected_api_errors(api_responses: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    errors = []
    for response in api_responses:
        status = int(response.get('status') or 0)
        if status < 400 or response.get('expectedFailure') is True:
            continue
        errors.append({
            'path': str(response.get('path') or ''),
            'status': status,
            'method': response.get('method'),
        })
    return errors


def list_unexpected_console_errors(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_failure_count = sum(
        1
        for response in summary.get('apiResponses', [])
        if response.get('expectedFailure') is True and int(response.get('status') or 0) >= 400
    )
    errors = []
    for entry in summary.get('consoleEntries', []):
        if entry.get('type') != 'error':
            continue
        text = str(entry.get('text') or '')
        if expected_failure_count and 'Failed to load resource' in text:
            expected_failure_count -= 1
            continue
        errors.append({'type': 'console', 'text': text})
    errors.extend({'type': 'pageerror', 'text': str(text)} for text in summary.get('pageErrors', []))
    return errors


def evaluate_browser_console(summary: Mapping[str, Any]) -> dict[str, Any]:
    unexpected_console = list_unexpected_console_errors(summary)
    unexpected_api = list_unexpected_api_errors(summary.get('apiResponses', []))
    if unexpected_console or unexpected_api:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'Unexpected browser console, page, or API errors were captured.',
            'failure_code': 'UNEXPECTED_BROWSER_CONSOLE_ERROR' if unexpected_console else 'UNEXPECTED_BROWSER_NETWORK_ERROR',
            'safe_diagnostics': {'console_errors': unexpected_console, 'api_errors': unexpected_api},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Browser diagnostics were clean apart from explicitly tagged Review Lab failure injection.',
        'failure_code': None,
        'safe_diagnostics': {'api_response_count': len(summary.get('apiResponses', []))},
    }
