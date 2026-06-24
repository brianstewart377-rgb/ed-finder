from __future__ import annotations

from .contract import SupportRoute, ReviewLabError, SupportRouteValidationMode
from .scenarios import scenario_names

VALIDATION_MODES: tuple[SupportRouteValidationMode, ...] = (
    'api_contract_validated',
    'browser_only_validated',
    'intentionally_not_exercised',
)


REVIEW_SUPPORT_ROUTE_MATRIX: tuple[SupportRoute, ...] = (
    SupportRoute(
        route='/api/events/live',
        frontend_caller='useEddnFeed SSE bootstrap',
        required_for_reviewed_flow=False,
        expected_status=200,
        review_only_handling='Review-only SSE keepalive stream.',
        allowed_response_characteristics=('text/event-stream', 'keepalive comments only', 'no live operational claims'),
        scenario_coverage=('planner_core', 'empty_optional_support_data', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/events/recent',
        frontend_caller='useEddnFeed recent-events polling',
        required_for_reviewed_flow=False,
        expected_status=200,
        review_only_handling='Review-only empty synthetic events payload.',
        allowed_response_characteristics=('JSON object', 'events array empty', 'jobs object empty'),
        scenario_coverage=('planner_core', 'empty_optional_support_data', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/v2/watchlist/{sync_key}',
        frontend_caller='useWatchlist scoped bootstrap',
        required_for_reviewed_flow=False,
        expected_status=200,
        review_only_handling='Normal scoped Watchlist route against the review database; empty for fresh sync keys.',
        allowed_response_characteristics=('JSON object', 'sync_key echo', 'watchlist array empty for fresh sync keys'),
        scenario_coverage=('planner_core', 'empty_optional_support_data', 'partial_optional_data', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/cache/stats',
        frontend_caller='AdminTab background query',
        required_for_reviewed_flow=False,
        expected_status=200,
        review_only_handling='Review-only zeroed cache stats payload.',
        allowed_response_characteristics=('JSON object', 'all counters zeroed', 'no operational/source claims'),
        scenario_coverage=('planner_core', 'empty_optional_support_data', 'partial_optional_data', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/facility-templates',
        frontend_caller='WholeSystemColonyPlanner',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only facility catalogue route against the review database.',
        allowed_response_characteristics=('JSON array', 'non-empty', 'real route shape'),
        scenario_coverage=('planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/systems/{id64}/simulation-summary',
        frontend_caller='WholeSystemColonyPlanner',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only simulation summary route against the review database.',
        allowed_response_characteristics=('JSON object', 'classification/buildability/system_id64 keys', 'real route shape'),
        scenario_coverage=('planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/systems/{id64}/slot-predictions',
        frontend_caller='WholeSystemColonyPlanner',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only slot prediction route against the review database.',
        allowed_response_characteristics=('JSON object', 'system_id64/predictions/prediction_status keys', 'real route shape'),
        scenario_coverage=('planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
)

REQUIRED_MATRIX_ROUTES = {
    '/api/events/live',
    '/api/events/recent',
    '/api/v2/watchlist/{sync_key}',
    '/api/cache/stats',
    '/api/facility-templates',
    '/api/systems/{id64}/simulation-summary',
    '/api/systems/{id64}/slot-predictions',
}


def support_route_payload() -> list[dict[str, object]]:
    return [route.to_dict() for route in REVIEW_SUPPORT_ROUTE_MATRIX]


def api_contract_validated_routes() -> tuple[SupportRoute, ...]:
    return tuple(route for route in REVIEW_SUPPORT_ROUTE_MATRIX if route.validation_mode == 'api_contract_validated')


def validate_support_route_matrix() -> None:
    known_scenarios = set(scenario_names())
    route_map = {route.route: route for route in REVIEW_SUPPORT_ROUTE_MATRIX}
    missing = sorted(REQUIRED_MATRIX_ROUTES - route_map.keys())
    if missing:
        raise ReviewLabError(
            'Support-route matrix is missing required reviewed-flow endpoints.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'missing_routes': missing},
        )
    if len(route_map) != len(REVIEW_SUPPORT_ROUTE_MATRIX):
        duplicates = sorted(route.route for route in REVIEW_SUPPORT_ROUTE_MATRIX if sum(1 for candidate in REVIEW_SUPPORT_ROUTE_MATRIX if candidate.route == route.route) > 1)
        raise ReviewLabError(
            'Support-route matrix contains duplicate route entries.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'duplicate_routes': sorted(set(duplicates))},
        )
    for route in REVIEW_SUPPORT_ROUTE_MATRIX:
        unknown_coverage = sorted(set(route.scenario_coverage) - known_scenarios)
        if unknown_coverage:
            raise ReviewLabError(
                'Support-route matrix references unknown scenario coverage.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'route': route.route, 'unknown_scenarios': unknown_coverage},
            )
        if not route.allowed_response_characteristics:
            raise ReviewLabError(
                'Support-route matrix rows must declare allowed response characteristics.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'route': route.route},
            )
        if route.validation_mode not in VALIDATION_MODES:
            raise ReviewLabError(
                'Support-route matrix rows must declare an explicit validation mode.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'route': route.route, 'validation_mode': route.validation_mode},
            )
