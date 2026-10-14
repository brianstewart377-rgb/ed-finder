#!/usr/bin/env python3
"""Read-only F2d ranking-plan probe and reusable publication assertion module."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, NoReturn

from scripts.operator.lib import f2d_operator_identity
from scripts.operator.lib.f2d_evidence import canonical_sha256, seal


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "ed-finder/v3-archetype-plan-probe/v1"
ROW_BOUND = 10_001
KNN_TIE_SLACK = 1_000
TARGET_RELATIONS = {"system_search", "system_archetype"}
PRIMARY_INDEXES = {
    "system_search": "system_search_pkey",
    "system_archetype": "system_archetype_pkey",
}
PARAMETER_TYPES = {"bigint", "double precision", "text"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PLACEHOLDER = re.compile(r"\$(\d+)")


class PlanProbeRefusal(RuntimeError):
    """A fail-closed refusal with the task's stable process exit code."""

    def __init__(self, exit_code: int, reason: str) -> None:
        self.exit_code = exit_code
        self.reason = reason
        super().__init__(reason)


def refuse_unlisted_checkout_modules() -> None:
    """Refuse a loaded repository module not covered by the operator manifest."""
    root = ROOT.resolve()
    listed = {
        entry for entry in f2d_operator_identity.manifest_entries(ROOT)
        if not entry.startswith("requirement:")
    }
    unlisted: list[str] = []
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        try:
            relative = Path(filename).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if relative.endswith((".pyc", ".pyo")):
            relative = (
                relative.rsplit("__pycache__/", 1)[0]
                + relative.rsplit("/", 1)[-1].split(".")[0] + ".py"
            )
        if relative not in listed:
            unlisted.append(relative)
    if unlisted:
        raise ValueError(
            "loaded checkout module is absent from F2d operator manifest: "
            + ", ".join(sorted(set(unlisted)))
        )


def _refuse(exit_code: int, reason: str) -> NoReturn:
    raise PlanProbeRefusal(exit_code, reason)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _timestamp(value: datetime | str, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            _refuse(20, f"{label}_invalid")
            raise AssertionError from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _rows(cursor: Any) -> list[Any]:
    return list(cursor.fetchall())


def _row_value(row: Any, key: str, position: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return row[position]


def _normal_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "ranking_version": document.get("ranking_version"),
        "ranking_sha256": document.get("ranking_sha256"),
        "statements": document.get("statements"),
    }


def validate_statements_document(document: dict[str, Any]) -> str:
    """Validate the image-produced statement envelope and return its digest."""

    if not isinstance(document, dict):
        _refuse(21, "statements_document_not_object")
    if not isinstance(document.get("ranking_version"), str) or not document[
        "ranking_version"
    ]:
        _refuse(21, "ranking_version_missing")
    ranking_digest = document.get("ranking_sha256")
    if not isinstance(ranking_digest, str) or _SHA256.fullmatch(ranking_digest) is None:
        _refuse(21, "ranking_sha256_invalid")
    statements = document.get("statements")
    if not isinstance(statements, list) or not statements:
        _refuse(21, "statements_missing")
    names: set[str] = set()
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            _refuse(21, f"statement_{index}_not_object")
        name = statement.get("name")
        sql_text = statement.get("sql")
        params = statement.get("params")
        param_types = statement.get("param_sql_types")
        if not isinstance(name, str) or not name or name in names:
            _refuse(21, f"statement_{index}_name_invalid")
        names.add(name)
        if not isinstance(sql_text, str) or not sql_text.lstrip().upper().startswith(
            "SELECT"
        ) and not sql_text.lstrip().upper().startswith("WITH"):
            _refuse(21, f"{name}_sql_invalid")
        if not isinstance(params, list) or not isinstance(param_types, list):
            _refuse(21, f"{name}_parameters_invalid")
        if len(params) != len(param_types) or any(
            value not in PARAMETER_TYPES for value in param_types
        ):
            _refuse(21, f"{name}_parameter_types_invalid")
        placeholders = sorted({int(value) for value in _PLACEHOLDER.findall(sql_text)})
        if placeholders != list(range(1, len(params) + 1)):
            _refuse(21, f"{name}_placeholders_invalid")
        if not isinstance(statement.get("kind"), str) or not isinstance(
            statement.get("expectations"), dict
        ):
            _refuse(21, f"{name}_expectations_invalid")
    digest = canonical_sha256(_normal_document(document))
    expected = (document.get("_runtime") or {}).get("statements_sha256")
    if expected is not None and expected != digest:
        _refuse(21, "statements_sha256_mismatch")
    return digest


def _walk(node: dict[str, Any], path: tuple[dict[str, Any], ...] = ()):
    current_path = (*path, node)
    yield node, current_path
    for child in node.get("Plans") or []:
        yield from _walk(child, current_path)


def _examined(node: dict[str, Any]) -> float:
    rows = float(node.get("Actual Rows", 0) or 0)
    removed = float(node.get("Rows Removed by Filter", 0) or 0)
    loops = float(node.get("Actual Loops", 0) or 0)
    return (rows + removed) * loops


def _node_observed(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in (
            "Node Type",
            "Relation Name",
            "Alias",
            "Index Name",
            "Plan Rows",
            "Actual Rows",
            "Actual Loops",
            "Rows Removed by Filter",
            "Heap Fetches",
        )
        if key in node
    }


def evaluate_plan_assertions(
    statement: dict[str, Any],
    explain_document: Any,
    *,
    generation_count: int,
    candidate_count: int | None = None,
) -> list[dict[str, Any]]:
    """Evaluate section 8.7 against one PostgreSQL JSON explain document."""

    assertions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any) -> None:
        assertions.append({"name": name, "passed": bool(passed), "observed": observed})

    try:
        envelope = explain_document[0]
        root = envelope["Plan"]
    except (KeyError, IndexError, TypeError):
        add("valid_explain_json", False, {"value": explain_document})
        return assertions

    walked = list(_walk(root))
    nodes = [node for node, _ in walked]
    kind = statement["kind"]
    expected = statement["expectations"]
    relation_nodes = [
        node for node in nodes if node.get("Relation Name") in TARGET_RELATIONS
    ]

    no_pick_sentinel = kind in {"galaxy_count", "anchored_knn_count"}
    if not no_pick_sentinel:
        for node in relation_nodes:
            relation = node["Relation Name"]
            allowed_indexes = {PRIMARY_INDEXES[relation]}
            if relation == "system_archetype" and kind.startswith("picked_"):
                allowed_indexes.add(expected["expected_index"])
            if relation == "system_archetype" and kind == "galaxy_page":
                allowed_indexes.add("system_archetype_summary_weighted")
            if relation == "system_search" and kind.startswith("anchored_"):
                allowed_indexes.add("system_search_position_gist")
            valid_access = (
                node.get("Node Type") in {"Index Scan", "Index Only Scan"}
                and node.get("Index Name") in allowed_indexes
            )
            add(
                f"bounded_index_access:{relation}:{node.get('Alias', '')}",
                valid_access,
                {
                    "allowed_indexes": sorted(allowed_indexes),
                    "node": _node_observed(node),
                },
            )
        for node, _ in walked:
            if node.get("Node Type") not in {"Hash Join", "Merge Join"}:
                continue
            descendant_relations = {
                child.get("Relation Name")
                for child, _ in _walk(node)
                if child.get("Relation Name") in TARGET_RELATIONS
            }
            if descendant_relations:
                add(
                    "no_hash_or_merge_join_over_ranked_relations",
                    False,
                    {
                        "relations": sorted(descendant_relations),
                        "node": _node_observed(node),
                    },
                )

    default_bound = ROW_BOUND
    if kind in {"anchored_filtered_page", "anchored_score_page"}:
        default_bound = (candidate_count or 0) * generation_count
    for node in relation_nodes:
        examined = _examined(node)
        add(
            f"examined_rows_bound:{node.get('Relation Name')}:{node.get('Alias', '')}",
            examined <= default_bound,
            {
                "bound": default_bound,
                "examined": examined,
                "node": _node_observed(node),
            },
        )

    if kind in {"picked_page", "picked_count"}:
        index_name = expected["expected_index"]
        window_entries = [
            (node, path)
            for node, path in walked
            if node.get("Index Name") == index_name
        ]
        windows = [node for node, _ in window_entries]
        add(
            "picked_window_index_present",
            bool(windows),
            {"expected_index": index_name},
        )
        for node, path in window_entries:
            required_type = "Index Only Scan" if kind == "picked_page" else {
                "Index Only Scan",
                "Index Scan",
            }
            type_passed = (
                node.get("Node Type") == required_type
                if isinstance(required_type, str)
                else node.get("Node Type") in required_type
            )
            add(
                "picked_window_scan_type",
                type_passed,
                {"node": _node_observed(node)},
            )
            add(
                "picked_window_actual_rows_bound",
                float(node.get("Actual Rows", 0) or 0)
                * float(node.get("Actual Loops", 0) or 0)
                <= ROW_BOUND,
                {"bound": ROW_BOUND, "node": _node_observed(node)},
            )
            limit_bound = 10_000 if kind == "picked_page" else ROW_BOUND
            ancestor_limits = [
                ancestor
                for ancestor in path[:-1]
                if ancestor.get("Node Type") == "Limit"
            ]
            add(
                "picked_window_limit_bound",
                bool(ancestor_limits)
                and any(
                    float(limit.get("Plan Rows", 0) or 0) <= limit_bound
                    and float(limit.get("Actual Rows", 0) or 0)
                    * float(limit.get("Actual Loops", 0) or 0)
                    <= limit_bound
                    for limit in ancestor_limits
                ),
                {
                    "bound": limit_bound,
                    "limits": [
                        _node_observed(limit) for limit in ancestor_limits
                    ],
                },
            )
            if kind == "picked_page":
                add(
                    "picked_window_heap_fetches_zero",
                    node.get("Heap Fetches") == 0,
                    {"node": _node_observed(node)},
                )
        if kind == "picked_page":
            sorts = [node for node in nodes if node.get("Node Type") == "Sort"]
            sort_inputs = [
                sum(_examined(child) for child in (node.get("Plans") or []))
                for node in sorts
            ]
            add(
                "picked_sort_input_rows_bound",
                bool(sort_inputs) and any(value <= 10_000 for value in sort_inputs),
                {"bound": 10_000, "input_rows": sort_inputs},
            )
            fetches = [
                node
                for node in relation_nodes
                if node.get("Relation Name") == "system_archetype"
                and node.get("Alias") == "fetch"
            ]
            fetch_rows = [_examined(node) for node in fetches]
            add(
                "picked_fetch_rows_bound",
                bool(fetch_rows)
                and all(value <= int(expected["page_size"]) for value in fetch_rows),
                {"bound": expected["page_size"], "rows": fetch_rows},
            )

    if kind == "galaxy_page":
        scans = [
            node
            for node in nodes
            if node.get("Index Name") == "system_archetype_summary_weighted"
            and node.get("Node Type") in {"Index Scan", "Index Only Scan"}
        ]
        add(
            "galaxy_window_summary_index",
            bool(scans) and all(_examined(node) <= ROW_BOUND for node in scans),
            {
                "bound": ROW_BOUND,
                "nodes": [_node_observed(node) for node in scans],
            },
        )

    if no_pick_sentinel:
        limits = [node for node in nodes if node.get("Node Type") == "Limit"]
        capped = [
            node
            for node in limits
            if float(node.get("Plan Rows", 0) or 0) <= ROW_BOUND
            and float(node.get("Actual Rows", 0) or 0)
            * float(node.get("Actual Loops", 0) or 0)
            <= ROW_BOUND
        ]
        add(
            "no_pick_count_sentinel_limit",
            bool(capped),
            {"bound": ROW_BOUND, "limits": [_node_observed(node) for node in limits]},
        )

    if kind in {"anchored_knn_page", "anchored_knn_count"}:
        knn_entries = [
            (node, path)
            for node, path in walked
            if node.get("Relation Name") == "system_search"
            and node.get("Node Type") == "Index Scan"
            and node.get("Index Name") == "system_search_position_gist"
        ]
        add(
            "anchored_knn_gist_index_scan",
            bool(knn_entries),
            {"nodes": [_node_observed(node) for node, _ in knn_entries]},
        )
        for node, path in knn_entries:
            node_position = len(path) - 1
            limit_positions = [
                position
                for position, ancestor in enumerate(path[:node_position])
                if ancestor.get("Node Type") == "Limit"
            ]
            structured = False
            if limit_positions:
                nearest_limit = max(limit_positions)
                structured = any(
                    ancestor.get("Node Type") == "Incremental Sort"
                    for ancestor in path[nearest_limit + 1 : node_position]
                ) and not any(
                    ancestor.get("Node Type") == "Sort"
                    for ancestor in path[nearest_limit + 1 : node_position]
                )
            add(
                "anchored_knn_limit_incremental_sort_shape",
                structured,
                {"path": [entry.get("Node Type") for entry in path]},
            )
            bound = (int(expected["inner_limit"]) + KNN_TIE_SLACK) * generation_count
            add(
                "anchored_knn_examined_rows_bound",
                _examined(node) <= bound,
                {
                    "bound": bound,
                    "generation_count": generation_count,
                    "node": _node_observed(node),
                },
            )

    if kind in {"anchored_filtered_page", "anchored_score_page"}:
        bound = (candidate_count or 0) * generation_count
        search_nodes = [
            node
            for node in relation_nodes
            if node.get("Relation Name") == "system_search"
        ]
        add(
            "anchored_candidate_gist_only",
            bool(search_nodes)
            and all(
                node.get("Node Type") == "Index Scan"
                and node.get("Index Name") == "system_search_position_gist"
                for node in search_nodes
            )
            and not any(node.get("Node Type") == "Seq Scan" for node in nodes),
            {
                "candidate_count": candidate_count,
                "generation_count": generation_count,
                "bound": bound,
                "nodes": [_node_observed(node) for node in search_nodes],
            },
        )
    return assertions


def _connection_in_transaction(connection: Any) -> bool:
    if hasattr(connection, "in_transaction"):
        return bool(connection.in_transaction)
    status = getattr(getattr(connection, "info", None), "transaction_status", None)
    if status is None:
        return not bool(getattr(connection, "autocommit", False))
    name = getattr(status, "name", str(status)).upper()
    return name not in {"IDLE", "0"}


def _check_maintenance(
    connection: Any,
    *,
    search_final_insert_at: datetime | str,
    archetype_final_insert_at: datetime | str,
) -> list[dict[str, Any]]:
    cursor = connection.execute(
        """
        SELECT relname, last_vacuum, last_analyze
        FROM pg_stat_user_tables
        WHERE schemaname = 'v3_derived'
          AND relname IN ('system_search', 'system_archetype')
        ORDER BY relname
        """
    )
    by_name = {
        _row_value(row, "relname", 0): row for row in _rows(cursor)
    }
    final_times = {
        "system_search": _timestamp(search_final_insert_at, "search_final_insert_at"),
        "system_archetype": _timestamp(
            archetype_final_insert_at, "archetype_final_insert_at"
        ),
    }
    checked: list[dict[str, Any]] = []
    for relation, final_at in final_times.items():
        row = by_name.get(relation)
        last_vacuum = _row_value(row, "last_vacuum", 1) if row is not None else None
        last_analyze = _row_value(row, "last_analyze", 2) if row is not None else None
        item = {
            "relation": f"v3_derived.{relation}",
            "final_insert_at": final_at.isoformat(),
            "last_vacuum": _iso(last_vacuum),
            "last_analyze": _iso(last_analyze),
        }
        checked.append(item)
        if last_vacuum is None or last_analyze is None:
            _refuse(20, f"{relation}_maintenance_timestamp_missing")
        if _timestamp(last_vacuum, f"{relation}_last_vacuum") <= final_at:
            _refuse(20, f"{relation}_last_vacuum_predates_final_insert")
        if _timestamp(last_analyze, f"{relation}_last_analyze") <= final_at:
            _refuse(20, f"{relation}_last_analyze_predates_final_insert")
    return checked


def _require_published_products(connection: Any, generation_id: str) -> None:
    cursor = connection.execute(
        """
        SELECT product_code, lifecycle_state, published_at
        FROM v3_meta.derived_product
        WHERE derived_generation_id = %s
          AND product_code IN ('system_search', 'system_archetype')
        ORDER BY product_code
        """,
        (generation_id,),
    )
    rows = _rows(cursor)
    valid = len(rows) == 2 and all(
        _row_value(row, "lifecycle_state", 1) == "READY"
        and _row_value(row, "published_at", 2) is not None
        for row in rows
    )
    if not valid:
        _refuse(23, "finder_products_not_ready_and_published")


def _generation_identity(connection: Any, generation_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT g.generation_key, g.lifecycle_state,
               c.publication_sequence,
               (c.derived_generation_id IS NOT NULL) AS is_current
        FROM v3_meta.derived_generation g
        LEFT JOIN v3_meta.current_derived_generation c
          ON c.singleton
         AND c.derived_generation_id = g.derived_generation_id
        WHERE g.derived_generation_id = %s
        """,
        (generation_id,),
    ).fetchone()
    if row is None:
        _refuse(21, "generation_identity_missing")
    identity = {
        "derived_generation_id": generation_id,
        "generation_key": _row_value(row, "generation_key", 0),
        "lifecycle_state": _row_value(row, "lifecycle_state", 1),
        "publication_sequence": _row_value(row, "publication_sequence", 2),
        "is_current": bool(_row_value(row, "is_current", 3)),
    }
    if identity["lifecycle_state"] != "PUBLISHED" or not identity["is_current"]:
        _refuse(21, "generation_identity_not_current_published")
    return identity


def _generation_rows(connection: Any) -> list[str]:
    cursor = connection.execute(
        """
        SELECT p.derived_generation_id::text
        FROM v3_meta.derived_product p
        WHERE p.product_code = 'system_search'
          AND EXISTS (
              SELECT 1
              FROM v3_derived.system_search s
              WHERE s.derived_generation_id = p.derived_generation_id
              LIMIT 1
          )
        ORDER BY p.derived_generation_id
        """
    )
    return [str(_row_value(row, "derived_generation_id", 0)) for row in _rows(cursor)]


def _candidate_count(
    connection: Any, dense_anchor_cell: dict[str, Any]
) -> dict[str, Any]:
    coordinates = dense_anchor_cell.get("coordinates") or {}
    try:
        x = float(coordinates["x"])
        y = float(coordinates["y"])
        z = float(coordinates["z"])
    except (KeyError, TypeError, ValueError) as exc:
        _refuse(21, "dense_anchor_coordinates_invalid")
        raise AssertionError from exc
    radius = 500.0
    started = time.monotonic()
    cursor = connection.execute(
        """
        SELECT count(*)
        FROM v3_derived.system_search
        WHERE position_ly <@ cube(
            array[%s::double precision - %s::double precision,
                  %s::double precision - %s::double precision,
                  %s::double precision - %s::double precision],
            array[%s::double precision + %s::double precision,
                  %s::double precision + %s::double precision,
                  %s::double precision + %s::double precision]
        )
        """,
        (x, radius, y, radius, z, radius, x, radius, y, radius, z, radius),
    )
    row = cursor.fetchone()
    duration_ms = (time.monotonic() - started) * 1000
    return {
        "count": int(_row_value(row, "count", 0)),
        "duration_ms": duration_ms,
        "radius_ly": radius,
        "coordinates": {"x": x, "y": y, "z": z},
        "index_required": "system_search_position_gist",
    }


def _explain(connection: Any, index: int, statement: dict[str, Any]) -> Any:
    from psycopg import sql as pg_sql

    prepared = pg_sql.Identifier(f"plan_probe_{index}")
    types = pg_sql.SQL(", ").join(
        pg_sql.SQL(value) for value in statement["param_sql_types"]
    )
    if statement["param_sql_types"]:
        prepare = pg_sql.SQL("PREPARE {} ({}) AS ").format(prepared, types)
    else:
        prepare = pg_sql.SQL("PREPARE {} AS ").format(prepared)
    connection.execute(prepare + pg_sql.SQL(statement["sql"]))
    literals = pg_sql.SQL(", ").join(
        pg_sql.Literal(value) for value in statement["params"]
    )
    if statement["params"]:
        explain = pg_sql.SQL(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE {} ({})"
        ).format(prepared, literals)
    else:
        explain = pg_sql.SQL(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE {}"
        ).format(prepared)
    try:
        row = connection.execute(explain).fetchone()
        value = _row_value(row, "QUERY PLAN", 0)
        if isinstance(value, str):
            value = json.loads(value)
        return value
    finally:
        connection.execute(pg_sql.SQL("DEALLOCATE {}").format(prepared))


def run_plan_probe(
    connection: Any,
    statements_document: dict[str, Any],
    *,
    generation_id: str,
    search_final_insert_at: datetime | str,
    archetype_final_insert_at: datetime | str,
    dense_anchor_cell: dict[str, Any],
    allow_unpublished: bool = False,
) -> dict[str, Any]:
    """Run all plan assertions on a caller-owned Psycopg connection."""

    statements_sha256 = validate_statements_document(statements_document)
    maintenance = _check_maintenance(
        connection,
        search_final_insert_at=search_final_insert_at,
        archetype_final_insert_at=archetype_final_insert_at,
    )
    if not allow_unpublished:
        _require_published_products(connection, generation_id)
    generation_identity = _generation_identity(connection, generation_id)

    settings_are_local = _connection_in_transaction(connection)
    connection.execute(
        "SELECT set_config(%s, %s, %s)",
        ("plan_cache_mode", "force_generic_plan", settings_are_local),
    )
    connection.execute(
        "SELECT set_config(%s, %s, %s)",
        ("statement_timeout", "60s", settings_are_local),
    )
    generations = _generation_rows(connection)
    generation_count = len(generations)
    if generation_count < 1:
        _refuse(21, "no_generation_holds_search_rows")

    statements = statements_document["statements"]
    needs_candidates = any(
        item["kind"] in {"anchored_filtered_page", "anchored_score_page"}
        for item in statements
    )
    candidate_measurement = (
        _candidate_count(connection, dense_anchor_cell) if needs_candidates else None
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, statement in enumerate(statements):
        explain_document = _explain(connection, index, statement)
        assertions = evaluate_plan_assertions(
            statement,
            explain_document,
            generation_count=generation_count,
            candidate_count=(
                candidate_measurement["count"] if candidate_measurement else None
            ),
        )
        for assertion in assertions:
            if not assertion["passed"]:
                failures.append(
                    {
                        "statement": statement["name"],
                        "assertion": assertion["name"],
                        "observed": assertion["observed"],
                    }
                )
        envelope = explain_document[0] if explain_document else {}
        root = envelope.get("Plan") or {}
        results.append(
            {
                "name": statement["name"],
                "kind": statement["kind"],
                "sql_sha256": hashlib.sha256(
                    statement["sql"].encode("utf-8")
                ).hexdigest(),
                "execution_time_ms": envelope.get("Execution Time"),
                "planning_time_ms": envelope.get("Planning Time"),
                "shared_hit_blocks": root.get("Shared Hit Blocks", 0),
                "shared_read_blocks": root.get("Shared Read Blocks", 0),
                "assertions": assertions,
                "plan": explain_document,
            }
        )

    runtime = statements_document.get("_runtime") or {}
    body = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed" if failures else "passed",
        "ranking_version": statements_document["ranking_version"],
        "ranking_sha256": statements_document["ranking_sha256"],
        "statements_sha256": statements_sha256,
        "image_digest": runtime.get("image_digest"),
        "generation": generation_identity,
        "search_generations": {
            "count": generation_count,
            "derived_generation_ids": generations,
        },
        "dense_anchor_cell": dense_anchor_cell,
        "bounding_box_candidate_measurement": candidate_measurement,
        "maintenance": maintenance,
        "settings_are_local": settings_are_local,
        "statements": results,
        "failures": failures,
        "f2d_operator_code_sha256": runtime.get("f2d_operator_code_sha256"),
        "read_only": True,
        "db_writes_performed": False,
    }
    return seal(body)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statements", type=Path, required=True)
    parser.add_argument("--statements-sha256", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--generation-key", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--publication-sequence", type=int, required=True)
    parser.add_argument("--search-final-insert-at", required=True)
    parser.add_argument("--archetype-final-insert-at", required=True)
    parser.add_argument("--dense-anchor-cell", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unpublished", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    attested = os.environ.get("F2D_OPERATOR_CODE_SHA256_ATTESTED", "")
    if _SHA256.fullmatch(attested) is None:
        print("plan probe identity refusal", file=sys.stderr)
        return 2
    try:
        refuse_unlisted_checkout_modules()
    except (f2d_operator_identity.OperatorIdentityError, ValueError):
        print("plan probe identity refusal", file=sys.stderr)
        return 2
    try:
        document = json.loads(args.statements.read_text(encoding="utf-8"))
        dense_anchor_cell = json.loads(args.dense_anchor_cell)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"plan probe statement refusal: {exc}", file=sys.stderr)
        return 21
    if not isinstance(document, dict) or not isinstance(dense_anchor_cell, dict):
        print("plan probe statement refusal: invalid input object", file=sys.stderr)
        return 21
    document["_runtime"] = {
        "statements_sha256": args.statements_sha256,
        "image_digest": args.image_digest,
        "generation_key": args.generation_key,
        "publication_sequence": args.publication_sequence,
        "f2d_operator_code_sha256": attested,
    }
    try:
        validate_statements_document(document)
    except PlanProbeRefusal as exc:
        print(f"plan probe refusal: {exc.reason}", file=sys.stderr)
        return exc.exit_code
    dsn = os.environ.get("V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL")
    if not dsn:
        print("plan probe database error: DSN missing", file=sys.stderr)
        return 4
    try:
        import psycopg

        refuse_unlisted_checkout_modules()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.read_only = True
            connection.execute(
                "SELECT set_config(%s, %s, false)",
                ("default_transaction_read_only", "on"),
            )
            receipt = run_plan_probe(
                connection,
                document,
                generation_id=args.generation_id,
                search_final_insert_at=args.search_final_insert_at,
                archetype_final_insert_at=args.archetype_final_insert_at,
                dense_anchor_cell=dense_anchor_cell,
                allow_unpublished=args.allow_unpublished,
            )
    except PlanProbeRefusal as exc:
        print(f"plan probe refusal: {exc.reason}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(f"plan probe database error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    args.output.write_text(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if receipt["status"] == "passed" else 22


if __name__ == "__main__":
    raise SystemExit(main())
