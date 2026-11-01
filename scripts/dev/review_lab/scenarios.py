from __future__ import annotations

from .contract import ReviewLabError, ScenarioDefinition


REGISTERED_SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name='synthetic_wiring',
        purpose='Prove the isolated Review Lab fixture reaches the real apps/web + Babylon runtime without re-running a normal product journey.',
        synthetic_data_profile='Review Lab V3 corpus: Review Wiring / Review Aggregate / Review Fallback in the disposable review database',
        required_review_only_routes=(),
        api_contracts=('health', 'finder'),
        browser_journey=('Load Explore -> observe Review Wiring fixture -> Babylon ready',),
        expected_network_policy=('same-origin review API only', 'no unexpected 4xx/5xx'),
        evidence_posture='Environment wiring evidence only; not product acceptance or a visual baseline.',
        browser_flow_keys=('syntheticWiring',),
    ),
    ScenarioDefinition(
        name='api_failure',
        purpose='Prove V3 Explore renders a bounded error state when the isolated Review Lab backend deliberately fails search.',
        synthetic_data_profile='Review-only backend mode returns tagged 503 search responses',
        required_review_only_routes=('/api/review/scenario/{mode}',),
        api_contracts=('health', 'review_control'),
        browser_journey=('Establish selected Review Wiring -> activate search failure -> change page size -> preserve selection and marker',),
        expected_network_policy=('only explicitly tagged synthetic 503 responses may fail',),
        evidence_posture='Synthetic failure evidence only; Cypress does not manufacture the failed response.',
        browser_flow_keys=('apiFailure',),
    ),
    ScenarioDefinition(
        name='empty_results',
        purpose='Prove V3 Explore and Babylon handle a deterministic empty result set supplied by the isolated Review Lab backend.',
        synthetic_data_profile='Review-only backend mode returns a contract-shaped empty search response',
        required_review_only_routes=('/api/review/scenario/{mode}',),
        api_contracts=('health', 'review_control'),
        browser_journey=('Activate review-only empty mode -> load Explore -> zero-target Babylon scene',),
        expected_network_policy=('same-origin review API only',),
        evidence_posture='Synthetic edge-state evidence only; Cypress does not stub the product API response.',
        browser_flow_keys=('emptyResults',),
    ),
    ScenarioDefinition(
        name='rankings_api_failure',
        purpose='Prove a synthetic ranked-search failure preserves the exact URL-owned selection and its Babylon marker.',
        synthetic_data_profile='Review-only backend mode returns tagged 503 rankings responses after selection is established',
        required_review_only_routes=('/api/review/scenario/{mode}',),
        api_contracts=('health', 'review_control'),
        browser_journey=('Establish selected Review Wiring -> activate rankings failure -> rerank -> preserve selection and marker',),
        expected_network_policy=('only explicitly tagged synthetic 503 responses may fail',),
        evidence_posture='Synthetic ranked failure evidence only; Cypress does not manufacture the failed response.',
        browser_flow_keys=('rankingsApiFailure',),
    ),
    ScenarioDefinition(
        name='rankings_empty_results',
        purpose='Prove ranked empty state and zero-target Babylon rendering, then recover through a normal Any search.',
        synthetic_data_profile='Review-only backend mode returns a contract-shaped empty rankings response with published fixture identity',
        required_review_only_routes=('/api/review/scenario/{mode}',),
        api_contracts=('health', 'review_control'),
        browser_journey=('Activate rankings empty mode -> zero-target Babylon scene -> Choose Any -> normal search',),
        expected_network_policy=('same-origin review API only',),
        evidence_posture='Synthetic ranked edge-state evidence only; no normal picker or visual acceptance.',
        browser_flow_keys=('rankingsEmptyResults',),
    ),
    ScenarioDefinition(
        name='renderer_recovery',
        purpose='Exercise Babylon context-loss/recovery behaviour that normal Product E2E cannot deterministically force.',
        synthetic_data_profile='Review Wiring / Review Aggregate / Review Fallback systems plus browser-local WEBGL_lose_context fault injection when available',
        required_review_only_routes=(),
        api_contracts=('health', 'finder'),
        browser_journey=('Load synthetic scene -> inject renderer fault -> prove recovery/remount usability',),
        expected_network_policy=('same-origin review API only', 'no uncaught runtime error'),
        evidence_posture='Renderer fault/recovery diagnostic evidence only.',
        browser_flow_keys=('rendererRecovery',),
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
