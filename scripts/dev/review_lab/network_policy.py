from __future__ import annotations

from typing import Any, Mapping

from .contract import REVIEW_SYSTEM_IDS


def is_expected_delta_console_503_message(text: str) -> bool:
    return text.strip() == 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)'


def validate_delta_fallback_sequence(summary: Mapping[str, Any]) -> bool:
    scenarios = summary.get('scenarios') or {}
    delta = scenarios.get('delta') or {}
    delta_responses = delta.get('apiResponses') or []
    seen_503 = None
    seen_fallback_200 = None
    delta_warehouse_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
    delta_fallback_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit"
    for index, response in enumerate(delta_responses):
        if response.get('path') == delta_warehouse_path and int(response.get('status') or 0) == 503 and seen_503 is None:
            seen_503 = index
        if response.get('path') == delta_fallback_path and int(response.get('status') or 0) == 200:
            seen_fallback_200 = index
            break
    checks = delta.get('checks') or {}
    return bool(
        seen_503 is not None
        and seen_fallback_200 is not None
        and seen_fallback_200 > seen_503
        and checks.get('provenanceFallbackVisible')
        and checks.get('technicalFallbackDisclosureVisible')
        and checks.get('fallbackRemainsNonCanonical')
        and checks.get('noDedicatedEvidenceClaim')
        and checks.get('noRecoveryScreen')
    )


def list_unexpected_api_errors(api_responses: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    allowed_delta_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
    errors = []
    for response in api_responses:
        status = int(response.get('status') or 0)
        path = str(response.get('path') or '')
        if status < 400:
            continue
        if path == allowed_delta_path and status == 503:
            continue
        errors.append({'path': path, 'status': status, 'method': response.get('method')})
    return errors


def list_unexpected_console_errors(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    console_entries = summary.get('consoleEntries') or []
    page_errors = summary.get('pageErrors') or []
    allow_expected_delta_console_503 = validate_delta_fallback_sequence(summary)
    allowed_delta_console_503_budget = 0
    if allow_expected_delta_console_503:
        delta_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
        allowed_delta_console_503_budget = sum(
            1
            for response in summary.get('apiResponses', [])
            if str(response.get('path') or '') == delta_path and int(response.get('status') or 0) == 503
        )

    errors = []
    for entry in console_entries:
        if entry.get('type') != 'error':
            continue
        text = str(entry.get('text') or '')
        if (
            allow_expected_delta_console_503
            and allowed_delta_console_503_budget > 0
            and is_expected_delta_console_503_message(text)
        ):
            allowed_delta_console_503_budget -= 1
            continue
        errors.append({'type': entry.get('type'), 'text': text})
    errors.extend({'type': 'pageerror', 'text': text} for text in page_errors)
    return errors


def evaluate_browser_console(summary: Mapping[str, Any]) -> dict[str, Any]:
    unexpected_console_errors = list_unexpected_console_errors(summary)
    unexpected_api_errors = list_unexpected_api_errors(summary.get('apiResponses', []))
    if unexpected_console_errors:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'Unexpected browser console or page errors were captured.',
            'failure_code': 'UNEXPECTED_BROWSER_CONSOLE_ERROR',
            'safe_diagnostics': {'errors': unexpected_console_errors},
        }
    if unexpected_api_errors:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'Unexpected API 4xx/5xx responses were captured during the browser journey.',
            'failure_code': 'UNEXPECTED_BROWSER_NETWORK_ERROR',
            'safe_diagnostics': {'errors': unexpected_api_errors},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Browser console and network policy passed; only the expected Delta dedicated-evidence 503 appeared.',
        'failure_code': None,
        'safe_diagnostics': {'api_response_count': len(summary.get('apiResponses', []))},
    }
