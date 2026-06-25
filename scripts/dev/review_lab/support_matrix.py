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
        route='/api/health',
        frontend_caller='App health bootstrap',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal meta health route against the isolated review API.',
        allowed_response_characteristics=('JSON object', 'status key', 'real route shape'),
        scenario_coverage=('planner_core', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/local/search',
        frontend_caller='Finder initial search and review result list',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal search route against the review database.',
        allowed_response_characteristics=('JSON object', 'results/count/total/source keys', 'synthetic review corpus'),
        scenario_coverage=('planner_core', 'large_result_set', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/system/{id64}',
        frontend_caller='System Detail and Colony Planner workspace bootstrap',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal system detail route against seeded review systems.',
        allowed_response_characteristics=('JSON object', 'record/system keys', 'real route shape'),
        scenario_coverage=('planner_core', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
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
        frontend_caller='useWatchlist scoped bootstrap and saved systems',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal scoped Watchlist route against the review database; disposable per sync key.',
        allowed_response_characteristics=('JSON object', 'sync_key echo', 'watchlist array'),
        scenario_coverage=('planner_core', 'empty_optional_support_data', 'partial_optional_data', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/watchlist',
        frontend_caller='retired unscoped watchlist compatibility route',
        required_for_reviewed_flow=False,
        expected_status=410,
        review_only_handling='Retired route must keep its production-equivalent gone response instead of becoming a fake success.',
        allowed_response_characteristics=('problem details JSON', 'HTTP 410', 'no review-only success payload'),
        scenario_coverage=('support_route_compatibility',),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/facility-templates',
        frontend_caller='Colony Planner templates and Suggested Builds',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only facility catalogue route against the review database.',
        allowed_response_characteristics=('JSON array', 'non-empty', 'real route shape'),
        scenario_coverage=('planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'planner_supported_actions', 'support_route_compatibility'),
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
    SupportRoute(
        route='/api/simulate/build',
        frontend_caller='Colony Planner Run Preview and Validation setup',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal deterministic simulation preview route against review data.',
        allowed_response_characteristics=('JSON object', 'final_score/buildability_score/services keys', 'real route shape'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/optimiser/candidates',
        frontend_caller='Colony Planner explicitly invoked Suggested Builds',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal deterministic optimiser route against review data; no fake success response.',
        allowed_response_characteristics=('JSON object', 'candidates array', 'bounded candidate count'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/observations/facts',
        frontend_caller='Observed Evidence list/create disposable facts',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal observed-facts route against disposable review database rows.',
        allowed_response_characteristics=('JSON object', 'facts array for GET', 'created fact for POST'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/observations/facts/{observation_id}',
        frontend_caller='Observed Evidence remove disposable fact',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal observed-fact delete route against disposable review database rows.',
        allowed_response_characteristics=('JSON object', 'deleted confirmation', 'real route shape'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/observations/compare',
        frontend_caller='Validation panel comparison',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal passive comparison route; does not alter predictions or mechanics.',
        allowed_response_characteristics=('JSON object', 'summary/comparisons keys', 'real route shape'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/observations/review',
        frontend_caller='Validation review guidance',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal passive review-guidance route; advisory only.',
        allowed_response_characteristics=('JSON object', 'summary/signals keys', 'real route shape'),
        scenario_coverage=('planner_supported_actions', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/colony-planner/system/{id64}/warehouse-planner-evidence',
        frontend_caller='Planner warehouse evidence card',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Review-safe evidence route with a deliberate Delta fallback posture.',
        allowed_response_characteristics=('JSON object or deliberate Delta 503', 'evidence envelope', 'fallback route when unavailable'),
        scenario_coverage=('planner_core', 'evidence_available', 'evidence_unavailable', 'evidence_unknown', 'evidence_not_evaluated', 'provenance_fallback', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/colony-planner/system/{id64}/provenance-cockpit',
        frontend_caller='Planner provenance evidence fallback',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Review-safe provenance fallback route.',
        allowed_response_characteristics=('JSON object', 'provenance_summary/evidence_panels keys', 'real route shape'),
        scenario_coverage=('planner_core', 'provenance_fallback', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/map/regions',
        frontend_caller='Map regions layer when toggled',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only map route against review data.',
        allowed_response_characteristics=('JSON object', 'regions array', 'real route shape'),
        scenario_coverage=('map_visible', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/map/clusters/hulls',
        frontend_caller='Map cluster layer when toggled',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only map route against review data.',
        allowed_response_characteristics=('JSON object', 'clusters array', 'real route shape'),
        scenario_coverage=('map_visible', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/map/heatmap',
        frontend_caller='Map heatmap layer when toggled',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only map route against review data.',
        allowed_response_characteristics=('JSON object', 'cells array', 'real route shape'),
        scenario_coverage=('map_visible', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/map/timeline',
        frontend_caller='Map timeline route when used by visible map controls',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal read-only map route against review data.',
        allowed_response_characteristics=('JSON object', 'points array', 'real route shape'),
        scenario_coverage=('map_visible', 'support_route_compatibility'),
        validation_mode='api_contract_validated',
    ),
)

REQUIRED_MATRIX_ROUTES = {
    '/api/health',
    '/api/local/search',
    '/api/system/{id64}',
    '/api/events/live',
    '/api/events/recent',
    '/api/v2/watchlist/{sync_key}',
    '/api/watchlist',
    '/api/facility-templates',
    '/api/systems/{id64}/simulation-summary',
    '/api/systems/{id64}/slot-predictions',
    '/api/simulate/build',
    '/api/optimiser/candidates',
    '/api/observations/facts',
    '/api/observations/facts/{observation_id}',
    '/api/observations/compare',
    '/api/observations/review',
    '/api/colony-planner/system/{id64}/warehouse-planner-evidence',
    '/api/colony-planner/system/{id64}/provenance-cockpit',
    '/api/map/regions',
    '/api/map/clusters/hulls',
    '/api/map/heatmap',
    '/api/map/timeline',
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