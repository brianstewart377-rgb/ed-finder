from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PACK = (
    ROOT
    / 'docs'
    / 'colonisation-redesign'
    / 'stage-27a-production-data-coverage-queries.sql'
)
MAX_RESULT_ROWS = 200
FORBIDDEN_PATTERNS = (
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
    # Defense in depth for known PostgreSQL side-effect families.
    r'\bpg_(?:try_)?advisory_[a-z_]*\s*\(',
    r'\bset_config\s*\(',
    r'refresh_map_mviews\s*\(',
)
# Function-like syntax in the pack is deliberately tiny. SQL structural words
# that can appear immediately before '(' are included here too; any other
# identifier-call surface (for example pg_notify()) fails closed.
SAFE_CALL_TOKENS = {
    'count',
    'min',
    'max',
    'coalesce',
    'jsonb_agg',
    'jsonb_build_object',
    'row_number',
    'filter',
    'distinct',
    'from',
    'over',
}
CALL_TOKEN_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')


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
    assert len(limits) == 1, (
        f'every coverage statement must have exactly one literal LIMIT: {statement}'
    )
    outer = re.search(r'\bLIMIT\s+(\d+)\s*$', statement, flags=re.IGNORECASE)
    assert outer is not None, (
        'the sole result bound must apply to the outer SELECT, not only to a nested query: '
        f'{statement}'
    )
    assert outer.group(1) == limits[0]
    return int(outer.group(1))


def _assert_safe_select_surface(statement: str) -> None:
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, statement, flags=re.IGNORECASE) is None, pattern
    call_tokens = {match.group(1).lower() for match in CALL_TOKEN_RE.finditer(statement)}
    unknown = sorted(call_tokens - SAFE_CALL_TOKENS)
    assert not unknown, f'coverage statement uses non-allowlisted call surface: {unknown}'


def test_stage27a_coverage_pack_is_bounded_select_only_sql():
    statements = _statements()

    assert len(statements) == 12
    assert all(statement.upper().startswith('SELECT') for statement in statements)

    for statement in statements:
        limit = _statement_limit(statement)
        assert 1 <= limit <= MAX_RESULT_ROWS
        _assert_safe_select_surface(statement)


def test_stage27a_limit_guard_rejects_nested_only_bounds():
    malicious = (
        'SELECT * FROM exploration_facts '
        'WHERE EXISTS (SELECT 1 LIMIT 200)'
    )
    with pytest.raises(AssertionError, match='outer SELECT'):
        _statement_limit(malicious)


def test_stage27a_select_guard_blocks_function_side_effects():
    for malicious in (
        "SELECT set_config('statement_timeout', '0', false) LIMIT 1",
        'SELECT pg_try_advisory_lock(1) LIMIT 1',
        'SELECT pg_try_advisory_xact_lock_shared(1) LIMIT 1',
        "SELECT pg_notify('audit', 'payload') LIMIT 1",
    ):
        with pytest.raises(AssertionError):
            _assert_safe_select_surface(malicious)


def test_stage27a_ring_breakdown_accounts_for_every_group_with_bounded_payload():
    ring_breakdown = _statements()[3]

    assert _statement_limit(ring_breakdown) == 1
    assert 'COUNT(*) AS provenance_groups' in ring_breakdown
    assert 'COUNT(*) FILTER (WHERE group_rank > 200) AS omitted_groups' in ring_breakdown
    assert 'ROW_NUMBER() OVER (' in ring_breakdown
    assert ') FILTER (WHERE group_rank <= 200)' in ring_breakdown
    assert 'jsonb_agg(' in ring_breakdown
    assert 'GROUP BY association_status, source, confidence' in ring_breakdown
    assert 'LIMIT 200' not in ring_breakdown


def test_stage27a_station_association_breakdown_preserves_every_group():
    station_breakdown = _statements()[6]

    assert _statement_limit(station_breakdown) == 1
    assert 'COUNT(*) AS association_groups' in station_breakdown
    assert 'jsonb_agg(' in station_breakdown
    assert 'GROUP BY association_status, lane, association_confidence, association_source' in station_breakdown
    assert 'LIMIT 200' not in station_breakdown


def test_stage27a_exploration_breakdown_accounts_for_every_group_with_bounded_payload():
    exploration_breakdown = _statements()[9]

    assert _statement_limit(exploration_breakdown) == 1
    assert 'COUNT(*) AS event_groups' in exploration_breakdown
    assert 'COUNT(*) FILTER (WHERE group_rank > 200) AS omitted_groups' in exploration_breakdown
    assert 'ROW_NUMBER() OVER (ORDER BY source, event_type)' in exploration_breakdown
    assert ') FILTER (WHERE group_rank <= 200)' in exploration_breakdown
    assert 'jsonb_agg(' in exploration_breakdown
    assert 'GROUP BY source, event_type' in exploration_breakdown
    assert 'LIMIT 200' not in exploration_breakdown


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
