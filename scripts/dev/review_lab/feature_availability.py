from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contract import ReviewLabError

FeatureAvailabilityState = Literal['supported', 'intentionally_unavailable', 'excluded']

MANIFEST_PATH = Path(__file__).resolve().parents[3] / 'frontend-v2' / 'src' / 'lib' / 'hostedReviewAvailability.manifest.json'
ALLOWED_STATES = {'supported', 'intentionally_unavailable', 'excluded'}


@dataclass(frozen=True)
class ReviewFeatureAvailability:
    key: str
    label: str
    state: FeatureAvailabilityState
    rationale: str
    routes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            'key': self.key,
            'label': self.label,
            'state': self.state,
            'rationale': self.rationale,
            'routes': list(self.routes),
        }


def _load_manifest(path: Path = MANIFEST_PATH) -> tuple[ReviewFeatureAvailability, ...]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except OSError as exc:
        raise ReviewLabError(
            'Hosted-review feature availability manifest could not be read.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'path': str(path), 'reason': type(exc).__name__},
        ) from exc
    features = payload.get('features') if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise ReviewLabError(
            'Hosted-review feature availability manifest must expose a features array.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'path': str(path)},
        )
    parsed: list[ReviewFeatureAvailability] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ReviewLabError(
                'Hosted-review feature availability entries must be objects.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'path': str(path), 'index': index},
            )
        key = feature.get('key')
        label = feature.get('label')
        state = feature.get('state')
        rationale = feature.get('rationale')
        routes = feature.get('routes', [])
        if not all(isinstance(value, str) and value for value in (key, label, state, rationale)):
            raise ReviewLabError(
                'Hosted-review feature availability entries require key, label, state, and rationale.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'path': str(path), 'index': index},
            )
        if state not in ALLOWED_STATES:
            raise ReviewLabError(
                'Hosted-review feature availability state is invalid.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'path': str(path), 'feature': key, 'state': state},
            )
        if not isinstance(routes, list) or not all(isinstance(route, str) and route.startswith('#') for route in routes):
            raise ReviewLabError(
                'Hosted-review feature availability routes must be hash route strings.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'path': str(path), 'feature': key},
            )
        parsed.append(ReviewFeatureAvailability(
            key=key,
            label=label,
            state=state,  # type: ignore[arg-type]
            rationale=rationale,
            routes=tuple(routes),
        ))
    return tuple(parsed)


REVIEW_FEATURE_AVAILABILITY: tuple[ReviewFeatureAvailability, ...] = _load_manifest()


def feature_availability_payload() -> list[dict[str, object]]:
    return [feature.to_dict() for feature in REVIEW_FEATURE_AVAILABILITY]


def validate_feature_availability() -> None:
    seen: set[str] = set()
    duplicate_keys: set[str] = set()
    route_owners: dict[str, str] = {}
    duplicate_routes: dict[str, list[str]] = {}
    for feature in REVIEW_FEATURE_AVAILABILITY:
        if feature.key in seen:
            duplicate_keys.add(feature.key)
        seen.add(feature.key)
        if not feature.rationale.strip():
            raise ReviewLabError(
                'Hosted-review feature availability rows must explain their rationale.',
                failure_code='STATIC_CONTAINMENT_FAILED',
                safe_diagnostics={'feature': feature.key},
            )
        for route in feature.routes:
            if route in route_owners:
                duplicate_routes.setdefault(route, [route_owners[route]]).append(feature.key)
            route_owners[route] = feature.key
    if duplicate_keys:
        raise ReviewLabError(
            'Hosted-review feature availability keys must be unique.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'duplicate_keys': sorted(duplicate_keys)},
        )
    if duplicate_routes:
        raise ReviewLabError(
            'Hosted-review route availability must have a single owning feature.',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'duplicate_routes': duplicate_routes},
        )
