import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
for path in (API_SRC, IMPORTER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import edsm_station_enrichment_probe as probe  # noqa: E402


SYSTEM = {'id64': 2008132031194, 'name': 'Exioce'}
BODIES = [
    {'id': 10, 'system_id64': 2008132031194, 'name': 'Exioce', 'distance_from_star': 0.0},
    {'id': 11, 'system_id64': 2008132031194, 'name': 'Exioce 1', 'distance_from_star': 120.0},
    {'id': 12, 'system_id64': 2008132031194, 'name': 'Exioce 2', 'distance_from_star': 240.0},
]


def local_station(**overrides):
    station = {
        'id': 1001,
        'market_id': 1001,
        'system_id64': 2008132031194,
        'name': 'Harper Plant',
        'station_type': 'Unknown',
        'distance_from_star': None,
        'body_name': None,
        'primary_economy': None,
        'has_market': False,
        'has_shipyard': False,
    }
    station.update(overrides)
    return station


def report_for(station, edsm_station, *, bodies=None, edsm_bodies=None, existing_links=None):
    return probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[station],
        local_bodies=bodies or BODIES,
        existing_links=existing_links or {},
        edsm_stations_payload={'stations': [edsm_station]},
        edsm_bodies_payload={'bodies': edsm_bodies or []},
    )


def first_station(report):
    return report['stations'][0]


def conflict_types(station_report):
    return {conflict['type'] for conflict in station_report['conflicts']}


def test_import_path_supports_repo_and_flat_container_layouts():
    repo_paths = probe._station_resolver_import_paths(
        ROOT / 'apps' / 'importer' / 'src' / 'edsm_station_enrichment_probe.py'
    )
    flat_paths = probe._station_resolver_import_paths(Path('/app/edsm_station_enrichment_probe.py'))

    assert ROOT / 'apps' / 'api' / 'src' in repo_paths
    assert Path('/app') in flat_paths


def test_exact_name_type_match_proposes_type_enrichment():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'distanceToArrival': 120.0,
        },
    )

    station = first_station(report)

    assert report['dry_run'] is True
    assert station['station_match']['status'] == 'matched'
    assert station['station_match']['source'] == 'id_name'
    assert station['proposed']['station_type'] == 'Coriolis'
    assert 'station_type' in station['fields_that_would_change']
    assert report['station_metadata_changes'][0]['proposed_station_type'] == 'Coriolis'


def test_unknown_local_type_known_edsm_type_proposes_dry_run_update():
    report = report_for(
        local_station(id=2002, market_id=2002, name='Riley Dock', station_type='Unknown'),
        {
            'id': 9999,
            'marketId': 9999,
            'name': 'Riley Dock',
            'type': 'Planetary settlement',
            'distanceToArrival': 240.0,
        },
    )

    station = first_station(report)

    assert station['station_match']['source'] == 'exact_name'
    assert station['proposed']['station_type'] == 'PlanetaryOutpost'
    assert station['proposed']['lane'] == 'surface'
    assert 'station_type' in station['fields_that_would_change']


def test_exioce_like_orbis_and_coriolis_type_evidence_are_metadata_changes():
    report = probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[
            local_station(id=2001, market_id=2001, name='Macmillan Depot', station_type='Unknown'),
            local_station(id=2002, market_id=2002, name='Miller Terminal', station_type='Unknown'),
        ],
        local_bodies=BODIES,
        existing_links={},
        edsm_stations_payload={'stations': [
            {
                'id': 2001,
                'name': 'Macmillan Depot',
                'type': 'Orbis Starport',
                'bodyName': 'Exioce 1',
                'distanceToArrival': 120.0,
            },
            {
                'id': 2002,
                'name': 'Miller Terminal',
                'type': 'Coriolis Starport',
                'bodyName': 'Exioce 2',
                'distanceToArrival': 240.0,
            },
        ]},
        edsm_bodies_payload={'bodies': []},
    )

    changes_by_name = {
        change['local_station']['name']: change
        for change in report['station_metadata_changes']
    }

    assert changes_by_name['Macmillan Depot']['proposed_station_type'] == 'Orbis'
    assert changes_by_name['Miller Terminal']['proposed_station_type'] == 'Coriolis'
    assert all('station_type' in change['fields_that_would_change'] for change in changes_by_name.values())


def test_fleet_carrier_is_ignored_for_station_body_links_even_with_body_evidence():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Fleet Carrier',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    proposed = first_station(report)['proposed']

    assert proposed['station_type'] == 'FleetCarrier'
    assert proposed['body_id'] is None
    assert proposed['association_status'] == 'unresolved'
    assert proposed['lane'] == 'unknown'
    assert proposed['occupies_colony_slot'] is False
    assert report['association_changes'] == []
    assert report['station_metadata_changes'] == []
    assert report['counts']['ignored_transient_non_slot'] == 1
    assert report['ignored_transient_non_slot'][0]['station_type_evidence']['proposed'] == 'FleetCarrier'
    assert 'not treated as permanent colony-slot' in proposed['resolver_notes']
    assert 'station_body_links' not in first_station(report)['fields_that_would_change']


def test_megaship_is_ignored_for_station_body_links():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'MegaShip',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    proposed = first_station(report)['proposed']

    assert proposed['station_type'] == 'MegaShip'
    assert proposed['body_id'] is None
    assert proposed['association_status'] == 'unresolved'
    assert report['association_changes'] == []
    assert report['ignored_transient_non_slot'][0]['body_evidence']['body_name'] == 'Exioce 1'


def test_carrier_like_rows_do_not_produce_association_changes():
    report = probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[
            local_station(id=3001, market_id=3001, name='Mobile One', station_type='Unknown'),
            local_station(id=3002, market_id=3002, name='Mobile Two', station_type='Unknown'),
            local_station(id=3003, market_id=3003, name='Mobile Three', station_type='Unknown'),
        ],
        local_bodies=BODIES,
        existing_links={},
        edsm_stations_payload={'stations': [
            {'id': 3001, 'name': 'Mobile One', 'type': 'FleetCarrier', 'bodyName': 'Exioce 1'},
            {'id': 3002, 'name': 'Mobile Two', 'type': 'Carrier', 'bodyName': 'Exioce 1'},
            {'id': 3003, 'name': 'Mobile Three', 'type': 'MegaShip', 'bodyName': 'Exioce 2'},
        ]},
        edsm_bodies_payload={'bodies': []},
    )

    assert report['association_changes'] == []
    assert report['counts']['ignored_transient_non_slot'] == 3
    assert len(report['ignored_transient_non_slot']) == 3


def test_exact_body_name_confirms_same_system_body_association():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    proposed = first_station(report)['proposed']

    assert proposed['body_id'] == 11
    assert proposed['body_name'] == 'Exioce 1'
    assert proposed['lane'] == 'orbital'
    assert proposed['association_status'] == 'confirmed'
    assert proposed['association_confidence'] == 'exact'
    assert proposed['association_source'] == 'edsm_body_name'
    assert report['association_changes'][0]['proposed_link']['association_status'] == 'confirmed'


def test_distance_only_body_match_infers_body_association():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Outpost',
            'distanceToArrival': 240.0,
        },
    )

    proposed = first_station(report)['proposed']

    assert proposed['body_id'] == 12
    assert proposed['association_status'] == 'inferred'
    assert proposed['association_confidence'] == 'strong_inference'
    assert proposed['association_source'] == 'edsm_distance'
    assert report['association_changes'][0]['proposed_link']['association_status'] == 'inferred'


def test_ambiguous_distance_body_match_remains_unresolved():
    ambiguous_bodies = [
        *BODIES,
        {'id': 13, 'system_id64': 2008132031194, 'name': 'Exioce 2 a', 'distance_from_star': 240.004},
    ]
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Outpost',
            'distanceToArrival': 240.0,
        },
        bodies=ambiguous_bodies,
    )

    station = first_station(report)

    assert station['proposed']['body_id'] is None
    assert station['proposed']['association_status'] == 'unresolved'
    assert 'multiple_body_distance_matches' in conflict_types(station)


def test_conflicting_station_distance_reports_conflict_and_blocks_body_proposal():
    report = report_for(
        local_station(station_type='Unknown', distance_from_star=120.0),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'bodyName': 'Exioce 2',
            'distanceToArrival': 240.0,
        },
    )

    station = first_station(report)

    assert 'station_distance_mismatch' in conflict_types(station)
    assert station['proposed']['association_status'] == 'unresolved'
    assert station['proposed']['body_id'] is None
    assert report['association_changes'] == []
    assert report['station_metadata_changes'][0]['proposed_station_type'] == 'Coriolis'
    assert report['conflicts'][0]['conflict']['type'] == 'station_distance_mismatch'


def test_confirmed_existing_link_is_preserved_against_weaker_edsm_evidence():
    existing_links = {
        1001: {
            'station_id': 1001,
            'market_id': 1001,
            'system_id64': 2008132031194,
            'body_id': 11,
            'body_name': 'Exioce 1',
            'lane': 'orbital',
            'association_status': 'confirmed',
            'association_confidence': 'exact',
            'association_source': 'manual',
            'resolver_notes': 'operator verified',
        },
    }
    report = report_for(
        local_station(station_type='Coriolis'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'distanceToArrival': 240.0,
        },
        existing_links=existing_links,
    )

    station = first_station(report)

    assert 'confirmed_link_preserved' in conflict_types(station)
    assert 'station_body_links' not in station['fields_that_would_change']


def test_apply_hard_fails_before_db_or_network(capsys):
    result = probe.main(['--system-name', 'Exioce', '--dsn', 'postgresql://example', '--apply'])

    captured = capsys.readouterr()
    assert result == 2
    assert 'not implemented' in captured.err
