from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_all_executable_body_writers_keep_an_ownership_guard():
    literal_writer_paths = {
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / 'apps', ROOT / 'scripts')
        for path in base.rglob('*.py')
        if re.search(
            r'\binsert\s+into\s+bodies\b',
            path.read_text(encoding='utf-8'),
            flags=re.IGNORECASE,
        )
    }

    assert literal_writer_paths == {
        'apps/eddn/src/eddn_listener.py',
    }

    eddn_source = (ROOT / 'apps' / 'eddn' / 'src' / 'eddn_listener.py').read_text(
        encoding='utf-8'
    )
    spansh_source = (ROOT / 'apps' / 'importer' / 'src' / 'import_spansh.py').read_text(
        encoding='utf-8'
    )
    canonical_seed_source = (ROOT / 'scripts/dev/v3_canonical_bootstrap.py').read_text(encoding='utf-8')
    preview_seed_source = (ROOT / 'sql' / 'seed_preview.sql').read_text(encoding='utf-8')

    assert 'bodies.system_id64 = EXCLUDED.system_id64' in eddn_source
    assert "'bodies', BODY_COLS" in spansh_source
    assert "guard_col='system_id64'" in spansh_source
    # The retired V2 review upsert is no longer an executable body writer.
    # Its V3 replacement inserts into a fresh canonical generation in one
    # transaction; it cannot update/re-parent an existing public.bodies row.
    assert not (ROOT / 'scripts/dev/review_environment_seed.py').exists()
    assert 'with connection.transaction():' in canonical_seed_source
    assert "insert(schema, 'bodies', canonical['bodies'])" in canonical_seed_source
    assert 'ON CONFLICT' not in canonical_seed_source
    assert 'jsonb_populate_record(NULL::{}, %s::jsonb)' in canonical_seed_source
    assert 'ON CONFLICT (id) DO NOTHING' in preview_seed_source
