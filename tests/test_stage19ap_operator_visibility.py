import inspect
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
API_ROUTERS = API_SRC / 'routers'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
if str(API_ROUTERS) not in sys.path:
    sys.path.insert(0, str(API_ROUTERS))
os.environ.setdefault('CORS_ORIGINS', 'http://localhost')

import operator_visibility as visibility  # noqa: E402

_ROUTER_SPEC = importlib.util.spec_from_file_location(
    'stage19ap_operator_router',
    API_ROUTERS / 'operator.py',
)
operator_router = importlib.util.module_from_spec(_ROUTER_SPEC)
assert _ROUTER_SPEC.loader is not None
_ROUTER_SPEC.loader.exec_module(operator_router)


class FakeAsyncTransaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakePoolAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakePoolAcquire(self.conn)


def source_run(**overrides):
    row = {
        'id': 101,
        'source_run_key': 'stage19anr-run',
        'source_name': 'edsm',
        'source_category': 'source_of_evidence',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'status': 'succeeded',
        'source_uri': 'file:///tmp/edsm-stations.json',
        'source_input_sha256': 'a' * 64,
        'source_manifest_sha256': None,
        'started_at': '2026-06-06T10:00:00Z',
        'finished_at': '2026-06-06T10:01:00Z',
        'duration_ms': 60000,
        'git_commit_sha': 'abc1234',
        'importer_name': 'stage_19t_edsm_station_import_mvp',
        'importer_version': 'v1',
        'trigger_context': 'unit_test',
        'artifact_path': '/var/lib/ed-finder/operator-artifacts/stage19anr-import.json',
        'artifact_sha256': 'b' * 64,
        'artifact_integrity_sha256': 'c' * 64,
        'rows_read': 5,
        'rows_staged': 5,
        'rows_rejected': 0,
        'rows_skipped': 0,
        'error_code': None,
        'error_summary': None,
        'safety_boundary': {
            'canonical_writes_planned': 0,
            'canonical_apply_enabled': False,
        },
        'metadata': {
            'stage': '19t',
            'artifact_record': {
                'path': '/var/lib/ed-finder/operator-artifacts/stage19anr-import.json',
                'file_sha256': 'b' * 64,
                'artifact_integrity_sha256': 'c' * 64,
                'bytes_written': 1234,
            },
        },
    }
    row.update(overrides)
    return row


def legacy_bridge(**overrides):
    row = {
        'id': 701,
        'source_run_key': 'source_runs:stage19anr-run',
        'dry_run': False,
        'adapter_name': 'stage19anr_warehouse_derived_compatible_stager',
        'adapter_version': 'v1',
        'metadata': {
            'schema_version': visibility.BRIDGE_SCHEMA_VERSION,
            'compatibility_bridge': True,
            'target_staging_fk': visibility.TARGET_STAGING_FK,
            'source_runs_provenance': {
                'id': 101,
                'source_run_key': 'stage19anr-run',
            },
            'staging_policy': {
                'do_not_pass_source_runs_id_to_legacy_staging_source_run_id': True,
                'legacy_source_run_id_required_for_legacy_staging': True,
            },
        },
    }
    row.update(overrides)
    return row


def staging_row(index=1, **overrides):
    row = {
        'id': 900 + index,
        'source_run_id': 701,
        'station_name': f'Stage 19 Port {index}',
        'station_type': 'Coriolis Starport',
        'system_name': f'Stage 19 System {index}',
        'source_class': 'diagnostic-only',
        'confidence': 'diagnostic-only',
        'provenance': {
            'canonical_write_allowed': False,
            'stage19anr_diagnostic_mark': {'source_run_key': 'stage19anr-run'},
        },
        'raw_payload': {'full': 'payload must not be returned'},
    }
    row.update(overrides)
    return row


class FakeAsyncConn:
    def __init__(self, *, source_runs=None, legacy_rows=None, staging_rows=None):
        self.source_runs = list(source_runs or [])
        self.legacy_rows = list(legacy_rows or [])
        self.staging_rows = list(staging_rows or [])
        self.statements = []

    def transaction(self, readonly=False):
        return FakeAsyncTransaction()

    async def fetch(self, sql, *params):
        self.statements.append((sql, params))
        compact = ' '.join(sql.lower().split())

        if 'operator_visibility:list_recent_source_runs' in compact:
            limit = int(params[-1])
            rows = list(self.source_runs)
            rows.sort(key=lambda row: (row['started_at'], row['id']), reverse=True)
            return [self._source_run_summary_row(row) for row in rows[:limit]]

        if 'operator_visibility:get_staging_impact_for_bridge:sample' in compact:
            legacy_id, limit = params
            rows = [row for row in self.staging_rows if row['source_run_id'] == legacy_id]
            rows.sort(key=lambda row: row['id'])
            return [self._staging_projection(row) for row in rows[:int(limit)]]

        if 'operator_visibility:list_diagnostic_staging_rows:by_source_run' in compact:
            legacy_id, marker_key, limit = params
            rows = [
                row for row in self.staging_rows
                if row['source_run_id'] == legacy_id and self._is_diagnostic(row, marker_key)
            ]
            rows.sort(key=lambda row: row['id'], reverse=True)
            return [self._staging_projection(row) for row in rows[:int(limit)]]

        if 'operator_visibility:list_diagnostic_staging_rows' in compact:
            marker_key, limit = params
            rows = [row for row in self.staging_rows if self._is_diagnostic(row, marker_key)]
            rows.sort(key=lambda row: row['id'], reverse=True)
            return [self._staging_projection(row) for row in rows[:int(limit)]]

        raise AssertionError(f'unexpected fetch SQL: {sql}')

    async def fetchrow(self, sql, *params):
        self.statements.append((sql, params))
        compact = ' '.join(sql.lower().split())

        if 'operator_visibility:get_source_run_detail' in compact:
            row = self._source_run_by_key(params[0])
            return self._source_run_detail_row(row) if row else None

        if 'operator_visibility:get_source_run_artifacts' in compact:
            row = self._source_run_by_key(params[0])
            if row is None:
                return None
            return {
                key: row.get(key)
                for key in (
                    'source_run_key',
                    'status',
                    'artifact_path',
                    'artifact_sha256',
                    'artifact_integrity_sha256',
                    'rows_read',
                    'rows_staged',
                    'metadata',
                )
            }

        if 'operator_visibility:get_legacy_bridge_for_source_run' in compact:
            return self._legacy_by_key(params[0])

        if 'operator_visibility:get_bridge_by_legacy_id' in compact:
            return self._legacy_by_id(params[0])

        if 'operator_visibility:get_source_runs_id' in compact:
            row = self._source_run_by_key(params[0])
            return {'id': row['id']} if row else None

        if 'operator_visibility:get_staging_impact_for_bridge:counts' in compact:
            legacy_id, source_runs_id, marker_key = params
            rows = [row for row in self.staging_rows if row['source_run_id'] == legacy_id]
            source_runs_rows = [
                row for row in self.staging_rows
                if source_runs_id is not None and row['source_run_id'] == source_runs_id
            ]
            return {
                'rows_total': len(rows),
                'rows_diagnostic_only': sum(
                    1 for row in rows
                    if row['source_class'] == 'diagnostic-only'
                    and row['confidence'] == 'diagnostic-only'
                ),
                'rows_canonical_write_blocked': sum(
                    1 for row in rows
                    if row['provenance'].get('canonical_write_allowed') is False
                ),
                'rows_with_stage_markers': sum(1 for row in rows if marker_key in row['provenance']),
                'rows_using_source_runs_id': len(source_runs_rows),
            }

        if 'operator_visibility:get_operator_safety_gates:active' in compact:
            return {'active_source_runs': sum(
                1 for row in self.source_runs
                if row['source_name'] == params[0]
                and row['domain'] == params[1]
                and row['import_scope'] == params[2]
                and row['status'] in {'planned', 'running'}
            )}

        if 'operator_visibility:get_operator_safety_gates:failed' in compact:
            return {'failed_unrecovered_source_runs': sum(
                1 for row in self.source_runs
                if row['source_name'] == params[0]
                and row['domain'] == params[1]
                and row['import_scope'] == params[2]
                and row['status'] in {'failed', 'rejected'}
            )}

        if 'operator_visibility:get_operator_safety_gates:latest' in compact:
            rows = [
                row for row in self.source_runs
                if row['source_name'] == params[0]
                and row['domain'] == params[1]
                and row['import_scope'] == params[2]
                and row['status'] == 'succeeded'
            ]
            rows.sort(key=lambda row: (row['started_at'], row['id']), reverse=True)
            if not rows:
                return None
            latest = rows[0]
            return {
                'source_run_key': latest['source_run_key'],
                'artifact_path': latest['artifact_path'],
                'artifact_sha256': latest['artifact_sha256'],
                'artifact_integrity_sha256': latest['artifact_integrity_sha256'],
            }

        raise AssertionError(f'unexpected fetchrow SQL: {sql}')

    def _source_run_by_key(self, source_run_key):
        return next((row for row in self.source_runs if row['source_run_key'] == source_run_key), None)

    def _legacy_by_key(self, bridge_key):
        return next((row for row in self.legacy_rows if row['source_run_key'] == bridge_key), None)

    def _legacy_by_id(self, legacy_id):
        return next((row for row in self.legacy_rows if row['id'] == legacy_id), None)

    def _bridge_present(self, source_run_key):
        return self._legacy_by_key(f'source_runs:{source_run_key}') is not None

    def _source_run_summary_row(self, row):
        return {
            key: row.get(key)
            for key in (
                'source_run_key',
                'source_name',
                'source_category',
                'domain',
                'import_scope',
                'status',
                'started_at',
                'finished_at',
                'duration_ms',
                'rows_read',
                'rows_staged',
                'rows_rejected',
                'rows_skipped',
                'trigger_context',
                'git_commit_sha',
                'error_code',
                'error_summary',
            )
        } | {
            'artifact_present': row.get('artifact_path') is not None,
            'artifact_hash_present': (
                row.get('artifact_sha256') is not None
                and row.get('artifact_integrity_sha256') is not None
            ),
            'bridge_present': self._bridge_present(row['source_run_key']),
        }

    def _source_run_detail_row(self, row):
        return dict(row) | self._source_run_summary_row(row)

    @staticmethod
    def _staging_projection(row):
        return {
            key: row.get(key)
            for key in (
                'id',
                'source_run_id',
                'station_name',
                'station_type',
                'system_name',
                'source_class',
                'confidence',
                'provenance',
            )
        }

    @staticmethod
    def _is_diagnostic(row, marker_key):
        return (
            row['source_class'] == 'diagnostic-only'
            or row['confidence'] == 'diagnostic-only'
            or marker_key in row['provenance']
        )


@pytest.mark.asyncio
async def test_recent_source_runs_list_returns_bounded_summaries():
    conn = FakeAsyncConn(
        source_runs=[
            source_run(source_run_key='older-run', id=100, started_at='2026-06-05T10:00:00Z'),
            source_run(),
        ],
        legacy_rows=[legacy_bridge()],
    )

    rows = await visibility.list_recent_source_runs(conn, limit=25)

    assert [row.source_run_key for row in rows] == ['stage19anr-run', 'older-run']
    assert rows[0].artifact_present is True
    assert rows[0].artifact_hash_present is True
    assert rows[0].bridge_present is True
    assert rows[0].staging_rows_known is True


@pytest.mark.asyncio
async def test_limit_hard_cap_is_enforced():
    conn = FakeAsyncConn(source_runs=[source_run(id=index, source_run_key=f'run-{index}') for index in range(150)])

    await visibility.list_recent_source_runs(conn, limit=1000)

    sql, params = conn.statements[-1]
    assert 'operator_visibility:list_recent_source_runs' in sql
    assert params[-1] == visibility.MAX_OPERATOR_VISIBILITY_LIMIT


@pytest.mark.asyncio
async def test_source_run_detail_handles_missing_bridge_and_artifact_gracefully():
    conn = FakeAsyncConn(source_runs=[
        source_run(
            source_run_key='no-bridge',
            artifact_path=None,
            artifact_sha256=None,
            artifact_integrity_sha256=None,
            metadata={},
        ),
    ])

    detail = await visibility.get_source_run_detail(conn, 'no-bridge')

    assert detail is not None
    assert detail.artifact_summary.artifact_path_redacted is None
    assert detail.artifact_summary.artifact_record_present is False
    assert detail.bridge_summary.bridge_present is False
    assert detail.staging_impact_summary is None
    assert 'legacy enrichment_source_runs bridge is missing' in detail.validation_warnings


@pytest.mark.asyncio
async def test_bridge_lookup_uses_deterministic_source_runs_key():
    conn = FakeAsyncConn(legacy_rows=[legacy_bridge()])

    bridge = await visibility.get_legacy_bridge_for_source_run(conn, 'stage19anr-run')

    assert bridge.bridge_present is True
    assert bridge.bridge_key == 'source_runs:stage19anr-run'
    assert conn.statements[-1][1] == ('source_runs:stage19anr-run',)


@pytest.mark.asyncio
async def test_staging_impact_uses_legacy_bridge_id_not_source_runs_id():
    conn = FakeAsyncConn(
        source_runs=[source_run(id=101)],
        legacy_rows=[legacy_bridge(id=701)],
        staging_rows=[staging_row(1), staging_row(2)],
    )

    impact = await visibility.get_staging_impact_for_bridge(conn, 701, limit=10)

    assert impact.legacy_source_run_id == 701
    assert impact.rows_total == 2
    assert impact.rows_using_legacy_bridge_id == 2
    assert impact.rows_using_source_runs_id == 0
    count_sql, count_params = next(
        statement for statement in conn.statements
        if 'get_staging_impact_for_bridge:counts' in statement[0]
    )
    sample_sql, sample_params = next(
        statement for statement in conn.statements
        if 'get_staging_impact_for_bridge:sample' in statement[0]
    )
    assert count_sql
    assert count_params[:2] == (701, 101)
    assert sample_sql
    assert sample_params[0] == 701


@pytest.mark.asyncio
async def test_diagnostic_rows_are_listed_with_bounded_limit_and_no_raw_payload():
    conn = FakeAsyncConn(staging_rows=[staging_row(index) for index in range(1, 5)])

    rows = await visibility.list_diagnostic_staging_rows(conn, limit=500)

    assert len(rows) == 4
    assert conn.statements[-1][1][-1] == visibility.MAX_OPERATOR_VISIBILITY_LIMIT
    encoded = visibility.to_operator_visibility_dict(rows)
    assert all('raw_payload' not in row for row in encoded)
    assert encoded[0]['canonical_write_allowed'] is False


@pytest.mark.asyncio
async def test_safety_gate_summary_produces_blockers_for_running_and_failed_runs():
    conn = FakeAsyncConn(
        source_runs=[
            source_run(),
            source_run(id=102, source_run_key='running-run', status='running'),
            source_run(id=103, source_run_key='failed-run', status='failed'),
        ],
        legacy_rows=[legacy_bridge()],
        staging_rows=[staging_row(1), staging_row(2)],
    )

    summary = await visibility.get_operator_safety_gates(conn)

    assert summary.no_running_source_runs is False
    assert summary.no_failed_unrecovered_source_runs is False
    assert summary.latest_artifacts_present is True
    assert summary.bridge_fk_path_verified is True
    assert summary.diagnostic_rows_isolated is True
    assert summary.safe_to_proceed is False
    assert any('planned/running source run' in blocker for blocker in summary.blockers)
    assert any('failed/rejected source run' in blocker for blocker in summary.blockers)


@pytest.mark.asyncio
async def test_file_paths_are_redacted_or_normalized_when_returned():
    conn = FakeAsyncConn(source_runs=[
        source_run(
            source_uri='file:///home/brian/private/edsm-stations.json',
            artifact_path='/var/lib/ed-finder/operator-artifacts/stage19anr-import.json',
        ),
    ])

    artifact = await visibility.get_source_run_artifacts(conn, 'stage19anr-run')
    detail = await visibility.get_source_run_detail(conn, 'stage19anr-run')

    assert artifact.artifact_path_redacted == '.../stage19anr-import.json'
    assert detail.source_uri_redacted == 'file://.../edsm-stations.json'
    encoded = visibility.to_operator_visibility_dict(detail)
    assert '/var/lib' not in repr(encoded)
    assert '/home/brian' not in repr(encoded)


@pytest.mark.asyncio
async def test_operator_query_endpoints_preserve_slash_and_space_source_run_keys():
    source_run_key = 'source/run 1'
    conn = FakeAsyncConn(
        source_runs=[source_run(source_run_key=source_run_key)],
        legacy_rows=[legacy_bridge(source_run_key=f'source_runs:{source_run_key}')],
        staging_rows=[
            staging_row(
                source_run_id=701,
                provenance={
                    'canonical_write_allowed': False,
                    'stage19anr_diagnostic_mark': {'source_run_key': source_run_key},
                },
            ),
        ],
    )
    pool = FakePool(conn)

    detail = await operator_router.operator_source_run_detail(source_run_key=source_run_key, pool=pool)
    artifacts = await operator_router.operator_source_run_artifacts(source_run_key=source_run_key, pool=pool)
    bridge = await operator_router.operator_source_run_bridge(source_run_key=source_run_key, pool=pool)
    staging = await operator_router.operator_source_run_staging_impact(
        source_run_key=source_run_key,
        limit=5,
        pool=pool,
    )

    assert detail['summary']['source_run_key'] == source_run_key
    assert artifacts['source_run_key'] == source_run_key
    assert bridge['source_run_key'] == source_run_key
    assert staging['source_run_key'] == source_run_key
    assert staging['staging_impact']['source_run_key'] == source_run_key
    route_paths = {route.path for route in operator_router.router.routes}
    assert '/api/operator/source-runs/{source_run_key}' not in route_paths
    assert '/api/operator/source-runs/{source_run_key}/artifacts' not in route_paths
    assert '/api/operator/source-runs/{source_run_key}/bridge' not in route_paths
    assert '/api/operator/source-runs/{source_run_key}/staging-impact' not in route_paths


def test_static_guardrails_for_operator_visibility_module_and_router():
    source = inspect.getsource(visibility) + inspect.getsource(operator_router)
    source_upper = source.upper()

    assert re.search(r'\bINSERT\s+INTO\b|\bUPDATE\s+\w+\b|\bDELETE\s+FROM\b', source, flags=re.IGNORECASE) is None
    canonical_write_patterns = (
        r'\binsert\s+into\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bupdate\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bdelete\s+from\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
    )
    for pattern in canonical_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None

    forbidden_fragments = (
        'SYSTEMCTL',
        'RUN_IMPORT',
        'RUN_IMPORT.SH',
        'DATABASE' + '_URL',
        'POSTGRESQL' + '://',
        'POSTGRES' + '://',
        'PASSWORD' + '=',
        'SECRET' + '=',
        'TOKEN' + '=',
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper
    assert re.search(r'(?<![a-z0-9_])\.timer(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert re.search(r'(?<![a-z0-9_])\.service(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert 'raw_payload' not in source
    assert 'canonical_apply(' not in source
