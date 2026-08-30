from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "checks" / "production_candidate_readiness.py"
SPEC = importlib.util.spec_from_file_location("production_candidate_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


def manifest(tmp_path: Path, lines: str = "001.sql\n002.sql|manual\n") -> Path:
    path = tmp_path / "migration-manifest.txt"
    (tmp_path / "001.sql").write_text("SELECT 1;\n")
    (tmp_path / "002.sql").write_text("SELECT 2;\n")
    path.write_text(lines)
    return path


def test_manifest_ledger_comparison_separates_auto_manual_and_mismatch(tmp_path):
    entries = readiness.parse_manifest(manifest(tmp_path))
    result = readiness.compare_migrations(entries, [("001.sql", "wrong", "baseline")])
    assert result["pending_automatic"] == []
    assert result["pending_manual"] == ["002.sql"]
    assert result["checksum_mismatches"][0]["filename"] == "001.sql"
    assert result["status"] == "fail"


@pytest.mark.parametrize("url", ["", "mysql://host/db", "postgresql:///db", "postgresql://host", "postgresql://host/db\nsecret"])
def test_configuration_fails_closed(url, tmp_path):
    args = Namespace(database_url=url, receipt_file=tmp_path / "r.json", manifest=manifest(tmp_path), full=False, statement_timeout="30s")
    with pytest.raises(readiness.AuditError):
        readiness.validate_inputs(args)


def test_target_redaction_never_contains_credentials():
    target = readiness.redacted_target("postgresql://alice:very-secret@db.example:5432/edfinder?sslmode=require")
    rendered = str(target)
    assert "alice" not in rendered
    assert "very-secret" not in rendered
    assert target["credentials_redacted"] is True


class Cursor:
    def __init__(self): self.sql = []; self.rows = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=()):
        self.sql.append(sql)
        if "transaction_read_only" in sql: self.rows = [("on",)]
        elif "server_version_num" in sql: self.rows = [("180001",)]
        elif "version()" in sql: self.rows = [("PostgreSQL 18.1",)]
        elif "pg_database_size" in sql: self.rows = [(123,)]
        elif "to_regclass" in sql: self.rows = [(True,)]
        elif "FROM schema_migrations" in sql: self.rows = []
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class Connection:
    def __init__(self): self.cur = Cursor(); self.autocommit = None; self.rolled_back = False; self.closed = False
    def cursor(self): return self.cur
    def rollback(self): self.rolled_back = True
    def close(self): self.closed = True


def test_database_session_is_read_only_and_never_commits(monkeypatch, tmp_path):
    connection = Connection(); captured = {}
    def connect(url, options): captured.update(url=url, options=options); return connection
    monkeypatch.setattr(readiness.psycopg2, "connect", connect)
    monkeypatch.setattr(readiness, "collect", lambda _cur, _full: {"base_data": {}, "full_build": {"grid": {"grid_cell_id_backlog": 0, "macro_grid_id_backlog": 0}, "ratings_v3_4": {"value": 0, "rating_dirty_backlog": 0}, "archetypes": {"value": 0, "scores": {"presence": "present"}, "traits": {"presence": "present"}}, "clusters": {"cluster_dirty_backlog": 0, "presence": "present"}, "topology": {"presence": "present"}, "economy_pair_synergy": {"presence": "present"}, "regional_analysis": {"presence": "present"}, "station_body_links": {"presence": "present"}, "materialized_views": {"objects": {}}}, "runtime_features": {}})
    args = Namespace(database_url="postgresql://user:secret@db/edfinder", receipt_file=tmp_path / "r.json", manifest=manifest(tmp_path), full=True, statement_timeout="30s")
    report = readiness.run_audit(args)
    assert "default_transaction_read_only=on" in captured["options"]
    assert connection.cur.sql[0] == "BEGIN READ ONLY"
    assert connection.rolled_back and connection.closed
    assert "secret" not in str(report)


class MissingCursor:
    def execute(self, _sql, _params=()): self.row = (False,)
    def fetchone(self): return self.row


def test_missing_optional_runtime_object_is_reported_not_raised():
    assert readiness.table_metric(MissingCursor(), "journal_events", False) == {"presence": "missing", "row_count": None, "count_method": "unavailable"}


def test_runtime_feature_population_is_explicitly_nonblocking():
    assert "journal_events" in readiness.RUNTIME_TABLES
    assert "journal_events" not in readiness.FULL_BUILD_DATASETS
    assert "ratings_v3_4" in readiness.FULL_BUILD_DATASETS
