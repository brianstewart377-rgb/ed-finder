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


def suppression_entries(report):
    return [
        entry for entry in report['skipped']
        if entry.get('reason') == probe.STATION_WRITE_SUPPRESSED_REASON
    ]


class FakeApplyConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.last_row = None

    def cursor(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.statements.append((sql, params))
        sql_lower = ' '.join(sql.lower().split())
        if 'insert into station_body_links' in sql_lower:
            (
                station_id,
                market_id,
                system_id64,
                body_id,
                body_name,
                lane,
                resolver_notes,
            ) = params
            row = self.rows.setdefault(('link', station_id), {})
            if row.get('association_status') == 'confirmed':
                self.last_row = None
                return
            row.update({
                'station_id': station_id,
                'market_id': market_id,
                'system_id64': system_id64,
                'body_id': body_id,
                'body_name': body_name,
                'lane': lane,
                'association_status': 'confirmed',
                'association_confidence': 'exact',
                'association_source': 'edsm_body_name',
                'resolver_notes': resolver_notes,
            })
            self.last_row = dict(row)
            return

        if 'set station_type' in sql_lower:
            new_type, source, confidence, station_id, system_id64 = params
            row = self.rows.get((station_id, system_id64))
            if row is None or row['station_type'] != 'Unknown':
                self.last_row = None
                return
            row['station_type'] = new_type
            row['station_type_source'] = source
            row['station_type_confidence'] = confidence
            self.last_row = {
                'id': station_id,
                'system_id64': system_id64,
                'name': row['name'],
                'station_type': new_type,
                'station_type_source': source,
                'station_type_confidence': confidence,
                'distance_from_star': row.get('distance_from_star'),
                'distance_source': row.get('distance_source'),
                'distance_confidence': row.get('distance_confidence'),
                'body_name': row.get('body_name'),
                'body_name_source': row.get('body_name_source'),
                'body_name_confidence': row.get('body_name_confidence'),
            }
            return

        if 'set distance_from_star' in sql_lower:
            distance, source, confidence, station_id, system_id64 = params
            row = self.rows.get((station_id, system_id64))
            if row is None:
                self.last_row = None
                return
            row['distance_from_star'] = distance
            row['distance_source'] = source
            row['distance_confidence'] = confidence
            self.last_row = {
                'id': station_id,
                'system_id64': system_id64,
                'name': row['name'],
                'station_type': row.get('station_type'),
                'station_type_source': row.get('station_type_source'),
                'station_type_confidence': row.get('station_type_confidence'),
                'distance_from_star': distance,
                'distance_source': source,
                'distance_confidence': confidence,
                'body_name': row.get('body_name'),
                'body_name_source': row.get('body_name_source'),
                'body_name_confidence': row.get('body_name_confidence'),
            }
            return

        if 'set body_name' in sql_lower:
            body_name, source, confidence, station_id, system_id64 = params
            row = self.rows.get((station_id, system_id64))
            if row is None:
                self.last_row = None
                return
            row['body_name'] = body_name
            row['body_name_source'] = source
            row['body_name_confidence'] = confidence
            self.last_row = {
                'id': station_id,
                'system_id64': system_id64,
                'name': row['name'],
                'station_type': row.get('station_type'),
                'station_type_source': row.get('station_type_source'),
                'station_type_confidence': row.get('station_type_confidence'),
                'distance_from_star': row.get('distance_from_star'),
                'distance_source': row.get('distance_source'),
                'distance_confidence': row.get('distance_confidence'),
                'body_name': body_name,
                'body_name_source': source,
                'body_name_confidence': confidence,
            }
            return

        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.last_row


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
            'id': 2002,
            'marketId': 2002,
            'name': 'Riley Dock',
            'type': 'Planetary settlement',
            'distanceToArrival': 240.0,
        },
    )

    station = first_station(report)

    assert station['station_match']['source'] == 'id_name'
    assert station['proposed']['station_type'] == 'PlanetaryOutpost'
    assert station['proposed']['lane'] == 'surface'
    assert 'station_type' in station['fields_that_would_change']


def test_name_only_match_is_diagnostic_not_trusted_for_apply():
    report = report_for(
        local_station(id=2002, market_id=2002, name='Riley Dock', station_type='Unknown'),
        {
            'id': 9999,
            'marketId': 9999,
            'name': 'Riley Dock',
            'type': 'Planetary settlement',
            'bodyName': 'Exioce 2',
            'distanceToArrival': 240.0,
        },
    )

    station = first_station(report)

    assert station['station_match']['source'] == 'exact_name'
    assert station['station_match']['status'] == 'matched'
    assert station['proposed']['association_status'] == 'unresolved'
    assert report['metadata_updates_planned'] == []
    assert report['confirmed_link_updates_planned'] == []
    assert any(entry['reason'] == 'weak_station_identity' for entry in report['skipped'])


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


def test_dry_run_report_does_not_apply_metadata_updates():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Orbis Starport',
            'distanceToArrival': 120.0,
        },
    )

    assert report['dry_run'] is True
    assert report['apply_mode'] == 'dry_run'
    assert report['metadata_updates_applied'] == []
    assert report['counts']['metadata_updates_applied'] == 0
    assert report['metadata_updates_planned'][0]['new_value'] == 'Orbis'


def test_apply_metadata_updates_unknown_to_orbis_and_coriolis():
    report = probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[
            local_station(id=2001, market_id=2001, name='Macmillan Depot', station_type='Unknown'),
            local_station(id=2002, market_id=2002, name='Miller Terminal', station_type='Unknown'),
        ],
        local_bodies=BODIES,
        existing_links={},
        edsm_stations_payload={'stations': [
            {'id': 2001, 'name': 'Macmillan Depot', 'type': 'Orbis Starport'},
            {'id': 2002, 'name': 'Miller Terminal', 'type': 'Coriolis Starport'},
        ]},
        edsm_bodies_payload={'bodies': []},
    )
    conn = FakeApplyConnection({
        (2001, 2008132031194): {'name': 'Macmillan Depot', 'station_type': 'Unknown'},
        (2002, 2008132031194): {'name': 'Miller Terminal', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)
    probe.apply_metadata_result(report, applied, skipped)

    assert skipped == []
    assert [row['new_value'] for row in applied] == ['Orbis', 'Coriolis']
    assert conn.rows[(2001, 2008132031194)]['station_type'] == 'Orbis'
    assert conn.rows[(2002, 2008132031194)]['station_type'] == 'Coriolis'
    assert report['dry_run'] is False
    assert report['apply_mode'] == 'metadata'
    assert report['counts']['metadata_updates_applied'] == 2


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


def test_metadata_apply_does_not_update_transient_rows():
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
    conn = FakeApplyConnection({
        (1001, 2008132031194): {'name': 'Harper Plant', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)

    assert applied == []
    assert skipped == []
    assert conn.statements == []
    assert report['association_changes'] == []


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


def test_exioce_stage17n2d_l_exact_edsm_metadata_and_links_ignore_legacy_distances():
    exioce_bodies = [
        {'id': 31, 'system_id64': 2008132031194, 'name': 'Exioce 3 d', 'distance_from_star': 590.0},
        {'id': 41, 'system_id64': 2008132031194, 'name': 'Exioce 4', 'distance_from_star': 1625.0},
        {'id': 51, 'system_id64': 2008132031194, 'name': 'Exioce 5 b', 'distance_from_star': 2220.0},
        {'id': 91, 'system_id64': 2008132031194, 'name': 'Experiment', 'distance_from_star': 20.0},
        {'id': 92, 'system_id64': 2008132031194, 'name': "O'Rourke Colony", 'distance_from_star': 40.0},
        {'id': 93, 'system_id64': 2008132031194, 'name': 'Democracy', 'distance_from_star': 60.0},
    ]
    report = probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[
            local_station(id=5001, market_id=5001, name='Macmillan Depot', station_type='Unknown', distance_from_star=20.0),
            local_station(id=5002, market_id=5002, name='Fort Lawrence', station_type='Unknown', distance_from_star=40.0),
            local_station(id=5003, market_id=5003, name='Miller Terminal', station_type='Unknown', distance_from_star=60.0),
            local_station(id=5004, market_id=5004, name='XFK-T4M', station_type='Unknown', distance_from_star=60.0),
        ],
        local_bodies=exioce_bodies,
        existing_links={},
        edsm_stations_payload={'stations': [
            {'id': 5001, 'name': 'Macmillan Depot', 'type': 'Orbis Starport', 'bodyName': 'Exioce 3 d', 'distanceToArrival': 592},
            {'id': 5002, 'name': 'Fort Lawrence', 'type': 'Orbis Starport', 'bodyName': 'Exioce 4', 'distanceToArrival': 1627},
            {'id': 5003, 'name': 'Miller Terminal', 'type': 'Coriolis Starport', 'bodyName': 'Exioce 5 b', 'distanceToArrival': 2219},
            {'id': 5004, 'name': 'XFK-T4M', 'type': 'Fleet Carrier', 'bodyName': 'Exioce 5 b', 'distanceToArrival': 2219},
        ]},
        edsm_bodies_payload={'bodies': []},
    )

    by_name = {station['local_station']['name']: station for station in report['stations']}

    assert by_name['Macmillan Depot']['proposed']['station_type'] == 'Orbis'
    assert by_name['Macmillan Depot']['proposed']['body_name'] == 'Exioce 3 d'
    assert by_name['Fort Lawrence']['proposed']['station_type'] == 'Orbis'
    assert by_name['Fort Lawrence']['proposed']['body_name'] == 'Exioce 4'
    assert by_name['Miller Terminal']['proposed']['station_type'] == 'Coriolis'
    assert by_name['Miller Terminal']['proposed']['body_name'] == 'Exioce 5 b'
    assert all(
        station['proposed']['association_status'] == 'confirmed'
        for name, station in by_name.items()
        if name != 'XFK-T4M'
    )
    assert {update['field'] for update in report['metadata_updates_planned']} == {
        'station_type',
        'distance_from_star',
        'body_name',
    }
    assert len(report['confirmed_link_updates_planned']) == 3
    assert len(report['association_changes']) == 3
    assert report['counts']['ignored_transient_non_slot'] == 1
    assert 'station_distance_mismatch' in conflict_types(by_name['Macmillan Depot'])
    assert by_name['XFK-T4M']['ignored_transient_non_slot'] is True


def test_metadata_apply_never_writes_association_changes():
    report = report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Orbis Starport',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )
    conn = FakeApplyConnection({
        (1001, 2008132031194): {'name': 'Harper Plant', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)

    assert report['association_changes']
    assert {row['field'] for row in applied} == {'station_type', 'distance_from_star', 'body_name'}
    assert skipped == []
    assert all('station_body_links' not in sql for sql, _params in conn.statements)
    assert conn.rows[(1001, 2008132031194)]['station_type'] == 'Orbis'
    assert conn.rows[(1001, 2008132031194)]['distance_source'] == 'edsm_system_api'
    assert conn.rows[(1001, 2008132031194)]['body_name_source'] == 'edsm_system_api'


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
    assert report['confirmed_link_updates_planned'][0]['association_source'] == 'edsm_body_name'


def test_apply_confirmed_links_writes_only_confirmed_edsm_body_name_links():
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
    conn = FakeApplyConnection({
        (1001, 2008132031194): {'name': 'Harper Plant', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_confirmed_link_updates(conn, report)
    probe.apply_confirmed_links_result(report, applied, skipped)

    assert skipped == []
    assert len(applied) == 1
    assert applied[0]['applied_link']['body_id'] == 11
    assert applied[0]['applied_link']['association_source'] == 'edsm_body_name'
    assert report['apply_mode'] == 'confirmed_links'


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


def test_conflicting_legacy_station_distance_reports_conflict_but_does_not_block_edsm_body_name():
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
    assert station['proposed']['association_status'] == 'confirmed'
    assert station['proposed']['body_id'] == 12
    assert report['association_changes'][0]['proposed_link']['association_status'] == 'confirmed'
    assert report['station_metadata_changes'][0]['proposed_station_type'] == 'Coriolis'
    assert report['conflicts'][0]['conflict']['type'] == 'station_distance_mismatch'


def test_metadata_apply_uses_edsm_distance_even_when_legacy_local_distance_mismatches():
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
    conn = FakeApplyConnection({
        (1001, 2008132031194): {'name': 'Harper Plant', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)

    assert {row['field'] for row in applied} == {'station_type', 'distance_from_star', 'body_name'}
    assert skipped == []
    assert conn.rows[(1001, 2008132031194)]['distance_from_star'] == 240.0
    assert conn.rows[(1001, 2008132031194)]['distance_source'] == 'edsm_system_api'
    assert not any(entry['reason'].startswith('conflicting_evidence') for entry in report['skipped'])
    assert report['counts']['station_write_suppressed_non_benign_conflict'] == 0


def test_known_station_type_mismatch_suppresses_all_station_metadata_writes():
    report = report_for(
        local_station(station_type='Coriolis', distance_from_star=12.0),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Orbis Starport',
            'distanceToArrival': 120.0,
        },
    )
    conn = FakeApplyConnection({
        (1001, 2008132031194): {'name': 'Harper Plant', 'station_type': 'Coriolis'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)

    assert applied == []
    assert skipped == []
    assert conn.rows[(1001, 2008132031194)]['station_type'] == 'Coriolis'
    assert 'distance_source' not in conn.rows[(1001, 2008132031194)]
    assert 'known_station_type_mismatch' in conflict_types(first_station(report))
    assert report['metadata_updates_planned'] == []
    assert report['counts']['station_write_suppressed_non_benign_conflict'] == 1
    assert suppression_entries(report)[0]['conflict_types'] == ['known_station_type_mismatch']
    assert suppression_entries(report)[0]['suppressed_write_fields'] == ['distance_from_star']


def test_station_economy_mismatch_suppresses_metadata_and_confirmed_link_writes():
    report = report_for(
        local_station(
            station_type='Outpost',
            distance_from_star=12.0,
            primary_economy='Colony',
        ),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Outpost',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
            'economy': 'Extraction',
        },
    )

    station = first_station(report)
    suppressed = suppression_entries(report)[0]

    assert 'station_economy_mismatch' in conflict_types(station)
    assert station['proposed']['association_status'] == 'confirmed'
    assert report['metadata_updates_planned'] == []
    assert report['confirmed_link_updates_planned'] == []
    assert report['counts']['station_write_suppressed_non_benign_conflict'] == 1
    assert suppressed['local_station']['id'] == 1001
    assert suppressed['local_station']['name'] == 'Harper Plant'
    assert suppressed['local_station']['system_id64'] == SYSTEM['id64']
    assert suppressed['conflict_types'] == ['station_economy_mismatch']
    assert suppressed['suppressed_write_fields'] == [
        'body_name',
        'distance_from_star',
        'station_body_links',
    ]


def test_id_name_mismatch_remains_unresolved_and_suppresses_writes():
    report = report_for(
        local_station(id=4001, market_id=4001, name='Harper Plant', station_type='Unknown'),
        {
            'id': 4001,
            'marketId': 4001,
            'name': 'Different Plant',
            'type': 'Orbis Starport',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    station = first_station(report)
    suppressed = suppression_entries(report)[0]

    assert station['station_match']['status'] == 'unresolved'
    assert 'id_name_mismatch' in conflict_types(station)
    assert report['metadata_updates_planned'] == []
    assert report['confirmed_link_updates_planned'] == []
    assert report['counts']['station_write_suppressed_non_benign_conflict'] == 1
    assert suppressed['conflict_types'] == ['id_name_mismatch']
    assert suppressed['suppressed_scopes'] == [
        'station_metadata',
        'body_name_metadata',
        'station_body_links',
    ]


def test_station_service_mismatch_does_not_block_trusted_metadata_writes():
    report = report_for(
        local_station(station_type='Unknown', has_market=True),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
            'haveMarket': False,
        },
    )

    station = first_station(report)

    assert 'station_service_mismatch' in conflict_types(station)
    assert report['counts']['station_write_suppressed_non_benign_conflict'] == 0
    assert {update['field'] for update in report['metadata_updates_planned']} == {
        'station_type',
        'distance_from_star',
        'body_name',
    }
    assert report['confirmed_link_updates_planned'][0]['association_source'] == 'edsm_body_name'


def test_unresolved_station_match_is_reported_and_not_applied():
    report = report_for(
        local_station(id=4001, market_id=4001, name='Unmatched Station', station_type='Unknown'),
        {
            'id': 9999,
            'name': 'Different Station',
            'type': 'Orbis Starport',
            'distanceToArrival': 120.0,
        },
    )
    conn = FakeApplyConnection({
        (4001, 2008132031194): {'name': 'Unmatched Station', 'station_type': 'Unknown'},
    })

    applied, skipped = probe.apply_metadata_updates(conn, report)

    assert applied == []
    assert skipped == []
    assert conn.statements == []
    assert report['unresolved'][0]['reason'] == 'No exact EDSM station id/name or unique station name match.'
    assert report['skipped'][0]['reason'] == 'unresolved_station_match'


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


def test_apply_metadata_requires_scoped_system_id64_before_db_or_network(capsys):
    result = probe.main(['--system-name', 'Exioce', '--dsn', 'postgresql://example', '--apply-metadata'])

    captured = capsys.readouterr()
    assert result == 2
    assert '--system-id64' in captured.err


def test_dry_run_and_apply_metadata_are_mutually_exclusive(capsys):
    result = probe.main([
        '--system-name', 'Exioce',
        '--system-id64', '2008132031194',
        '--dsn', 'postgresql://example',
        '--dry-run',
        '--apply-metadata',
    ])

    captured = capsys.readouterr()
    assert result == 2
    assert 'mutually exclusive' in captured.err
