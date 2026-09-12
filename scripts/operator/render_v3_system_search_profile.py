#!/usr/bin/env python3
"""Render the trusted read-only profiler with the writer's exact SELECT.

Run on the Actions runner, never the production host. No database dependency.
The host script validates all three metadata values before SQL interpolation.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.v3_system_search import projection_query_sql  # noqa: E402


def shell_query(query: str) -> str:
    return (query
            .replace('{schema}', '${canonical_schema}')
            .replace('%(generation_id)s', "'${generation_id}'::uuid")
            .replace('%(chunk_ordinal)s', '${chunk_ordinal}'))


def render_profile() -> str:
    source = (ROOT / 'scripts/operator/actions/v3-system-search-profile.sh').read_text()
    queries = {
        '__SEARCH_CANDIDATE_SQL__': projection_query_sql(),
        '__SEARCH_LEGACY_SQL__': (
            ROOT / 'scripts/operator/v3_system_search_legacy.sql'
        ).read_text().strip(),
    }
    for marker, query in queries.items():
        if source.count(marker) != 1:
            raise ValueError(f'expected exactly one {marker} marker')
        source = source.replace(marker, shell_query(query))
    return source


if __name__ == '__main__':
    print(render_profile(), end='')
