from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'

if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import backfill_station_body_links as script  # noqa: E402


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, tuple(params or ())))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)


class _FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.cursors: list[_FakeCursor] = []

    def cursor(self, cursor_factory=None):  # noqa: ARG002
        cursor = _FakeCursor(self.rows)
        self.cursors.append(cursor)
        return cursor


def test_build_station_set_evidence_payload_reflects_station_link_coverage():
    conn = _FakeConnection([
        {
            'id64': 42,
            'system_name': 'Test System',
            'station_count': 4,
            'linked_station_count': 3,
            'observed_at': '2026-07-11T12:00:00+00:00',
        }
    ])

    payload = script.build_station_set_evidence_payload(conn, 42)

    assert payload is not None
    assert payload['source_name'] == 'canonical_app_data'
    assert payload['evidence_type'] == 'station_set'
    assert payload['value']['station_count'] == 4
    assert payload['value']['linked_station_count'] == 3
    assert payload['value']['unresolved_station_count'] == 1
    assert payload['provenance']['trigger_context'] == 'station_body_link_backfill'
    assert payload['summary'] == (
        'Canonical station data for Test System currently includes 4 stations; '
        '3/4 local station-body links are matched.'
    )
    assert payload['evidence_key'].startswith('evd_')


def test_promote_station_set_evidence_dedupes_equivalent_active_record():
    conn = _FakeConnection([
        {
            'id64': 42,
            'system_name': 'Test System',
            'station_count': 4,
            'linked_station_count': 4,
            'observed_at': '2026-07-11T12:00:00+00:00',
        },
        {
            'value_json': {
                'system_name': 'Test System',
                'station_count': 4,
                'linked_station_count': 4,
                'unresolved_station_count': 0,
                'station_link_runtime_available': True,
            },
            'summary': (
                'Canonical station data for Test System currently includes 4 stations; '
                '4/4 local station-body links are matched.'
            ),
            'confidence': 'high',
            'origin': 'derived',
            'freshness_status': 'current',
        },
    ])

    result = script.promote_station_set_evidence(conn, 42)

    assert result == 'deduped'
    executed = conn.cursors[-1].executed
    assert any('FROM evidence_records' in query for query, _ in executed)
    assert not any('INSERT INTO evidence_records' in query for query, _ in executed)
