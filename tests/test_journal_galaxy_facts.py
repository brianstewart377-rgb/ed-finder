from datetime import datetime, timezone

import pytest

from shared_contracts.journal_galaxy_facts import normalize_scan, reconcile_fields

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def scan(**payload):
    return {'event_type': 'Scan', 'event_timestamp': NOW,
            'event_payload': {'GameVersion': '4.1.0.0', 'SystemAddress': '9007199254740993',
                              'BodyID': '0', **payload}}


def test_units_and_lossless_identity_are_preserved_without_private_fields():
    result = normalize_scan(scan(Radius=1000, SurfaceGravity=9.80665, SurfacePressure=101325,
                                 OrbitalPeriod=86400, RotationPeriod=-86400, Landable=False,
                                 Commander='Private name', FID='F123', Credits=999), now=NOW)
    assert result['system_id64'] == '9007199254740993'
    assert result['frontier_body_id'] == '0'
    assert result['fields'] == {'radius_km': 1, 'surface_gravity_g': 1, 'surface_pressure_atm': 1,
                                'orbital_period_days': 1, 'rotation_period_days': -1, 'is_landable': False}
    assert 'Private name' not in str(result) and 'F123' not in str(result) and 'Credits' not in str(result)


@pytest.mark.parametrize('payload', [
    {'Radius': True}, {'Radius': float('nan')}, {'SurfaceGravity': -1}, {'Eccentricity': 1.1},
    {'Landable': 'yes'}, {'BodyID': True, 'Radius': 1}, {'SystemAddress': 123.0, 'Radius': 1},
    {'GameVersion': '3.8.0.0', 'Radius': 1}, {'GameVersion': None, 'Radius': 1},
])
def test_invalid_or_legacy_facts_are_held(payload):
    with pytest.raises(ValueError):
        normalize_scan(scan(**payload), now=NOW)


def test_future_observation_is_not_treated_as_current():
    event = scan(Radius=1000)
    event['event_timestamp'] = datetime(2027, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='future'):
        normalize_scan(event, now=NOW)


def test_old_upload_fills_missing_stable_facts_but_preserves_newer_values():
    current = {'radius_km': 2000, 'surface_gravity_g': None, 'source_updated_at': NOW}
    observation = {'observed_at': '2020-01-01T00:00:00+00:00',
                   'fields': {'radius_km': 1000, 'surface_gravity_g': 1}}
    changes, decisions = reconcile_fields(current, observation, {})
    assert changes == {'surface_gravity_g': 1}
    assert decisions['radius_km'] == 'PRESERVE_CONFLICT'


def test_field_provenance_prevents_a_later_processed_older_journal_overwrite():
    current = {'radius_km': 2000, 'source_updated_at': datetime(2020, 1, 1, tzinfo=timezone.utc)}
    observation = {'observed_at': '2025-01-01T00:00:00+00:00', 'fields': {'radius_km': 1000}}
    assert reconcile_fields(current, observation, {'radius_km': NOW})[0] == {}
    assert reconcile_fields(current, observation, {})[0] == {'radius_km': 1000}
    assert reconcile_fields({**current, 'source_updated_at': None}, observation, {})[0] == {}


def test_arbitrary_canonical_columns_are_rejected():
    with pytest.raises(ValueError, match='unsupported_canonical_field'):
        reconcile_fields({}, {'observed_at': NOW.isoformat(), 'fields': {'source_run_id': 'forged'}}, {})
