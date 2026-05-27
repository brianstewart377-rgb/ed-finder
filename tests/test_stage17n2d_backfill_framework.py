import os
import sys
from pathlib import Path


os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
for path in (API_SRC, IMPORTER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import edsm_station_enrichment_probe as edsm_probe  # noqa: E402
import enrich_system_data as enrich  # noqa: E402
from ingest.journal_normaliser import normalise_scan_event  # noqa: E402


SYSTEM = {'id64': 2008132031194, 'name': 'Exioce'}
BIG_BODY_ID = 576462760435454682
BODIES = [
    {'id': 10, 'system_id64': 2008132031194, 'name': 'Exioce', 'distance_from_star': 0.0},
    {'id': 11, 'system_id64': 2008132031194, 'name': 'Exioce 1', 'distance_from_star': 120.0},
]
BIG_BODIES = [
    {'id': BIG_BODY_ID, 'system_id64': 2008132031194, 'name': 'Exioce 3', 'distance_from_star': 350.0},
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


def station_report_for(station, edsm_station, *, bodies=None):
    return edsm_probe.build_enrichment_report(
        local_system=SYSTEM,
        local_stations=[station],
        local_bodies=bodies or BODIES,
        existing_links={},
        edsm_stations_payload={'stations': [edsm_station]},
        edsm_bodies_payload={'bodies': []},
    )


class RingApplyConnection:
    def __init__(self):
        self.rings = {}
        self.scan_facts = {}
        self.statements = []
        self.last_row = None
        self.last_rows = []
        self.committed = False
        self.rolled_back = False

    def cursor(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        self.last_row = None
        self.last_rows = []
        sql_lower = ' '.join(sql.lower().split())
        if 'select id64, name from systems where id64 = %s' in sql_lower:
            if params and params[0] == SYSTEM['id64']:
                self.last_rows = [SYSTEM]
            return

        if 'from bodies' in sql_lower and 'where system_id64 = %s' in sql_lower:
            self.last_rows = BIG_BODIES if params and params[0] == SYSTEM['id64'] else []
            return

        if 'insert into body_rings' in sql_lower:
            (
                system_id64,
                body_id,
                body_name,
                ring_name,
                ring_type,
                ring_class,
                mass_mt,
                inner_radius,
                outer_radius,
                source,
                confidence,
            ) = params
            key = (system_id64, body_id, ring_name, source)
            next_row = {
                'system_id64': system_id64,
                'body_id': body_id,
                'body_name': body_name,
                'ring_name': ring_name,
                'ring_type': ring_type,
                'ring_class': ring_class,
                'mass_mt': mass_mt,
                'inner_radius': inner_radius,
                'outer_radius': outer_radius,
                'source': source,
                'confidence': confidence,
            }
            if self.rings.get(key) == next_row:
                self.last_row = None
                return
            self.rings[key] = next_row
            self.last_row = {
                'system_id64': system_id64,
                'body_id': body_id,
                'body_name': body_name,
                'ring_name': ring_name,
                'source': source,
                'confidence': confidence,
            }
            return

        if 'insert into body_scan_facts' in sql_lower:
            system_id64, body_id, body_name, source, confidence = params
            assert -(2**31) <= body_id <= 2**31 - 1
            key = (system_id64, body_id)
            existing = self.scan_facts.get(key)
            if existing and existing['is_ringed'] is True and source in existing['data_sources']:
                self.last_row = None
                return
            data_sources = sorted(set((existing or {}).get('data_sources', []) + [source]))
            row = {
                'system_id64': system_id64,
                'body_id': body_id,
                'body_name': body_name,
                'is_ringed': True,
                'data_sources': data_sources,
                'confidence': confidence,
            }
            self.scan_facts[key] = row
            self.last_row = row
            return

        raise AssertionError(sql)

    def fetchone(self):
        return self.last_row

    def fetchall(self):
        return self.last_rows


def test_dry_run_ring_plan_writes_nothing():
    conn = RingApplyConnection()

    report = enrich.process_ring_system_payload(
        conn,
        {'bodies': [{'id': 11, 'name': 'Exioce 1', 'rings': [{'name': 'Exioce 1 A Ring'}]}]},
        system=SYSTEM,
        local_bodies=BODIES,
        source='spansh',
        dry_run=True,
        apply_rings=False,
    )

    assert report['counts']['ring_rows_planned'] == 1
    assert report['applied'] == []
    assert conn.statements == []


def test_apply_flags_require_explicit_dirty_marking():
    args = enrich.parse_args([
        '--rings',
        '--source', 'spansh',
        '--spansh-file', '/tmp/spansh.json',
        '--limit', '1',
        '--apply-rings',
    ])

    assert 'Apply flags require --mark-dirty' in '\n'.join(enrich.validate_args(args))


def test_main_failure_reporting_uses_sys_stderr_without_name_error(monkeypatch, capsys):
    def fail(_args):
        raise RuntimeError('boom')

    monkeypatch.setattr(enrich, 'run', fail)
    code = enrich.main(['--rings', '--source', 'edsm', '--system-id64', str(SYSTEM['id64'])])
    captured = capsys.readouterr()
    assert code == 1
    assert 'enrich_system_data failed: boom' in captured.err


def test_station_metadata_batch_plans_trusted_edsm_updates():
    report = station_report_for(
        local_station(station_type='Unknown', distance_from_star=20.0),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Orbis Starport',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    planned_fields = {update['field'] for update in report['metadata_updates_planned']}

    assert planned_fields == {'station_type', 'distance_from_star', 'body_name'}
    assert report['confirmed_link_updates_planned'][0]['association_source'] == 'edsm_body_name'
    assert report['conflicts'][0]['conflict']['type'] == 'station_distance_mismatch'


def test_confirmed_links_require_exact_local_body_name_match():
    report = station_report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Coriolis Starport',
            'bodyName': 'Exioce Missing',
            'distanceToArrival': 120.0,
        },
    )

    assert report['confirmed_link_updates_planned'] == []
    assert report['metadata_updates_planned'][0]['field'] == 'station_type'
    assert any(entry['conflict']['type'] == 'edsm_body_name_not_found_locally' for entry in report['conflicts'])


def test_fleet_carriers_are_ignored_for_colony_slot_links():
    report = station_report_for(
        local_station(station_type='Unknown'),
        {
            'id': 1001,
            'name': 'Harper Plant',
            'type': 'Fleet Carrier',
            'bodyName': 'Exioce 1',
            'distanceToArrival': 120.0,
        },
    )

    assert report['association_changes'] == []
    assert report['confirmed_link_updates_planned'] == []
    assert report['ignored_transient_non_slot'][0]['body_evidence']['body_name'] == 'Exioce 1'


def test_spansh_ring_payload_plans_trusted_body_ring_rows():
    plan = enrich.build_ring_plan(
        system=SYSTEM,
        local_bodies=BODIES,
        source_payload={'bodies': [{
            'id': 11,
            'name': 'Exioce 1',
            'rings': [{'name': 'Exioce 1 A Ring', 'type': 'Icy', 'outerRadius': 25}],
        }]},
        source='spansh',
    )

    assert plan['conflicts'] == []
    assert plan['rows'] == [{
        'system_id64': 2008132031194,
        'body_id': 11,
        'body_name': 'Exioce 1',
        'ring_name': 'Exioce 1 A Ring',
        'ring_type': 'Icy',
        'ring_class': None,
        'mass_mt': None,
        'inner_radius': None,
        'outer_radius': 25.0,
        'source': 'spansh_dump',
        'confidence': 'source_ring_payload',
    }]


def test_missing_ring_payload_remains_unknown_not_false():
    plan = enrich.build_ring_plan(
        system=SYSTEM,
        local_bodies=BODIES,
        source_payload={'bodies': [{'id': 11, 'name': 'Exioce 1'}]},
        source='spansh',
    )

    assert plan['rows'] == []
    assert plan['skipped'][0]['reason'] == 'missing_ring_array_unknown'
    assert plan['counts']['missing_ring_array_unknown'] == 1


def test_explicit_no_rings_full_scan_sets_false():
    fact = normalise_scan_event({
        'SystemAddress': 2008132031194,
        'BodyID': 11,
        'BodyName': 'Exioce 1',
        'PlanetClass': 'Rocky body',
        'Rings': [],
    })

    assert fact['is_ringed'] is False
    assert fact['rings'] == []


def test_bigint_ring_apply_writes_body_rings_and_skips_scan_facts():
    conn = RingApplyConnection()

    report = enrich.process_ring_system_payload(
        conn,
        {'bodies': [{'name': 'Exioce 3', 'rings': [{
            'name': 'Exioce 3 A Ring',
            'type': 'Metal Rich',
            'mass': 123.0,
            'innerRadius': 10,
            'outerRadius': 20,
        }]}]},
        system=SYSTEM,
        local_bodies=BIG_BODIES,
        source='edsm',
        dry_run=False,
        apply_rings=True,
    )

    assert report['applied'] == [{
        'system_id64': 2008132031194,
        'body_id': BIG_BODY_ID,
        'body_name': 'Exioce 3',
        'ring_name': 'Exioce 3 A Ring',
        'source': edsm_probe.TRUSTED_EDSM_SOURCE,
        'confidence': 'source_ring_payload',
    }]
    ring_key = (2008132031194, BIG_BODY_ID, 'Exioce 3 A Ring', edsm_probe.TRUSTED_EDSM_SOURCE)
    assert conn.rings[ring_key]['body_id'] == BIG_BODY_ID
    assert conn.rings[ring_key]['ring_type'] == 'Metal Rich'
    assert conn.rings[ring_key]['mass_mt'] == 123.0
    assert report['scan_fact_applied'] == []
    assert report['scan_fact_skipped'] == [{
        'system_id64': 2008132031194,
        'body_id': BIG_BODY_ID,
        'body_name': 'Exioce 3',
        'reason': 'body_scan_facts_body_id_schema_mismatch',
    }]
    assert not any('INSERT INTO body_scan_facts' in sql for sql, _params in conn.statements)
    assert report['dirty_system_ids'] == [2008132031194]


def test_ring_apply_is_idempotent_without_duplicate_body_rings():
    conn = RingApplyConnection()
    payload = {'bodies': [{'name': 'Exioce 3', 'rings': [{'name': 'Exioce 3 A Ring'}]}]}

    first = enrich.process_ring_system_payload(
        conn,
        payload,
        system=SYSTEM,
        local_bodies=BIG_BODIES,
        source='edsm',
        dry_run=False,
        apply_rings=True,
    )
    second = enrich.process_ring_system_payload(
        conn,
        payload,
        system=SYSTEM,
        local_bodies=BIG_BODIES,
        source='edsm',
        dry_run=False,
        apply_rings=True,
    )

    assert len(first['applied']) == 1
    assert first['scan_fact_applied'] == []
    assert len(first['scan_fact_skipped']) == 1
    assert first['dirty_system_ids'] == [2008132031194]
    assert second['applied'] == []
    assert second['scan_fact_applied'] == []
    assert len(second['scan_fact_skipped']) == 1
    assert second['dirty_system_ids'] == []
    assert len(conn.rings) == 1


def test_run_mark_dirty_path_is_called_for_applied_rings(monkeypatch):
    conn = RingApplyConnection()
    marked = []

    def mark_dirty(_conn, system_ids):
        marked.extend(system_ids)
        return len(system_ids)

    monkeypatch.setattr(enrich, 'mark_systems_rating_dirty', mark_dirty)
    args = enrich.parse_args([
        '--rings',
        '--system-id64', str(SYSTEM['id64']),
        '--source', 'edsm',
        '--apply-rings',
        '--mark-dirty',
    ])

    report = enrich.run(
        args,
        connect=lambda _dsn: conn,
        edsm_fetcher=lambda _name, timeout=None: {
            'bodies': {'bodies': [{'name': 'Exioce 3', 'rings': [{'name': 'Exioce 3 A Ring'}]}]},
        },
        sleep=lambda _seconds: None,
    )

    assert marked == [2008132031194]
    assert report['dirty']['marked'] == 1
    assert conn.committed is True


def test_json_summary_includes_station_and_ring_counts():
    report = enrich._new_report(
        enrich.parse_args(['--rings', '--source', 'spansh', '--spansh-file', '/tmp/spansh.json']),
        dry_run=True,
    )
    enrich._merge_ring_report(report, {
        'system': {'id64': 2008132031194, 'name': 'Exioce'},
        'rows': [{'system_id64': 2008132031194}],
        'applied': [],
        'scan_fact_applied': [],
        'scan_fact_skipped': [{'reason': 'body_scan_facts_body_id_schema_mismatch'}],
        'skipped': [{'reason': 'missing_ring_array_unknown'}],
        'apply_skipped': [],
        'conflicts': [{'type': 'body_id_name_mismatch'}],
        'counts': {'ring_rows_planned': 1},
        'dirty_system_ids': [],
    })

    enrich._finalise_report(report)

    assert set(report['summary']) >= {'stations', 'rings', 'conflicts'}
    assert report['summary']['rings']['planned'] == 1
    assert report['summary']['rings']['scan_fact_skipped'] == 1
    assert report['summary']['rings']['skipped'] == 1
    assert report['summary']['rings']['conflicts'] == 1
