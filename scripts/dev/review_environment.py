#!/usr/bin/env python3
"""Manage and verify the isolated disposable local review stack."""
from __future__ import annotations

import argparse
import json
import time
from typing import Any, Mapping

from review_lab import api_contracts, browser_runner, feature_availability, lifecycle, network_policy, observations, reporting, scenarios, support_matrix
from review_lab.contract import CONFIRM_FLAG, REQUIRED_PHASE_NAMES, ReviewLabError, elapsed_ms
from review_lab.process_registry import ReviewProcessRegistry

ReviewEnvironmentError = ReviewLabError

REVIEW_SUPPORT_ROUTE_MATRIX = tuple(route.to_dict() for route in support_matrix.REVIEW_SUPPORT_ROUTE_MATRIX)
REVIEW_FEATURE_AVAILABILITY = tuple(feature.to_dict() for feature in feature_availability.REVIEW_FEATURE_AVAILABILITY)
KNOWN_PRODUCT_OBSERVATIONS = observations.KNOWN_PRODUCT_OBSERVATIONS

validate_review_database_name = lifecycle.validate_review_database_name
validate_review_api_host = lifecycle.validate_review_api_host
validate_review_api_port = lifecycle.validate_review_api_port
extract_service_block = lifecycle.extract_service_block
validate_compose_text = lifecycle.validate_compose_text
validate_support_route_matrix = support_matrix.validate_support_route_matrix
validate_feature_availability = feature_availability.validate_feature_availability
run_preflight = lifecycle.run_preflight
up_review_stack = lifecycle.up_review_stack
review_status = lifecycle.review_status
down_review_stack = lifecycle.down_review_stack
run_static_phase = lifecycle.run_static_phase
run_stack_phase = lifecycle.run_stack_phase
run_api_contract_phase = api_contracts.run_api_contract_phase
run_browser_phase = browser_runner.run_browser_phase
capture_docker_baseline = lifecycle.capture_docker_baseline
compare_docker_baseline = lifecycle.compare_docker_baseline
list_review_owned_resources = lifecycle.list_review_owned_resources
assert_no_preexisting_review_resources = lifecycle.assert_no_preexisting_review_resources
probe_event_stream = lifecycle.probe_event_stream
healthcheck_url = lifecycle.healthcheck_url
frontend_start_command = lifecycle.frontend_start_command
phase_result = reporting.phase_result
browser_phase_result = reporting.browser_phase_result
first_failed_phase = reporting.first_failed_phase
evaluate_browser_console = network_policy.evaluate_browser_console
validate_delta_fallback_sequence = network_policy.validate_delta_fallback_sequence
evaluate_product_observations = observations.evaluate_product_observations


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Manage the isolated disposable local Review Lab stack.')
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('preflight', help='Read-only validation of the review lab stack.')
    subparsers.add_parser('list-scenarios', help='List the finite Review Lab scenario registry.')

    report_parser = subparsers.add_parser('report', help='Read the latest sanitised Review Lab verification report.')
    report_parser.add_argument('--latest', action='store_true')

    up_parser = subparsers.add_parser('up', help=argparse.SUPPRESS)
    up_parser.add_argument(CONFIRM_FLAG, action='store_true')

    subparsers.add_parser('status', help=argparse.SUPPRESS)

    down_parser = subparsers.add_parser('down', help='Stop and remove only the isolated review stack.')
    down_parser.add_argument(CONFIRM_FLAG, action='store_true')

    verify_parser = subparsers.add_parser('verify', help='Perform deterministic Review Lab verification.')
    verify_parser.add_argument('--mode', choices=('quick', 'full'), default='full')
    verify_parser.add_argument('--scenario', choices=('all', *scenarios.scenario_names()), default='all')
    verify_parser.add_argument(CONFIRM_FLAG, action='store_true')
    return parser.parse_args(argv)


def require_confirmation(args: argparse.Namespace) -> None:
    if not getattr(args, 'confirm_local_review_environment', False):
        raise ReviewEnvironmentError(f'{args.command} is mutating and requires {CONFIRM_FLAG}')


def print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def report_latest() -> dict[str, Any]:
    try:
        return reporting.load_latest_report()
    except FileNotFoundError as exc:
        raise ReviewEnvironmentError(str(exc), failure_code='STATIC_CONTAINMENT_FAILED') from exc


def _default_failure_code_for_phase(phase_name: str) -> str:
    return {
        'static': 'STATIC_CONTAINMENT_FAILED',
        'stack': 'REVIEW_STACK_START_FAILED',
        'api_contracts': 'UNEXPECTED_API_ERROR',
        'browser_desktop': 'BROWSER_JOURNEY_FAILED',
        'browser_accessibility': 'BROWSER_JOURNEY_FAILED',
        'browser_console': 'UNEXPECTED_BROWSER_CONSOLE_ERROR',
        'teardown': 'DOCKER_BASELINE_NOT_RESTORED',
        'product_observations': 'UNEXPECTED_PRODUCT_OBSERVATION',
    }[phase_name]


def _timed_call(callback):
    started_at = time.monotonic()
    value = callback()
    return {'value': value, 'duration_ms': elapsed_ms(started_at)}


def _blocking_product_observations(observations_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        observation
        for observation in observations_list
        if observation.get('observedInRun') and observation.get('productAcceptanceReady') is False
    ]


def _mark_failed_phase(phases: dict[str, dict[str, Any]], phase_name: str, exc: ReviewEnvironmentError) -> None:
    phases[phase_name] = phase_result(
        status='failed',
        duration_ms=0,
        summary=str(exc),
        failure_code=exc.failure_code or _default_failure_code_for_phase(phase_name),
        safe_diagnostics=exc.safe_diagnostics or {},
    )
    failed_index = REQUIRED_PHASE_NAMES.index(phase_name)
    for skipped_name in REQUIRED_PHASE_NAMES[failed_index + 1:]:
        if phases[skipped_name]['status'] == 'skipped':
            phases[skipped_name] = phase_result(
                status='skipped',
                duration_ms=0,
                summary=f'Skipped because {phase_name} failed.',
                failure_code=None,
                safe_diagnostics={'skipped_by': phase_name},
            )


def verify_review_environment(*, mode: str = 'full', scenario: str = 'all') -> dict[str, Any]:
    selected_scenarios = scenarios.resolve_scenarios(scenario)
    context = reporting.create_verify_context(mode, selected_scenarios)
    process_registry = ReviewProcessRegistry(context.run_dir)
    phases = reporting.default_phase_results()
    baseline_before = capture_docker_baseline()
    started_at = time.monotonic()
    verification_error: ReviewEnvironmentError | None = None
    report: dict[str, Any] = {
        'ok': False,
        'mode': mode,
        'run_id': context.run_id,
        'command': context.command_text(),
        'selected_scenarios': [scenario_def.name for scenario_def in selected_scenarios],
        'phase_results': phases,
        'support_route_matrix': REVIEW_SUPPORT_ROUTE_MATRIX,
        'support_route_matrix_complete': False,
        'feature_availability': REVIEW_FEATURE_AVAILABILITY,
        'delta_503_fallback_correlation_verified': False,
        'unexpected_console_errors': [],
        'unexpected_api_errors': [],
        'known_product_observations': [],
        'unexpected_product_observations': [],
        'docker_baseline_restored': False,
        'static_test_count': 0,
        'environment_ready': False,
        'product_acceptance_ready': False,
        'first_failure_phase': None,
        'failure_code': None,
        'failure_summary': None,
        'skipped_phases': [],
    }

    try:
        static_result = _timed_call(run_static_phase)
        phases['static'] = phase_result(
            status='passed',
            duration_ms=static_result['duration_ms'],
            summary=static_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=static_result['value']['safe_diagnostics'],
        )
        report['static_test_count'] = static_result['value']['static_test_count']
        report['support_route_matrix_complete'] = True

        stack_result = _timed_call(run_stack_phase)
        phases['stack'] = phase_result(
            status='passed',
            duration_ms=stack_result['duration_ms'],
            summary=stack_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=stack_result['value']['safe_diagnostics'],
        )

        api_result = _timed_call(lambda: run_api_contract_phase(selected_scenarios))
        phases['api_contracts'] = phase_result(
            status='passed',
            duration_ms=api_result['duration_ms'],
            summary=api_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=api_result['value']['safe_diagnostics'],
        )

        if mode == 'full':
            browser_result = _timed_call(lambda: run_browser_phase(context.run_dir, selected_scenarios, process_registry))
            browser_value = browser_result['value']
            phases['browser_desktop'] = browser_phase_result(browser_result['duration_ms'], browser_value['browser_desktop'])
            phases['browser_accessibility'] = browser_phase_result(browser_result['duration_ms'], browser_value['browser_accessibility'])
            phases['browser_console'] = browser_phase_result(browser_result['duration_ms'], browser_value['browser_console'])
            phases['product_observations'] = browser_phase_result(browser_result['duration_ms'], browser_value['product_observations'])
            report['delta_503_fallback_correlation_verified'] = browser_value['delta_503_fallback_correlation_verified']
            report['unexpected_console_errors'] = browser_value['unexpected_console_errors']
            report['unexpected_api_errors'] = browser_value['unexpected_api_errors']
            report['known_product_observations'] = browser_value['known_product_observations']
            report['unexpected_product_observations'] = browser_value['unexpected_product_observations']
            first_browser_failure = first_failed_phase(phases, start_at='browser_desktop')
            if first_browser_failure is not None:
                failed_phase_name, failed_phase = first_browser_failure
                verification_error = ReviewEnvironmentError(
                    failed_phase['summary'],
                    failure_code=failed_phase['failure_code'],
                    safe_diagnostics=failed_phase['safe_diagnostics'],
                )
                report['first_failure_phase'] = failed_phase_name
            else:
                report['environment_ready'] = True
                report['product_acceptance_ready'] = (
                    phases['product_observations']['status'] == 'passed'
                    and not _blocking_product_observations(report['known_product_observations'])
                )
        else:
            for phase_name in ('browser_desktop', 'browser_accessibility', 'browser_console', 'product_observations'):
                phases[phase_name] = phase_result(
                    status='skipped',
                    duration_ms=0,
                    summary='Skipped in quick mode.',
                    failure_code=None,
                    safe_diagnostics={'reason': 'quick mode omits browser verification'},
                )
            report['environment_ready'] = True
            report['product_acceptance_ready'] = False
    except ReviewEnvironmentError as exc:
        verification_error = exc
        failed_phase_name = next((name for name in REQUIRED_PHASE_NAMES if phases[name]['status'] == 'skipped'), 'static')
        report['first_failure_phase'] = failed_phase_name
        _mark_failed_phase(phases, failed_phase_name, exc)
    finally:
        teardown_started_at = time.monotonic()
        teardown_error: ReviewEnvironmentError | None = None
        process_registry.stop_all()
        try:
            down_review_stack()
            baseline_after = capture_docker_baseline()
            mismatch = compare_docker_baseline(baseline_before, baseline_after)
            if mismatch['containers_added'] or mismatch['containers_removed'] or mismatch['volumes_added'] or mismatch['volumes_removed']:
                raise ReviewEnvironmentError(
                    'Docker baseline was not restored after verification.',
                    failure_code='DOCKER_BASELINE_NOT_RESTORED',
                    safe_diagnostics=mismatch,
                )
            remaining_review_resources = list_review_owned_resources()
            if remaining_review_resources['containers'] or remaining_review_resources['volumes']:
                raise ReviewEnvironmentError(
                    'Review-owned Docker resources remained after teardown.',
                    failure_code='REVIEW_RESOURCES_NOT_REMOVED',
                    safe_diagnostics=remaining_review_resources,
                )
            phases['teardown'] = phase_result(
                status='passed',
                duration_ms=elapsed_ms(teardown_started_at),
                summary='Review stack teardown succeeded, the non-review Docker baseline matched the pre-verify snapshot, and no review-owned resources remained.',
                failure_code=None,
                safe_diagnostics={
                    'baseline_container_count': len(baseline_after['containers']),
                    'baseline_volume_count': len(baseline_after['volumes']),
                    'remaining_review_resources': remaining_review_resources,
                    'owned_processes': process_registry.safe_diagnostics(),
                },
            )
            report['docker_baseline_restored'] = True
        except ReviewEnvironmentError as exc:
            teardown_error = exc
            phases['teardown'] = phase_result(
                status='failed',
                duration_ms=elapsed_ms(teardown_started_at),
                summary=str(exc),
                failure_code=exc.failure_code or 'DOCKER_BASELINE_NOT_RESTORED',
                safe_diagnostics=exc.safe_diagnostics or {},
            )

        report['verify_duration_ms'] = elapsed_ms(started_at)
        report['skipped_phases'] = [phase_name for phase_name, phase in phases.items() if phase['status'] == 'skipped']
        if teardown_error is not None:
            report['ok'] = False
            report['environment_ready'] = False
            report['failure_code'] = teardown_error.failure_code
            report['failure_summary'] = str(teardown_error)
            report['first_failure_phase'] = report['first_failure_phase'] or 'teardown'
        elif verification_error is not None:
            report['ok'] = False
            report['environment_ready'] = False
            report['failure_code'] = verification_error.failure_code
            report['failure_summary'] = str(verification_error)
        else:
            report['ok'] = all(phase['status'] in {'passed', 'skipped'} for phase in phases.values())
            report['failure_code'] = None
            report['failure_summary'] = None
        reporting.write_verify_report(context, report)

    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == 'preflight':
            print_json(run_preflight())
            return 0
        if args.command == 'list-scenarios':
            print_json(scenarios.list_scenarios_payload())
            return 0
        if args.command == 'report':
            if not args.latest:
                raise ReviewEnvironmentError('report currently requires --latest', failure_code='STATIC_CONTAINMENT_FAILED')
            print_json(report_latest())
            return 0
        if args.command == 'up':
            require_confirmation(args)
            print_json(up_review_stack())
            return 0
        if args.command == 'status':
            print_json(review_status())
            return 0
        if args.command == 'down':
            require_confirmation(args)
            print_json(down_review_stack())
            return 0
        if args.command == 'verify':
            require_confirmation(args)
            report = verify_review_environment(mode=args.mode, scenario=args.scenario)
            print_json(report)
            return 0 if report['ok'] else 2
    except ReviewEnvironmentError as exc:
        print_json(
            {
                'ok': False,
                'error': str(exc),
                'failure_code': exc.failure_code,
                'safe_diagnostics': exc.safe_diagnostics,
            }
        )
        return 2
    raise ReviewEnvironmentError(f'unknown command {args.command!r}')


if __name__ == '__main__':
    raise SystemExit(main())
