from __future__ import annotations

from .contract import ScenarioDefinition, ReviewLabError


REGISTERED_SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name='planner_core',
        purpose='Prove the core Finder -> System Detail -> Colony Planner review journey against the isolated stack.',
        synthetic_data_profile='Review Alpha/Beta/Gamma/Delta synthetic planner corpus',
        required_review_only_routes=(
            '/api/events/live',
            '/api/events/recent',
            '/api/v2/watchlist/{sync_key}',
            '/api/facility-templates',
            '/api/systems/{id64}/simulation-summary',
            '/api/systems/{id64}/slot-predictions',
        ),
        api_contracts=('health', 'finder', 'system_detail', 'facility_templates', 'simulation_summary', 'slot_predictions'),
        browser_journey=(
            'Finder -> Review Alpha -> System Detail -> Open Colony Planner',
            'Finder -> Review Beta -> System Detail -> Colony Planner',
            'Finder -> Review Gamma -> System Detail -> Colony Planner',
            'Finder -> Review Delta -> System Detail -> Colony Planner',
        ),
        expected_network_policy=('no unexpected 4xx/5xx', 'no recovery screen', 'only correlated Delta 503 allowed'),
        evidence_posture='Exercises Alpha available, Beta unavailable, Gamma unknown, and Delta fallback planner evidence.',
        accessibility_checks=('modal_escape_close', 'keyboard_open_planner', 'desktop_telemetry_toggle'),
        viewport_checks=(
            'planner_desktop_primary required acceptance',
            'planner_laptop_minimum required acceptance',
            'planner_constrained_diagnostic bounded diagnostic',
            'finder_mobile required acceptance',
            'planner_mobile_resilience bounded resilience',
        ),
        product_observation_policy='Record constrained and phone-width planner layout diagnostics without letting them redefine desktop-first planner acceptance.',
        browser_flow_keys=('alpha', 'beta', 'gamma', 'delta'),
        requires_product_observations=True,
    ),
    ScenarioDefinition(
        name='evidence_available',
        purpose='Validate Review Alpha available evidence posture.',
        synthetic_data_profile='Review Alpha synthetic available evidence contract',
        required_review_only_routes=('/api/facility-templates', '/api/systems/{id64}/simulation-summary', '/api/systems/{id64}/slot-predictions'),
        api_contracts=('health', 'finder', 'system_detail_alpha', 'alpha_evidence'),
        browser_journey=('Finder -> Review Alpha -> System Detail -> Open Colony Planner',),
        expected_network_policy=('no unexpected 4xx/5xx',),
        evidence_posture='Dedicated evidence available, still report-only and non-canonical.',
        accessibility_checks=('keyboard_open_planner',),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('alpha',),
    ),
    ScenarioDefinition(
        name='evidence_unavailable',
        purpose='Validate Review Beta unavailable evidence posture.',
        synthetic_data_profile='Review Beta synthetic unavailable evidence contract',
        required_review_only_routes=('/api/facility-templates', '/api/systems/{id64}/simulation-summary', '/api/systems/{id64}/slot-predictions'),
        api_contracts=('health', 'finder', 'system_detail_beta', 'beta_evidence'),
        browser_journey=('Finder -> Review Beta -> System Detail -> Colony Planner',),
        expected_network_policy=('no unexpected 4xx/5xx',),
        evidence_posture='Dedicated evidence unavailable posture stays honest.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('beta',),
    ),
    ScenarioDefinition(
        name='evidence_unknown',
        purpose='Validate Review Gamma unknown evidence posture.',
        synthetic_data_profile='Review Gamma synthetic unknown evidence contract',
        required_review_only_routes=('/api/facility-templates', '/api/systems/{id64}/simulation-summary', '/api/systems/{id64}/slot-predictions'),
        api_contracts=('health', 'finder', 'system_detail_gamma', 'gamma_evidence'),
        browser_journey=('Finder -> Review Gamma -> System Detail -> Colony Planner',),
        expected_network_policy=('no unexpected 4xx/5xx',),
        evidence_posture='Selected-system evidence remains unknown.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('gamma',),
    ),
    ScenarioDefinition(
        name='evidence_not_evaluated',
        purpose='Validate Review Delta not-evaluated dedicated evidence failure posture.',
        synthetic_data_profile='Review Delta synthetic not-evaluated evidence contract',
        required_review_only_routes=('/api/facility-templates', '/api/systems/{id64}/simulation-summary', '/api/systems/{id64}/slot-predictions'),
        api_contracts=('health', 'finder', 'system_detail_delta', 'delta_evidence_503'),
        browser_journey=('Finder -> Review Delta -> System Detail -> Colony Planner',),
        expected_network_policy=('Delta 503 only when correlated to fallback',),
        evidence_posture='Dedicated evidence remains not evaluated and report-only.',
        accessibility_checks=(),
        viewport_checks=('planner_mobile_resilience bounded resilience',),
        product_observation_policy='Record only bounded phone-width planner resilience diagnostics without blocking environment readiness.',
        browser_flow_keys=('delta',),
        requires_product_observations=True,
    ),
    ScenarioDefinition(
        name='provenance_fallback',
        purpose='Validate Review Delta provenance fallback path and disclosure.',
        synthetic_data_profile='Review Delta synthetic provenance fallback contract',
        required_review_only_routes=('/api/facility-templates', '/api/systems/{id64}/simulation-summary', '/api/systems/{id64}/slot-predictions'),
        api_contracts=('health', 'delta_evidence_503', 'delta_provenance'),
        browser_journey=('Finder -> Review Delta -> System Detail -> Colony Planner',),
        expected_network_policy=('503 -> fallback request -> 200 -> visible fallback posture',),
        evidence_posture='Visible provenance bridge fallback remains report-only and non-canonical.',
        accessibility_checks=(),
        viewport_checks=('planner_mobile_resilience bounded resilience',),
        product_observation_policy='Record only bounded phone-width planner resilience diagnostics without blocking environment readiness.',
        browser_flow_keys=('delta',),
        requires_product_observations=True,
    ),
    ScenarioDefinition(
        name='planner_supported_actions',
        purpose='Validate supported Planner actions: Observed Evidence, Validation, and explicitly invoked Suggested Builds.',
        synthetic_data_profile='Review Alpha disposable planner action data',
        required_review_only_routes=(
            '/api/facility-templates',
            '/api/simulate/build',
            '/api/optimiser/candidates',
            '/api/observations/facts',
            '/api/observations/facts/{observation_id}',
            '/api/observations/compare',
            '/api/observations/review',
        ),
        api_contracts=('facility_templates', 'simulate_build', 'optimiser_candidates', 'observed_facts_crud', 'observation_compare', 'observation_review'),
        browser_journey=('Finder -> Review Alpha -> Colony Planner -> Evidence -> create/remove fact -> Preview -> Validation -> Suggested Builds',),
        expected_network_policy=('no unexpected 4xx/5xx', 'all supported planner action calls use real route contracts'),
        evidence_posture='Observed Evidence remains disposable and passive; Validation remains advisory.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('planner_actions',),
    ),
    ScenarioDefinition(
        name='map_visible',
        purpose='Validate the visible hosted-review Map journey and read-only map routes.',
        synthetic_data_profile='Review synthetic systems with map coordinates and map layer data',
        required_review_only_routes=(
            '/api/map/regions',
            '/api/map/clusters/hulls',
            '/api/map/heatmap',
            '/api/map/timeline',
        ),
        api_contracts=('map_regions', 'map_cluster_hulls', 'map_heatmap', 'map_timeline'),
        browser_journey=('Finder -> Map -> enable Regions, Heatmap, and Clusters',),
        expected_network_policy=('no unexpected 4xx/5xx from visible Map requests',),
        evidence_posture='Not applicable; read-only map scenario.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('map',),
    ),
    ScenarioDefinition(
        name='unavailable_review_surfaces',
        purpose='Validate Admin, Operator, and Search Tuning are not exposed as normal hosted-review player surfaces.',
        synthetic_data_profile='Hosted-review frontend availability matrix',
        required_review_only_routes=(),
        api_contracts=('feature_availability', 'unavailable_surfaces'),
        browser_journey=('Open #admin, #operator, #search-tuning and verify deliberate unavailable state with no operational calls.',),
        expected_network_policy=('no unexpected 4xx/5xx', 'no admin/operator/search-tuning operational requests'),
        evidence_posture='Not applicable; availability scenario.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
        browser_flow_keys=('unavailable_surfaces',),
    ),
    ScenarioDefinition(
        name='excluded_review_features',
        purpose='Validate Profile Sync remains excluded from hosted-review scope.',
        synthetic_data_profile='Hosted-review frontend availability matrix',
        required_review_only_routes=(),
        api_contracts=('feature_availability',),
        browser_journey=(),
        expected_network_policy=('Profile Sync is not exposed as an operational review surface.',),
        evidence_posture='Not applicable; excluded feature.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
    ),    ScenarioDefinition(
        name='empty_optional_support_data',
        purpose='Validate optional noisy routes return safe empty review-only payloads.',
        synthetic_data_profile='Review support routes with empty synthetic event/cache data and fresh scoped Watchlist state',
        required_review_only_routes=('/api/events/live', '/api/events/recent', '/api/v2/watchlist/{sync_key}'),
        api_contracts=('events_live', 'events_recent', 'watchlist'),
        browser_journey=(),
        expected_network_policy=('no unexpected 404 for optional noisy routes',),
        evidence_posture='Not applicable; support-route only.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
    ),
    ScenarioDefinition(
        name='large_result_set',
        purpose='Validate Finder large-result-set contract stays deterministic for review data.',
        synthetic_data_profile='Review Alpha/Beta/Gamma/Delta synthetic finder dataset with stable ordering',
        required_review_only_routes=(),
        api_contracts=('health', 'finder_large_result_set'),
        browser_journey=(),
        expected_network_policy=('no unexpected 4xx/5xx',),
        evidence_posture='Not applicable; finder contract only.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
    ),
    ScenarioDefinition(
        name='partial_optional_data',
        purpose='Validate contract-shaped responses when optional synthetic fields are absent or unknown.',
        synthetic_data_profile='Review Beta/Gamma/Delta synthetic records with optional/unknown payload members',
        required_review_only_routes=('/api/v2/watchlist/{sync_key}',),
        api_contracts=('health', 'finder', 'system_detail', 'beta_evidence', 'gamma_evidence', 'delta_provenance'),
        browser_journey=(),
        expected_network_policy=('no malformed JSON contracts',),
        evidence_posture='Unknown/unavailable/not-evaluated states stay explicit instead of breaking contracts.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
    ),
    ScenarioDefinition(
        name='support_route_compatibility',
        purpose='Validate the explicit review support-route compatibility matrix.',
        synthetic_data_profile='Review-only support routes with contract-shaped responses for reviewed flows',
        required_review_only_routes=(
            '/api/events/live',
            '/api/events/recent',
            '/api/v2/watchlist/{sync_key}',
            '/api/facility-templates',
            '/api/systems/{id64}/simulation-summary',
            '/api/systems/{id64}/slot-predictions',
        ),
        api_contracts=('support_route_matrix', 'events_live', 'events_recent', 'watchlist', 'watchlist_legacy_gone', 'facility_templates', 'simulation_summary', 'slot_predictions', 'simulate_build', 'optimiser_candidates', 'observed_facts_crud', 'observation_compare', 'observation_review', 'map_regions', 'map_cluster_hulls', 'map_heatmap', 'map_timeline', 'feature_availability'),
        browser_journey=(),
        expected_network_policy=('unexpected reviewed-flow 404/5xx fails verification',),
        evidence_posture='Not applicable; support-route coverage only.',
        accessibility_checks=(),
        viewport_checks=(),
        product_observation_policy='No separate product observation requirement.',
    ),
)

SCENARIO_BY_NAME = {scenario.name: scenario for scenario in REGISTERED_SCENARIOS}


def validate_scenario_registry() -> None:
    if not REGISTERED_SCENARIOS:
        raise ReviewLabError('Scenario registry is empty.', failure_code='STATIC_CONTAINMENT_FAILED')
    names = [scenario.name for scenario in REGISTERED_SCENARIOS]
    if len(names) != len(set(names)):
        raise ReviewLabError('Scenario registry contains duplicate names.', failure_code='STATIC_CONTAINMENT_FAILED', safe_diagnostics={'scenario_names': names})
    for scenario in REGISTERED_SCENARIOS:
        if not scenario.api_contracts:
            raise ReviewLabError(
                f'Scenario {scenario.name!r} must declare at least one API contract.',
                failure_code='STATIC_CONTAINMENT_FAILED',
            )
        if scenario.requires_product_observations and not scenario.browser_flow_keys:
            raise ReviewLabError(
                f'Scenario {scenario.name!r} cannot require product observations without a browser journey.',
                failure_code='STATIC_CONTAINMENT_FAILED',
            )


def resolve_scenarios(selection: str) -> tuple[ScenarioDefinition, ...]:
    validate_scenario_registry()
    if selection == 'all':
        return REGISTERED_SCENARIOS
    scenario = SCENARIO_BY_NAME.get(selection)
    if scenario is None:
        raise ReviewLabError(
            f'Unknown review scenario {selection!r}.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'known_scenarios': list(SCENARIO_BY_NAME)},
        )
    return (scenario,)


def scenario_names() -> tuple[str, ...]:
    return tuple(scenario.name for scenario in REGISTERED_SCENARIOS)


def list_scenarios_payload() -> dict[str, object]:
    validate_scenario_registry()
    return {
        'ok': True,
        'scenario_count': len(REGISTERED_SCENARIOS),
        'scenarios': [scenario.to_dict() for scenario in REGISTERED_SCENARIOS],
    }


def selected_browser_flow_keys(selected: tuple[ScenarioDefinition, ...]) -> tuple[str, ...]:
    ordered_keys: list[str] = []
    for scenario in selected:
        for key in scenario.browser_flow_keys:
            if key not in ordered_keys:
                ordered_keys.append(key)
    return tuple(ordered_keys)


def selection_requires_product_observations(selected: tuple[ScenarioDefinition, ...]) -> bool:
    return any(scenario.requires_product_observations for scenario in selected)
