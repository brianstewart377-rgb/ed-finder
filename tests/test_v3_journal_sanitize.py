"""Unit tests for V3 journal sanitization (A1-A14 allowlist, Task 4).

Covers edfinder_api.journal.sanitize (minimize_time, sanitize_observation).
The A1-A14 sanitization table in the implementation plan is the single
source of truth: deterministic observation_id, week-bucketed time, verbatim
tokens, and fail-closed hard exclusions (lat/long, credits, MarketID,
commander identity).
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest

from edfinder_api.journal.sanitize import (
    OBSERVATION_NAMESPACE_UUID,
    minimize_time,
    sanitize_observation,
)

SRC = bytes.fromhex('ab' * 32)
SRC_HEX = 'ab' * 32  # 32 bytes -> 64 hex chars
TS = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)

# Event types for which sanitize_observation MUST return None (never exported).
EXCLUDED_EVENT_TYPES = (
    'FSDJump', 'CarrierJump', 'Location', 'Touchdown', 'Liftoff', 'ApproachBody',
    'LeaveBody', 'Disembark', 'Embark', 'Screenshot', 'Docked', 'Fileheader',
    'LoadGame', 'Commander', 'Died', 'Resurrect', 'SellExplorationData',
    'MultiSellExplorationData', 'FSDTarget', 'NavRoute', 'NavRouteClear',
)


def _canonical_json(key: dict) -> str:
    """Deterministic JSON serialization of a canonical event key (mirrors the
    contract: sorted keys, compact separators, ascii-escaped)."""
    return json.dumps(key, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _row(
    event_type: str,
    *,
    key: dict | None = None,
    payload: dict | None = None,
    ts: datetime = TS,
    src: bytes = SRC,
) -> dict:
    return {
        'event_type': event_type,
        'event_key': key if key is not None else {'SystemAddress': 12345},
        # Default payload carries a system name: the CRE contract requires
        # system_name on every non-sale exported observation.
        'event_payload': payload if payload is not None else {'StarSystem': 'X'},
        'event_timestamp': ts,
        'source_record_hash': src,
    }


def _assert_no_excluded_keys(obs: dict) -> None:
    """Fail-closed assertion: none of the hard-excluded field names may appear
    anywhere in the sanitized observation (top-level or nested)."""
    excluded_names = {
        'Latitude', 'Longitude', 'lat', 'lon', 'Value', 'Bonus', 'TotalValue',
        'MarketID', 'Commander', 'FID', 'Squadron', 'credits', 'CreditBalance',
    }
    stack = [obs]
    while stack:
        item = stack.pop()
        if not isinstance(item, dict):
            continue
        for k, v in item.items():
            assert k not in excluded_names, f'excluded field leaked: {k}'
            stack.append(v)


# ---------------------------------------------------------------------------
# minimize_time — ISO-8601 week buckets
# ---------------------------------------------------------------------------

def test_minimize_time_week_bucket_2026_08_28():
    # 2026-08-28 is a Friday; its ISO calendar week is 2026-W35 (verified).
    assert minimize_time(datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)) == '2026-W35'


def test_minimize_time_naive_datetime_assumed_utc():
    assert minimize_time(datetime(2026, 8, 28, 0, 0, 0)) == '2026-W35'


def test_minimize_time_never_emits_exact_timestamp():
    out = minimize_time(TS)
    assert isinstance(out, str)
    # No date (YYYY-MM-DD) and no clock time may appear — week bucket only.
    assert '2026-08-28' not in out and 'T' not in out
    assert out == '2026-W35'


def test_minimize_time_week_boundary_year_edge():
    # 2027-01-01 is a Friday and belongs to ISO week 53 of 2026 (standard
    # ISO calendar edge — the ISO year differs from the calendar year).
    assert minimize_time(datetime(2027, 1, 1, 6, 0, 0, tzinfo=timezone.utc)) == '2026-W53'


# ---------------------------------------------------------------------------
# sanitize_observation — inclusions (A1-A14)
# ---------------------------------------------------------------------------

def test_scan_full_observation_allowlist():
    payload = {
        'StarSystem': 'Sol',
        'BodyName': 'Earth',
        'BodyClass': 'PlanetClass (rocky body)',
        'Atmosphere': 'thin carbon dioxide atmosphere',
        'Volcanism': 'major silicate vapour geysers volcanism',
        'MassEM': 0.99,
        'Radius': 6371000.0,
        'SurfaceGravity': 9.8,
        'SurfaceTemperature': 288.0,
        'Landable': True,
        'TerraformState': 'Terraformable',
        'GameVersion': 'U15',
        'GameBuild': '12345',
    }
    key = {'SystemAddress': 12345, 'BodyID': 3}
    obs = sanitize_observation(_row('Scan', key=key, payload=payload))
    assert obs is not None
    assert obs['observation_type'] == 'Scan'
    assert obs['system_id64'] == '12345'
    assert obs['system_name'] == 'Sol'
    assert obs['body_id'] == '3'
    assert obs['body_name'] == 'Earth'
    assert obs['observed_week'] == '2026-W35'
    assert obs['game_version'] == 'U15'
    assert obs['game_build'] == '12345'
    assert obs['source_event_sha256'] == SRC_HEX
    assert obs['evidence_quality'] == 'OBSERVED_PERSONAL'
    env = obs['body_environment']
    assert env['body_class'] == 'PlanetClass (rocky body)'
    assert env['atmosphere'] == 'thin carbon dioxide atmosphere'
    assert env['volcanism'] == 'major silicate vapour geysers volcanism'
    assert env['mass_em'] == 0.99
    assert env['radius_km'] == 6371000.0
    assert env['surface_gravity_g'] == 9.8
    assert env['surface_temperature_k'] == 288.0
    assert env['landable'] is True
    assert env['terraform_state'] == 'Terraformable'
    _assert_no_excluded_keys(obs)


def test_observation_id_is_deterministic_uuid5():
    key = {'SystemAddress': 12345, 'BodyID': 3}
    expected = str(uuid.uuid5(OBSERVATION_NAMESPACE_UUID, f'Scan:{_canonical_json(key)}'))
    a = sanitize_observation(_row('Scan', key=key))
    b = sanitize_observation(_row('Scan', key=key))
    assert a is not None and b is not None
    assert a['observation_id'] == b['observation_id'] == expected


def test_observation_id_differs_across_event_types():
    key = {'SystemAddress': 12345, 'BodyID': 3}
    a = sanitize_observation(_row('Scan', key=key))
    b = sanitize_observation(_row('ScanOrganic', key={**key, 'ScanType': 'Log'}))
    assert a is not None and b is not None
    assert a['observation_id'] != b['observation_id']


def test_scanorganic_tokens_verbatim_with_trailing_semicolons():
    payload = {
        'StarSystem': 'Foo',
        'Body': 3,
        'Genus': '$Genus_Foo;',
        'Species': '$Species_Bar;',
        'Variant': '$Variant_Baz;',
        'ScanType': 'Log',
    }
    key = {'SystemAddress': 10, 'BodyID': '3'}
    obs = sanitize_observation(_row('ScanOrganic', key=key, payload=payload))
    assert obs is not None
    # Tokens pass through verbatim — trailing ';' is part of the canonical token.
    assert obs['genus'] == '$Genus_Foo;'
    assert obs['species'] == '$Species_Bar;'
    assert obs['variant'] == '$Variant_Baz;'
    # body_id is the JOURNAL body id from the event key — never ed-finder bodies.id.
    assert obs['body_id'] == '3'
    assert obs['body_name'] == '3'  # payload Body is numeric; string form preserved


def test_codexentry_region_and_entry_id_without_coordinates():
    payload = {'StarSystem': 'X', 'Region': 'Alpha Quadrant', 'Body': 'ABC 1'}
    key = {
        'SystemAddress': 1,
        'BodyID': 2,
        'EntryID': 'E01',
        'Latitude': 12.345,
        'Longitude': -45.678,
    }
    obs = sanitize_observation(_row('CodexEntry', key=key, payload=payload))
    assert obs is not None
    assert obs['codex_region'] == 'Alpha Quadrant'
    assert obs['codex_entry_id'] == 'E01'
    assert obs['body_name'] == 'ABC 1'
    # Hard exclusion: codex lat/long must NOT appear in exports even though
    # they are part of the identity key.
    assert 'Latitude' not in obs and 'Longitude' not in obs
    _assert_no_excluded_keys(obs)


def test_fssbodysignals_signals_and_genuses():
    payload = {
        'StarSystem': 'X',
        'PlanetClass': 'PlanetClass (water world)',
        'Signals': [{'Type': '$SAA_SignalType_Biological;', 'Count': 3}],
        'Genuses': [{'Genus': '$Genus_Stratum;', 'Genus_Localised': 'Stratum'}],
    }
    obs = sanitize_observation(_row('FSSBodySignals', payload=payload))
    assert obs is not None
    assert obs['signals'] == [{'Type': '$SAA_SignalType_Biological;', 'Count': 3}]
    # Genuses projected to canonical genus tokens; localised names excluded.
    assert obs['genuses'] == ['$Genus_Stratum;']
    assert obs['body_environment']['body_class'] == 'PlanetClass (water world)'
    _assert_no_excluded_keys(obs)


def test_saasignalsfound_genuses_tokens_only():
    payload = {
        'StarSystem': 'X',
        'Genuses': [
            {'Genus': '$Genus_Tussock;', 'Genus_Localised': 'Tussock'},
            {'Genus': '$Genus_Fungus;', 'Genus_Localised': 'Fungus'},
        ],
    }
    obs = sanitize_observation(_row('SAASignalsFound', payload=payload))
    assert obs is not None
    assert obs['genuses'] == ['$Genus_Tussock;', '$Genus_Fungus;']
    assert 'Genus_Localised' not in obs
    _assert_no_excluded_keys(obs)


def test_sellorganicdata_sale_list_without_values_or_marketid():
    payload = {
        'MarketID': 3223000000,
        'BioData': [
            {
                'Name': '$Codex_Ent_Bacterial_01_Name;',
                'Genus': '$Genus_Bacterial;',
                'Species': '$Species_Bacterial_01;',
                'Variant': '$Variant_Bacterial_01;',
                'Value': 1000,
                'Bonus': 50,
                'TotalValue': 1050,
                'Count': 3,
            },
        ],
    }
    key = {'MarketID': '3223000000', 'BioDataSha256': 'aa' * 32}
    obs = sanitize_observation(_row('SellOrganicData', key=key, payload=payload))
    assert obs is not None
    assert obs['sale'] == [{
        'genus': '$Genus_Bacterial;',
        'species': '$Species_Bacterial_01;',
        'variant': '$Variant_Bacterial_01;',
        'count': 3,
    }]
    # Hard exclusions for sale events: no MarketID, no Value/Bonus/TotalValue,
    # no localised Name.
    assert 'MarketID' not in obs
    assert 'Value' not in obs and 'Bonus' not in obs and 'TotalValue' not in obs
    _assert_no_excluded_keys(obs)


def test_fssdiscoveryscan_system_level_observation():
    payload = {'SystemName': 'X', 'BodyCount': 7}
    obs = sanitize_observation(_row('FSSDiscoveryScan', payload=payload))
    assert obs is not None
    assert obs['system_id64'] == '12345'
    assert obs['system_name'] == 'X'
    # System-level observation: no body fields; BodyCount is not allowlisted.
    assert 'body_id' not in obs and 'body_name' not in obs
    assert 'BodyCount' not in obs
    _assert_no_excluded_keys(obs)


def test_fssallbodiesfound_system_level_observation():
    payload = {'SystemName': 'Y'}
    obs = sanitize_observation(_row('FSSAllBodiesFound', payload=payload))
    assert obs is not None
    assert obs['observation_type'] == 'FSSAllBodiesFound'
    assert obs['system_name'] == 'Y'
    assert 'body_id' not in obs
    _assert_no_excluded_keys(obs)


def test_event_key_and_payload_accepted_as_json_strings():
    # asyncpg returns jsonb columns as text; build_export feeds str forms.
    row = {
        'event_type': 'Scan',
        'event_key': json.dumps({'SystemAddress': 12345, 'BodyID': 3}),
        'event_payload': json.dumps({'StarSystem': 'Sol', 'BodyName': 'Earth'}),
        'event_timestamp': TS,
        'source_record_hash': SRC,
    }
    obs = sanitize_observation(row)
    assert obs is not None
    assert obs['system_id64'] == '12345'
    assert obs['system_name'] == 'Sol'
    assert obs['body_name'] == 'Earth'


def test_game_version_and_build_absent_when_missing():
    obs = sanitize_observation(_row('Scan', payload={'StarSystem': 'Sol'}))
    assert obs is not None
    assert 'game_version' not in obs and 'game_build' not in obs


# ---------------------------------------------------------------------------
# sanitize_observation — exclusions (fail-closed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('event_type', EXCLUDED_EVENT_TYPES)
def test_excluded_event_types_return_none(event_type: str):
    assert sanitize_observation(_row(event_type, payload={'StarSystem': 'X'})) is None


def test_travel_event_payload_never_exported():
    # Travel events carry lat/long and station names — entire rows are excluded.
    for event_type in ('Location', 'Touchdown', 'Liftoff', 'ApproachBody', 'LeaveBody', 'Docked'):
        assert sanitize_observation(_row(event_type)) is None


def test_credit_fields_never_leak_from_included_event_payload():
    payload = {
        'StarSystem': 'Sol',
        'BodyName': 'Earth',
        'Value': 999,
        'Bonus': 1,
        'TotalValue': 1000,
        'MarketID': 5,
    }
    obs = sanitize_observation(_row('Scan', payload=payload))
    assert obs is not None
    assert 'Value' not in obs and 'Bonus' not in obs and 'TotalValue' not in obs
    assert 'MarketID' not in obs
    _assert_no_excluded_keys(obs)


def test_commander_identity_never_leaks():
    payload = {
        'StarSystem': 'Sol',
        'BodyName': 'Earth',
        'Commander': 'CMDR Foo',
        'FID': 'F123456',
    }
    obs = sanitize_observation(_row('Scan', payload=payload))
    assert obs is not None
    assert 'Commander' not in obs and 'FID' not in obs
    _assert_no_excluded_keys(obs)


def test_latitude_longitude_absent_even_when_payload_carries_them():
    payload = {'StarSystem': 'Sol', 'Latitude': 12.5, 'Longitude': -77.0}
    obs = sanitize_observation(_row('Scan', payload=payload))
    assert obs is not None
    assert 'Latitude' not in obs and 'Longitude' not in obs
    _assert_no_excluded_keys(obs)


def test_sale_nested_values_excluded():
    payload = {
        'MarketID': 1,
        'TotalValue': 12345,
        'BioData': [
            {'Genus': '$Genus_A;', 'Species': '$Species_B;', 'Value': 900, 'Count': 2},
        ],
    }
    obs = sanitize_observation(_row('SellOrganicData', key={'MarketID': '1', 'BioDataSha256': 'bb' * 32}, payload=payload))
    assert obs is not None
    assert obs['sale'] == [{'genus': '$Genus_A;', 'species': '$Species_B;', 'count': 2}]
    _assert_no_excluded_keys(obs)


# ---------------------------------------------------------------------------
# CRE consumer-schema directives (orchestrator, Task 6 schema review):
# 1) the observation JSON must contain NO null-valued keys anywhere;
# 2) system_id64 + system_name ALWAYS present for every exported type
#    EXCEPT SellOrganicData, which omits both;
# 3) the sale object is {genus, species, variant} + count only.
# ---------------------------------------------------------------------------

def _walk_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_values(v)
    else:
        yield obj


def test_observation_never_contains_null_values():
    # Every exported type with a maximal payload: no None anywhere.
    payloads = {
        'Scan': {'StarSystem': 'S', 'BodyName': 'B', 'BodyClass': 'C', 'Landable': True},
        'FSSBodySignals': {'StarSystem': 'S', 'Signals': [{'Type': '$SAA_SignalType_Biological;', 'Count': 2}]},
        'SAASignalsFound': {'StarSystem': 'S', 'Genuses': [{'Genus': '$Genus_A;', 'Genus_Localised': 'A'}]},
        'SAAScanComplete': {'StarSystem': 'S', 'BodyName': 'B'},
        'CodexEntry': {'StarSystem': 'S', 'Region': 'R'},
        'ScanOrganic': {'StarSystem': 'S', 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;'},
        'SellOrganicData': {'BioData': [{'Genus': '$Genus_A;', 'Species': '$Species_B;', 'Count': 1}]},
        'FSSDiscoveryScan': {'SystemName': 'S'},
        'FSSAllBodiesFound': {'SystemName': 'S'},
    }
    for event_type, payload in payloads.items():
        key = {'SystemAddress': 12345}
        if event_type in ('Scan', 'FSSBodySignals', 'SAASignalsFound', 'SAAScanComplete',
                          'ScanOrganic', 'CodexEntry'):
            key['BodyID'] = 7
        if event_type == 'CodexEntry':
            key['EntryID'] = 'E01'
        if event_type == 'SellOrganicData':
            key = {'MarketID': '1', 'BioDataSha256': 'cc' * 32}
        obs = sanitize_observation(_row(event_type, key=key, payload=payload))
        assert obs is not None, event_type
        assert list(_walk_values(obs)) and all(v is not None for v in _walk_values(obs)), event_type


def test_null_payload_values_omitted_not_emitted():
    # Explicit JSON nulls in the stored payload must be treated as absent.
    payload = {
        'StarSystem': 'Sol',
        'BodyName': None,
        'BodyClass': None,
        'Atmosphere': None,
        'GameVersion': None,
        'GameBuild': None,
        'Signals': [{'Type': '$SAA_SignalType_Biological;', 'Count': None}],
        'Genuses': [{'Genus': None, 'Genus_Localised': 'X'}, {'Genus': '$Genus_B;'}],
    }
    obs = sanitize_observation(_row('FSSBodySignals', payload=payload))
    assert obs is not None
    assert 'body_name' not in obs and 'game_version' not in obs and 'game_build' not in obs
    assert obs['signals'] == [{'Type': '$SAA_SignalType_Biological;'}]
    assert obs['genuses'] == ['$Genus_B;']
    assert all(v is not None for v in _walk_values(obs))


@pytest.mark.parametrize('event_type', [
    'Scan', 'FSSBodySignals', 'SAASignalsFound', 'SAAScanComplete',
    'CodexEntry', 'ScanOrganic', 'FSSDiscoveryScan', 'FSSAllBodiesFound',
])
def test_system_fields_present_for_all_non_sale_types(event_type: str):
    payload = {'StarSystem': 'X'} if event_type not in ('FSSDiscoveryScan', 'FSSAllBodiesFound') else {'SystemName': 'X'}
    obs = sanitize_observation(_row(event_type, payload=payload))
    assert obs is not None
    assert obs['system_id64'] == '12345'
    assert obs['system_name'] == 'X'


def test_sellorganicdata_omits_system_fields():
    payload = {'BioData': [{'Genus': '$Genus_A;', 'Species': '$Species_B;', 'Count': 1}]}
    key = {'MarketID': '1', 'BioDataSha256': 'dd' * 32}
    obs = sanitize_observation(_row('SellOrganicData', key=key, payload=payload))
    assert obs is not None
    assert 'system_id64' not in obs and 'system_name' not in obs
    assert obs['sale'] == [{'genus': '$Genus_A;', 'species': '$Species_B;', 'count': 1}]
    _assert_no_excluded_keys(obs)


def test_missing_system_name_raises_for_non_sale_type():
    with pytest.raises(ValueError, match='system_name always present'):
        sanitize_observation(_row('Scan', payload={'BodyName': 'Earth'}))


def test_missing_system_address_raises_for_non_sale_type():
    with pytest.raises(ValueError, match='system_id64 always present'):
        sanitize_observation(_row('Scan', key={'BodyID': 3}))
