from __future__ import annotations

from typing import Any, Mapping


KNOWN_PRODUCT_OBSERVATIONS: dict[str, dict[str, Any]] = {
    'planner_constrained_layout_compromise_diagnostic': {
        'key': 'planner_constrained_layout_compromise_diagnostic',
        'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
        'owner': 'PR #259',
        'environmentReady': True,
        'productAcceptanceReady': True,
        'description': 'Constrained 1024x768 planner layout compromises are recorded as diagnostics only when navigation remains safe.',
    },
    'planner_mobile_resilience_overflow_diagnostic': {
        'key': 'planner_mobile_resilience_overflow_diagnostic',
        'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
        'owner': 'PR #259',
        'environmentReady': True,
        'productAcceptanceReady': True,
        'description': 'Phone-width planner overflow is a bounded resilience diagnostic and does not define desktop planner acceptance.',
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
        key = str(observation.get('key') or '')
        known_definition = KNOWN_PRODUCT_OBSERVATIONS.get(key)
        if (
            known_definition is not None
            and observation.get('classification') == known_definition['classification']
            and observation.get('owner') == known_definition['owner']
        ):
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
        'summary': 'Known viewport diagnostics remained bounded and did not block environment readiness.',
        'failure_code': None,
        'safe_diagnostics': {
            'known_product_observations': known,
            'unexpected_product_observations': [],
        },
    }
