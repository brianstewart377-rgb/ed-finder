from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "operator" / "audit_production_candidate.py"
SPEC = importlib.util.spec_from_file_location("audit_production_candidate", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def test_manifest_modes_and_checksums_are_authoritative(tmp_path):
    (tmp_path / "001.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "002.sql").write_text("SELECT 2;\n", encoding="utf-8")
    manifest = tmp_path / "migration-manifest.txt"
    manifest.write_text("001.sql\n002.sql|manual\n", encoding="utf-8")

    entries = audit.load_manifest(manifest)

    assert [(entry.filename, entry.mode) for entry in entries] == [("001.sql", "auto"), ("002.sql", "manual")]
    assert entries[0].checksum == hashlib.sha256(b"SELECT 1;\n").hexdigest()


class LedgerReader:
    def relation_kind(self, name):
        return "r" if name == "schema_migrations" else None

    def rows(self, query, params=()):
        assert "schema_migrations" in query
        return [("001.sql", "wrong"), ("unexpected.sql", "abc")]


def test_migration_audit_separates_auto_manual_checksum_and_unexpected(tmp_path):
    (tmp_path / "001.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "002.sql").write_text("SELECT 2;", encoding="utf-8")
    manifest = tmp_path / "migration-manifest.txt"
    manifest.write_text("001.sql\n002.sql|manual\n", encoding="utf-8")

    result = audit.migration_audit(LedgerReader(), audit.load_manifest(manifest))

    assert result["pending_auto"] == []
    assert result["pending_manual"] == ["002.sql"]
    assert result["checksum_mismatches"] == ["001.sql"]
    assert result["unexpected_ledger_entries"] == ["unexpected.sql"]


def _otherwise_ready_report():
    required = [
        {"name": "grid", "present": True, "eligible": 2, "missing": 0},
        {"name": "ratings", "present": True, "eligible": 2, "rows": 2, "wrong_version": 0, "dirty": 0},
        {"name": "topology", "present": True, "eligible": 2, "rows": 2},
        {"name": "economy_pair_synergy", "present": True, "eligible": 2, "source_built": 2, "rows": 2, "covered": 2},
        {"name": "archetypes", "present": True, "eligible": 2, "scores": 2, "traits": 2, "dirty": 0},
        {"name": "regional_analysis", "present": True, "eligible": 2, "rows": 2},
        {"name": "station_body_links", "present": True, "eligible": 2, "covered": 2},
        {"name": "clusters", "present": True, "eligible": 2, "rows": 1, "dirty_rows": 0, "system_dirty": 0},
    ]
    return {
        "server": {"version_num": 180000},
        "migrations": {"ledger_present": True, "pending_auto": [], "pending_manual": [], "checksum_mismatches": [], "unexpected_ledger_entries": []},
        "base_tables": [{"name": name, "classification": "required_base", "present": True, "row_count": 2} for name in ("systems", "bodies", "stations", "body_rings")],
        "required_builds": required,
        "materialized_views": [{"name": "mv", "classification": "required_build", "present": True, "populated": True, "row_count": 2}],
        "runtime_feature_tables": [],
    }


def test_required_builds_block_but_runtime_feature_tables_do_not():
    report = _otherwise_ready_report()
    report["runtime_feature_tables"] = [
        {"name": "journal_events", "classification": "inventory_only", "present": True, "row_count": 0},
        {"name": "routes", "classification": "inventory_only", "present": False, "row_count": None},
        {"name": "app_users", "classification": "inventory_only", "present": True, "row_count": 0},
    ]
    assert audit.blockers_for(report) == []

    report["required_builds"][1]["wrong_version"] = 1
    assert audit.blockers_for(report) == ["ratings v3.4 build incomplete"]


def test_requires_exact_postgres_18_and_complete_synergy_coverage():
    report = _otherwise_ready_report()
    report["server"]["version_num"] = 190000
    report["required_builds"][3].update(source_built=2, covered=1)

    assert audit.blockers_for(report) == [
        "PostgreSQL server major version is not 18",
        "economy_pair_synergy coverage incomplete",
    ]


def test_command_fails_closed_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert audit.main([]) == 2
    assert "no database was contacted" in capsys.readouterr().err


def test_connection_failure_does_not_leak_database_url_or_password(monkeypatch, capsys):
    secret = "postgresql://user:super-secret@example.invalid/db"

    def fail(*args, **kwargs):
        raise RuntimeError(f"could not connect to {secret}")

    monkeypatch.setattr(audit.psycopg2, "connect", fail)
    assert audit.main(["--database-url", secret, "--json"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"] == "RuntimeError"
    assert secret not in captured.out + captured.err
    assert "super-secret" not in captured.out + captured.err


def test_missing_optional_relation_is_reported_without_querying_it():
    class MissingReader:
        def relation_kind(self, name):
            return None

        def count(self, name):
            raise AssertionError("missing relation must not be counted")

    assert audit._relation(MissingReader(), "routes", classification="inventory_only") == {
        "name": "routes", "classification": "inventory_only", "present": False, "row_count": None
    }


def test_missing_metric_dependency_is_reported_without_aborting_transaction():
    class MissingReader:
        def relation_kind(self, name):
            return None if name == "ratings" else "r"

        def rows(self, query):
            raise AssertionError("metric SQL must not run with missing dependencies")

    result = audit._metric(MissingReader(), "ratings", "SELECT forbidden", ("systems", "ratings"))
    assert result["present"] is False
    assert result["missing_relations"] == ["ratings"]


def test_compose_resolution_is_explicit_and_does_not_start_services(monkeypatch):
    called = []

    class Completed:
        stdout = json.dumps({"services": {"maintenance": {"environment": {"DATA_INVARIANTS_DATABASE_URL": "postgresql://resolved.invalid/db"}}}})

    def fake_run(command, **kwargs):
        called.append(command)
        return Completed()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    monkeypatch.setattr(audit.psycopg2, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    assert audit.main(["--compose"]) == 2
    assert called[0][-3:] == ["config", "--format", "json"]
    assert "up" not in called[0] and "run" not in called[0] and "exec" not in called[0]


def test_read_only_contract_and_json_human_rendering():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "set_session(readonly=True, autocommit=False)" in source
    assert 'SHOW transaction_read_only' in source
    assert not any(token in source for token in ("INSERT INTO systems", "UPDATE systems", "DELETE FROM systems", "CREATE TABLE schema_migrations"))

    report = _otherwise_ready_report()
    report.update({"ready": True, "read_only": True, "server": {"version": "18.1", "version_num": 180001, "database_size_bytes": 42}, "blockers": []})
    assert json.loads(json.dumps(report))["read_only"] is True
    assert "PostgreSQL 18.1" in audit.render_human(report)
