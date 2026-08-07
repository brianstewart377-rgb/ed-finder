"""2026-08-07 Codex Review finding: BODY_RING_ASSOCIATION_STATUS_CASE_SQL was
defined independently in three files with no shared module — identical at
the time, but CLAUDE.md's own "Known hazards" section already documents
this pattern (BODY_RING_ASSOCIATION_STATUS_CASE_SQL / body_rings writers)
as exactly the kind of copy that silently drifts. Now a single definition
in shared_contracts/body_ring_association_status.py, imported everywhere.
This test asserts identity, not just equal-looking text — the whole point
is that "changing one changes all three" is now structurally true rather
than something a future editor has to remember to keep in sync by hand.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'eddn' / 'src'))
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))
sys.path.insert(0, str(ROOT))

from shared_contracts.body_ring_association_status import (  # noqa: E402
    BODY_RING_ASSOCIATION_STATUS_CASE_SQL as canonical_sql,
)


def test_eddn_listener_uses_the_shared_constant():
    import eddn_listener

    assert eddn_listener.BODY_RING_ASSOCIATION_STATUS_CASE_SQL is canonical_sql


def test_ingest_eddn_client_uses_the_shared_constant():
    from ingest import eddn_client

    assert eddn_client.BODY_RING_ASSOCIATION_STATUS_CASE_SQL is canonical_sql


def test_journal_import_store_uses_the_shared_constant():
    from journal_import import store

    assert store.BODY_RING_ASSOCIATION_STATUS_CASE_SQL is canonical_sql
