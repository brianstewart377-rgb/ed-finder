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
from exploration.store import decode_fact_cursor  # noqa: E402

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
        'CarrierJump', 'FSDJump', 'Location', 'Scan', 'FSSDiscoveryScan',
        'FSSAllBodiesFound',
        'SAASignalsFound', 'FSSBodySignals', 'CodexEntry', 'SAAScanComplete',
        'ScanOrganic', 'SellOrganicData', 'SellExplorationData',
        'MultiSellExplorationData', 'RedeemVoucher',
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


def test_observation_rejects_payload_over_size_bound():
    oversized_payload = {'blob': 'x' * 40_000}
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(payload=oversized_payload))


def test_observation_accepts_payload_under_size_bound():
    normal_payload = {'BodyName': 'Test System 1', 'PlanetClass': 'Rocky body'}
    observation = ExplorationObservationInput.model_validate(
        _valid_observation(payload=normal_payload)
    )
    assert observation.payload == normal_payload


def test_observation_rejects_system_id64_above_bigint_max():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(system_id64=9_223_372_036_854_775_808)
        )


def test_observation_rejects_negative_body_id():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(body_id=-1))


def test_observation_rejects_non_finite_floats_in_payload():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(payload={'value': float('nan')}))
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(payload={'value': float('inf')}))


def test_observation_accepts_finite_floats_in_payload():
    observation = ExplorationObservationInput.model_validate(
        _valid_observation(payload={'value': 1.5})
    )
    assert observation.payload == {'value': 1.5}


def test_observation_rejects_boundary_timestamp_that_overflows_on_utc_conversion():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(observed_at='0001-01-01T00:00:00+14:00')
        )


def test_observation_rejects_nul_character_in_observation_key():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(observation_key='a' * 15 + '\x00')
        )


def test_observation_rejects_nul_character_in_system_name():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(system_name='Sol\x00'))


def test_observation_rejects_nul_character_in_body_name():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(body_name='Sol\x00 1'))


def test_observation_rejects_nul_character_nested_in_payload():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(payload={'notes': 'a\x00b'})
        )
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(payload={'signals': [{'name': 'a\x00b'}]})
        )
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(
            _valid_observation(payload={'a\x00b': 'value'})
        )


def test_request_rejects_non_visit_event_types_in_edsm_batches():
    with pytest.raises(ValidationError):
        ExplorationImportRequest.model_validate({
            'sync_key': 'a' * 32,
            'source': 'edsm',
            'observations': [_valid_observation(event_type='Scan')],
        })


def test_request_accepts_visit_event_types_in_edsm_batches():
    request = ExplorationImportRequest.model_validate({
        'sync_key': 'a' * 32,
        'source': 'edsm',
        'observations': [_valid_observation(event_type='FSDJump')],
    })
    assert request.source == 'edsm'


def test_request_accepts_non_visit_event_types_in_journal_batches():
    request = ExplorationImportRequest.model_validate({
        'sync_key': 'a' * 32,
        'source': 'journal',
        'observations': [_valid_observation(event_type='Scan')],
    })
    assert request.source == 'journal'


def test_malformed_fact_cursor_is_rejected_cleanly():
    with pytest.raises(ValueError, match='valid exploration facts cursor'):
        decode_fact_cursor('%%%not-base64%%%')
