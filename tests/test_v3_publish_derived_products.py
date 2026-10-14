"""Atomic Finder publication, rollback, and private host commit handshake."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

import pytest

from scripts.operator.lib.f2d_evidence import load_sealed, seal
from scripts import v3_archetype_plan_probe as probe
from scripts import v3_publish_derived_products as publisher


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
IDENTITY = "a" * 64
STATEMENTS = {
    "ranking_version": "ranking-test",
    "ranking_sha256": "b" * 64,
    "statements": [{
        "name": "fake-page", "sql": "SELECT 1", "params": [],
        "param_sql_types": [], "kind": "galaxy_page", "expectations": {},
    }],
}


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    """Model publication state so unit assertions also prove rollback effects."""

    autocommit = False

    def __init__(self, *, already_published=False, ready=True, sentinel=10001):
        self.already_published = already_published
        self.ready = ready
        self.sentinel = sentinel
        self.pending = []
        self.committed = []
        self.events = []

    def execute(self, query, params=None):
        self.events.append((query, params))
        if "g.generation_key" in query:
            return Cursor([("fixture", "PUBLISHED", 1)])
        if "FOR UPDATE" in query:
            return Cursor([
                (code, "READY" if self.ready else "BUILDING", "VERIFIED",
                 NOW if self.already_published and code == "system_search" else None)
                for code in sorted(publisher.PRODUCTS)
            ])
        if "publish_derived_product(" in query:
            code = "system_search" if "'system_search'" in query else "system_archetype"
            self.pending.append(code)
            return Cursor([(NOW,)])
        if "transaction_timestamp()" in query:
            return Cursor([(NOW,)])
        if "derived_product_publication_audit" in query:
            return Cursor([(code, "v1", "d" * 64, NOW, "github:test/run-1")
                           for code in sorted(self.pending)])
        if "count(*)" in query:
            return Cursor([(self.sentinel,)])
        if "pg_class" in query:
            return Cursor([(code, 198_500_000.0) for code in publisher.PRODUCTS])
        return Cursor([])

    def commit(self):
        self.events.append(("COMMIT", None))
        self.committed = list(self.pending)
        self.pending = []

    def rollback(self):
        self.events.append(("ROLLBACK", None))
        self.pending = []


def invoke(connection, directory, **overrides):
    kwargs = dict(
        generation_id=str(uuid4()), generation_key="fixture", publication_sequence=1,
        actor="github:test/run-1", search_final_insert_at=NOW.isoformat(),
        archetype_final_insert_at=NOW.isoformat(), dense_anchor_cell={"cell": 1},
        publish_dir=directory, f2d_identity=IDENTITY,
    )
    kwargs.update(overrides)
    return publisher.publish_products(connection, STATEMENTS, **kwargs)


def stub_probe(monkeypatch, *, status="passed"):
    calls = []

    def run(connection, document, **kwargs):
        assert set(connection.pending) == set(publisher.PRODUCTS)
        assert kwargs["allow_unpublished"] is True
        calls.append((connection, document, kwargs))
        return seal({"status": status, "failures": [] if status == "passed" else ["index"]})

    monkeypatch.setattr(probe, "run_plan_probe", run)
    return calls


def test_success_probes_same_connection_then_handshake_then_commit(monkeypatch, tmp_path):
    connection = Connection()
    calls = stub_probe(monkeypatch)

    def decision(directory, timeout):
        assert directory == tmp_path and timeout == 120
        ready = json.loads((directory / "ready-to-commit.json").read_text())
        assert ready["products"] == list(publisher.PRODUCTS)
        assert ready["published_at"]["system_search"] == ready["published_at"]["system_archetype"]
        assert ready["plan_probe_receipt_sha256"]
        assert (directory / "ready-to-commit.json").stat().st_mode & 0o777 == 0o600
        connection.events.append(("HOST_IMAGE_CHECK", None))

    monkeypatch.setattr(publisher, "_wait_for_decision", decision)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 0 and receipt["status"] == "published"
    assert receipt["publication_performed"] and receipt["db_writes_performed"]
    assert calls[0][0] is connection
    assert connection.committed == list(publisher.PRODUCTS)
    assert [event[0] for event in connection.events[-2:]] == ["HOST_IMAGE_CHECK", "COMMIT"]
    assert len(receipt["audit_rows"]) == 2
    assert set(receipt["view_visibility"]["counts"].values()) == {10001}
    publisher.atomic_json(tmp_path / "receipt.json", receipt)
    assert load_sealed(tmp_path / "receipt.json") == receipt


def test_failed_probe_rolls_back_both_products_without_ready_file(monkeypatch, tmp_path):
    connection = Connection()
    stub_probe(monkeypatch, status="failed")
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 22
    assert not connection.pending and not connection.committed
    assert not receipt["publication_performed"] and not receipt["db_writes_performed"]
    assert receipt["plan_probe_receipt"]["status"] == "failed"
    assert not (tmp_path / "ready-to-commit.json").exists()


@pytest.mark.parametrize("decision", [
    {"decision": "abort", "reason": "image_changed"},
    {"decision": "commit", "extra": True}, None, [], {"decision": "invalid"},
])
def test_abort_and_malformed_host_decision_roll_back(monkeypatch, tmp_path, decision):
    connection = Connection()
    stub_probe(monkeypatch)
    wait = publisher._wait_for_decision

    def deliver(directory, timeout):
        (directory / "commit-decision.json").write_text(json.dumps(decision))
        wait(directory, timeout)

    monkeypatch.setattr(publisher, "_wait_for_decision", deliver)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 77
    assert not connection.pending and not connection.committed
    assert not receipt["db_writes_performed"]


def test_one_second_handshake_timeout_rolls_back(monkeypatch, tmp_path):
    connection = Connection()
    stub_probe(monkeypatch)
    receipt = invoke(connection, tmp_path, handshake_timeout_seconds=1)
    assert receipt["exit_code"] == 78 and "timeout" in receipt["failures"][0]
    assert not connection.pending and not connection.committed


def test_repeat_publication_refuses_without_calling_publisher(monkeypatch, tmp_path):
    connection = Connection(already_published=True)
    calls = stub_probe(monkeypatch)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 72
    assert receipt["failures"] == ["publication_already_happened"]
    assert not calls and not connection.pending and not connection.committed
    assert not any("publish_derived_product(" in query for query, _ in connection.events)


@pytest.mark.parametrize("ready,sentinel", [(False, 10001), (True, 10000)])
def test_product_or_visibility_failure_rolls_back(monkeypatch, tmp_path, ready, sentinel):
    connection = Connection(ready=ready, sentinel=sentinel)
    calls = stub_probe(monkeypatch)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 71 and not calls
    assert not connection.pending and not connection.committed


def test_live_maintenance_refusal_has_exit_76(monkeypatch, tmp_path):
    connection = Connection()

    def maintenance(*args, **kwargs):
        raise probe.PlanProbeRefusal(20, "system_search_last_analyze_predates_final_insert")

    monkeypatch.setattr(probe, "run_plan_probe", maintenance)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 76
    assert not connection.pending and not connection.committed


@pytest.mark.parametrize("value", [
    None, {"status": "passed"}, {"status": "passed", "content_sha256": "0" * 64},
])
def test_unsealed_or_malformed_probe_result_rolls_back(monkeypatch, tmp_path, value):
    connection = Connection()
    monkeypatch.setattr(probe, "run_plan_probe", lambda *args, **kwargs: value)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 22
    assert not connection.pending and not connection.committed
    assert not (tmp_path / "ready-to-commit.json").exists()


@pytest.mark.parametrize("filename", ["ready-to-commit.json", "commit-decision.json"])
def test_stale_handshake_files_refuse_before_any_database_statement(tmp_path, filename):
    (tmp_path / filename).write_text('{"decision":"commit"}')
    connection = Connection()
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 77
    assert connection.events == [("ROLLBACK", None)]


def test_identity_is_first_before_argument_files_or_database(monkeypatch):
    def refuse(*args):
        raise publisher.f2d_operator_identity.OperatorIdentityError("attested_identity_mismatch")

    monkeypatch.setattr(publisher.f2d_operator_identity, "require_operator_code_identity", refuse)
    assert publisher.main([]) == 2


def test_program_sql_only_writes_through_two_parameterized_publish_calls():
    source = (ROOT / "scripts/v3_publish_derived_products.py").read_text()
    tree = ast.parse(source)
    queries = [
        node.args[0].value for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute" and node.args
        and isinstance(node.args[0], ast.Constant)
    ]
    assert not any(query.strip().upper().startswith(("DELETE", "TRUNCATE", "UPDATE", "INSERT"))
                   for query in queries)
    writes = [query for query in queries if "publish_derived_product(" in query]
    assert writes == [
        "SELECT v3_meta.publish_derived_product(%s,'system_search',%s)",
        "SELECT v3_meta.publish_derived_product(%s,'system_archetype',%s)",
    ]
    assert all("LIMIT 10001" in query for query in queries if "v3_app." in query)
    assert "SET LOCAL plan_cache_mode = 'force_generic_plan'" in queries
    assert "SET LOCAL statement_timeout = '600s'" in queries


@pytest.fixture
def publication_database():
    """Real migration 015 guards with the full 10,001-row sentinel fixture."""
    from psycopg import sql
    from tests.ratings_v4_pg_fixture import canonical_database
    from tests import test_v3_derived_product_publication as fixture

    with canonical_database() as state:
        connection = state[0]
        for name in (*fixture.PRE_015, "015_v3_derived_product_publication.sql"):
            connection.execute((fixture.MIGRATIONS / name).read_text())
        generation = fixture._insert_generation(connection)
        fixture._seed_rating(connection, generation)
        connection.execute(
            """
            INSERT INTO v3_derived.system_rating_vector (
                derived_generation_id, system_id64, chunk_ordinal,
                loaded_body_count, physical_body_count, subtype_projection_sha256,
                potential, quality, quality_min, quality_max, completeness, confidence
            ) SELECT derived_generation_id, n, chunk_ordinal,
                     loaded_body_count, physical_body_count, subtype_projection_sha256,
                     potential, quality, quality_min, quality_max, completeness, confidence
                FROM v3_derived.system_rating_vector CROSS JOIN generate_series(43,10042) n
               WHERE derived_generation_id=%s AND system_id64=42
            """, (generation,),
        )
        fixture._make_ready(connection, generation)
        fixture._publish_generation(connection, generation)
        for code in publisher.PRODUCTS:
            fixture._register_product(connection, generation, code)
        fixture._insert_search_row(connection, generation)
        fixture._insert_archetype_row(connection, generation)
        # Copy the real complete rows using identifiers quoted by Psycopg.
        for table in publisher.PRODUCTS:
            columns = [row[0] for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='v3_derived' AND table_name=%s "
                "ORDER BY ordinal_position", (table,),
            ).fetchall()]
            connection.execute(sql.SQL(
                "INSERT INTO v3_derived.{} ({}) SELECT {} "
                "FROM v3_derived.{} t CROSS JOIN generate_series(43,10042) n "
                "WHERE t.derived_generation_id=%s AND t.system_id64=42"
            ).format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
                sql.SQL(",").join(sql.SQL("n") if name == "system_id64"
                                  else sql.Identifier("t", name) for name in columns),
                sql.Identifier(table),
            ), (generation,))
        connection.execute(
            "UPDATE v3_meta.derived_product SET lifecycle_state='READY', "
            "validation_receipt=%s::jsonb,validation_sha256=%s,validated_at=transaction_timestamp() "
            "WHERE derived_generation_id=%s",
            (json.dumps({"status": "VERIFIED"}), fixture.HASH, generation),
        )
        key = connection.execute(
            "SELECT generation_key FROM v3_meta.derived_generation WHERE derived_generation_id=%s",
            (generation,),
        ).fetchone()[0]
        yield connection, generation, key


def _database_invoke(state, directory, monkeypatch, *, probe_status="passed", decision="commit"):
    import psycopg
    from psycopg.conninfo import make_conninfo

    observer, generation, key = state

    def run(connection, document, **kwargs):
        assert kwargs["allow_unpublished"]
        assert connection.execute(
            "SELECT count(*) FROM v3_meta.derived_product "
            "WHERE derived_generation_id=%s AND published_at IS NOT NULL", (generation,),
        ).fetchone()[0] == 2
        # Other connections cannot see this transaction's uncommitted products.
        assert observer.execute(
            "SELECT count(*) FROM v3_meta.derived_product "
            "WHERE derived_generation_id=%s AND published_at IS NOT NULL", (generation,),
        ).fetchone()[0] == 0
        return seal({"status": probe_status, "failures": []})

    monkeypatch.setattr(probe, "run_plan_probe", run)
    stop = threading.Event()

    def host():
        deadline = time.monotonic() + 20
        while not stop.is_set() and time.monotonic() < deadline:
            if (directory / "ready-to-commit.json").exists():
                if decision is not None:
                    value = {"decision": decision}
                    if decision == "abort":
                        value["reason"] = "image_digest_changed"
                    publisher.atomic_json(directory / "commit-decision.json", value)
                return
            stop.wait(0.01)

    worker = threading.Thread(target=host, daemon=True)
    worker.start()
    try:
        dsn = make_conninfo(observer.info.dsn, password=observer.info.password)
        with psycopg.connect(dsn, autocommit=False) as connection:
            return invoke(connection, directory, generation_id=str(generation), generation_key=key,
                          handshake_timeout_seconds=1 if decision is None else 120)
    finally:
        stop.set()
        worker.join(timeout=1)


def _assert_database_publication(state, *, published):
    connection, generation, _ = state
    rows = connection.execute(
        "SELECT published_at FROM v3_meta.derived_product WHERE derived_generation_id=%s",
        (generation,),
    ).fetchall()
    assert len(rows) == 2
    assert all((row[0] is not None) is published for row in rows)
    if published:
        assert rows[0][0] == rows[1][0]
    audit = connection.execute(
        "SELECT count(*) FROM v3_meta.derived_product_publication_audit WHERE derived_generation_id=%s",
        (generation,),
    ).fetchone()[0]
    assert audit == (2 if published else 0)
    assert connection.execute(
        "SELECT count(*) FROM (SELECT 1 FROM v3_app.system_search LIMIT 10001) t"
    ).fetchone()[0] == (10001 if published else 0)
    assert connection.execute(
        "SELECT count(*) FROM (SELECT 1 FROM v3_app.system_archetype LIMIT 10001) t"
    ).fetchone()[0] == (10001 if published else 0)


def test_database_success_publishes_both_with_equal_timestamp_audit_and_views(
    publication_database, monkeypatch, tmp_path,
):
    receipt = _database_invoke(publication_database, tmp_path, monkeypatch)
    assert receipt["exit_code"] == 0
    _assert_database_publication(publication_database, published=True)


@pytest.mark.parametrize("probe_status,decision,exit_code", [
    ("failed", "commit", 22), ("passed", "abort", 77), ("passed", None, 78),
])
def test_database_probe_abort_and_timeout_roll_back(
    publication_database, monkeypatch, tmp_path, probe_status, decision, exit_code,
):
    receipt = _database_invoke(publication_database, tmp_path, monkeypatch,
                               probe_status=probe_status, decision=decision)
    assert receipt["exit_code"] == exit_code
    assert not receipt["publication_performed"] and not receipt["db_writes_performed"]
    _assert_database_publication(publication_database, published=False)


def test_database_one_already_published_refuses_without_second_product_write(
    publication_database, monkeypatch, tmp_path,
):
    connection, generation, _ = publication_database
    connection.execute("SELECT v3_meta.publish_derived_product(%s,'system_search',%s)",
                       (generation, "earlier-publication"))
    receipt = _database_invoke(publication_database, tmp_path, monkeypatch)
    assert receipt["exit_code"] == 72 and not receipt["db_writes_performed"]
    assert connection.execute(
        "SELECT product_code FROM v3_meta.derived_product_publication_audit "
        "WHERE derived_generation_id=%s", (generation,),
    ).fetchall() == [("system_search",)]
