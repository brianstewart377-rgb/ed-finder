"""Regression test for import_spansh.py's ring/rejected-body filter.

Emergent adversarial-review recurrence check (2026-08-07), item A2:
body_ring_rows_from_spansh_body() hardcodes association_status='local_matched'
on every ring row, with a comment claiming this is only safe because
flush_rings() filters ring_batch against rejected_body_ids first (bodies
whose upsert was rejected by the system_id64 ownership guard — see the
bodies.id hazard in CLAUDE.md). That filter used to live only as an inline
list comprehension inside flush_rings()'s closure, nested inside the ~1500
line import_galaxy() function — the invariant the comment claims was
untestable without driving a full dump-file import against a real database.
Extracted into _filter_rings_by_rejected_bodies() so it can be tested
directly, the same pattern used for save_checkpoint_safely() in
test_import_spansh_checkpoint_failure_handling.py.
"""
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = str(ROOT / 'apps' / 'importer' / 'src')
if IMPORTER_SRC not in sys.path:
    sys.path.insert(0, IMPORTER_SRC)

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import import_spansh  # noqa: E402


def test_ring_owned_by_rejected_body_is_dropped():
    ring_batch = [
        {'system_id64': 1, 'body_id': 100, 'ring_name': 'A Ring'},
    ]
    rejected_body_ids = {(1, 100)}

    keep, skipped = import_spansh._filter_rings_by_rejected_bodies(ring_batch, rejected_body_ids)

    assert keep == []
    assert skipped == 1


def test_ring_owned_by_accepted_body_is_kept():
    ring_batch = [
        {'system_id64': 1, 'body_id': 100, 'ring_name': 'A Ring'},
    ]
    rejected_body_ids: set = set()

    keep, skipped = import_spansh._filter_rings_by_rejected_bodies(ring_batch, rejected_body_ids)

    assert keep == ring_batch
    assert skipped == 0


def test_only_the_rejected_body_ids_ring_rows_are_dropped_from_a_mixed_batch():
    """A single flush can contain rings for many bodies across many
    systems — rejecting one colliding body must not touch any other
    row's ring in the same batch."""
    ring_batch = [
        {'system_id64': 1, 'body_id': 100, 'ring_name': 'Rejected Body Ring'},
        {'system_id64': 1, 'body_id': 101, 'ring_name': 'Accepted Body Ring'},
        {'system_id64': 2, 'body_id': 100, 'ring_name': 'Different System, Same Body Id'},
    ]
    rejected_body_ids = {(1, 100)}

    keep, skipped = import_spansh._filter_rings_by_rejected_bodies(ring_batch, rejected_body_ids)

    assert keep == [
        {'system_id64': 1, 'body_id': 101, 'ring_name': 'Accepted Body Ring'},
        {'system_id64': 2, 'body_id': 100, 'ring_name': 'Different System, Same Body Id'},
    ]
    assert skipped == 1


def test_empty_ring_batch_and_empty_rejection_set():
    keep, skipped = import_spansh._filter_rings_by_rejected_bodies([], set())

    assert keep == []
    assert skipped == 0
