from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .contract import (
    EXPECTED_FRONTEND_PREVIEW_PORT,
    FRONTEND_DIR,
    REVIEW_LAB_BROWSER_MARKER,
    REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION,
    VERIFY_BROWSER_SPEC,
    ReviewLabError,
)
from .lifecycle import review_api_origin, review_preview_origin, run_subprocess
from .network_policy import (
    evaluate_browser_console,
    list_unexpected_api_errors,
    list_unexpected_console_errors,
    validate_delta_fallback_sequence,
)
from .observations import evaluate_product_observations
from .process_registry import ReviewProcessRegistry
from .scenarios import ScenarioDefinition, selected_browser_flow_keys, selection_requires_product_observations
from .timeouts import TIMEOUTS


def evaluate_browser_desktop(summary: dict[str, Any], selected_scenarios: tuple[ScenarioDefinition, ...]) -> dict[str, Any]:
    scenarios = summary.get('scenarios') or {}
    required_by_flow = {
        'alpha': {'systemDetailLoaded', 'plannerOpened', 'reportOnlyBoundaryVisible', 'canonicalBoundaryVisible'},
        'beta': {'systemDetailLoaded', 'plannerOpened', 'unavailablePostureVisible'},
        'gamma': {'systemDetailLoaded', 'plannerOpened', 'unknownPostureVisible'},
        'delta': {
            'systemDetailLoaded',
            'plannerOpened',
            'provenanceFallbackVisible',
            'reportOnlyBoundaryVisible',
            'fallbackRemainsNonCanonical',
            'technicalFallbackDisclosureVisible',
            'noDedicatedEvidenceClaim',
            'noRecoveryScreen',
        },
    }
    active_flow_keys = selected_browser_flow_keys(selected_scenarios)
    missing: dict[str, list[str]] = {}
    for flow_key in active_flow_keys:
        scenario = scenarios.get(flow_key)
        required_checks = required_by_flow[flow_key]
        if not isinstance(scenario, dict) or scenario.get('status') != 'passed':
            missing[flow_key] = ['scenario_failed']
            continue
        checks = scenario.get('checks') or {}
        missing_checks = [name for name in sorted(required_checks) if not checks.get(name)]
        if missing_checks:
            missing[flow_key] = missing_checks
    if missing:
        failure_code = 'DELTA_FALLBACK_NOT_TRIGGERED' if 'delta' in missing else 'BROWSER_JOURNEY_FAILED'
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'One or more browser review journeys did not satisfy the expected UI contract.',
            'failure_code': failure_code,
            'safe_diagnostics': {'missing_checks': missing},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Desktop browser journeys passed for the selected review scenarios against the real review stack.',
        'failure_code': None,
        'safe_diagnostics': {'scenario_names': list(active_flow_keys)},
    }


def evaluate_browser_accessibility(summary: dict[str, Any], selected_scenarios: tuple[ScenarioDefinition, ...]) -> dict[str, Any]:
    accessibility = summary.get('accessibility') or {}
    required_checks: list[str] = []
    if any('modal_escape_close' in scenario.accessibility_checks for scenario in selected_scenarios):
        required_checks.append('modalEscapeCloseWorks')
    if any('keyboard_open_planner' in scenario.accessibility_checks for scenario in selected_scenarios):
        required_checks.append('alphaKeyboardOpenPlannerWorks')
    if any('mobile_telemetry_toggle' in scenario.accessibility_checks for scenario in selected_scenarios):
        required_checks.append('mobileTelemetryToggleKeyboardWorks')
    if not required_checks:
        return {
            'status': 'skipped',
            'duration_ms': 0,
            'summary': 'No accessibility checks were requested for the selected scenario set.',
            'failure_code': None,
            'safe_diagnostics': {'reason': 'scenario selection has no accessibility checks'},
        }
    missing = [name for name in required_checks if not accessibility.get(name)]
    if missing:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'Browser accessibility coverage did not complete the required keyboard checks.',
            'failure_code': 'BROWSER_JOURNEY_FAILED',
            'safe_diagnostics': {'missing_checks': missing},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Keyboard-driven modal close, planner open, and telemetry dock toggle checks passed.',
        'failure_code': None,
        'safe_diagnostics': {'checks': required_checks},
    }


def _wait_for_preview_ready(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(review_preview_origin(), timeout=2) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.5)
            continue
    raise ReviewLabError(
        'Frontend preview did not become ready in time.',
        failure_code='FRONTEND_PREVIEW_TIMEOUT',
        safe_diagnostics={'preview_origin': review_preview_origin()},
    )


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(('127.0.0.1', port)) != 0


def _playwright_status_hint(text: str) -> str:
    lowered = (text or '').lower()
    if not lowered.strip():
        return 'none'
    if 'already used' in lowered and 'reuseexistingserver' in lowered:
        return 'playwright_web_server_conflict'
    if 'no tests found' in lowered:
        return 'no_tests_found'
    if '1 skipped' in lowered or 'skipped' in lowered:
        return 'test_skipped'
    if 'review lab browser verification requires' in lowered or 'edfinder_review_lab_run' in lowered:
        return 'review_lab_configuration_error'
    if 'error:' in lowered:
        return 'playwright_error'
    return 'unknown'


def _browser_runner_diagnostics(
    *,
    completed: Any,
    review_marker_present: bool,
    output_path_configured: bool,
    scenario_plan_configured: bool,
    summary_exists: bool,
    summary_schema_valid: bool,
) -> dict[str, Any]:
    return {
        'playwright_return_code': completed.returncode if completed is not None else None,
        'review_marker_present': review_marker_present,
        'output_path_configured': output_path_configured,
        'scenario_plan_configured': scenario_plan_configured,
        'summary_exists': summary_exists,
        'summary_schema_valid': summary_schema_valid,
        'stdout_status_hint': _playwright_status_hint(getattr(completed, 'stdout', '') if completed is not None else ''),
        'stderr_status_hint': _playwright_status_hint(getattr(completed, 'stderr', '') if completed is not None else ''),
    }


def _validate_browser_summary(summary: Any, selected_scenarios: tuple[ScenarioDefinition, ...]) -> None:
    expected_scenarios = [scenario.name for scenario in selected_scenarios]
    expected_flow_keys = list(selected_browser_flow_keys(selected_scenarios))
    required_sections = {
        'scenarios': dict,
        'accessibility': dict,
        'productObservations': list,
        'apiResponses': list,
        'consoleEntries': list,
        'pageErrors': list,
    }
    schema_valid = (
        isinstance(summary, dict)
        and summary.get('summarySchemaVersion') == REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION
        and summary.get('reviewLabRun') is True
        and summary.get('selectedScenarioNames') == expected_scenarios
        and summary.get('browserFlowKeys') == expected_flow_keys
        and all(isinstance(summary.get(key), expected_type) for key, expected_type in required_sections.items())
        and 'fatalError' in summary
    )
    if not schema_valid:
        raise ReviewLabError(
            'Browser verification summary failed the Review Lab handshake validation.',
            failure_code='BROWSER_RUNNER_CONFIGURATION_FAILED',
        )


def run_browser_phase(run_dir: Path, selected_scenarios: tuple[ScenarioDefinition, ...], registry: ReviewProcessRegistry) -> dict[str, Any]:
    if not VERIFY_BROWSER_SPEC.is_file():
        raise ReviewLabError(
            'Review-environment browser collector is missing.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'expected_spec': str(VERIFY_BROWSER_SPEC.relative_to(FRONTEND_DIR.parent))},
        )
    if not _port_available(EXPECTED_FRONTEND_PREVIEW_PORT):
        raise ReviewLabError(
            'Frontend preview port is already occupied; refusing to reuse an arbitrary host process.',
            failure_code='FRONTEND_PREVIEW_TIMEOUT',
            safe_diagnostics={'preview_port': EXPECTED_FRONTEND_PREVIEW_PORT},
        )

    output_path = run_dir / 'browser-summary.json'
    browser_plan = {
        'selectedScenarioNames': [scenario.name for scenario in selected_scenarios],
        'browserFlowKeys': list(selected_browser_flow_keys(selected_scenarios)),
        'includeProductObservations': selection_requires_product_observations(selected_scenarios),
    }
    (run_dir / 'browser-plan.json').write_text(json.dumps(browser_plan, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    env = {
        REVIEW_LAB_BROWSER_MARKER: '1',
        'EDFINDER_REVIEW_OUTPUT_PATH': str(output_path),
        'EDFINDER_REVIEW_SCENARIOS_JSON': json.dumps(browser_plan, sort_keys=True),
        'VITE_DEV_API_TARGET': review_api_origin(),
    }

    run_subprocess(
        ['yarn', 'build', '--configLoader', 'runner'],
        cwd=FRONTEND_DIR,
        env_overrides=env,
        timeout_seconds=TIMEOUTS.frontend_build,
        failure_code='FRONTEND_BUILD_TIMEOUT',
    )
    registry.start(
        'frontend-preview',
        ['yarn', 'preview', '--port', str(EXPECTED_FRONTEND_PREVIEW_PORT), '--strictPort'],
        cwd=FRONTEND_DIR,
        env=env,
        stdout_log_name='frontend-preview.stdout.log',
        stderr_log_name='frontend-preview.stderr.log',
    )
    _wait_for_preview_ready(TIMEOUTS.preview_readiness)
    completed = run_subprocess(
        ['npx', 'playwright', 'test', 'e2e/review-environment.spec.js', '--config', 'playwright.config.ts', '--project', 'chromium', '--reporter=line'],
        cwd=FRONTEND_DIR,
        env_overrides=env,
        timeout_seconds=TIMEOUTS.playwright,
        allow_failure=True,
        failure_code='BROWSER_PHASE_TIMEOUT',
    )
    if not output_path.is_file():
        raise ReviewLabError(
            'Browser verification did not produce a structured summary.',
            failure_code='BROWSER_SUMMARY_MISSING',
            safe_diagnostics=_browser_runner_diagnostics(
                completed=completed,
                review_marker_present=env.get(REVIEW_LAB_BROWSER_MARKER) == '1',
                output_path_configured=bool(env.get('EDFINDER_REVIEW_OUTPUT_PATH')),
                scenario_plan_configured=bool(env.get('EDFINDER_REVIEW_SCENARIOS_JSON')),
                summary_exists=False,
                summary_schema_valid=False,
            ),
        )

    try:
        summary = json.loads(output_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ReviewLabError(
            'Browser verification summary was not valid JSON.',
            failure_code='BROWSER_RUNNER_CONFIGURATION_FAILED',
            safe_diagnostics=_browser_runner_diagnostics(
                completed=completed,
                review_marker_present=env.get(REVIEW_LAB_BROWSER_MARKER) == '1',
                output_path_configured=bool(env.get('EDFINDER_REVIEW_OUTPUT_PATH')),
                scenario_plan_configured=bool(env.get('EDFINDER_REVIEW_SCENARIOS_JSON')),
                summary_exists=True,
                summary_schema_valid=False,
            ),
        ) from exc
    try:
        _validate_browser_summary(summary, selected_scenarios)
    except ReviewLabError as exc:
        raise ReviewLabError(
            str(exc),
            failure_code=exc.failure_code,
            safe_diagnostics=_browser_runner_diagnostics(
                completed=completed,
                review_marker_present=env.get(REVIEW_LAB_BROWSER_MARKER) == '1',
                output_path_configured=bool(env.get('EDFINDER_REVIEW_OUTPUT_PATH')),
                scenario_plan_configured=bool(env.get('EDFINDER_REVIEW_SCENARIOS_JSON')),
                summary_exists=True,
                summary_schema_valid=False,
            ),
        ) from exc
    desktop_phase = evaluate_browser_desktop(summary, selected_scenarios)
    accessibility_phase = evaluate_browser_accessibility(summary, selected_scenarios)
    console_phase = evaluate_browser_console(summary)
    if browser_plan['includeProductObservations']:
        product_phase = evaluate_product_observations(summary)
    else:
        product_phase = {
            'status': 'skipped',
            'duration_ms': 0,
            'summary': 'No product observations were requested for the selected scenario set.',
            'failure_code': None,
            'safe_diagnostics': {'reason': 'scenario selection does not request product observations'},
        }
    unexpected_api_errors = list_unexpected_api_errors(summary.get('apiResponses', []))
    unexpected_console_errors = list_unexpected_console_errors(summary)
    delta_correlation_verified = desktop_phase['status'] == 'passed' and validate_delta_fallback_sequence(summary)
    return {
        'browser_desktop': desktop_phase,
        'browser_accessibility': accessibility_phase,
        'browser_console': console_phase,
        'product_observations': product_phase,
        'unexpected_api_errors': unexpected_api_errors,
        'unexpected_console_errors': unexpected_console_errors,
        'known_product_observations': product_phase['safe_diagnostics'].get('known_product_observations', []),
        'unexpected_product_observations': product_phase['safe_diagnostics'].get('unexpected_product_observations', []),
        'delta_503_fallback_correlation_verified': delta_correlation_verified,
    }
