from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg2
import pytest


ROOT = Path(__file__).resolve().parents[2]
COVERAGE_PACK = (
    ROOT
    / 'docs'
    / 'colonisation-redesign'
    / 'stage-27a-production-data-coverage-queries.sql'
)
MAX_RESULT_ROWS = 200


def _statements() -> list[str]:
    lines = []
    for raw_line in COVERAGE_PACK.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('--', 1)[0]
        if line.strip():
            lines.append(line)
    sql = '\n'.join(lines)
    return [part.strip() for part in sql.split(';') if part.strip()]


def _statement_limit(statement: str) -> int:
    limits = re.findall(r'\bLIMIT\s+(\d+)\b', statement, flags=re.IGNORECASE)
    assert len(limits) == 1
    outer = re.search(r'\bLIMIT\s+(\d+)\s*$', statement, flags=re.IGNORECASE)
    assert outer is not None
    assert outer.group(1) == limits[0]
    return int(outer.group(1))


@pytest.mark.db
def test_stage27a_coverage_pack_executes_against_current_migrated_schema_read_only():
    statements = _statements()
    assert len(statements) == 12

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute('SHOW transaction_read_only')
            assert cur.fetchone() == ('on',)

            for index, statement in enumerate(statements, start=1):
                limit = _statement_limit(statement)
                assert 1 <= limit <= MAX_RESULT_ROWS
                try:
                    cur.execute(statement)
                    rows = cur.fetchall()
                    assert len(rows) <= limit
                except Exception as exc:
                    raise AssertionError(
                        f'Stage 27A coverage statement {index} no longer matches the migrated schema or result bound'
                    ) from exc
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.db
def test_stage27a_identity_drift_queries_detect_cross_system_fixtures_read_only():
    """Exercise the actual drift statements, not only their predicate text.

    Temporary tables shadow the canonical names only for this connection. They
    let the test construct deliberately impossible cross-system rows without
    weakening the real station/body write guards or persisting fixture data.
    After the fixture transaction commits, the audit statements themselves run
    in a read-only transaction exactly as the production coverage pack must.
    """
    statements = _statements()
    station_drift = statements[7]
    ring_drift = statements[8]

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                'CREATE TEMP TABLE bodies ('
                'id BIGINT PRIMARY KEY, system_id64 BIGINT NOT NULL'
                ') ON COMMIT PRESERVE ROWS'
            )
            cur.execute(
                'CREATE TEMP TABLE station_body_links ('
                'system_id64 BIGINT NOT NULL, body_id BIGINT'
                ') ON COMMIT PRESERVE ROWS'
            )
            cur.execute(
                'CREATE TEMP TABLE body_rings ('
                'system_id64 BIGINT NOT NULL, body_id BIGINT'
                ') ON COMMIT PRESERVE ROWS'
            )
            cur.execute(
                'INSERT INTO bodies (id, system_id64) VALUES '
                '(9001, 2002), (9002, 1001)'
            )
            cur.execute(
                'INSERT INTO station_body_links (system_id64, body_id) VALUES '
                '(1001, 9001), (1001, 9002)'
            )
            cur.execute(
                'INSERT INTO body_rings (system_id64, body_id) VALUES '
                '(1001, 9001), (1001, 9002)'
            )
        conn.commit()

        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute('SHOW transaction_read_only')
            assert cur.fetchone() == ('on',)

            cur.execute(station_drift)
            assert cur.fetchone() == (1,)

            cur.execute(ring_drift)
            assert cur.fetchone() == (1,)
    finally:
        conn.rollback()
        conn.close()
