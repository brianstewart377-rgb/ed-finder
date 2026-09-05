from __future__ import annotations

from .contract import ReviewLabError, SupportRoute
from .scenarios import scenario_names


REVIEW_SUPPORT_ROUTE_MATRIX: tuple[SupportRoute, ...] = (
    SupportRoute(
        route='/api/health',
        frontend_caller='apps/web API facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal route backed by the isolated Review Lab runtime.',
        allowed_response_characteristics=('JSON health object', 'isolated database connected'),
        scenario_coverage=scenario_names(),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/local/autocomplete',
        frontend_caller='apps/web ExploreWorkspace through generated SDK facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal route over synthetic Review Lab systems.',
        allowed_response_characteristics=('JSON results list', 'decimal-string id64 in browser'),
        scenario_coverage=('explore_inspect',),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/local/search',
        frontend_caller='apps/web ExploreWorkspace through generated SDK facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal isolated response, with bounded browser-only failure/empty injection.',
        allowed_response_characteristics=('JSON results list', 'synthetic Review Lab systems'),
        scenario_coverage=('explore_inspect', 'api_failure', 'empty_results', 'renderer_recovery'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/system/{id64}',
        frontend_caller='apps/web SystemDetail through generated SDK facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal detail route over the isolated Review Lab database.',
        allowed_response_characteristics=('JSON detail envelope', 'synthetic Review Alpha identity'),
        scenario_coverage=('explore_inspect', 'navigation_containment'),
        validation_mode='api_contract_validated',
    ),
)


def support_route_payload() -> list[dict[str, object]]:
    return [route.to_dict() for route in REVIEW_SUPPORT_ROUTE_MATRIX]


def api_contract_validated_routes() -> tuple[SupportRoute, ...]:
    return REVIEW_SUPPORT_ROUTE_MATRIX


def validate_support_route_matrix() -> None:
    known_scenarios = set(scenario_names())
    routes = [route.route for route in REVIEW_SUPPORT_ROUTE_MATRIX]
    if len(routes) != len(set(routes)):
        raise ReviewLabError('Support-route matrix contains duplicates.', failure_code='STATIC_CONTAINMENT_FAILED')
    for route in REVIEW_SUPPORT_ROUTE_MATRIX:
        unknown = sorted(set(route.scenario_coverage) - known_scenarios)
        if unknown or not route.allowed_response_characteristics:
            raise ReviewLabError(
                'Support-route matrix contains an invalid V3 Review Lab contract.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'route': route.route, 'unknown_scenarios': unknown},
            )
