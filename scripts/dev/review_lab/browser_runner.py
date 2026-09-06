from __future__ import annotations

import json
import socket
import time
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import Any

from .contract import (
    EXPECTED_FRONTEND_PREVIEW_HOST,
    EXPECTED_FRONTEND_PREVIEW_PORT,
    FRONTEND_DIR,
    REVIEW_LAB_BROWSER_MARKER,
    REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION,
    REVIEW_LAB_VIEWPORT_PROFILES,
    VERIFY_BROWSER_CONFIG,
    VERIFY_BROWSER_SPEC,
    ReviewLabError,
)
from .lifecycle import review_api_origin, review_preview_origin, run_subprocess
from .network_policy import evaluate_browser_console, list_unexpected_api_errors, list_unexpected_console_errors
from .process_registry import ReviewProcessRegistry
from .scenarios import ScenarioDefinition, selected_browser_flow_keys
from .timeouts import TIMEOUTS


REQUIRED_CHECKS_BY_FLOW: dict[str, set[str]] = {
    'syntheticWiring': {'syntheticSystemVisible', 'babylonReady'},
    'apiFailure': {'failureModeActivated', 'errorRendered', 'selectionContextPreserved'},
    'emptyResults': {'emptyModeActivated', 'emptyRendered', 'zeroTargetScene', 'babylonReady'},
    'rendererRecovery': {'babylonReady', 'rendererLifecycleExercised', 'rendererRemainedUsable', 'noUncaughtError'},
}


def _validated_preview_endpoint() -> tuple[str, int]:
    """Return the fixed Review Lab preview endpoint, failing closed if altered."""
    if EXPECTED_FRONTEND_PREVIEW_HOST != '127.0.0.1' or EXPECTED_FRONTEND_PREVIEW_PORT != 4173:
        raise ReviewLabError(
            'apps/web preview endpoint is not the expected loopback-only target.',
            failure_code='BROWSER_RUNNER_CONFIGURATION_FAILED',
        )
    return EXPECTED_FRONTEND_PREVIEW_HOST, EXPECTED_FRONTEND_PREVIEW_PORT


def evaluate_browser_synthetic(summary: dict[str, Any], selected_scenarios: tuple[ScenarioDefinition, ...]) -> dict[str, Any]:
    scenarios = summary.get('scenarios') or {}
    missing: dict[str, list[str]] = {}
    for flow in selected_browser_flow_keys(selected_scenarios):
        result = scenarios.get(flow)
        if not isinstance(result, dict) or result.get('status') != 'passed':
            missing[flow] = ['scenario_failed']
            continue
        checks = result.get('checks') or {}
        failed = [name for name in sorted(REQUIRED_CHECKS_BY_FLOW[flow]) if not checks.get(name)]
        if failed:
            missing[flow] = failed
    if missing:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'One or more Review Lab-only synthetic scenarios failed.',
            'failure_code': 'BROWSER_JOURNEY_FAILED',
            'safe_diagnostics': {'missing_scenario_checks': missing},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Selected Review Lab-only synthetic edge/failure scenarios passed.',
        'failure_code': None,
        'safe_diagnostics': {
            'scenario_names': list(selected_browser_flow_keys(selected_scenarios)),
            'profile_names': [profile['profile_name'] for profile in REVIEW_LAB_VIEWPORT_PROFILES],
            'frontend': 'apps/web',
            'renderer': 'Babylon',
            'product_acceptance_owned_here': False,
        },
    }


def _wait_for_preview_ready(timeout_seconds: int) -> None:
    preview_host, preview_port = _validated_preview_endpoint()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        connection = HTTPConnection(preview_host, preview_port, timeout=2)
        try:
            connection.request('GET', '/')
            response = connection.getresponse()
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (HTTPException, OSError):
            pass
        finally:
            connection.close()
        time.sleep(0.5)
    raise ReviewLabError(
        'apps/web preview did not become ready in time.',
        failure_code='FRONTEND_PREVIEW_TIMEOUT',
        safe_diagnostics={'preview_origin': review_preview_origin()},
    )


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(('127.0.0.1', port)) != 0


def _validate_browser_summary(summary: Any, selected_scenarios: tuple[ScenarioDefinition, ...]) -> None:
    expected_names = [scenario.name for scenario in selected_scenarios]
    expected_flows = list(selected_browser_flow_keys(selected_scenarios))
    schema_valid = (
        isinstance(summary, dict)
        and summary.get('summarySchemaVersion') == REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION
        and summary.get('reviewLabRun') is True
        and summary.get('selectedScenarioNames') == expected_names
        and summary.get('browserFlowKeys') == expected_flows
        and isinstance(summary.get('scenarios'), dict)
        and isinstance(summary.get('apiResponses'), list)
        and isinstance(summary.get('externalOrigins'), list)
        and isinstance(summary.get('consoleEntries'), list)
        and isinstance(summary.get('pageErrors'), list)
        and 'fatalError' in summary
    )
    if not schema_valid:
        raise ReviewLabError(
            'Browser summary failed the trusted Review Lab handshake.',
            failure_code='BROWSER_RUNNER_CONFIGURATION_FAILED',
        )


def _ensure_cypress_succeeded(completed: Any, diagnostics: dict[str, Any]) -> None:
    if completed.returncode != 0:
        raise ReviewLabError(
            'Cypress reported a failed Review Lab browser run.',
            failure_code='BROWSER_JOURNEY_FAILED',
            safe_diagnostics=diagnostics,
        )


def run_browser_phase(run_dir: Path, selected_scenarios: tuple[ScenarioDefinition, ...], registry: ReviewProcessRegistry) -> dict[str, Any]:
    if not VERIFY_BROWSER_SPEC.is_file() or not VERIFY_BROWSER_CONFIG.is_file():
        raise ReviewLabError(
            'apps/web Review Lab browser collector is missing.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'expected_spec': str(VERIFY_BROWSER_SPEC.relative_to(FRONTEND_DIR.parent.parent))},
        )
    if not _port_available(EXPECTED_FRONTEND_PREVIEW_PORT):
        raise ReviewLabError(
            'apps/web preview port is occupied; refusing an arbitrary host process.',
            failure_code='FRONTEND_PREVIEW_TIMEOUT',
            safe_diagnostics={'preview_port': EXPECTED_FRONTEND_PREVIEW_PORT},
        )

    output_path = run_dir / 'browser-summary.json'
    browser_plan = {
        'selectedScenarioNames': [scenario.name for scenario in selected_scenarios],
        'browserFlowKeys': list(selected_browser_flow_keys(selected_scenarios)),
    }
    (run_dir / 'browser-plan.json').write_text(json.dumps(browser_plan, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    env = {
        REVIEW_LAB_BROWSER_MARKER: '1',
        'EDFINDER_REVIEW_OUTPUT_PATH': str(output_path),
        'EDFINDER_REVIEW_SCENARIOS_JSON': json.dumps(browser_plan, sort_keys=True),
        'VITE_DEV_API_TARGET': review_api_origin(),
    }

    run_subprocess(['pnpm', 'build'], cwd=FRONTEND_DIR, env_overrides=env, timeout_seconds=TIMEOUTS.frontend_build, failure_code='FRONTEND_BUILD_TIMEOUT')
    registry.start(
        'apps-web-preview',
        [
            'pnpm',
            'preview',
            '--host',
            EXPECTED_FRONTEND_PREVIEW_HOST,
            '--port',
            str(EXPECTED_FRONTEND_PREVIEW_PORT),
            '--strictPort',
        ],
        cwd=FRONTEND_DIR,
        env=env,
        stdout_log_name='apps-web-preview.stdout.log',
        stderr_log_name='apps-web-preview.stderr.log',
    )
    _wait_for_preview_ready(TIMEOUTS.preview_readiness)
    completed = run_subprocess(
        ['pnpm', 'exec', 'cypress', 'run', '--browser', 'chrome', '--spec', 'cypress/e2e/review-lab.cy.ts', '--config-file', 'cypress.review.config.ts'],
        cwd=FRONTEND_DIR,
        env_overrides=env,
        timeout_seconds=TIMEOUTS.cypress,
        allow_failure=True,
        failure_code='BROWSER_PHASE_TIMEOUT',
    )
    diagnostics = {
        'cypress_return_code': completed.returncode,
        'review_marker_present': True,
        'output_path_configured': True,
        'scenario_plan_configured': True,
        'summary_exists': output_path.is_file(),
    }
    if not output_path.is_file():
        raise ReviewLabError('Browser collector did not produce a structured summary.', failure_code='BROWSER_SUMMARY_MISSING', safe_diagnostics=diagnostics)
    try:
        summary = json.loads(output_path.read_text(encoding='utf-8'))
        _validate_browser_summary(summary, selected_scenarios)
    except (json.JSONDecodeError, ReviewLabError) as exc:
        raise ReviewLabError('Browser summary was invalid.', failure_code='BROWSER_RUNNER_CONFIGURATION_FAILED', safe_diagnostics=diagnostics) from exc
    _ensure_cypress_succeeded(completed, diagnostics)

    return {
        'browser_synthetic': evaluate_browser_synthetic(summary, selected_scenarios),
        'browser_console': evaluate_browser_console(summary),
        'unexpected_api_errors': list_unexpected_api_errors(summary.get('apiResponses', [])),
        'unexpected_console_errors': list_unexpected_console_errors(summary),
        'synthetic_failure_injection_verified': summary.get('scenarios', {}).get('apiFailure', {}).get('status') == 'passed',
    }
