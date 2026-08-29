"""Unit tests for the V3 journal semantic identity contract (V3.0).

Covers edfinder_api.journal.identity (event_identity, canonical_key,
bio_data_sha256) plus the event_contract strip behaviour the identity
contract depends on. The V3.0 event identity table in the implementation
plan is the single source of truth for these cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest

from edfinder_api.journal.event_contract import strip_payload
from edfinder_api.journal.identity import bio_data_sha256, canonical_key, event_identity

# A real source-record hash is a 32-byte SHA-256; its hex form is 64 chars
# (the backend fix wave restored the fixture to the production shape — a
# 64-byte fixture would assert a 128-char hex key that can never occur:
# store._hash_bytes and the DB CHECK both enforce 32 bytes).
SRC = bytes.fromhex('ab' * 32)


def test_codexentry_repeat_dedupes_by_entry_id():
    base = {'SystemAddress': 12345, 'BodyID': 6, 'EntryID': 'E01'}
    a = event_identity('CodexEntry', {**base, 'event_ts': '2026-01-01T00:00:00Z'}, SRC)
    b = event_identity('CodexEntry', {**base, 'event_ts': '2026-02-02T00:00:00Z'}, SRC)
    assert a == b == {'SystemAddress': '12345', 'BodyID': '6', 'EntryID': 'E01'}


def test_scanorganic_body_renamed_and_stages_distinct():
    key = event_identity('ScanOrganic',
        {'SystemAddress': 10, 'Body': 3, 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
         'Variant': 'V1', 'ScanType': 'Log'}, SRC)
    assert key['BodyID'] == '3' and 'Body' not in key and key['ScanType'] == 'Log'
    sample = event_identity('ScanOrganic',
        {'SystemAddress': 10, 'Body': 3, 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
         'Variant': 'V1', 'ScanType': 'Sample'}, SRC)
    assert sample != key


def test_scanorganic_pre_u15_without_variant_is_distinct_from_u15():
    pre_u15 = event_identity('ScanOrganic',
        {'SystemAddress': 10, 'Body': 3, 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
         'ScanType': 'Log'}, SRC)
    u15 = event_identity('ScanOrganic',
        {'SystemAddress': 10, 'Body': 3, 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
         'Variant': 'V1', 'ScanType': 'Log'}, SRC)
    assert pre_u15 != u15
    assert 'Variant' not in pre_u15 and 'Variant' in u15


def test_fsdjump_timestamp_is_part_of_travel_chronology_key():
    # (signature: event_identity(event_type, payload, src, *, event_timestamp)
    #  — travel events read event_timestamp from the caller via an optional
    #  kwarg; distinctness is the travel-chronology exception)
    a = event_identity('FSDJump', {'SystemAddress': 7}, SRC, event_timestamp='2026-01-01T00:00:00Z')
    b = event_identity('FSDJump', {'SystemAddress': 7}, SRC, event_timestamp='2026-02-02T00:00:00Z')
    assert a != b
    assert a == {'SystemAddress': '7', 'EventTimestamp': '2026-01-01T00:00:00Z'}
    assert b == {'SystemAddress': '7', 'EventTimestamp': '2026-02-02T00:00:00Z'}


def test_fsdjump_and_carrierjump_require_event_timestamp():
    with pytest.raises(ValueError):
        event_identity('FSDJump', {'SystemAddress': 7}, SRC)
    with pytest.raises(ValueError):
        event_identity('CarrierJump', {'SystemAddress': 7}, SRC)
    with pytest.raises(ValueError):
        event_identity('FSDJump', {}, SRC, event_timestamp='2026-01-01T00:00:00Z')


def test_carrierjump_timestamp_chronology_distinct():
    a = event_identity('CarrierJump', {'SystemAddress': 42}, SRC, event_timestamp='2026-01-01T00:00:00Z')
    b = event_identity('CarrierJump', {'SystemAddress': 42}, SRC, event_timestamp='2026-01-02T00:00:00Z')
    assert a != b
    assert a['SystemAddress'] == '42' and 'EventTimestamp' in a


def test_loadgame_falls_back_to_content_address():
    a = event_identity('LoadGame', {'Commander': 'X', 'FID': 'F1'}, SRC)
    assert a == {'source_record_hash': 'ab' * 32}


def test_content_addressed_events_use_source_record_hash():
    for event_type in (
        'Fileheader', 'Commander', 'Died', 'Resurrect',
        'SellExplorationData', 'MultiSellExplorationData',
        'FSDTarget', 'NavRoute', 'NavRouteClear',
    ):
        key = event_identity(event_type, {'anything': 1}, SRC)
        assert key == {'source_record_hash': 'ab' * 32}, event_type


def test_body_events_without_lat_long_are_equal():
    base = {'SystemAddress': 99, 'BodyID': 4}
    a = event_identity('Touchdown', dict(base), SRC)
    b = event_identity('Touchdown', dict(base), SRC)
    assert a == b == {'SystemAddress': '99', 'BodyID': '4'}
    with_ll = event_identity('Touchdown', {**base, 'Latitude': 1.5, 'Longitude': -2.5}, SRC)
    assert with_ll != a
    assert with_ll['Latitude'] == '1.5' and with_ll['Longitude'] == '-2.5'


def test_latitude_longitude_rounded_to_4_decimals():
    key = event_identity('CodexEntry',
        {'SystemAddress': 1, 'EntryID': 'E2', 'Latitude': 12.34567, 'Longitude': -45.67891}, SRC)
    assert key['Latitude'] == '12.3457' and key['Longitude'] == '-45.6789'


def test_screenshot_filename_disambiguates():
    base = {'SystemAddress': 5, 'BodyID': 1}
    a = event_identity('Screenshot', {**base, 'Filename': 'ED_1.png'}, SRC)
    b = event_identity('Screenshot', {**base, 'Filename': 'ED_2.png'}, SRC)
    assert a != b
    assert a['Filename'] == 'ED_1.png' and b['Filename'] == 'ED_2.png'


def test_docked_collapses_per_station():
    a = event_identity('Docked', {'SystemAddress': 8, 'StationName': 'Marshburn Gateway'}, SRC)
    b = event_identity('Docked', {'SystemAddress': 8, 'StationName': 'Marshburn Gateway'}, SRC)
    other = event_identity('Docked', {'SystemAddress': 8, 'StationName': 'Other Port'}, SRC)
    assert a == b == {'SystemAddress': '8', 'StationName': 'Marshburn Gateway'}
    assert other != a


def test_fssdiscoveryscan_repeated_honks_collapse():
    a = event_identity('FSSDiscoveryScan', {'SystemAddress': 3}, SRC)
    b = event_identity('FSSDiscoveryScan', {'SystemAddress': 3}, SRC)
    assert a == b == {'SystemAddress': '3'}


def test_sellorganicdata_key_uses_biodata_sha():
    bio = [{'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;', 'Variant': 'V1'}]
    a = event_identity('SellOrganicData', {'MarketID': 128666824, 'BioData': bio}, SRC)
    b = event_identity('SellOrganicData', {'MarketID': 128666824, 'BioData': bio}, SRC)
    assert a == b
    assert a['MarketID'] == '128666824'
    assert len(a['BioDataSha256']) == 64
    different = event_identity('SellOrganicData',
        {'MarketID': 128666824, 'BioData': [{**bio[0], 'Species': '$Species_Other;'}]}, SRC)
    assert different != a


def test_canonical_ordering_is_irrelevant_to_the_key():
    payload_a = {'SystemAddress': 12345, 'BodyID': 6, 'EntryID': 'E01'}
    payload_b = {'EntryID': 'E01', 'BodyID': 6, 'SystemAddress': 12345}
    key_a = event_identity('CodexEntry', payload_a, SRC)
    key_b = event_identity('CodexEntry', payload_b, SRC)
    assert json.dumps(key_a, sort_keys=True) == json.dumps(key_b, sort_keys=True)
    assert key_a == key_b


def test_canonical_key_sorts_nested_keys_and_stringifies_ints():
    result = canonical_key({'b': 1, 'a': {'d': 2, 'c': [1, {'f': 3, 'e': 4}]}})
    assert result == {'a': {'c': ['1', {'e': '4', 'f': '3'}], 'd': '2'}, 'b': '1'}
    assert list(result.keys()) == ['a', 'b']
    assert list(result['a'].keys()) == ['c', 'd']
    assert list(result['a']['c'][1].keys()) == ['e', 'f']


def test_canonical_key_keeps_bool_distinct_from_int():
    assert canonical_key({'x': True}) == {'x': True}
    assert canonical_key({'x': 1}) == {'x': '1'}
    assert canonical_key({'x': True}) != canonical_key({'x': 1})


def test_bio_data_sha256_is_deterministic_and_order_insensitive():
    bio = [
        {'Genus': '$Genus_A;', 'Species': '$Species_B;', 'Variant': 'V1'},
        {'Genus': '$Genus_C;', 'Species': '$Species_D;'},
    ]
    shuffled = [bio[1], bio[0]]
    assert bio_data_sha256(bio) == bio_data_sha256(shuffled)
    assert len(bio_data_sha256(bio)) == 32
    assert bio_data_sha256(bio) != bio_data_sha256([bio[0]])


def test_server_strips_non_allowlisted_fields():
    stripped, removed = strip_payload('Scan', {'BodyName': 'A', 'SystemAddress': 1, 'Secret': 42})
    assert removed == 1 and 'Secret' not in stripped and stripped['BodyName'] == 'A'


def test_identity_ignores_non_key_payload_fields():
    key = event_identity('CodexEntry',
        {'SystemAddress': 1, 'BodyID': 2, 'EntryID': 'E9', 'Name_Localised': 'Anything'}, SRC)
    assert key == {'SystemAddress': '1', 'BodyID': '2', 'EntryID': 'E9'}


def test_uint64_rejects_fractional_floats_fail_closed():
    # int(1.5) would truncate to '1' and collide with the real uint64 1 —
    # fail closed instead (backend fix wave).
    with pytest.raises(ValueError, match='integral uint64'):
        event_identity('Scan', {'SystemAddress': 1.5, 'BodyID': 1}, SRC)
    with pytest.raises(ValueError, match='integral uint64'):
        event_identity('ScanOrganic',
            {'SystemAddress': 10, 'Body': 3.7, 'Genus': '$Genus_Foo;', 'ScanType': 'Log'}, SRC)


def test_uint64_accepts_integral_floats():
    key = event_identity('Scan', {'SystemAddress': 1.0, 'BodyID': 2.0}, SRC)
    assert key == {'SystemAddress': '1', 'BodyID': '2'}


def test_entry_id_is_used_as_is_without_trim():
    # Contract: "EntryID -> string as-is" — surrounding whitespace is NOT
    # trimmed (deviates from the generic trimmed-string branch on purpose).
    key = event_identity('CodexEntry',
        {'SystemAddress': 1, 'EntryID': '  E01  '}, SRC)
    assert key['EntryID'] == '  E01  '


def test_entry_id_numeric_is_stringified_as_is():
    # Real journal EntryIDs are numeric; str() conversion, never trim.
    key = event_identity('CodexEntry', {'SystemAddress': 1, 'EntryID': 2100301}, SRC)
    assert key['EntryID'] == '2100301'
