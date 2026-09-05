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
    'exploreInspect': {'exploreLoaded', 'syntheticSystemVisible', 'babylonReady', 'inspectLoaded', 'exactId64Preserved'},
    'apiFailure': {'failureInjected', 'errorRendered', 'selectionContextPreserved'},
    'emptyResults': {'emptyInjected', 'emptyRendered', 'zeroTargetScene', 'babylonReady'},
    'rendererRecovery': {'babylonReady', 'rendererLifecycleExercised', 'rendererRemainedUsable', 'noUncaughtError'},
    'navigationContainment': {'directInspectLoaded', 'headingFocused', 'returnedToExplore', 'sameOriginOnly'},
}


def evaluate_browser_desktop(summary: dict[str, Any], selected_scenarios: tuple[ScenarioDefinition, ...]) -> dict[str, Any]:
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
            'summary': 'One or more synthetic V3 browser scenarios failed.',
            'failure_code': 'BROWSER_JOURNEY_FAILED',
            'safe_diagnostics': {'missing_scenario_checks': missing},
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Synthetic V3 Explore, Inspect, Babylon, failure, empty-state, and containment scenarios passed.',
        'failure_code': None,
        'safe_diagnostics': {
            'scenario_names': list(selected_browser_flow_keys(selected_scenarios)),
            'profile_names': [profile['profile_name'] for profile in REVIEW_LAB_VIEWPORT_PROFILES],
            'frontend': 'apps/web',
            'renderer': 'Babylon',
        },
    }


def evaluate_browser_accessibility(summary: dict[str, Any], selected_scenarios: tuple[ScenarioDefinition, ...]) -> dict[str, Any]:
    required: list[str] = []
    if any('keyboard_typeahead' in scenario.accessibility_checks for scenario in selected_scenarios):
        required.append('keyboardTypeaheadWorks')
    if any('inspect_heading_focus' in scenario.accessibility_checks for scenario in selected_scenarios):
        required.append('inspectHeadingFocused')
    if not required:
        return {
            'status': 'skipped',
            'duration_ms': 0,
            'summary': 'Selected synthetic scenarios have no additional accessibility contract.',
            'failure_code': None,
            'safe_diagnostics': {'reason': 'no requested Review Lab accessibility checks'},
        }
    accessibility = summary.get('accessibility') or {}
    missing = [name for name in required if not accessibility.get(name)]
    return {
        'status': 'failed' if missing else 'passed',
        'duration_ms': 0,
        'summary': 'Review Lab keyboard and focus contracts failed.' if missing else 'Review Lab keyboard and focus contracts passed.',
        'failure_code': 'BROWSER_JOURNEY_FAILED' if missing else None,
        'safe_diagnostics': {'missing_checks': missing, 'checks': required},
    }


def _wait_for_preview_ready(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(review_preview_origin(), timeout=2) as response:  # nosemgrep: loopback Review Lab origin
                if response.status == 200:
                    return
        except URLError:
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
        and isinstance(summary.get('accessibility'), dict)
        and isinstance(summary.get('apiResponses'), list)
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
        ['pnpm', 'preview', '--port', str(EXPECTED_FRONTEND_PREVIEW_PORT), '--strictPort'],
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

    desktop_phase = evaluate_browser_desktop(summary, selected_scenarios)
    accessibility_phase = evaluate_browser_accessibility(summary, selected_scenarios)
    console_phase = evaluate_browser_console(summary)
    product_phase = {
        'status': 'skipped',
        'duration_ms': 0,
        'summary': 'Product acceptance and visual baselines belong to normal Product E2E.',
        'failure_code': None,
        'safe_diagnostics': {'reason': 'hard lane boundary'},
    }
    return {
        'browser_desktop': desktop_phase,
        'browser_accessibility': accessibility_phase,
        'browser_console': console_phase,
        'product_observations': product_phase,
        'unexpected_api_errors': list_unexpected_api_errors(summary.get('apiResponses', [])),
        'unexpected_console_errors': list_unexpected_console_errors(summary),
        'known_product_observations': [],
        'unexpected_product_observations': [],
        'synthetic_failure_injection_verified': summary.get('scenarios', {}).get('apiFailure', {}).get('status') == 'passed',
    }
