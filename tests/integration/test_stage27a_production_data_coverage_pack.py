from __future__ import annotations

import os
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


def _statements() -> list[str]:
    lines = []
    for raw_line in COVERAGE_PACK.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('--', 1)[0]
        if line.strip():
            lines.append(line)
    sql = '\n'.join(lines)
    return [part.strip() for part in sql.split(';') if part.strip()]


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
                try:
                    cur.execute(statement)
                    cur.fetchall()
                except Exception as exc:
                    raise AssertionError(
                        f'Stage 27A coverage statement {index} no longer matches the migrated schema'
                    ) from exc
    finally:
        conn.rollback()
        conn.close()
