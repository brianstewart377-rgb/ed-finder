"""Regression test for import_spansh.py's swallowed checkpoint/counter errors.

Emergent adversarial-review recurrence check (2026-08-07), item A6: both
increment_error_count and every periodic save_checkpoint() call site wrapped
their DB write in `except Exception: pass` — a failed write during a
multi-hour import was completely invisible, and (worse, not part of the
original finding but found while fixing it) never rolled back, which would
have poisoned the connection's transaction for every later flush in the
same run.

The four periodic call sites were byte-identical copy-pasted try/except
blocks; extracted into save_checkpoint_safely() so this is tested once,
directly, rather than needing to exercise ~1500 lines of import loop
scaffolding four times.
"""
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = str(ROOT / 'apps' / 'importer' / 'src')
if IMPORTER_SRC not in sys.path:
    sys.path.insert(0, IMPORTER_SRC)

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import import_spansh  # noqa: E402


def _failing_conn() -> MagicMock:
    conn = MagicMock()
    cursor_ctx = MagicMock()
    cursor_ctx.__enter__.return_value.execute.side_effect = RuntimeError('connection reset')
    conn.cursor.return_value = cursor_ctx
    return conn


def test_increment_error_count_logs_and_rolls_back_on_failure(caplog):
    conn = _failing_conn()

    with caplog.at_level(logging.WARNING, logger='import_spansh'):
        import_spansh.increment_error_count(conn, 'test_dump.json.gz', 5)

    assert conn.rollback.called
    assert conn.commit.called is False
    assert any('Failed to increment error count' in record.message for record in caplog.records)


def test_save_checkpoint_safely_logs_and_rolls_back_on_failure(caplog):
    conn = _failing_conn()

    with caplog.at_level(logging.WARNING, logger='import_spansh'):
        import_spansh.save_checkpoint_safely(conn, 'test_dump.json.gz', 0, 1000, 12345)

    assert conn.rollback.called
    assert conn.commit.called is False
    assert any('Failed to save checkpoint' in record.message for record in caplog.records)


def test_save_checkpoint_safely_does_not_swallow_on_success():
    conn = MagicMock()
    cursor_ctx = MagicMock()
    conn.cursor.return_value = cursor_ctx

    import_spansh.save_checkpoint_safely(conn, 'test_dump.json.gz', 0, 1000, 12345)

    assert conn.commit.called
    assert conn.rollback.called is False
