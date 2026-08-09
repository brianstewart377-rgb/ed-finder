from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from exploration.api_models import (  # noqa: E402
    ALLOWED_EXPLORATION_EVENT_TYPES,
    ExplorationImportRequest,
    ExplorationObservationInput,
)

pytestmark = pytest.mark.unit


def _valid_observation(**overrides: object) -> dict[str, object]:
    base = {
        'observation_key': 'a' * 32,
        'event_type': 'Scan',
        'observed_at': '2026-08-08T09:00:00Z',
        'system_id64': 1000,
        'system_name': 'Test System',
        'body_id': 1,
        'body_name': 'Test System 1',
        'payload': {'BodyName': 'Test System 1'},
    }
    base.update(overrides)
    return base


def test_allowed_event_types_cover_all_six_facets():
    assert ALLOWED_EXPLORATION_EVENT_TYPES == {
        'FSDJump', 'Location', 'Scan', 'FSSDiscoveryScan',
        'SAASignalsFound', 'FSSBodySignals', 'CodexEntry', 'SAAScanComplete',
    }


def test_observation_rejects_event_type_outside_allowlist():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(event_type='ShipTargeted'))


def test_observation_accepts_naive_datetime_as_utc():
    observation = ExplorationObservationInput.model_validate(
        _valid_observation(observed_at='2026-08-08T09:00:00')
    )
    assert observation.observed_at.tzinfo is not None
    assert observation.observed_at.isoformat() == '2026-08-08T09:00:00+00:00'


def test_request_rejects_legacy_sync_key():
    with pytest.raises(ValidationError):
        ExplorationImportRequest.model_validate({
            'sync_key': 'legacy',
            'observations': [],
        })


def test_request_rejects_short_sync_key():
    with pytest.raises(ValidationError):
        ExplorationImportRequest.model_validate({
            'sync_key': 'tooshort',
            'observations': [],
        })


def test_request_accepts_valid_sync_key_and_defaults_source_to_journal():
    request = ExplorationImportRequest.model_validate({
        'sync_key': 'a' * 32,
        'observations': [_valid_observation()],
    })
    assert request.source == 'journal'
    assert len(request.observations) == 1


def test_observation_key_is_not_stripped_and_whitespace_only_is_rejected():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(observation_key=' ' * 16))
