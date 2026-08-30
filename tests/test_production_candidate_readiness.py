from __future__ import annotations

import importlib.util
import json
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


def metric(value=0):
    return {"presence": "present", "value": value, "count_method": "exact"}


def complete_report(profile="full", major=18):
    views = {
        name: {
            "presence": "present", "populated": True,
            "required_unique_index": index, "unique_index_valid": True,
        }
        for name, index in readiness.REQUIRED_MATERIALIZED_VIEWS.items()
    }
    present = {"presence": "present", "row_count": 1, "count_method": "exact"}
    full_build = {
        "grid": {"grid_cell_id_backlog": 0, "macro_grid_id_backlog": 0},
        "ratings_v3_4": {"presence": "present", "value": 0, "rating_dirty_backlog": 0},
        "topology": {**present, "missing_for_ratings": metric()},
        "economy_pair_synergy": {**present, "constants": present},
        "archetypes": {
            "presence": "present", "value": 0, "scores": present, "traits": present,
            "missing_scores_for_ratings": metric(), "missing_traits_for_scores": metric(),
        },
        "regional_analysis": {**present, "missing_for_positioned_systems": metric()},
        "station_body_links": {**present, "required_backfill": metric()},
        "clusters": {**present, "cluster_dirty_backlog": 0, "summary_dirty_backlog": metric()},
        "materialized_views": {"objects": views},
    }
    return {
        "profile": profile,
        "postgresql": {"major_version": major},
        "migrations": {"status": "pass"},
        "data": {"base_data": {}, "full_build": full_build, "runtime_features": {}},
    }


def test_manifest_ledger_comparison_separates_auto_manual_and_mismatch(tmp_path):
    result = readiness.compare_migrations(
        readiness.parse_manifest(manifest(tmp_path)), [("001.sql", "wrong", "baseline")]
    )
    assert result["pending_automatic"] == []
    assert result["pending_manual"] == ["002.sql"]
    assert result["checksum_mismatches"][0]["filename"] == "001.sql"
    assert result["status"] == "fail"


@pytest.mark.parametrize(
    "url", ["", "mysql://host/db", "postgresql:///db", "postgresql://host", "postgresql://host/db\nsecret"]
)
def test_configuration_fails_closed(url, tmp_path):
    args = Namespace(database_url=url, receipt_file=tmp_path / "r.json", manifest=manifest(tmp_path), full=False, statement_timeout="30s")
    with pytest.raises(readiness.AuditError):
        readiness.validate_inputs(args)


def test_complete_pg18_full_profile_is_ready():
    assert readiness.determine_readiness(complete_report()) == ("ready", [])


def test_non_pg18_and_backlogs_block_full_readiness():
    report = complete_report(major=17)
    report["data"]["full_build"]["grid"]["grid_cell_id_backlog"] = 1
    status, reasons = readiness.determine_readiness(report)
    assert status == "not_ready"
    assert "PostgreSQL major version is not 18" in reasons
    assert "grid grid_cell_id_backlog is non-zero" in reasons


def test_safe_profile_intentionally_remains_non_ready():
    report = complete_report(profile="production_safe")
    report["data"]["runtime_features"] = {
        "journal_events": {"presence": "missing", "row_count": None},
        "app_users": {"presence": "present", "row_count": 0},
    }
    status, reasons = readiness.determine_readiness(report)
    assert status == "not_ready"
    assert reasons == ["heavy coverage checks remain pending; run --full in an approved window"]


@pytest.mark.parametrize("state", ["missing", "unpopulated", "missing_index", "nonunique"])
def test_materialized_view_contract_failures_block(state):
    report = complete_report()
    view = report["data"]["full_build"]["materialized_views"]["objects"]["mv_map_regions"]
    if state == "missing":
        view["presence"] = "missing"
    elif state == "unpopulated":
        view["populated"] = False
    else:
        view["unique_index_valid"] = False
    status, reasons = readiness.determine_readiness(report)
    assert status == "not_ready"
    assert any("mv_map_regions" in reason for reason in reasons)


class CatalogCursor:
    def __init__(self, *, exists=True, populated=True, index_valid=True):
        self.values = iter([(exists,), (populated,), (index_valid,)])
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        self.row = next(self.values)

    def fetchone(self):
        return self.row


@pytest.mark.parametrize("index_valid", [True, False])
def test_materialized_view_catalog_requires_bound_unique_valid_ready_index(index_valid):
    cursor = CatalogCursor(index_valid=index_valid)
    result = readiness.materialized_view_metric(cursor, "mv_map_regions", "ux_mv_map_regions_cell")
    assert result["unique_index_valid"] is index_valid
    sql, params = cursor.calls[-1]
    assert "i.indisunique" in sql and "i.indisvalid" in sql and "i.indisready" in sql
    assert "JOIN pg_class mv" in sql and "JOIN pg_class idx" in sql
    assert params == ("mv_map_regions", "ux_mv_map_regions_cell")


class Cursor:
    def __init__(self, major=18, address="10.0.0.18"):
        self.major = major
        self.address = address
        self.sql = []
        self.rows = []

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=()):
        self.sql.append(sql)
        if "transaction_read_only" in sql: self.rows = [("on",)]
        elif "server_version_num" in sql: self.rows = [(f"{self.major}0001",)]
        elif "version()" in sql: self.rows = [(f"PostgreSQL {self.major}.1",)]
        elif "pg_database_size" in sql: self.rows = [(123,)]
        elif "current_database(), current_user" in sql: self.rows = [("candidate_v3", "auditor", self.address, 5432)]
        elif "to_regclass" in sql: self.rows = [(True,)]
        elif "FROM schema_migrations" in sql: self.rows = []
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, **cursor_args):
        self.cur = Cursor(**cursor_args)
        self.autocommit = None
        self.rolled_back = False
        self.closed = False
    def cursor(self): return self.cur
    def rollback(self): self.rolled_back = True
    def close(self): self.closed = True


def run_mocked_audit(monkeypatch, tmp_path, **connection_args):
    connection = Connection(**connection_args)
    captured = {}
    monkeypatch.setattr(readiness.psycopg2, "connect", lambda url, options: (captured.update(url=url, options=options) or connection))
    monkeypatch.setattr(readiness, "collect", lambda _cur, _full: complete_report()["data"])
    monkeypatch.setattr(readiness, "compare_migrations", lambda _manifest, _ledger: {
        "status": "pass", "pending_automatic": [], "pending_manual": [],
        "checksum_mismatches": [], "ledger_only_entries": [],
    })
    args = Namespace(database_url="postgresql://dsn-user:very-secret@hint-host/candidate?token=hidden", receipt_file=tmp_path / "r.json", manifest=manifest(tmp_path), full=True, statement_timeout="30s")
    return readiness.run_audit(args), connection, captured


def test_database_session_is_read_only_identified_and_secret_free(monkeypatch, tmp_path, capsys):
    report, connection, captured = run_mocked_audit(monkeypatch, tmp_path)
    assert report["readiness"] == "ready"
    assert report["target"]["database_reported"] == {
        "database": "candidate_v3", "user": "auditor", "server_address": "10.0.0.18",
        "server_port": 5432, "address_source": "server_reported",
    }
    assert "default_transaction_read_only=on" in captured["options"]
    assert connection.cur.sql[0] == "BEGIN READ ONLY"
    assert connection.rolled_back and connection.closed
    readiness.write_receipt(tmp_path / "receipt.json", report)
    readiness.print_human(report, tmp_path / "receipt.json")
    rendered = json.dumps(report) + (tmp_path / "receipt.json").read_text() + capsys.readouterr().out
    assert "candidate_v3" in rendered and "10.0.0.18" in rendered
    assert "very-secret" not in rendered and "dsn-user" not in rendered and "token=hidden" not in rendered


def test_null_server_address_is_cleanly_reported(monkeypatch, tmp_path):
    report, _, _ = run_mocked_audit(monkeypatch, tmp_path, address=None)
    target = report["target"]["database_reported"]
    assert target["server_address"] is None
    assert target["address_source"] == "local_socket"


def test_connection_errors_fail_closed_without_rendering_secret(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        readiness.psycopg2,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            readiness.psycopg2.OperationalError("password=raw-secret")
        ),
    )
    result = readiness.main([
        "--database-url", "postgresql://user:dsn-secret@db/candidate",
        "--receipt-file", str(tmp_path / "receipt.json"),
        "--manifest", str(manifest(tmp_path)),
    ])
    output = capsys.readouterr()
    assert result == 2
    assert "OperationalError" in output.err
    assert "raw-secret" not in output.err and "dsn-secret" not in output.err


class MissingCursor:
    def execute(self, _sql, _params=()): self.row = (False,)
    def fetchone(self): return self.row


def test_missing_optional_runtime_object_is_reported_not_raised():
    assert readiness.table_metric(MissingCursor(), "journal_events", False) == {"presence": "missing", "row_count": None, "count_method": "unavailable"}


def test_safe_system_backlogs_remain_partial_index_predicates():
    source = SCRIPT.read_text()
    assert "WHERE grid_cell_id IS NULL" in source
    assert "WHERE macro_grid_id IS NULL" in source
    assert "WHERE rating_dirty=TRUE" in source
    assert "WHERE cluster_dirty=TRUE" in source
    assert 'SELECT COUNT(*) FROM systems"' not in source
