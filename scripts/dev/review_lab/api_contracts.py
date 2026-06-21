from __future__ import annotations

from typing import Any, Iterable

from .contract import REQUIRED_REVIEW_SYSTEM_NAMES, REVIEW_SYSTEM_IDS, ReviewLabError
from .lifecycle import ensure_contract_shape, fetch_json, probe_event_stream
from .scenarios import ScenarioDefinition
from .support_matrix import api_contract_validated_routes


def _record_support_route_check(diagnostics: dict[str, Any], route: str) -> None:
    checked = diagnostics.setdefault('support_routes_checked', [])
    if route not in checked:
        checked.append(route)


def run_api_contract_phase(selected_scenarios: Iterable[ScenarioDefinition]) -> dict[str, Any]:
    selected_names = {scenario.name for scenario in selected_scenarios}
    diagnostics: dict[str, Any] = {'contracts_checked': [], 'support_routes_checked': []}

    health = fetch_json('GET', '/api/health')
    if health['status'] != 200 or not isinstance(health['body'], dict):
        raise ReviewLabError(
            'Health endpoint did not return the expected contract.',
            failure_code='REVIEW_API_HEALTH_FAILED',
            safe_diagnostics={'route': '/api/health', 'status': health['status']},
        )
    diagnostics['contracts_checked'].append('health')

    if selected_names & {
        'planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'large_result_set', 'partial_optional_data', 'support_route_compatibility',
    }:
        finder = fetch_json(
            'POST',
            '/api/local/search',
            {
                'reference_coords': {'x': 0, 'y': 0, 'z': 0},
                'filters': {
                    'distance': {'min': 0, 'max': 200},
                    'population': {'value': None, 'comparison': 'equal'},
                    'economy': 'any',
                },
                'size': 100 if 'large_result_set' in selected_names else 50,
                'from': 0,
                'sort_by': 'rating',
                'galaxy_wide': False,
            },
        )
        ensure_contract_shape(finder, required_keys={'results', 'count', 'total', 'source'}, failure_code='UNEXPECTED_API_ERROR', route='/api/local/search')
        result_names = {result.get('name') for result in finder['body']['results'] if isinstance(result, dict)}
        missing_names = [name for name in REQUIRED_REVIEW_SYSTEM_NAMES if name not in result_names]
        if missing_names:
            raise ReviewLabError(
                'Finder response did not include every required review system.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'missing_systems': missing_names},
            )
        if 'large_result_set' in selected_names and finder['body']['count'] < len(REQUIRED_REVIEW_SYSTEM_NAMES):
            raise ReviewLabError(
                'Large-result-set scenario did not return the full synthetic review corpus.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'count': finder['body']['count'], 'total': finder['body']['total']},
            )
        diagnostics['finder_systems'] = sorted(result_names)
        diagnostics['contracts_checked'].append('finder')

    required_detail_labels: list[str] = []
    if selected_names & {'planner_core', 'evidence_available', 'partial_optional_data', 'support_route_compatibility'}:
        required_detail_labels.append('alpha')
    if selected_names & {'planner_core', 'evidence_unavailable', 'partial_optional_data'}:
        required_detail_labels.append('beta')
    if selected_names & {'planner_core', 'evidence_unknown', 'partial_optional_data'}:
        required_detail_labels.append('gamma')
    if selected_names & {'planner_core', 'evidence_not_evaluated', 'provenance_fallback'}:
        required_detail_labels.append('delta')
    detail_names: dict[str, str] = {}
    for label in dict.fromkeys(required_detail_labels):
        system_id64 = REVIEW_SYSTEM_IDS[label]
        detail = fetch_json('GET', f'/api/system/{system_id64}')
        ensure_contract_shape(detail, required_keys={'record', 'system'}, failure_code='UNEXPECTED_API_ERROR', route=f'/api/system/{system_id64}')
        system_detail = detail['body']['system']
        if not isinstance(system_detail, dict):
            raise ReviewLabError(
                'System Detail contract did not expose the nested system payload.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': f'/api/system/{system_id64}'},
            )
        missing_system_keys = sorted({'id64', 'name', 'stations', 'bodies'} - set(system_detail))
        if missing_system_keys:
            raise ReviewLabError(
                'System Detail payload is missing required nested fields.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': f'/api/system/{system_id64}', 'missing_keys': missing_system_keys},
            )
        detail_names[label] = system_detail['name']
    if detail_names:
        diagnostics['system_detail_names'] = detail_names
        diagnostics['contracts_checked'].append('system_detail')

    if selected_names & {'planner_core', 'evidence_available'}:
        alpha = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['alpha']}/warehouse-planner-evidence")
        ensure_contract_shape(alpha, required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'}, failure_code='UNEXPECTED_API_ERROR', route='alpha warehouse evidence')
        if alpha['body']['evidence_envelope']['status'] != 'available':
            raise ReviewLabError('Review Alpha did not return available dedicated evidence.', failure_code='UNEXPECTED_API_ERROR', safe_diagnostics={'status': alpha['body']['evidence_envelope']['status']})
        diagnostics['contracts_checked'].append('alpha_evidence')

    if selected_names & {'planner_core', 'evidence_unavailable', 'partial_optional_data'}:
        beta = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['beta']}/warehouse-planner-evidence")
        ensure_contract_shape(beta, required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'}, failure_code='UNEXPECTED_API_ERROR', route='beta warehouse evidence')
        if beta['body']['evidence_envelope']['status'] != 'unavailable':
            raise ReviewLabError('Review Beta did not preserve the unavailable posture.', failure_code='UNEXPECTED_API_ERROR', safe_diagnostics={'status': beta['body']['evidence_envelope']['status']})
        diagnostics['contracts_checked'].append('beta_evidence')

    if selected_names & {'planner_core', 'evidence_unknown', 'partial_optional_data'}:
        gamma = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['gamma']}/warehouse-planner-evidence")
        ensure_contract_shape(gamma, required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'}, failure_code='UNEXPECTED_API_ERROR', route='gamma warehouse evidence')
        if gamma['body']['evidence_envelope']['status'] != 'unknown':
            raise ReviewLabError('Review Gamma did not preserve the unknown posture.', failure_code='UNEXPECTED_API_ERROR', safe_diagnostics={'status': gamma['body']['evidence_envelope']['status']})
        diagnostics['contracts_checked'].append('gamma_evidence')

    delta_response = None
    if selected_names & {'planner_core', 'evidence_not_evaluated', 'provenance_fallback'}:
        delta_response = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence")
        if delta_response['status'] != 503 or not isinstance(delta_response['body'], dict):
            raise ReviewLabError('Review Delta did not return the expected dedicated-evidence 503.', failure_code='DELTA_FALLBACK_NOT_TRIGGERED', safe_diagnostics={'status': delta_response['status']})
        expected_fallback = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit"
        if delta_response['body'].get('fallback_route') != expected_fallback:
            raise ReviewLabError('Review Delta did not point to the provenance fallback route.', failure_code='DELTA_FALLBACK_NOT_TRIGGERED', safe_diagnostics={'fallback_route': delta_response['body'].get('fallback_route')})
        diagnostics['delta_fallback_route'] = expected_fallback
        diagnostics['contracts_checked'].append('delta_evidence_503')

    if selected_names & {'planner_core', 'provenance_fallback', 'partial_optional_data'}:
        delta_provenance = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit")
        ensure_contract_shape(delta_provenance, required_keys={'system', 'provenance_summary', 'evidence_panels', 'warnings'}, failure_code='DELTA_FALLBACK_PROVENANCE_FAILED', route='delta provenance fallback')
        if delta_provenance['body']['system']['name'] != 'Review Delta':
            raise ReviewLabError('Review Delta provenance fallback did not load the review-only synthetic contract.', failure_code='DELTA_FALLBACK_PROVENANCE_FAILED', safe_diagnostics={'system_name': delta_provenance['body']['system'].get('name')})
        diagnostics['contracts_checked'].append('delta_provenance')

    if selected_names & {'planner_core', 'empty_optional_support_data', 'partial_optional_data', 'support_route_compatibility'}:
        live_events = probe_event_stream('/api/events/live')
        recent = fetch_json('GET', '/api/events/recent')
        watchlist = fetch_json('GET', '/api/watchlist')
        cache_stats = fetch_json('GET', '/api/cache/stats')
        if live_events['status'] != 200:
            raise ReviewLabError(
                '/api/events/live did not return the expected SSE handshake response.',
                failure_code='REQUIRED_ROUTE_MISSING',
                safe_diagnostics={'route': '/api/events/live', 'status': live_events['status']},
            )
        content_type = str(live_events.get('content_type') or '').lower()
        if 'text/event-stream' not in content_type:
            raise ReviewLabError(
                '/api/events/live did not return an event-stream content type.',
                failure_code='REQUIRED_ROUTE_MISSING',
                safe_diagnostics={'route': '/api/events/live', 'content_type': live_events.get('content_type')},
            )
        if not live_events.get('stream_opened'):
            raise ReviewLabError(
                '/api/events/live did not complete the expected bounded SSE handshake.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={
                    'route': '/api/events/live',
                    'initial_byte_count': live_events.get('initial_byte_count', 0),
                    'read_bytes_limit': live_events.get('read_bytes_limit'),
                },
            )
        ensure_contract_shape(recent, required_keys={'events', 'jobs'}, failure_code='REQUIRED_ROUTE_MISSING', route='/api/events/recent')
        ensure_contract_shape(watchlist, required_keys={'watchlist'}, failure_code='REQUIRED_ROUTE_MISSING', route='/api/watchlist')
        ensure_contract_shape(cache_stats, required_keys={'cache_hits', 'cache_misses', 'db_cache_rows'}, failure_code='REQUIRED_ROUTE_MISSING', route='/api/cache/stats')
        diagnostics['contracts_checked'].extend(['events_live', 'events_recent', 'watchlist', 'cache_stats'])
        for route in ('/api/events/live', '/api/events/recent', '/api/watchlist', '/api/cache/stats'):
            _record_support_route_check(diagnostics, route)

    if selected_names & {'planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'support_route_compatibility'}:
        facility_templates = fetch_json('GET', '/api/facility-templates')
        if facility_templates['status'] != 200 or not isinstance(facility_templates['body'], list) or not facility_templates['body']:
            raise ReviewLabError('Facility templates route is missing or empty in the review runtime.', failure_code='REQUIRED_ROUTE_MISSING', safe_diagnostics={'route': '/api/facility-templates', 'status': facility_templates['status']})
        simulation_summary = fetch_json('GET', f"/api/systems/{REVIEW_SYSTEM_IDS['alpha']}/simulation-summary")
        slot_predictions = fetch_json('GET', f"/api/systems/{REVIEW_SYSTEM_IDS['alpha']}/slot-predictions")
        ensure_contract_shape(simulation_summary, required_keys={'classification', 'buildability', 'system_id64'}, failure_code='REQUIRED_ROUTE_MISSING', route='/api/systems/{id64}/simulation-summary')
        ensure_contract_shape(slot_predictions, required_keys={'system_id64', 'predictions', 'prediction_status'}, failure_code='REQUIRED_ROUTE_MISSING', route='/api/systems/{id64}/slot-predictions')
        diagnostics['contracts_checked'].extend(['facility_templates', 'simulation_summary', 'slot_predictions'])
        for route in (
            '/api/facility-templates',
            '/api/systems/{id64}/simulation-summary',
            '/api/systems/{id64}/slot-predictions',
        ):
            _record_support_route_check(diagnostics, route)

    diagnostics['contracts_checked'] = sorted(set(diagnostics['contracts_checked']))
    diagnostics['support_routes_checked'] = sorted(set(diagnostics['support_routes_checked']))
    expected_api_routes = {route.route for route in api_contract_validated_routes()}
    missing_api_routes = sorted(expected_api_routes - set(diagnostics['support_routes_checked']))
    if missing_api_routes:
        raise ReviewLabError(
            'One or more api-contract-validated support routes were not exercised.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'missing_routes': missing_api_routes},
        )
    return {
        'summary': 'Loopback review API health, Finder, System Detail, planner evidence, provenance fallback, and support-route contracts passed.',
        'safe_diagnostics': diagnostics,
    }
