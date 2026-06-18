import gzip
import json
import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_snapshot_loader as loader  # noqa: E402


FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
NESTED_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_nested_system_station_snapshot.json'


def test_loader_reads_local_edsm_station_snapshot_fixture():
    report = loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
    )

    assert report['schema_version'] == 'enrichment_snapshot_load_plan/v1'
    assert report['dry_run'] is True
    assert report['source_run']['source'] == 'edsm_nightly_stations'
    assert report['source_run']['source_class'] == 'semi-stable'
    assert report['source_run']['adapter_version'] == 'v1'
    assert report['source_run']['metadata']['source_format_version'] == 'json_snapshot_stream/v1'
    assert report['source_file']['source_file_name'] == 'edsm_station_snapshot.json'
    assert len(report['source_file']['file_sha256']) == 64
    assert report['source_file']['source_updated_at'] == '2026-01-02T00:00:00Z'
    assert report['source_file']['metadata']['record_stream_shape'] == 'json_array'
    assert report['source_file']['metadata']['source_timestamp_summary'] == {
        'records_with_source_updated_at': 2,
        'records_without_source_updated_at': 1,
        'unique_source_updated_at_values': 2,
        'earliest_source_updated_at': '2026-01-01T00:00:00Z',
        'latest_source_updated_at': '2026-01-02T00:00:00Z',
    }
    assert report['summary']['raw_records'] == 3
    assert report['summary']['staged_rows'] == 2
    assert report['summary']['staged_edsm_stations'] == 2
    assert report['summary']['skipped_rows'] == 1
    assert report['summary']['skipped_row_reasons'] == {'invalid_station_snapshot_record': 1}
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['summary']['distance_to_arrival_classification'] == 'volatile'
    assert report['summary']['source_format_version'] == 'json_snapshot_stream/v1'
    assert report['summary']['source_freshness_summary'] == {
        'freshness_distribution': {'source_updated_at': 2},
        'records_with_source_updated_at': 2,
        'records_without_source_updated_at': 1,
        'freshness_preserves_unknown': True,
    }

    by_name = {row['station_name']: row for row in report['staged_rows']}
    macmillan = by_name['Macmillan Depot']
    assert macmillan['system_id64'] == 2008132031194
    assert macmillan['market_id'] == 128666
    assert macmillan['edsm_station_id'] == 128666
    assert macmillan['station_type'] == 'Orbis Starport'
    assert macmillan['distance_to_arrival'] == 592.25
    assert macmillan['body_name'] == 'Exioce 3 d'
    assert macmillan['controlling_faction'] == 'Exioce Blue Mafia'
    assert macmillan['provenance']['distance_to_arrival_classification'] == 'volatile'
    assert macmillan['provenance']['canonical_write_allowed'] is False
    assert macmillan['raw_payload']['distanceToArrival'] == 592.25


def test_loader_honours_limit_without_loading_or_writing_canonical_data():
    report = loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
        limit=1,
    )

    assert report['summary']['records_seen'] == 1
    assert report['summary']['raw_records'] == 1
    assert report['summary']['staged_rows'] == 1
    assert report['summary']['skipped_rows'] == 0
    assert report['planned_rows'] == []
    assert report['dry_run'] is True
    assert report['summary']['dry_run_only'] is True
    assert report['summary']['canonical_writes_planned'] == 0


def test_loader_reads_gzipped_local_fixture(tmp_path):
    gz_path = tmp_path / 'edsm_station_snapshot.json.gz'
    with gzip.open(gz_path, 'wt', encoding='utf-8') as handle:
        handle.write(FIXTURE.read_text(encoding='utf-8'))

    report = loader.build_snapshot_load_report(
        source_file=gz_path,
        source='edsm_nightly_stations',
    )

    assert report['source_file']['compression'] == 'gzip'
    assert report['summary']['raw_records'] == 3
    assert report['summary']['staged_rows'] == 2


def test_invalid_records_are_skipped_with_warnings_not_crashes():
    report = loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
    )

    skipped = report['skipped_rows']
    assert len(skipped) == 1
    assert skipped[0]['reason'] == 'invalid_station_snapshot_record'
    assert skipped[0]['warnings'] == [
        {'field': 'station_name', 'reason': 'missing_required_field'},
    ]
    assert report['summary']['skipped_row_reason_distribution'] == {
        'invalid_station_snapshot_record': 1,
    }


def test_normalisation_accepts_edsm_station_snapshot_shapes():
    row = loader.normalise_edsm_station_snapshot_record(
        {
            'systemName': 'Sol',
            'systemId64': '10477373803',
            'marketId': '322',
            'id': '1234',
            'name': 'Galileo',
            'type': 'Coriolis Starport',
            'distanceToArrival': '503.2',
            'bodyName': 'Moon',
            'services': ['Dock', 'Shipyard'],
            'economy': 'High Tech',
            'secondEconomy': 'Service',
            'controllingFaction': {'name': 'Mother Gaia'},
            'updatedAt': '2026-01-02T00:00:00Z',
        },
        source='edsm_nightly_stations',
    )

    assert row['system_id64'] == 10477373803
    assert row['market_id'] == 322
    assert row['edsm_station_id'] == 1234
    assert row['distance_to_arrival'] == 503.2
    assert row['economies'] == ['High Tech', 'Service']
    assert row['controlling_faction'] == 'Mother Gaia'
    assert row['freshness_class'] == 'source_updated_at'
    assert row['source_record_hash']


def test_update_time_object_normalises_to_scalar_source_updated_at_and_preserves_raw_payload(tmp_path):
    update_time = {
        'information': '2017-04-21 07:06:46',
        'market': None,
        'shipyard': None,
        'outfitting': None,
    }
    source_file = tmp_path / 'update-time-object.json'
    source_file.write_text(json.dumps([
        {
            'systemName': 'Sol',
            'systemId64': 10477373803,
            'marketId': 322,
            'id': 1234,
            'name': 'Galileo',
            'type': 'Coriolis Starport',
            'updateTime': update_time,
        }
    ]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    raw_record = report['raw_records_planned'][0]
    station_row = report['staged_rows'][0]
    assert raw_record['source_updated_at'] == '2017-04-21 07:06:46'
    assert station_row['source_updated_at'] == '2017-04-21 07:06:46'
    assert raw_record['raw_payload']['updateTime'] == update_time
    assert station_row['raw_payload']['updateTime'] == update_time
    assert isinstance(raw_record['source_updated_at'], str)
    assert isinstance(station_row['source_updated_at'], str)


def test_update_time_object_falls_back_to_market_when_information_missing(tmp_path):
    source_file = tmp_path / 'update-time-market-fallback.json'
    source_file.write_text(json.dumps([
        {
            'systemName': 'Fallback System',
            'marketId': 400,
            'id': 400,
            'name': 'Fallback Port',
            'type': 'Outpost',
            'updateTime': {
                'information': None,
                'market': '2018-01-02 03:04:05',
                'shipyard': None,
                'outfitting': None,
            },
        }
    ]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['raw_records_planned'][0]['source_updated_at'] == '2018-01-02 03:04:05'
    assert report['staged_rows'][0]['source_updated_at'] == '2018-01-02 03:04:05'


def test_update_time_object_with_no_valid_timestamp_uses_none(tmp_path):
    source_file = tmp_path / 'update-time-none.json'
    source_file.write_text(json.dumps([
        {
            'systemName': 'Unknown Freshness',
            'marketId': 500,
            'id': 500,
            'name': 'Archive Station',
            'type': 'Outpost',
            'updateTime': {
                'information': None,
                'market': None,
                'shipyard': None,
                'outfitting': None,
            },
        }
    ]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['raw_records_planned'][0]['source_updated_at'] is None
    assert report['staged_rows'][0]['source_updated_at'] is None
    assert report['staged_rows'][0]['freshness_class'] == 'file_snapshot'


def test_scalar_update_time_string_still_works(tmp_path):
    source_file = tmp_path / 'update-time-scalar.json'
    source_file.write_text(json.dumps([
        {
            'systemName': 'Scalar Freshness',
            'marketId': 600,
            'id': 600,
            'name': 'Scalar Port',
            'type': 'Outpost',
            'updateTime': '2019-02-03 04:05:06',
        }
    ]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['raw_records_planned'][0]['source_updated_at'] == '2019-02-03 04:05:06'
    assert report['staged_rows'][0]['source_updated_at'] == '2019-02-03 04:05:06'


def test_report_output_is_deterministic_for_fixed_fixture():
    first = loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
    )
    second = loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_cli_outputs_json_report(capsys):
    exit_code = loader.main([
        '--source-file',
        str(FIXTURE),
        '--source',
        'edsm_nightly_stations',
        '--json',
        '--limit',
        '2',
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['summary']['records_seen'] == 2
    assert payload['summary']['staged_rows'] == 2


def test_apply_flags_fail_closed():
    with pytest.raises(SystemExit):
        loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_stations',
            '--apply',
        ])


def test_dry_run_is_default_and_write_flags_are_absent_from_report():
    args = loader.parse_args([
        '--source-file',
        str(FIXTURE),
        '--source',
        'edsm_nightly_stations',
    ])
    report = loader.build_snapshot_load_report(
        source_file=Path(args.source_file),
        source=args.source,
    )

    assert args.dry_run is True
    assert report['dry_run'] is True
    assert report['source_run']['dry_run'] is True
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['planned_rows'] == []


def test_loader_rejects_live_or_remote_source_paths():
    with pytest.raises(ValueError, match='local path'):
        loader.build_snapshot_load_report(
            source_file=Path('https://www.edsm.net/dump.json'),
            source='edsm_nightly_stations',
        )


def test_loader_rejects_unknown_source_adapter():
    with pytest.raises(ValueError, match='unsupported offline source'):
        loader.build_snapshot_load_report(
            source_file=FIXTURE,
            source='mystery_vendor_snapshot',
        )


def test_missing_source_file_fails_clearly(tmp_path, capsys):
    missing_file = tmp_path / 'missing-stations.json'

    with pytest.raises(ValueError, match='source file does not exist'):
        loader.build_snapshot_load_report(
            source_file=missing_file,
            source='edsm_nightly_stations',
        )

    exit_code = loader.main([
        '--source-file',
        str(missing_file),
        '--source',
        'edsm_nightly_stations',
    ])

    assert exit_code == 2
    assert 'source file does not exist' in capsys.readouterr().err


def test_duplicate_station_records_share_source_hash_and_report_deterministically(tmp_path):
    station = {
        'systemName': 'Duplicate Test',
        'systemId64': 42,
        'marketId': 123,
        'id': 123,
        'name': 'Repeat Depot',
        'type': 'Outpost',
        'distanceToArrival': 15.5,
    }
    source_file = tmp_path / 'duplicate-stations.json'
    source_file.write_text(json.dumps([station, dict(station)]), encoding='utf-8')

    first = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )
    second = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert first == second
    assert first['summary']['raw_records'] == 2
    assert first['summary']['staged_rows'] == 2
    raw_hashes = [row['source_record_hash'] for row in first['raw_records_planned']]
    staged_hashes = [row['source_record_hash'] for row in first['staged_rows']]
    assert len(set(raw_hashes)) == 1
    assert len(set(staged_hashes)) == 1
    assert len({row['source_record_key'] for row in first['raw_records_planned']}) == 2
    assert first['summary']['duplicate_source_record_hashes'] == 1
    assert first['summary']['duplicate_source_records'] == 1
    assert first['source_record_duplicate_groups'] == [{
        'source_record_hash': raw_hashes[0],
        'count': 2,
        'record_indexes': [1, 2],
        'handling': 'reported_only_dry_run; explicit staging writes upsert by source_record_hash',
    }]


def test_unsupported_station_source_shape_is_reported_without_guessing(tmp_path):
    source_file = tmp_path / 'unsupported-station-shape.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Nested System',
                'bodies': [{'name': 'Nested 1'}],
            }
        ]),
        encoding='utf-8',
    )

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['summary']['records_seen'] == 1
    assert report['summary']['staged_rows'] == 0
    assert report['summary']['raw_records'] == 1
    assert report['summary']['unsupported_source_shapes'] == 1
    assert report['skipped_rows'] == [{
        'record_index': 1,
        'source_record_hash': report['raw_records_planned'][0]['source_record_hash'],
        'reason': 'unsupported_station_snapshot_source_shape',
        'warnings': [{
            'field': 'bodies',
            'reason': 'unsupported_source_shape',
            'source_shape': 'nested_body_collection',
        }],
        'raw_payload': {
            'systemName': 'Nested System',
            'bodies': [{'name': 'Nested 1'}],
        },
    }]
    assert report['raw_records_planned'][0]['validation_status'] == 'skipped'


def test_nested_system_station_snapshot_extracts_supported_station_rows():
    report = loader.build_snapshot_load_report(
        source_file=NESTED_FIXTURE,
        source='edsm_nightly_stations',
    )

    assert report['dry_run'] is True
    assert report['summary']['records_seen'] == 2
    assert report['summary']['raw_records'] == 2
    assert report['summary']['staged_rows'] == 3
    assert report['summary']['staged_edsm_stations'] == 3
    assert report['summary']['nested_station_collections'] == 2
    assert report['summary']['nested_station_records_extracted'] == 3
    assert report['summary']['nested_station_records_skipped'] == 0
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['planned_rows'] == []
    assert 'staged_body_rows' not in report

    raw_hashes = {row['source_record_hash'] for row in report['raw_records_planned']}
    staged_hashes = {row['source_record_hash'] for row in report['staged_rows']}
    assert len(raw_hashes) == 2
    assert len(staged_hashes) == 3
    assert raw_hashes.isdisjoint(staged_hashes)
    assert all(row['source_run_key'] == report['source_run']['source_run_key'] for row in report['staged_rows'])
    assert all(row['source_file_key'] == report['source_file']['source_file_key'] for row in report['staged_rows'])
    assert {row['provenance']['parent_source_record_hash'] for row in report['staged_rows']} == raw_hashes

    by_name = {row['station_name']: row for row in report['staged_rows']}
    alpha = by_name['Alpha Orbital']
    assert alpha['system_name'] == 'Nested Alpha'
    assert alpha['system_id64'] == 111111111
    assert alpha['market_id'] == 9001001
    assert alpha['edsm_station_id'] == 1001
    assert alpha['station_type'] == 'Orbis Starport'
    assert alpha['provenance']['station_type_normalized'] == 'Orbis'
    assert alpha['provenance']['station_type_classification'] == 'permanent_colony_slot'
    assert alpha['provenance']['source_record_kind'] == 'nested_station_record'
    assert alpha['provenance']['nested_body_collection_state'] == 'unsupported_source_only'
    assert alpha['provenance']['canonical_write_allowed'] is False

    beta = by_name['Beta Plant']
    assert beta['system_name'] == 'Nested Beta'
    assert beta['system_id64'] == 222222222
    assert beta['market_id'] == 9001003
    assert beta['edsm_station_id'] == 1003
    assert beta['station_type'] == 'Planetary Settlement'
    assert beta['body_name'] == 'Nested Beta A 2'
    assert beta['provenance']['station_type_normalized'] == 'PlanetaryOutpost'


def test_nested_system_body_collection_remains_warning_not_body_truth():
    report = loader.build_snapshot_load_report(
        source_file=NESTED_FIXTURE,
        source='edsm_nightly_stations',
    )

    body_warnings = [
        warning for warning in report['warnings']
        if warning.get('reason') == 'unsupported_source_shape'
        and warning.get('source_shape') == 'nested_body_collection'
    ]
    assert body_warnings == [{
        'record_index': 1,
        'source_record_hash': report['raw_records_planned'][0]['source_record_hash'],
        'field': 'bodies',
        'reason': 'unsupported_source_shape',
        'source_shape': 'nested_body_collection',
        'handling': 'preserved_in_raw_record_only_not_staged',
    }]
    assert report['summary']['unsupported_source_shapes'] == 1
    assert report['summary']['warning_reason_distribution']['unsupported_source_shape'] == 1
    assert report['raw_records_planned'][0]['raw_payload']['bodies'][0]['name'] == 'Nested Alpha 1'
    assert report['raw_records_planned'][0]['validation_status'] == 'accepted'
    assert report['raw_records_planned'][0]['validation_warnings'] == [
        {
            'field': 'bodies',
            'reason': 'unsupported_source_shape',
            'source_shape': 'nested_body_collection',
            'handling': 'preserved_in_raw_record_only_not_staged',
        },
    ]
    assert all('bodies' not in row['raw_payload'] for row in report['staged_rows'])
    assert report['summary']['canonical_writes_planned'] == 0


def test_nested_fleet_carrier_station_type_is_labelled_not_canonical_truth():
    report = loader.build_snapshot_load_report(
        source_file=NESTED_FIXTURE,
        source='edsm_nightly_stations',
    )

    carrier = {row['station_name']: row for row in report['staged_rows']}['FC Test']
    assert carrier['station_type'] == 'Fleet Carrier'
    assert carrier['provenance']['station_type_normalized'] == 'FleetCarrier'
    assert carrier['provenance']['station_type_classification'] == 'transient_non_slot'
    assert carrier['validation_warnings'] == [
        {
            'field': 'station_type',
            'reason': 'transient_non_slot_station_type',
            'station_type_normalized': 'FleetCarrier',
        },
    ]
    assert any(
        warning.get('reason') == 'transient_non_slot_station_type'
        and warning.get('source_record_hash') == carrier['source_record_hash']
        for warning in report['warnings']
    )


def test_conflicting_station_records_with_same_source_identity_are_report_only(tmp_path):
    station = {
        'systemName': 'Conflict Test',
        'systemId64': 424242,
        'marketId': 7654,
        'name': 'Conflict Port',
        'type': 'Outpost',
    }
    changed_station = dict(station)
    changed_station['type'] = 'Coriolis Starport'
    source_file = tmp_path / 'conflicting-stations.json'
    source_file.write_text(json.dumps([station, changed_station]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['summary']['staged_rows'] == 2
    assert report['summary']['conflicts'] == 1
    assert report['conflicts'][0]['reason'] == 'duplicate_source_identity_conflict'
    assert report['conflicts'][0]['entity'] == 'station'
    assert report['conflicts'][0]['handling'] == 'report_only_conflict_no_canonical_write'
    assert report['summary']['canonical_writes_planned'] == 0


def test_unknown_extra_fields_are_retained_in_raw_and_staging_evidence(tmp_path):
    station = {
        'systemName': 'Extra Fields',
        'systemId64': 43,
        'marketId': 777,
        'id': 777,
        'name': 'Archive Terminal',
        'type': 'Coriolis Starport',
        'distanceToArrival': 250.75,
        'unexpectedNested': {
            'futureField': 'retained',
            'values': [1, {'deep': True}],
        },
    }
    source_file = tmp_path / 'extra-fields.json'
    source_file.write_text(json.dumps([station]), encoding='utf-8')

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['summary']['staged_rows'] == 1
    assert report['raw_records_planned'][0]['raw_payload']['unexpectedNested']['futureField'] == 'retained'
    assert report['staged_rows'][0]['raw_payload']['unexpectedNested']['values'][1]['deep'] is True


def test_sparse_valid_station_record_uses_defaults_and_warning_not_skip(tmp_path):
    source_file = tmp_path / 'sparse-station.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Sparse System',
                'name': 'Bare Station',
            }
        ]),
        encoding='utf-8',
    )

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )
    row = report['staged_rows'][0]

    assert report['summary']['staged_rows'] == 1
    assert report['summary']['skipped_rows'] == 0
    assert report['summary']['warnings'] == 1
    assert row['system_id64'] is None
    assert row['market_id'] is None
    assert row['edsm_station_id'] is None
    assert row['services'] == []
    assert row['economies'] == []
    assert row['freshness_class'] == 'file_snapshot'
    assert row['validation_warnings'] == [
        {'field': 'market_id', 'reason': 'missing_station_source_identity'},
    ]


def test_malformed_non_object_records_are_reported_as_skipped_not_successful(tmp_path):
    source_file = tmp_path / 'malformed-records.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Valid System',
                'marketId': 9001,
                'name': 'Valid Station',
            },
            12,
            'not an object',
        ]),
        encoding='utf-8',
    )

    report = loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )

    assert report['summary']['records_seen'] == 3
    assert report['summary']['staged_rows'] == 1
    assert report['summary']['skipped_rows'] == 2
    assert [row['reason'] for row in report['skipped_rows']] == [
        'record_is_not_object',
        'record_is_not_object',
    ]


def test_loader_source_does_not_import_network_db_or_container_write_paths():
    source = Path(loader.__file__).read_text(encoding='utf-8').lower()

    assert 'urlopen' not in source
    assert 'requests' not in source
    assert 'psycopg2' not in source
    assert 'subprocess' not in source
    assert 'docker compose' not in source
    assert 'psql' not in source
