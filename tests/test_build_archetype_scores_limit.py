"""Regression test for build_archetype_scores.py's --limit 0 handling.

Emergent adversarial-review recurrence check (2026-08-07), item B5: the
original `limit or 10_000_000` pattern in _fetch_system_ids treats an
explicit `--limit 0` the same as "no --limit given" and silently replaces
it with the 10M safety cap, since 0 is falsy in Python. CLAUDE.md's
"Nightly job caps" section already documents the hidden-cap half of this
(operationally mitigated by always passing --limit in nightly_update.sh),
but the --limit 0 mishandling itself was never fixed.
"""
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = str(ROOT / 'apps' / 'importer' / 'src')
if IMPORTER_SRC not in sys.path:
    sys.path.insert(0, IMPORTER_SRC)

# build_archetype_scores imports build_ratings, which reads DATABASE_URL at
# module level (fail-fast, no insecure default) — a dummy value is enough
# to satisfy that import-time read, since this test never connects.
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from build_archetype_scores import _resolve_fetch_limit  # noqa: E402


def test_explicit_limit_is_honored_including_zero():
    assert _resolve_fetch_limit(0) == 0
    assert _resolve_fetch_limit(1) == 1
    assert _resolve_fetch_limit(500_000) == 500_000


def test_missing_limit_falls_back_to_the_safety_cap():
    assert _resolve_fetch_limit(None) == 10_000_000
