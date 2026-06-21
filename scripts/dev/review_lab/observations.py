from __future__ import annotations

from typing import Any, Mapping


KNOWN_PRODUCT_OBSERVATIONS: dict[str, dict[str, Any]] = {
    'known-pr259-narrow-viewport-planner-overflow': {
        'key': 'known-pr259-narrow-viewport-planner-overflow',
        'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
        'owner': 'PR #259',
        'environmentReady': True,
        'productAcceptanceReady': False,
        'description': 'Known PR #259 narrow-viewport planner overflow remains a product observation and not an environment readiness blocker.',
    },
}


def evaluate_product_observations(summary: Mapping[str, Any]) -> dict[str, Any]:
    observations = summary.get('productObservations') or []
    known_map = {
        key: {
            **value,
            'observedInRun': False,
        }
        for key, value in KNOWN_PRODUCT_OBSERVATIONS.items()
    }
    unexpected = []
    for observation in observations:
        if (
            observation.get('key') in KNOWN_PRODUCT_OBSERVATIONS
            and observation.get('classification') == 'PRODUCT_NARROW_VIEWPORT_OVERFLOW'
            and observation.get('owner') == 'PR #259'
        ):
            key = str(observation['key'])
            known_map[key] = {
                **known_map[key],
                **observation,
                'observedInRun': True,
            }
        else:
            unexpected.append(observation)

    known = list(known_map.values())
    if unexpected:
        return {
            'status': 'failed',
            'duration_ms': 0,
            'summary': 'Unexpected product observations were captured during verification.',
            'failure_code': 'UNEXPECTED_PRODUCT_OBSERVATION',
            'safe_diagnostics': {
                'known_product_observations': known,
                'unexpected_product_observations': unexpected,
            },
        }
    return {
        'status': 'passed',
        'duration_ms': 0,
        'summary': 'Known narrow-viewport planner overflow remained recorded as a PR #259 product observation without blocking environment readiness.',
        'failure_code': None,
        'safe_diagnostics': {
            'known_product_observations': known,
            'unexpected_product_observations': [],
        },
    }
