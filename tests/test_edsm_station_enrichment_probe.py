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


def test_fleet_carrier_remains_non_slot_even_with_body_evidence():
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
    assert proposed['body_id'] == 11
    assert proposed['association_status'] == 'confirmed'
    assert proposed['lane'] == 'unknown'
    assert proposed['occupies_colony_slot'] is False
    assert 'not treated as permanent colony-slot' in proposed['resolver_notes']


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
