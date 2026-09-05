from __future__ import annotations

from typing import Any, Iterable

from .contract import REQUIRED_REVIEW_SYSTEM_NAMES, REVIEW_SYSTEM_IDS, ReviewLabError
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

    if 'autocomplete' in requested:
        autocomplete = fetch_json('GET', '/api/local/autocomplete?q=Review&limit=10')
        ensure_contract_shape(
            autocomplete,
            required_keys={'results'},
            failure_code='UNEXPECTED_API_ERROR',
            route='/api/local/autocomplete',
        )
        names = {row.get('name') for row in autocomplete['body']['results'] if isinstance(row, dict)}
        if 'Review Alpha' not in names:
            raise ReviewLabError(
                'Autocomplete did not expose the required synthetic anchor.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': '/api/local/autocomplete'},
            )
        diagnostics['contracts_checked'].append('autocomplete')

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

    if 'system_detail' in requested:
        detail = fetch_json('GET', f"/api/system/{REVIEW_SYSTEM_IDS['alpha']}")
        ensure_contract_shape(
            detail,
            required_keys={'record', 'system'},
            failure_code='UNEXPECTED_API_ERROR',
            route='/api/system/{id64}',
        )
        system = detail['body']['system']
        if not isinstance(system, dict) or system.get('name') != 'Review Alpha':
            raise ReviewLabError(
                'System Detail did not return the Review Alpha synthetic contract.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': '/api/system/{id64}'},
            )
        diagnostics['contracts_checked'].append('system_detail')

    diagnostics['contracts_checked'] = sorted(set(diagnostics['contracts_checked']))
    return {
        'summary': 'Isolated V3 health, autocomplete, Finder, and System Detail contracts passed.',
        'safe_diagnostics': diagnostics,
    }
