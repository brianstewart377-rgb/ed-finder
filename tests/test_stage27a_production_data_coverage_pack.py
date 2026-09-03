from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PACK = (
    ROOT
    / 'docs'
    / 'colonisation-redesign'
    / 'stage-27a-production-data-coverage-queries.sql'
)
MAX_RESULT_ROWS = 200


def _raw_sql() -> str:
    return COVERAGE_PACK.read_text(encoding='utf-8')


def _sql_without_line_comments() -> str:
    lines = []
    for raw_line in _raw_sql().splitlines():
        line = raw_line.split('--', 1)[0]
        if line.strip():
            lines.append(line)
    return '\n'.join(lines)


def _statements() -> list[str]:
    return [part.strip() for part in _sql_without_line_comments().split(';') if part.strip()]


def _statement_limit(statement: str) -> int:
    limits = re.findall(r'\bLIMIT\s+(\d+)\b', statement, flags=re.IGNORECASE)
    assert len(limits) == 1, f'every coverage statement must have exactly one literal LIMIT: {statement}'
    return int(limits[0])


def test_stage27a_coverage_pack_is_bounded_select_only_sql():
    statements = _statements()

    assert len(statements) == 12
    assert all(statement.upper().startswith('SELECT') for statement in statements)

    for statement in statements:
        limit = _statement_limit(statement)
        assert 1 <= limit <= MAX_RESULT_ROWS

    sql = _sql_without_line_comments()
    forbidden_patterns = (
        r'\bINSERT\b',
        r'\bUPDATE\b',
        r'\bDELETE\b',
        r'\bMERGE\b',
        r'\bCREATE\b',
        r'\bALTER\b',
        r'\bDROP\b',
        r'\bTRUNCATE\b',
        r'\bGRANT\b',
        r'\bREVOKE\b',
        r'\bSET\b',
        r'\bRESET\b',
        r'\bLOCK\b',
        r'\bCALL\b',
        r'\bDO\s+\$\$',
        r'\bCOPY\b',
        r'\bFOR\s+(UPDATE|SHARE)\b',
        # Block the entire PostgreSQL advisory-lock family, including
        # pg_try_advisory_lock*, xact/shared variants, and unlock helpers.
        r'\bpg_(?:try_)?advisory_[a-z_]*\s*\(',
        r'refresh_map_mviews\s*\(',
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, sql, flags=re.IGNORECASE) is None, pattern


def test_stage27a_coverage_pack_does_not_expose_credentials_or_commander_keys():
    # Scan the complete checked-in file, comments included. Commented examples
    # are still repository disclosure and must not be able to hide credentials.
    sql = _raw_sql().lower()

    for forbidden in (
        'password',
        'postgresql://',
        'postgres://',
        'database_url',
        'admin_token',
        'frontier_client_secret',
        'sync_key',
    ):
        assert forbidden not in sql


def test_stage27a_coverage_pack_keeps_identity_drift_checks_explicit():
    sql = _sql_without_line_comments()

    assert 'cross_system_station_body_links' in sql
    assert 'l.system_id64 <> b.system_id64' in sql
    assert 'cross_system_ring_body_links' in sql
    assert 'r.system_id64 <> b.system_id64' in sql
    assert "association_status = 'local_matched'" in sql
