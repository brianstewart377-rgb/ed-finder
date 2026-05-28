import os
import sys

import pytest

os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'api', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'importer', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'eddn', 'src'))

eddn_listener = pytest.importorskip('eddn_listener')
from ingest.journal_normaliser import normalise_scan_event
from ingest.eddn_client import _resolve_ring_rows_with_local_bodies, _ring_rows_from_scan_facts
from import_spansh import body_ring_rows_from_spansh_body
from ring_facts import normalise_ring_payload, ring_rows_for_body
from routers.systems import _body_payload_from_row


def test_ring_payload_parses_one_ring_with_class_and_type():
    result = normalise_ring_payload({
        'Rings': [{
            'Name': 'Test 4 A Ring',
            'Type': 'Metal Rich',
            'RingClass': 'eRingClass_MetalRich',
            'MassMT': 123.5,
            'InnerRad': 0,
            'OuterRad': '2500000',
        }],
    })

    assert result.ring_array_present is True
    assert result.explicit_no_rings is False
    assert result.rings == [{
        'ring_name': 'Test 4 A Ring',
        'ring_type': 'Metal Rich',
        'ring_class': 'eRingClass_MetalRich',
        'mass_mt': 123.5,
        'inner_radius': 0.0,
        'outer_radius': 2500000.0,
    }]


def test_ring_payload_parses_multiple_ring_key_variants():
    result = normalise_ring_payload({
        'rings': [
            {'name': 'A Ring', 'class': 'Icy', 'mass': '0'},
            {'ringName': 'B Ring', 'ringClass': 'Metallic', 'outer_radius': 10},
        ],
    })

    assert [ring['ring_name'] for ring in result.rings] == ['A Ring', 'B Ring']
    assert result.rings[0]['mass_mt'] == 0.0
    assert result.rings[1]['ring_class'] == 'Metallic'


def test_missing_ring_array_is_unknown_not_no_rings():
    result = normalise_ring_payload({'BodyName': 'Test 4'})

    assert result.rings == []
    assert result.ring_array_present is False
    assert result.explicit_no_rings is False


def test_empty_ring_array_requires_trusted_full_scan_for_no_rings():
    untrusted = normalise_ring_payload({'Rings': []})
    trusted = normalise_ring_payload({'Rings': []}, trusted_empty_means_no_rings=True)

    assert untrusted.explicit_no_rings is False
    assert trusted.explicit_no_rings is True


def test_ring_rows_for_body_adds_provenance_without_inventing_unknown_fields():
    rows, explicit_no_rings = ring_rows_for_body(
        {'Rings': [{'Name': 'Test 4 A Ring'}]},
        system_id64=42,
        body_id=7,
        body_name='Test 4',
        source='eddn_scan',
    )

    assert explicit_no_rings is False
    assert rows == [{
        'system_id64': 42,
        'body_id': 7,
        'body_name': 'Test 4',
        'ring_name': 'Test 4 A Ring',
        'ring_type': None,
        'ring_class': None,
        'mass_mt': None,
        'inner_radius': None,
        'outer_radius': None,
        'source': 'eddn_scan',
        'confidence': 'source_ring_payload',
    }]


def _scan_event(**overrides):
    event = {
        'SystemAddress': 42,
        'BodyID': 7,
        'BodyName': 'Test 4',
        'PlanetClass': 'Rocky body',
    }
    event.update(overrides)
    return event


def test_eddn_scan_with_rings_sets_true_and_keeps_ring_rows():
    fact = normalise_scan_event(_scan_event(Rings=[{'Name': 'Test 4 A Ring', 'RingClass': 'Icy'}]))

    assert fact['is_ringed'] is True
    assert fact['rings'][0]['ring_name'] == 'Test 4 A Ring'
    row = _ring_rows_from_scan_facts([fact])[0]
    assert row['source'] == 'eddn_scan'
    assert row['body_id'] is None
    assert row['source_body_id'] == 7


def test_eddn_scan_ring_row_exact_body_name_match_maps_to_local_body_id():
    fact = normalise_scan_event(_scan_event(Rings=[{'Name': 'Test 4 A Ring'}]))
    source_rows = _ring_rows_from_scan_facts([fact])

    resolved, skipped = _resolve_ring_rows_with_local_bodies(source_rows, [
        {'system_id64': 42, 'id': 576462760435454682, 'name': 'Test 4'},
    ])

    assert skipped == []
    assert resolved[0]['body_id'] == 576462760435454682
    assert resolved[0]['source_body_id'] == 7
    assert resolved[0]['body_name'] == 'Test 4'
    assert resolved[0]['association_status'] == 'local_matched'


def test_eddn_scan_body_id_is_not_used_as_ring_body_id_without_local_match():
    fact = normalise_scan_event(_scan_event(Rings=[{'Name': 'Test 4 A Ring'}]))
    source_rows = _ring_rows_from_scan_facts([fact])

    resolved, skipped = _resolve_ring_rows_with_local_bodies(source_rows, [])

    assert resolved == []
    assert skipped[0]['body_id'] is None
    assert skipped[0]['source_body_id'] == 7
    assert skipped[0]['reason'] == 'local_body_not_found_by_name'


def test_eddn_scan_ambiguous_body_name_match_is_not_trusted():
    fact = normalise_scan_event(_scan_event(Rings=[{'Name': 'Test 4 A Ring'}]))
    source_rows = _ring_rows_from_scan_facts([fact])

    resolved, skipped = _resolve_ring_rows_with_local_bodies(source_rows, [
        {'system_id64': 42, 'id': 101, 'name': 'Test 4'},
        {'system_id64': 42, 'id': 102, 'name': 'Test 4'},
    ])

    assert resolved == []
    assert skipped[0]['reason'] == 'local_body_name_not_unique'


def test_eddn_scan_ring_without_ring_identity_is_not_written():
    fact = normalise_scan_event(_scan_event(Rings=[{'RingClass': 'Icy'}]))
    source_rows = _ring_rows_from_scan_facts([fact])

    resolved, skipped = _resolve_ring_rows_with_local_bodies(source_rows, [
        {'system_id64': 42, 'id': 576462760435454682, 'name': 'Test 4'},
    ])

    assert resolved == []
    assert skipped[0]['reason'] == 'missing_ring_identity'


def test_eddn_scan_belt_body_id_zero_is_not_trusted_ring_evidence():
    fact = normalise_scan_event(_scan_event(
        BodyID=0,
        BodyName='Test Belt',
        Rings=[{'Name': 'Test Belt A Ring'}],
    ))
    source_rows = _ring_rows_from_scan_facts([fact])

    resolved, skipped = _resolve_ring_rows_with_local_bodies(source_rows, [
        {'system_id64': 42, 'id': 0, 'name': 'Test Belt'},
    ])

    assert resolved == []
    assert skipped[0]['body_id'] is None
    assert skipped[0]['source_body_id'] == 0
    assert skipped[0]['reason'] == 'belt_source_evidence'


def test_eddn_listener_scan_ring_payload_builds_ring_rows():
    rows = eddn_listener.normalise_ring_rows(
        {'Rings': [{'Name': 'Test 4 A Ring', 'InnerRad': 0}]},
        system_id64=42,
        body_id=7,
        body_name='Test 4',
    )

    assert rows == [{
        'system_id64': 42,
        'body_id': None,
        'source_body_id': 7,
        'body_name': 'Test 4',
        'ring_name': 'Test 4 A Ring',
        'ring_type': None,
        'ring_class': None,
        'mass_mt': None,
        'inner_radius': 0.0,
        'outer_radius': None,
        'source': 'eddn_scan',
        'confidence': 'source_ring_payload',
    }]


def test_eddn_scan_empty_rings_sets_explicit_false():
    fact = normalise_scan_event(_scan_event(Rings=[]))

    assert fact['is_ringed'] is False
    assert fact['rings'] == []
    assert _ring_rows_from_scan_facts([fact]) == []


def test_eddn_scan_missing_rings_remains_unknown():
    fact = normalise_scan_event(_scan_event())

    assert fact['is_ringed'] is None
    assert fact['rings'] == []


def test_spansh_ring_payload_builds_ring_rows_but_not_no_ring_rows():
    rows = body_ring_rows_from_spansh_body(
        42,
        7,
        'Test 4',
        {'rings': [{'name': 'Test 4 A Ring', 'type': 'Metal Rich'}]},
    )
    no_rows = body_ring_rows_from_spansh_body(42, 8, 'Test 5', {'rings': []})

    assert rows[0]['source'] == 'spansh_dump'
    assert rows[0]['confidence'] == 'source_ring_payload'
    assert no_rows == []


def test_api_serializes_ringed_body_with_ring_details():
    body = _body_payload_from_row({
        'name': 'Test 4',
        '_scan_is_ringed': None,
        '_scan_data_sources': None,
        '_rings': [{
            'ring_name': 'Test 4 A Ring',
            'ring_type': 'Metal Rich',
            'ring_class': None,
            'mass_mt': None,
            'inner_radius': None,
            'outer_radius': None,
            'source': 'spansh_dump',
            'confidence': 'source_ring_payload',
        }],
        '_ring_sources': ['spansh_dump'],
        '_ring_confidences': ['source_ring_payload'],
    }, 'Test')

    assert body['is_ringed'] is True
    assert body['ring_state'] == 'ringed'
    assert body['ring_count'] == 1
    assert body['rings'][0]['ring_name'] == 'Test 4 A Ring'
    assert body['ring_source'] == 'spansh_dump'


def test_api_serializes_trusted_not_ringed_and_unknown_separately():
    not_ringed = _body_payload_from_row({
        'name': 'Test 5',
        '_scan_is_ringed': False,
        '_scan_data_sources': ['eddn_scan'],
    }, 'Test')
    unknown = _body_payload_from_row({
        'name': 'Test 6',
        '_scan_is_ringed': None,
        '_scan_data_sources': None,
    }, 'Test')

    assert not_ringed['is_ringed'] is False
    assert not_ringed['ring_state'] == 'not_ringed'
    assert not_ringed['ring_count'] == 0
    assert not_ringed['rings'] == []
    assert unknown['is_ringed'] is None
    assert unknown['ring_state'] == 'unknown'
    assert unknown['ring_count'] is None
    assert unknown['rings'] is None


def test_api_ignores_source_only_ringed_scan_without_local_ring_row():
    body = _body_payload_from_row({
        'name': 'Test 7',
        '_scan_is_ringed': True,
        '_scan_data_sources': ['eddn_scan'],
        '_rings': None,
        '_ring_sources': None,
        '_ring_confidences': None,
    }, 'Test')

    assert body['is_ringed'] is None
    assert body['ring_state'] == 'unknown'
    assert body['ring_count'] is None
