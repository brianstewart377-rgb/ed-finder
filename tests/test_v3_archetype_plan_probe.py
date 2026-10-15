from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts.operator.lib.f2d_evidence import canonical_sha256
from scripts import v3_archetype_plan_probe as probe


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "database,user,expected_code",
    [
        ("edfinder_v3_phase4c_full_20260827_r5", "edfinder_v3", 0),
        ("other_database", "edfinder_v3", 24),
        ("edfinder_v3_phase4c_full_20260827_r5", "other_role", 24),
    ],
)
def test_main_checks_connected_database_identity_before_probe_statements(
    database: str, user: str, expected_code: int,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, *_args):
            executed.append(query)
            return SimpleNamespace(fetchone=lambda: (database, user))

    connection = Connection()
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *_a, **_k: connection))
    monkeypatch.setattr(probe, "refuse_unlisted_checkout_modules", lambda: None)
    monkeypatch.setattr(probe, "validate_statements_document", lambda _document: None)
    monkeypatch.setattr(
        probe, "run_plan_probe",
        lambda *_a, **_k: executed.append("probe") or {"status": "passed"},
    )
    monkeypatch.setenv("F2D_OPERATOR_CODE_SHA256_ATTESTED", "a" * 64)
    monkeypatch.setenv("V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL", "postgresql://unused/test")
    statements = tmp_path / "statements.json"
    statements.write_text("{}", encoding="utf-8")
    output = tmp_path / "receipt.json"
    result = probe.main([
        "--statements", str(statements),
        "--statements-sha256", "b" * 64,
        "--image-digest", "image@sha256:" + "c" * 64,
        "--generation-key", "test", "--generation-id", "generation",
        "--publication-sequence", "1",
        "--search-final-insert-at", "2026-01-01T00:00:00+00:00",
        "--archetype-final-insert-at", "2026-01-01T00:00:00+00:00",
        "--dense-anchor-cell", "{}", "--output", str(output),
    ])
    assert result == expected_code
    assert executed[0] == "SELECT current_database(), current_user"
    if expected_code:
        assert executed == ["SELECT current_database(), current_user"]
        assert not hasattr(connection, "read_only")
        assert not output.exists()
    else:
        assert executed[-1] == "probe"
        assert connection.read_only is True
        assert json.loads(output.read_text()) == {"status": "passed"}


def _scan(
    relation: str,
    index: str | None,
    *,
    node_type: str = "Index Scan",
    alias: str | None = None,
    rows: int = 1,
    loops: int = 1,
    removed: int = 0,
    heap_fetches: int | None = None,
) -> dict:
    node = {
        "Node Type": node_type,
        "Relation Name": relation,
        "Alias": alias or relation,
        "Actual Rows": rows,
        "Actual Loops": loops,
        "Rows Removed by Filter": removed,
    }
    if index is not None:
        node["Index Name"] = index
    if heap_fetches is not None:
        node["Heap Fetches"] = heap_fetches
    return node


def _explain(root: dict) -> list[dict]:
    return [{"Plan": root, "Planning Time": 1.0, "Execution Time": 2.0}]


def _picked_plan(*, heap_fetches: int = 0, search_rows: int = 1) -> list[dict]:
    window = _scan(
        "system_archetype",
        "system_archetype_paradise_b_weighted",
        node_type="Index Only Scan",
        alias="ar",
        rows=10_000,
        heap_fetches=heap_fetches,
    )
    search = _scan(
        "system_search",
        "system_search_pkey",
        alias="s",
        rows=search_rows,
        loops=50,
    )
    ranked = {
        "Node Type": "Nested Loop",
        "Actual Rows": 10_000,
        "Actual Loops": 1,
        "Plans": [window, search],
    }
    sorted_rows = {
        "Node Type": "Sort",
        "Actual Rows": 50,
        "Actual Loops": 1,
        "Plans": [ranked],
    }
    fetch = _scan(
        "system_archetype",
        "system_archetype_pkey",
        alias="picked",
        rows=1,
        loops=50,
    )
    return _explain(
        {
            "Node Type": "Nested Loop",
            "Actual Rows": 50,
            "Actual Loops": 1,
            "Plans": [
                {
                    "Node Type": "Limit",
                    "Plan Rows": 50,
                    "Actual Rows": 50,
                    "Actual Loops": 1,
                    "Plans": [sorted_rows],
                },
                fetch,
            ],
        }
    )


def _picked_statement() -> dict:
    return {
        "name": "picked_paradise_60_page_50",
        "kind": "picked_page",
        "expectations": {
            "expected_index": "system_archetype_paradise_b_weighted",
            "page_size": 50,
        },
    }


def _failed(assertions: list[dict], name: str | None = None) -> list[dict]:
    return [
        item
        for item in assertions
        if not item["passed"] and (name is None or item["name"] == name)
    ]


def test_conforming_picked_plan_passes_and_heap_fetch_fails() -> None:
    assertions = probe.evaluate_plan_assertions(
        _picked_statement(), _picked_plan(), generation_count=1
    )
    assert not _failed(assertions)

    assertions = probe.evaluate_plan_assertions(
        _picked_statement(), _picked_plan(heap_fetches=1), generation_count=1
    )
    assert _failed(assertions, "picked_window_heap_fetches_zero")


def _deployed_picked_plan() -> list[dict]:
    """PostgreSQL JSON shape for the CTEs/join emitted by build_ranked_query."""
    window = _scan(
        "system_archetype", "system_archetype_paradise_b_weighted",
        node_type="Index Only Scan", alias="ar", rows=10_000, heap_fetches=0,
    )
    window.update({
        "Parent Relationship": "Outer", "Schema": "v3_derived",
        "Index Cond": "(derived_generation_id = $0)",
    })
    search = _scan("system_search", "system_search_pkey", alias="s", loops=10_000)
    search.update({
        "Parent Relationship": "Inner", "Schema": "v3_derived",
        "Index Cond": "((derived_generation_id = $1) AND (system_id64 = ar.system_id64))",
    })
    picked = _scan("system_archetype", "system_archetype_pkey", alias="picked", loops=50)
    picked.update({
        "Parent Relationship": "Inner", "Schema": "v3_derived",
        "Index Cond": "((derived_generation_id = $2) AND (system_id64 = page.system_id64))",
    })
    return _explain({
        "Node Type": "Sort", "Actual Rows": 50, "Actual Loops": 1,
        "Sort Key": ["page.selected_archetype_weighted_e4 DESC", "page.system_id64"],
        "Plans": [{
            "Node Type": "Nested Loop", "Join Type": "Inner",
            "Actual Rows": 50, "Actual Loops": 1,
            "Plans": [{
                "Node Type": "Subquery Scan", "Alias": "page",
                "Parent Relationship": "Outer", "Actual Rows": 50, "Actual Loops": 1,
                "Plans": [{
                    "Node Type": "Limit", "Plan Rows": 50,
                    "Actual Rows": 50, "Actual Loops": 1,
                    "Plans": [{
                        "Node Type": "Sort", "Actual Rows": 50, "Actual Loops": 1,
                        "Sort Key": ["ar.paradise_weighted_e4 DESC", "s.system_id64"],
                        "Plans": [{
                            "Node Type": "Nested Loop", "Join Type": "Inner",
                            "Actual Rows": 10_000, "Actual Loops": 1,
                            "Plans": [{
                                "Node Type": "Limit", "Plan Rows": 10_000,
                                "Actual Rows": 10_000, "Actual Loops": 1,
                                "Plans": [window],
                            }, search],
                        }],
                    }],
                }],
            }, picked],
        }],
    })


def test_deployed_picked_page_fetch_is_outside_ranked_page_limit() -> None:
    from ranking.profile import PROFILE_SPEC
    from ranking.ranking_sql import build_ranked_query

    sql, _params = build_ranked_query(
        PROFILE_SPEC, picked_archetype="paradise", picked_economy=None,
        hard_filters={}, reference_coords=None, limit=50, offset=0, min_score=60,
    )
    assert "JOIN v3_app.system_archetype picked ON picked.system_id64 = page.system_id64" in sql
    plan = _deployed_picked_plan()
    assertions = probe.evaluate_plan_assertions(_picked_statement(), plan, generation_count=1)
    assert not _failed(assertions)
    picked = plan[0]["Plan"]["Plans"][0]["Plans"][1]
    picked["Actual Loops"] = 51
    assertions = probe.evaluate_plan_assertions(_picked_statement(), plan, generation_count=1)
    assert _failed(assertions, "picked_fetch_rows_bound")


def test_picked_alias_inside_window_does_not_substitute_for_final_fetch() -> None:
    plan = _deployed_picked_plan()
    page = plan[0]["Plan"]["Plans"][0]["Plans"][0]
    window = page["Plans"][0]["Plans"][0]["Plans"][0]["Plans"][0]["Plans"][0]
    window["Alias"] = "picked"
    plan[0]["Plan"]["Plans"][0]["Plans"].pop()
    assertions = probe.evaluate_plan_assertions(_picked_statement(), plan, generation_count=1)
    assert _failed(assertions, "picked_fetch_rows_bound")


def test_picked_fetch_structural_match_cross_checks_emitted_alias() -> None:
    plan = _deployed_picked_plan()
    plan[0]["Plan"]["Plans"][0]["Plans"][1]["Alias"] = "fetch"
    assertions = probe.evaluate_plan_assertions(_picked_statement(), plan, generation_count=1)
    assert _failed(assertions, "picked_fetch_alias_matches_sql")


@pytest.mark.parametrize(
    "node_type,heap_fetches,expected_failure",
    [("Index Only Scan", 0, None), ("Index Scan", 0, "picked_window_scan_type"),
     ("Index Only Scan", 1, "picked_window_heap_fetches_zero"),
     ("Index Only Scan", None, "picked_window_heap_fetches_zero")],
)
def test_picked_count_requires_index_only_and_zero_heap_fetches(
    node_type: str, heap_fetches: int | None, expected_failure: str | None,
) -> None:
    statement = _picked_statement()
    statement["kind"] = "picked_count"
    plan = _explain({
        "Node Type": "Aggregate", "Actual Rows": 1, "Actual Loops": 1,
        "Plans": [{
            "Node Type": "Limit", "Plan Rows": 10_001,
            "Actual Rows": 10_001, "Actual Loops": 1,
            "Plans": [_scan(
                "system_archetype", "system_archetype_paradise_b_weighted",
                node_type=node_type, alias="ar", rows=10_001, heap_fetches=heap_fetches,
            )],
        }],
    })
    assertions = probe.evaluate_plan_assertions(statement, plan, generation_count=1)
    if expected_failure:
        assert _failed(assertions, expected_failure)
    else:
        assert not _failed(assertions)


@pytest.mark.parametrize("node_type", ["Seq Scan", "Bitmap Heap Scan", "Bitmap Index Scan"])
def test_disallowed_search_scan_shapes_fail(node_type: str) -> None:
    plan = _picked_plan()
    search = plan[0]["Plan"]["Plans"][0]["Plans"][0]["Plans"][0]["Plans"][1]
    search["Node Type"] = node_type
    search.pop("Index Name", None)
    assertions = probe.evaluate_plan_assertions(
        _picked_statement(), plan, generation_count=1
    )
    assert any(
        not item["passed"] and item["name"].startswith("bounded_index_access")
        for item in assertions
    )


def test_hash_join_fed_by_archetype_fails() -> None:
    plan = _picked_plan()
    plan[0]["Plan"]["Node Type"] = "Hash Join"
    assertions = probe.evaluate_plan_assertions(
        _picked_statement(), plan, generation_count=1
    )
    assert _failed(assertions, "no_hash_or_merge_join_over_ranked_relations")


@pytest.mark.parametrize("rows,passes", [(10_001, True), (10_002, False)])
def test_examined_row_bound_is_inclusive(rows: int, passes: bool) -> None:
    plan = _picked_plan(search_rows=1)
    search = plan[0]["Plan"]["Plans"][0]["Plans"][0]["Plans"][0]["Plans"][1]
    search["Actual Rows"] = rows
    search["Actual Loops"] = 1
    assertions = probe.evaluate_plan_assertions(
        _picked_statement(), plan, generation_count=1
    )
    matching = [
        item
        for item in assertions
        if item["name"].startswith("examined_rows_bound:system_search")
    ]
    assert matching and matching[0]["passed"] is passes


def _galaxy_statement(kind: str = "galaxy_page") -> dict:
    return {
        "name": kind,
        "kind": kind,
        "expectations": {"expected_index": "system_archetype_summary_weighted"},
    }


def test_galaxy_page_requires_summary_weighted_index() -> None:
    summary = _scan(
        "system_archetype", "system_archetype_summary_weighted", alias="sum", rows=24
    )
    search = _scan("system_search", "system_search_pkey", alias="s", rows=1, loops=24)
    plan = _explain(
        {
            "Node Type": "Limit",
            "Plan Rows": 24,
            "Actual Rows": 24,
            "Actual Loops": 1,
            "Plans": [summary, search],
        }
    )
    assertions = probe.evaluate_plan_assertions(
        _galaxy_statement(), plan, generation_count=1
    )
    assert not _failed(assertions)
    summary["Index Name"] = "system_archetype_pkey"
    assertions = probe.evaluate_plan_assertions(
        _galaxy_statement(), plan, generation_count=1
    )
    assert _failed(assertions, "galaxy_window_summary_index")


def test_no_pick_sentinel_accepts_capped_seq_scan_but_rejects_unbounded_work() -> None:
    scan = _scan("system_search", None, node_type="Seq Scan", rows=10_001)
    limit = {
        "Node Type": "Limit",
        "Plan Rows": 10_001,
        "Actual Rows": 10_001,
        "Actual Loops": 1,
        "Plans": [scan],
    }
    assertions = probe.evaluate_plan_assertions(
        _galaxy_statement("galaxy_count"), _explain(limit), generation_count=1
    )
    assert not _failed(assertions)

    assertions = probe.evaluate_plan_assertions(
        _galaxy_statement("galaxy_count"), _explain(scan), generation_count=1
    )
    assert _failed(assertions, "no_pick_count_sentinel_limit")

    scan["Rows Removed by Filter"] = 1
    assertions = probe.evaluate_plan_assertions(
        _galaxy_statement("galaxy_count"), _explain(limit), generation_count=1
    )
    assert any(
        not item["passed"] and item["name"].startswith("examined_rows_bound")
        for item in assertions
    )


def _knn_plan(rows: int, *, incremental: bool = True) -> list[dict]:
    scan = _scan(
        "system_search", "system_search_position_gist", alias="s", rows=rows
    )
    ordering = {
        "Node Type": "Incremental Sort" if incremental else "Sort",
        "Actual Rows": min(rows, 24),
        "Actual Loops": 1,
        "Plans": [scan],
    }
    return _explain(
        {
            "Node Type": "Limit",
            "Plan Rows": 24,
            "Actual Rows": 24,
            "Actual Loops": 1,
            "Plans": [ordering],
        }
    )


def _knn_statement() -> dict:
    return {
        "name": "anchored_nearest_dense_page_24",
        "kind": "anchored_knn_page",
        "expectations": {"inner_limit": 24},
    }


def test_anchored_knn_requires_gist_incremental_sort_and_generation_scaled_bound() -> None:
    assertions = probe.evaluate_plan_assertions(
        _knn_statement(), _knn_plan(1_024), generation_count=1
    )
    assert not _failed(assertions)

    assertions = probe.evaluate_plan_assertions(
        _knn_statement(), _knn_plan(1_025), generation_count=1
    )
    assert _failed(assertions, "anchored_knn_examined_rows_bound")

    assertions = probe.evaluate_plan_assertions(
        _knn_statement(), _knn_plan(1_025), generation_count=2
    )
    assert not _failed(assertions)

    assertions = probe.evaluate_plan_assertions(
        _knn_statement(), _knn_plan(10, incremental=False), generation_count=1
    )
    assert _failed(assertions, "anchored_knn_limit_incremental_sort_shape")


@pytest.mark.parametrize("kind", ["anchored_knn_page", "anchored_knn_count"])
def test_knn_tie_slack_replaces_generic_bound_for_gist_node(kind: str) -> None:
    statement = _knn_statement()
    statement["kind"] = kind
    statement["expectations"]["inner_limit"] = 10_001
    assertions = probe.evaluate_plan_assertions(statement, _knn_plan(10_501), generation_count=2)
    assert not _failed(assertions)
    assertions = probe.evaluate_plan_assertions(statement, _knn_plan(22_003), generation_count=2)
    assert _failed(assertions, "anchored_knn_examined_rows_bound")


def test_bounding_box_measurement_filters_target_generation_before_scaling() -> None:
    class Connection:
        def execute(self, sql, params):
            assert "derived_generation_id = %s" in sql
            assert "target-generation" not in sql
            assert params == ("target-generation", 1.0, 500.0, 2.0, 500.0, 3.0, 500.0,
                              1.0, 500.0, 2.0, 500.0, 3.0, 500.0)
            # Two generations each hold ten candidates in this box.
            rows = {"target-generation": 10, "other-generation": 10}
            return SimpleNamespace(fetchone=lambda: (rows[params[0]],))

    measurement = probe._candidate_count(
        Connection(), {"coordinates": {"x": 1, "y": 2, "z": 3}},
        generation_id="target-generation",
    )
    assert measurement["count"] == 10
    assert measurement["derived_generation_id"] == "target-generation"
    statement = {"name": "filtered", "kind": "anchored_filtered_page", "expectations": {}}
    plan = _explain(_scan("system_search", "system_search_position_gist", rows=21))
    assertions = probe.evaluate_plan_assertions(
        statement, plan, generation_count=2, candidate_count=measurement["count"],
    )
    assert _failed(assertions, "examined_rows_bound:system_search:system_search")


def test_probe_receipts_target_candidates_with_two_search_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statement = {
        "name": "filtered", "kind": "anchored_filtered_page", "expectations": {},
        "sql": "SELECT 1", "params": [], "param_sql_types": [],
    }
    document = {"ranking_version": "test", "ranking_sha256": "a" * 64,
                "statements": [statement]}
    monkeypatch.setattr(probe, "_check_maintenance", lambda *_a, **_k: [])
    monkeypatch.setattr(probe, "_require_published_products", lambda *_a: None)
    monkeypatch.setattr(probe, "_generation_identity", lambda *_a: {})
    monkeypatch.setattr(probe, "_generation_rows", lambda *_a: ["target", "other"])
    monkeypatch.setattr(probe, "_explain", lambda *_a: _explain(
        _scan("system_search", "system_search_position_gist", rows=21),
    ))

    class Connection:
        autocommit = True

        def execute(self, sql, params):
            if "SELECT count(*)" not in sql:
                return None
            generations = {"target": 10, "other": 10}
            count = (
                generations[params[0]] if "derived_generation_id = %s" in sql
                else sum(generations.values())
            )
            return SimpleNamespace(fetchone=lambda: (count,))

    receipt = probe.run_plan_probe(
        Connection(), document, generation_id="target",
        search_final_insert_at="2026-01-01T00:00:00+00:00",
        archetype_final_insert_at="2026-01-01T00:00:00+00:00",
        dense_anchor_cell={"coordinates": {"x": 0, "y": 0, "z": 0}},
    )
    assert receipt["search_generations"]["count"] == 2
    assert receipt["bounding_box_candidate_measurement"]["count"] == 10
    assert receipt["status"] == "failed"
    assert receipt["failures"][0]["observed"]["bound"] == 20


@pytest.mark.parametrize(
    "kind", ["anchored_filtered_page", "anchored_score_page"]
)
def test_unbounded_anchored_requests_use_candidate_count_times_g(kind: str) -> None:
    statement = {"name": kind, "kind": kind, "expectations": {}}
    plan = _explain(
        _scan(
            "system_search", "system_search_position_gist", alias="s", rows=20
        )
    )
    assertions = probe.evaluate_plan_assertions(
        statement, plan, generation_count=2, candidate_count=10
    )
    assert not _failed(assertions)
    assertions = probe.evaluate_plan_assertions(
        statement, plan, generation_count=1, candidate_count=10
    )
    assert any(
        not item["passed"] and item["name"].startswith("examined_rows_bound")
        for item in assertions
    )


class _RowsCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _MaintenanceConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return _RowsCursor(self.rows)


@pytest.mark.parametrize("field", ["last_vacuum", "last_analyze"])
def test_maintenance_precondition_refuses_null_and_predating(field: str) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        {
            "relname": relation,
            "last_vacuum": now + timedelta(seconds=1),
            "last_analyze": now + timedelta(seconds=1),
        }
        for relation in ("system_archetype", "system_search")
    ]
    rows[0][field] = None
    with pytest.raises(probe.PlanProbeRefusal) as caught:
        probe._check_maintenance(
            _MaintenanceConnection(rows),
            search_final_insert_at=now,
            archetype_final_insert_at=now,
        )
    assert caught.value.exit_code == 20

    rows[0][field] = now - timedelta(seconds=1)
    with pytest.raises(probe.PlanProbeRefusal) as caught:
        probe._check_maintenance(
            _MaintenanceConnection(rows),
            search_final_insert_at=now,
            archetype_final_insert_at=now,
        )
    assert caught.value.exit_code == 20


def test_run_plan_probe_runs_every_statement_after_assertion_failure_and_seals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = [
        {
            "name": f"statement_{index}",
            "kind": "galaxy_page",
            "sql": "SELECT 1",
            "params": [],
            "param_sql_types": [],
            "expectations": {},
        }
        for index in range(3)
    ]
    document = {
        "ranking_version": "test",
        "ranking_sha256": "a" * 64,
        "statements": statements,
        "_runtime": {
            "image_digest": "image@sha256:" + "b" * 64,
            "f2d_operator_code_sha256": "c" * 64,
        },
    }
    executed: list[int] = []
    monkeypatch.setattr(probe, "_check_maintenance", lambda *_a, **_k: [])
    monkeypatch.setattr(probe, "_require_published_products", lambda *_a: None)
    monkeypatch.setattr(
        probe,
        "_generation_identity",
        lambda *_a: {
            "derived_generation_id": "generation",
            "generation_key": "test",
            "lifecycle_state": "PUBLISHED",
            "publication_sequence": 1,
            "is_current": True,
        },
    )
    monkeypatch.setattr(probe, "_generation_rows", lambda *_a: ["generation"])

    def explain(_connection, index, _statement):
        executed.append(index)
        return _explain({"Node Type": "Result", "Actual Rows": 1, "Actual Loops": 1})

    monkeypatch.setattr(probe, "_explain", explain)
    monkeypatch.setattr(
        probe,
        "evaluate_plan_assertions",
        lambda statement, *_a, **_k: [
            {
                "name": "fixture",
                "passed": statement["name"] != "statement_0",
                "observed": {"name": statement["name"]},
            }
        ],
    )

    class Connection:
        autocommit = True

        def execute(self, *_args, **_kwargs):
            return _RowsCursor([])

    receipt = probe.run_plan_probe(
        Connection(),
        document,
        generation_id="generation",
        search_final_insert_at="2026-01-01T00:00:00+00:00",
        archetype_final_insert_at="2026-01-01T00:00:00+00:00",
        dense_anchor_cell={"coordinates": {"x": 0, "y": 0, "z": 0}},
    )
    assert executed == [0, 1, 2]
    assert receipt["status"] == "failed"
    body = dict(receipt)
    seal_value = body.pop("content_sha256")
    assert canonical_sha256(body) == seal_value


def test_statement_validation_refusal_uses_exit_21() -> None:
    with pytest.raises(probe.PlanProbeRefusal) as caught:
        probe.validate_statements_document({})
    assert caught.value.exit_code == 21


def test_loaded_unlisted_checkout_module_refuses_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "deploy/v3-production/f2d-operator-code.txt"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("deploy/v3-production/f2d-operator-code.txt\n", encoding="utf-8")
    unlisted = tmp_path / "unlisted.py"
    unlisted.write_text("loaded = True\n", encoding="utf-8")
    specification = importlib.util.spec_from_file_location("f2d_unlisted_fixture", unlisted)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, specification.name, module)
    # Isolate the checkout from pytest's own loaded repository test modules.
    monkeypatch.setattr(probe, "ROOT", tmp_path, raising=False)
    monkeypatch.setenv("F2D_OPERATOR_CODE_SHA256_ATTESTED", "a" * 64)
    monkeypatch.setenv("V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL", "postgresql://unused/test")
    monkeypatch.setattr(probe, "validate_statements_document", lambda _document: None)
    statements = tmp_path / "statements.json"
    statements.write_text(json.dumps({}), encoding="utf-8")
    connected: list[bool] = []

    def connect(*_args, **_kwargs):
        connected.append(True)
        raise AssertionError("unlisted checkout code must refuse before connecting")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    result = probe.main([
        "--statements", str(statements),
        "--statements-sha256", "b" * 64,
        "--image-digest", "image@sha256:" + "c" * 64,
        "--generation-key", "test", "--generation-id", "generation",
        "--publication-sequence", "1",
        "--search-final-insert-at", "2026-01-01T00:00:00+00:00",
        "--archetype-final-insert-at", "2026-01-01T00:00:00+00:00",
        "--dense-anchor-cell", "{}", "--output", str(tmp_path / "receipt.json"),
    ])
    assert result == 2
    assert connected == []
    assert "plan probe identity refusal" in capsys.readouterr().err
    assert not (tmp_path / "receipt.json").exists()


@pytest.fixture
def plan_probe_database():
    from tests.ratings_v4_pg_fixture import canonical_database

    with canonical_database() as database:
        connection = database[0]
        for name in (
            "003_ratings_v4_derived.sql",
            "004_v3_search_spatial_clusters.sql",
            "006_v3_derived_product_lifecycle.sql",
            "010_v3_system_search_body_type_counts.sql",
            "011_v3_system_archetype.sql",
            "015_v3_derived_product_publication.sql",
        ):
            connection.execute((ROOT / "sql/v3/migrations" / name).read_text())
        yield database


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_disposable_pg18_executes_every_generated_statement(plan_probe_database) -> None:
    from tests.test_archetype_rankings_v3 import _build_published_generation

    sys.path.insert(0, str(ROOT / "apps/api/src"))
    try:
        from scripts.v3_plan_probe_statements import build_statements_document
    finally:
        sys.path.pop(0)

    connection = plan_probe_database[0]
    _build_published_generation(plan_probe_database)
    generation_id = connection.execute(
        "SELECT derived_generation_id::text FROM v3_meta.current_derived_generation"
    ).fetchone()[0]
    search_final = connection.execute(
        "SELECT max(completed_at) FROM v3_derived.search_build_chunk "
        "WHERE derived_generation_id=%s",
        (generation_id,),
    ).fetchone()[0]
    archetype_final = connection.execute(
        "SELECT max(completed_at) FROM v3_derived.archetype_build_chunk "
        "WHERE derived_generation_id=%s",
        (generation_id,),
    ).fetchone()[0]
    connection.execute("VACUUM (ANALYZE) v3_derived.system_search")
    connection.execute("VACUUM (ANALYZE) v3_derived.system_archetype")
    document = build_statements_document((0.0, 0.0, 0.0))
    receipt = probe.run_plan_probe(
        connection,
        document,
        generation_id=generation_id,
        search_final_insert_at=search_final,
        archetype_final_insert_at=archetype_final,
        dense_anchor_cell={
            "cell_key": "fixture",
            "coordinates": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
    )
    assert receipt["status"] in {"passed", "failed"}
    assert len(receipt["statements"]) == 80
    assert all(statement["plan"] for statement in receipt["statements"])
    body = dict(receipt)
    assert canonical_sha256({key: value for key, value in body.items() if key != "content_sha256"}) == body[
        "content_sha256"
    ]
