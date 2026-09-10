from __future__ import annotations

from .contract import ReviewLabError, SupportRoute
from .scenarios import scenario_names


REVIEW_SUPPORT_ROUTE_MATRIX: tuple[SupportRoute, ...] = (
    SupportRoute(
        route='/api/health',
        frontend_caller='Review Lab wrapper and apps/web API facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal route backed by the isolated Review Lab runtime.',
        allowed_response_characteristics=('JSON health object', 'isolated database connected'),
        scenario_coverage=scenario_names(),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/local/search',
        frontend_caller='apps/web ExploreWorkspace through the normal generated SDK facade',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Normal synthetic fixture response, or backend-owned review-only failure/empty mode.',
        allowed_response_characteristics=(
            'normal synthetic Review Lab systems',
            'tagged review-only 503 in api_failure mode',
            'contract-shaped empty result in empty_results mode',
        ),
        scenario_coverage=('synthetic_wiring', 'api_failure', 'empty_results', 'renderer_recovery'),
        validation_mode='api_contract_validated',
    ),
    SupportRoute(
        route='/api/review/scenario/{mode}',
        frontend_caller='Review Lab collector only; never the product frontend',
        required_for_reviewed_flow=True,
        expected_status=200,
        review_only_handling='Changes only the isolated review_main.py scenario mode.',
        allowed_response_characteristics=('normal', 'api_failure', 'empty_results'),
        scenario_coverage=('api_failure', 'empty_results'),
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
