import os
import sys
from pathlib import Path


os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
SCRIPTS = ROOT / 'scripts'
for path in (API_SRC, IMPORTER_SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import edsm_station_enrichment_probe as edsm_probe  # noqa: E402
import enrich_system_data as enrich  # noqa: E402
import repair_eddn_ring_identity as ring_repair  # noqa: E402
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


class MinimalBatchConnection:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def station_local_payload(system, *, station_id=None):
    station_id = station_id or int(system['id64'] % 100000)
    return {
        'system': dict(system),
        'stations': [local_station(
            id=station_id,
            market_id=station_id,
            system_id64=system['id64'],
            name='Harper Plant',
        )],
        'bodies': [{'id': station_id + 1, 'system_id64': system['id64'], 'name': f"{system['name']} 1"}],
        'existing_links': {},
    }


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


class RingRepairConnection:
    def __init__(self, *, bodies=None, body_rings=None, systems=None):
        self.bodies = list(bodies or [])
        self.body_rings = [dict(row) for row in (body_rings or [])]
        system_ids = set(systems or [])
        system_ids.update(row['system_id64'] for row in self.bodies)
        system_ids.update(row['system_id64'] for row in self.body_rings)
        self.systems = {
            int(system_id64): {'rating_dirty': False}
            for system_id64 in system_ids
        }
        self.statements = []
        self.last_row = None
        self.last_rows = []
        self.rowcount = -1
        self.commits = 0
        self.rollbacks = 0
        self.dirty_batches = []
        self.repair_update_batches = []

    def cursor(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        self.last_row = None
        self.last_rows = []
        self.rowcount = -1
        sql_lower = ' '.join(sql.lower().split())

        if sql_lower == 'set statement_timeout = 0':
            return

        if 'select count(*)::bigint as total' in sql_lower:
            self.last_row = self._summary()
            return

        if 'for update of br' in sql_lower:
            limit = params[0]
            rows = self._safe_candidates()
            self.last_rows = rows[:limit]
            return

        if 'repair_eddn_ring_identity:update_repair_batch' in sql_lower:
            ids, local_body_ids = params
            self.repair_update_batches.append(list(ids))
            local_by_id = dict(zip(ids, local_body_ids))
            updated = []
            for row in self.body_rings:
                if row['id'] not in local_by_id:
                    continue
                row['source_body_id'] = row.get('source_body_id')
                if row['source_body_id'] is None:
                    row['source_body_id'] = row.get('body_id')
                row['body_id'] = local_by_id[row['id']]
                updated.append((row['id'], row['system_id64']))
            self.last_rows = updated
            self.rowcount = len(updated)
            return

        if 'repair_eddn_ring_identity:mark_dirty_only_systems' in sql_lower:
            limit = params[0]
            ids = sorted({
                row['system_id64']
                for row in self.body_rings
                if row.get('source') == 'eddn_scan' and self._is_local_body_id(row)
            })
            self.last_rows = [(sid,) for sid in (ids[:limit] if limit else ids)]
            return

        if 'repair_eddn_ring_identity:mark_dirty' in sql_lower:
            ids = [int(value) for value in params[0]]
            self.dirty_batches.append(ids)
            changed = 0
            for system_id64 in ids:
                state = self.systems.setdefault(system_id64, {'rating_dirty': False})
                if state['rating_dirty'] is not True:
                    state['rating_dirty'] = True
                    changed += 1
            self.rowcount = changed
            return

        raise AssertionError(sql)

    def fetchone(self):
        return self.last_row

    def fetchall(self):
        return self.last_rows

    def ring(self, ring_id):
        return next(row for row in self.body_rings if row['id'] == ring_id)

    def _is_local_body_id(self, row):
        return any(
            body['system_id64'] == row['system_id64'] and body['id'] == row.get('body_id')
            for body in self.bodies
        )

    def _statuses(self):
        statuses = []
        for row in self.body_rings:
            if row.get('source') != 'eddn_scan':
                continue
            matches = [
                body for body in self.bodies
                if body['system_id64'] == row['system_id64']
                and body['name'] == row.get('body_name')
            ]
            local_body_id = min((body['id'] for body in matches), default=None)
            status = {
                **row,
                'match_count': len(matches),
                'local_body_id': local_body_id,
                'body_id_matches_local': self._is_local_body_id(row),
                'would_conflict': False,
            }
            statuses.append(status)

        target_counts = {}
        for status in statuses:
            if status['match_count'] == 1 and not status['body_id_matches_local']:
                key = (
                    status['system_id64'],
                    status['local_body_id'],
                    status.get('ring_name'),
                    status['source'],
                )
                target_counts[key] = target_counts.get(key, 0) + 1

        for status in statuses:
            existing_conflict = any(
                other['id'] != status['id']
                and other['system_id64'] == status['system_id64']
                and other.get('body_id') == status['local_body_id']
                and other.get('source') == status['source']
                and other.get('ring_name') == status.get('ring_name')
                for other in self.body_rings
            )
            key = (
                status['system_id64'],
                status['local_body_id'],
                status.get('ring_name'),
                status['source'],
            )
            status['would_conflict'] = existing_conflict or target_counts.get(key, 0) > 1
        return statuses

    def _summary(self):
        statuses = self._statuses()
        would_update = [
            status for status in statuses
            if status['match_count'] == 1
            and not status['body_id_matches_local']
            and not status['would_conflict']
        ]
        would_conflict = [
            status for status in statuses
            if status['match_count'] == 1
            and not status['body_id_matches_local']
            and status['would_conflict']
        ]
        return {
            'total': len(statuses),
            'already_local_bigint': sum(1 for status in statuses if status['body_id_matches_local']),
            'matched_by_name': sum(1 for status in statuses if status['match_count'] == 1),
            'ambiguous_name': sum(1 for status in statuses if status['match_count'] > 1),
            'unmatched': sum(1 for status in statuses if status['match_count'] == 0),
            'would_conflict': len(would_conflict),
            'would_ignore': len(statuses) - len(would_update),
            'would_update': len(would_update),
        }

    def _safe_candidates(self):
        def text_key(value):
            return (value is None, '' if value is None else value)

        def source_body_id_key(value):
            return (value is None, 0 if value is None else value)

        rows = [
            {
                'id': status['id'],
                'system_id64': status['system_id64'],
                'old_body_id': status.get('body_id'),
                'source_body_id': status.get('source_body_id'),
                'local_body_id': status['local_body_id'],
                'body_name': status.get('body_name'),
                'ring_name': status.get('ring_name'),
            }
            for status in self._statuses()
            if status['match_count'] == 1
            and not status['body_id_matches_local']
            and not status['would_conflict']
        ]
        return sorted(
            rows,
            key=lambda row: (
                row['system_id64'],
                text_key(row.get('body_name')),
                text_key(row.get('ring_name')),
                source_body_id_key(row.get('source_body_id')),
                row['id'],
            ),
        )


def _repair_args(*extra):
    return ring_repair.parse_args(['--dsn', 'postgresql://test/test', *extra])


def _repair_fixture_connection():
    return RingRepairConnection(
        bodies=[
            {'id': 100, 'system_id64': 1, 'name': 'Alpha 1'},
            {'id': 200, 'system_id64': 2, 'name': 'Ambiguous 1'},
            {'id': 201, 'system_id64': 2, 'name': 'Ambiguous 1'},
            {'id': 300, 'system_id64': 3, 'name': 'Conflict 1'},
            {'id': 400, 'system_id64': 4, 'name': 'Local 1'},
        ],
        body_rings=[
            {
                'id': 1,
                'system_id64': 1,
                'body_id': 7,
                'source_body_id': None,
                'body_name': 'Alpha 1',
                'ring_name': 'Alpha 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 2,
                'system_id64': 2,
                'body_id': 8,
                'source_body_id': None,
                'body_name': 'Ambiguous 1',
                'ring_name': 'Ambiguous 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 3,
                'system_id64': 3,
                'body_id': 9,
                'source_body_id': None,
                'body_name': 'Conflict 1',
                'ring_name': 'Conflict 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 4,
                'system_id64': 3,
                'body_id': 300,
                'source_body_id': 9,
                'body_name': 'Conflict 1',
                'ring_name': 'Conflict 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 5,
                'system_id64': 5,
                'body_id': 10,
                'source_body_id': None,
                'body_name': 'Missing 1',
                'ring_name': 'Missing 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 6,
                'system_id64': 4,
                'body_id': 400,
                'source_body_id': 12,
                'body_name': 'Local 1',
                'ring_name': 'Local 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 7,
                'system_id64': 1,
                'body_id': 7,
                'source_body_id': None,
                'body_name': 'Alpha 1',
                'ring_name': 'Alpha 1 A Ring',
                'source': 'spansh_dump',
            },
        ],
    )


def test_repair_eddn_ring_identity_dry_run_default_writes_nothing():
    conn = _repair_fixture_connection()

    report = ring_repair.run(conn, _repair_args())

    assert report['mode'] == 'dry-run'
    assert report['total'] == 6
    assert report['would_update'] == 1
    assert report['updated'] == 0
    assert conn.ring(1)['body_id'] == 7
    assert conn.ring(1)['source_body_id'] is None
    assert conn.repair_update_batches == []
    assert conn.dirty_batches == []
    assert conn.statements[0][0] == 'SET statement_timeout = 0'


def test_repair_eddn_ring_identity_apply_repairs_only_safe_exact_matches():
    conn = _repair_fixture_connection()

    report = ring_repair.run(conn, _repair_args('--apply', '--batch-size', '10'))

    assert report['updated'] == 1
    assert report['batches'] == 1
    assert report['before'] == {
        'total': 6,
        'already_local_bigint': 2,
        'matched_by_name': 4,
        'ambiguous_name': 1,
        'unmatched': 1,
        'would_conflict': 1,
        'would_ignore': 5,
        'would_update': 1,
    }
    assert conn.ring(1)['body_id'] == 100
    assert conn.ring(1)['source_body_id'] == 7
    assert conn.ring(2)['body_id'] == 8
    assert conn.ring(3)['body_id'] == 9
    assert conn.ring(5)['body_id'] == 10
    assert conn.ring(7)['body_id'] == 7
    assert conn.dirty_batches == [[1]]
    assert conn.systems[1]['rating_dirty'] is True
    assert not any('body_scan_facts' in sql.lower() for sql, _params in conn.statements)


def test_repair_eddn_ring_identity_preserves_existing_source_body_id():
    conn = RingRepairConnection(
        bodies=[{'id': 100, 'system_id64': 1, 'name': 'Alpha 1'}],
        body_rings=[{
            'id': 1,
            'system_id64': 1,
            'body_id': 7,
            'source_body_id': 7007,
            'body_name': 'Alpha 1',
            'ring_name': 'Alpha 1 A Ring',
            'source': 'eddn_scan',
        }],
    )

    report = ring_repair.run(conn, _repair_args('--apply', '--batch-size', '10'))

    assert report['updated'] == 1
    assert conn.ring(1)['body_id'] == 100
    assert conn.ring(1)['source_body_id'] == 7007


def test_repair_eddn_ring_identity_batches_multiple_batches_and_limit():
    conn = RingRepairConnection(
        bodies=[
            {'id': 1000 + index, 'system_id64': index, 'name': f'System {index} 1'}
            for index in range(1, 6)
        ],
        body_rings=[
            {
                'id': index,
                'system_id64': index,
                'body_id': 10 + index,
                'source_body_id': None,
                'body_name': f'System {index} 1',
                'ring_name': f'System {index} 1 A Ring',
                'source': 'eddn_scan',
            }
            for index in range(1, 6)
        ],
    )

    report = ring_repair.run(
        conn,
        _repair_args('--apply', '--batch-size', '2', '--limit', '3', '--skip-dirty'),
    )

    assert report['updated'] == 3
    assert report['batches'] == 2
    assert conn.repair_update_batches == [[1, 2], [3]]
    assert [conn.ring(index)['body_id'] for index in range(1, 6)] == [
        1001,
        1002,
        1003,
        14,
        15,
    ]
    assert report['after']['would_update'] == 2


def test_repair_eddn_ring_identity_skip_dirty_avoids_dirty_marking():
    conn = _repair_fixture_connection()

    report = ring_repair.run(conn, _repair_args('--apply', '--skip-dirty'))

    assert report['updated'] == 1
    assert report['skipped_dirty'] is True
    assert report['dirty_systems_marked'] == 0
    assert conn.dirty_batches == []
    assert conn.systems[1]['rating_dirty'] is False


def test_repair_eddn_ring_identity_dirty_marking_uses_sorted_batches():
    conn = RingRepairConnection(
        bodies=[
            {'id': 100, 'system_id64': 30, 'name': 'Gamma 1'},
            {'id': 200, 'system_id64': 10, 'name': 'Alpha 1'},
            {'id': 300, 'system_id64': 20, 'name': 'Beta 1'},
        ],
        body_rings=[
            {
                'id': 1,
                'system_id64': 30,
                'body_id': 1,
                'source_body_id': None,
                'body_name': 'Gamma 1',
                'ring_name': 'Gamma 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 2,
                'system_id64': 10,
                'body_id': 2,
                'source_body_id': None,
                'body_name': 'Alpha 1',
                'ring_name': 'Alpha 1 A Ring',
                'source': 'eddn_scan',
            },
            {
                'id': 3,
                'system_id64': 20,
                'body_id': 3,
                'source_body_id': None,
                'body_name': 'Beta 1',
                'ring_name': 'Beta 1 A Ring',
                'source': 'eddn_scan',
            },
        ],
    )

    report = ring_repair.run(conn, _repair_args('--apply', '--batch-size', '2'))

    assert report['updated'] == 3
    assert conn.repair_update_batches == [[2, 3], [1]]
    assert conn.dirty_batches == [[10, 20], [30]]
    assert report['dirty_systems_marked'] == 3


def test_repair_eddn_ring_identity_repeated_apply_is_idempotent():
    conn = _repair_fixture_connection()

    first = ring_repair.run(conn, _repair_args('--apply', '--batch-size', '10'))
    second = ring_repair.run(conn, _repair_args('--apply', '--batch-size', '10'))

    assert first['updated'] == 1
    assert second['updated'] == 0
    assert second['batches'] == 0
    assert second['dirty_systems_marked'] == 0
    assert conn.ring(1)['body_id'] == 100
    assert conn.ring(1)['source_body_id'] == 7


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


def test_station_fetch_timeout_exhaustion_reports_failure_without_writes(monkeypatch):
    args = enrich.parse_args([
        '--stations',
        '--system-id64', str(SYSTEM['id64']),
        '--apply-confirmed-links',
        '--mark-dirty',
    ])
    apply_calls = []

    def fail_fetch(_name, **_kwargs):
        raise TimeoutError('The read operation timed out')

    monkeypatch.setattr(edsm_probe, 'fetch_local_payload', lambda *_args, **_kwargs: station_local_payload(SYSTEM))
    monkeypatch.setattr(
        edsm_probe,
        'apply_confirmed_link_updates',
        lambda *_args, **_kwargs: apply_calls.append(True) or ([], []),
    )

    report = enrich.process_station_system(
        MinimalBatchConnection(),
        SYSTEM,
        args=args,
        dry_run=False,
        edsm_fetcher=fail_fetch,
        sleep=lambda _seconds: None,
    )

    assert report['fetch_failed'] is True
    assert report['fetch_errors'][0]['reason'] == 'edsm_fetch_failed'
    assert report['systems_fetch_failed'] == [{'id64': SYSTEM['id64'], 'name': SYSTEM['name']}]
    assert report['confirmed_link_updates_applied'] == []
    assert apply_calls == []


def test_apply_confirmed_links_skips_failed_system_and_applies_valid_systems(monkeypatch):
    systems = [
        {'id64': 1, 'name': 'Timeout System'},
        {'id64': 2, 'name': 'Valid System'},
    ]
    conn = MinimalBatchConnection()
    applied_systems = []
    dirty_batches = []

    def local_payload(_conn, *, system_name=None, system_id64=None):
        system = next(row for row in systems if row['id64'] == system_id64 or row['name'] == system_name)
        return station_local_payload(system)

    def fetcher(system_name, **_kwargs):
        if system_name == 'Timeout System':
            raise edsm_probe.EdsmFetchError(
                'EDSM stations fetch failed for timeout system',
                system_name=system_name,
                system_id64=1,
                endpoint='stations',
                attempts=2,
                reason='The read operation timed out',
            )
        return {
            'stations': {'stations': [{
                'id': 2,
                'name': 'Harper Plant',
                'type': 'Coriolis Starport',
                'bodyName': 'Valid System 1',
                'distanceToArrival': 120.0,
            }]},
            'bodies': {'bodies': []},
        }

    def apply_links(_conn, report):
        applied_systems.append(report['system']['id64'])
        return ([{'system_id64': report['system']['id64'], 'station_id': 2}], [])

    monkeypatch.setattr(enrich, 'select_station_systems', lambda _conn, _args: systems)
    monkeypatch.setattr(edsm_probe, 'fetch_local_payload', local_payload)
    monkeypatch.setattr(edsm_probe, 'apply_confirmed_link_updates', apply_links)
    monkeypatch.setattr(enrich, 'mark_systems_rating_dirty', lambda _conn, ids: dirty_batches.append(list(ids)) or len(ids))

    args = enrich.parse_args([
        '--stations',
        '--limit', '2',
        '--apply-confirmed-links',
        '--mark-dirty',
    ])
    report = enrich.run(args, connect=lambda _dsn: conn, edsm_fetcher=fetcher, sleep=lambda _seconds: None)

    assert applied_systems == [2]
    assert report['stations']['systems_fetch_failed'] == [{'id64': 1, 'name': 'Timeout System'}]
    assert report['summary']['stations']['systems_fetch_failed'] == 1
    assert report['summary']['stations']['fetch_errors'] == 1
    assert report['summary']['stations']['applied'] == 1
    assert dirty_batches == [[2]]
    assert conn.committed is True


def test_json_report_includes_fetch_error_summary():
    report = enrich._new_report(
        enrich.parse_args(['--stations', '--system-id64', str(SYSTEM['id64'])]),
        dry_run=True,
    )
    enrich._merge_station_report(report, {
        'system': SYSTEM,
        'counts': {'fetch_errors': 1, 'systems_fetch_failed': 1},
        'fetch_errors': [{
            'system': SYSTEM,
            'system_id64': SYSTEM['id64'],
            'system_name': SYSTEM['name'],
            'reason': 'edsm_fetch_failed',
            'message': 'The read operation timed out',
        }],
        'systems_fetch_failed': [SYSTEM],
        'fetch_failed': True,
        'dirty_system_ids': [],
    })
    enrich._finalise_report(report)

    payload = enrich.json.dumps(report, default=enrich._json_default)

    assert '"fetch_errors"' in payload
    assert report['summary']['fetch_errors'] == 1
    assert report['summary']['systems_fetch_failed'] == 1


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
