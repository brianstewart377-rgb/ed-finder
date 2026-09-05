from __future__ import annotations

from .contract import ReviewLabError, ScenarioDefinition


REGISTERED_SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name='explore_inspect',
        purpose='Exercise V3 Explore, Babylon, and canonical Inspect with isolated synthetic systems.',
        synthetic_data_profile='Review Alpha/Beta/Gamma/Delta in the disposable review database',
        required_review_only_routes=(),
        api_contracts=('health', 'autocomplete', 'finder', 'system_detail'),
        browser_journey=('Explore -> Review Alpha -> Babylon selection -> Inspect',),
        expected_network_policy=('same-origin review API only', 'no unexpected 4xx/5xx'),
        evidence_posture='Synthetic diagnostic evidence only; not a product visual baseline.',
        accessibility_checks=('keyboard_typeahead',),
        viewport_checks=('v3_desktop_synthetic',),
        product_observation_policy='Review Lab does not own product acceptance observations.',
        browser_flow_keys=('exploreInspect',),
    ),
    ScenarioDefinition(
        name='api_failure',
        purpose='Prove V3 Explore renders a bounded error state for a deliberately failed search.',
        synthetic_data_profile='Two intercepted review-only 503 responses covering the bounded query retry',
        required_review_only_routes=(),
        api_contracts=('health', 'finder'),
        browser_journey=('Explore -> injected search failure -> recoverable error rendering',),
        expected_network_policy=('two explicitly tagged synthetic 503 responses',),
        evidence_posture='Failure injection is confined to the Review Lab browser process.',
        accessibility_checks=(),
        viewport_checks=('v3_desktop_synthetic',),
        product_observation_policy='Review Lab does not own product acceptance observations.',
        browser_flow_keys=('apiFailure',),
    ),
    ScenarioDefinition(
        name='empty_results',
        purpose='Prove V3 Explore and Babylon handle a deterministic empty synthetic result set.',
        synthetic_data_profile='Contract-shaped empty search response injected in Review Lab',
        required_review_only_routes=(),
        api_contracts=('health', 'finder'),
        browser_journey=('Explore -> empty results -> zero-target Babylon scene',),
        expected_network_policy=('same-origin review API only',),
        evidence_posture='Synthetic diagnostic evidence only; not a product visual baseline.',
        accessibility_checks=(),
        viewport_checks=('v3_desktop_synthetic',),
        product_observation_policy='Review Lab does not own product acceptance observations.',
        browser_flow_keys=('emptyResults',),
    ),
    ScenarioDefinition(
        name='renderer_recovery',
        purpose='Exercise Babylon WebGL context loss/restoration where the browser exposes the recovery mechanism.',
        synthetic_data_profile='Review systems plus browser-local WEBGL_lose_context injection',
        required_review_only_routes=(),
        api_contracts=('health', 'finder'),
        browser_journey=('Explore -> Babylon ready -> context loss -> context restore',),
        expected_network_policy=('same-origin review API only', 'no uncaught runtime error'),
        evidence_posture='Diagnostic resource-lifecycle evidence only.',
        accessibility_checks=(),
        viewport_checks=('v3_desktop_synthetic',),
        product_observation_policy='Review Lab does not own product acceptance observations.',
        browser_flow_keys=('rendererRecovery',),
    ),
    ScenarioDefinition(
        name='navigation_containment',
        purpose='Prove direct Inspect and return navigation remain inside the isolated V3 application.',
        synthetic_data_profile='Review Alpha canonical detail',
        required_review_only_routes=(),
        api_contracts=('health', 'system_detail'),
        browser_journey=('Direct Inspect -> Review Alpha -> Back to Explore',),
        expected_network_policy=('same-origin review API only', 'no production hosts'),
        evidence_posture='Synthetic diagnostic evidence only; not a product visual baseline.',
        accessibility_checks=('inspect_heading_focus',),
        viewport_checks=('v3_desktop_synthetic',),
        product_observation_policy='Review Lab does not own product acceptance observations.',
        browser_flow_keys=('navigationContainment',),
    ),
)

SCENARIO_BY_NAME = {scenario.name: scenario for scenario in REGISTERED_SCENARIOS}


def validate_scenario_registry() -> None:
    if not REGISTERED_SCENARIOS:
        raise ReviewLabError('Scenario registry is empty.', failure_code='STATIC_CONTAINMENT_FAILED')
    names = [scenario.name for scenario in REGISTERED_SCENARIOS]
    if len(names) != len(set(names)):
        raise ReviewLabError(
            'Scenario registry contains duplicate names.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'scenario_names': names},
        )
    for scenario in REGISTERED_SCENARIOS:
        if not scenario.api_contracts or not scenario.browser_flow_keys:
            raise ReviewLabError(
                f'Scenario {scenario.name!r} must declare API and browser contracts.',
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
    return False
