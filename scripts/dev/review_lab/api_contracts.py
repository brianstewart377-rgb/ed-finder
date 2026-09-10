from __future__ import annotations

from typing import Any, Iterable

from .contract import REQUIRED_REVIEW_SYSTEM_NAMES, ReviewLabError
from .lifecycle import ensure_contract_shape, fetch_json
from .scenarios import ScenarioDefinition


def run_api_contract_phase(selected_scenarios: Iterable[ScenarioDefinition]) -> dict[str, Any]:
    requested = {contract for scenario in selected_scenarios for contract in scenario.api_contracts}
    diagnostics: dict[str, Any] = {'contracts_checked': []}

    health = fetch_json('GET', '/api/health')
    if health['status'] != 200 or not isinstance(health['body'], dict):
        raise ReviewLabError(
            'Health endpoint did not return the expected isolated contract.',
            failure_code='REVIEW_API_HEALTH_FAILED',
            safe_diagnostics={'route': '/api/health', 'status': health['status']},
        )
    diagnostics['contracts_checked'].append('health')

    if 'finder' in requested:
        finder = fetch_json(
            'POST',
            '/api/local/search',
            {
                'galaxy_wide': True,
                'filters': {'economy': 'any'},
                'sort_by': 'development',
                'size': 24,
                'from': 0,
            },
        )
        ensure_contract_shape(
            finder,
            required_keys={'results', 'count', 'total', 'source'},
            failure_code='UNEXPECTED_API_ERROR',
            route='/api/local/search',
        )
        names = {row.get('name') for row in finder['body']['results'] if isinstance(row, dict)}
        missing = sorted(set(REQUIRED_REVIEW_SYSTEM_NAMES) - names)
        if missing:
            raise ReviewLabError(
                'Finder did not expose every required synthetic Review Lab system.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'missing_systems': missing},
            )
        diagnostics['finder_systems'] = sorted(names)
        diagnostics['contracts_checked'].append('finder')

    if 'review_control' in requested:
        control = fetch_json('POST', '/api/review/scenario/normal')
        ensure_contract_shape(
            control,
            required_keys={'scenario'},
            failure_code='UNEXPECTED_API_ERROR',
            route='/api/review/scenario/{mode}',
        )
        if control['body']['scenario'] != 'normal':
            raise ReviewLabError(
                'Review Lab scenario control did not reset to normal mode.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': '/api/review/scenario/{mode}'},
            )
        diagnostics['contracts_checked'].append('review_control')

    diagnostics['contracts_checked'] = sorted(set(diagnostics['contracts_checked']))
    return {
        'summary': 'Isolated Review Lab health, Finder wiring, and review-only control contracts passed.',
        'safe_diagnostics': diagnostics,
    }
