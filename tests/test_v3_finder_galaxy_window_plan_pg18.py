"""Production-scale generic plans for the Finder ranking SQL on PostgreSQL 18.

The 2026-10-22 ``publish-finder-products`` run (workflow run 39808363037) was
refused because plan-probe statement 72, ``galaxy_wide_development_page_24``,
hit the 60 s statement timeout under ``force_generic_plan``. The galaxy-wide
window read ``v3_app.system_archetype_summary`` with no generation predicate
of its own, so ``derived_generation_id`` reached ``v3_derived.system_archetype``
only through the view's join and ``system_archetype_summary_weighted`` could
not supply the ORDER BY: PostgreSQL scanned the whole ~198.5M-row generation by
primary key and sorted it.

A disposable fixture cannot hold 198.5M rows, so this module builds a real
two-search-generation / one-archetype-generation database through the
migration guards and then imports production-scale relation statistics with
PostgreSQL 18's ``pg_restore_relation_stats``. The planner scales ``reltuples``
by the relation's real page count, so the imported density makes every table
and index look production-sized while the executed plans stay fast. The
``v3_meta`` pointer/product tables are left never-analyzed (the production
generic plan estimated 1,330 rows for ``current_derived_generation``) and,
separately, analyzed, so the fixed SQL is proven under both.

The probe statements are generated from the API ranking SQL exactly as the
operator does (``scripts/v3_plan_probe_statements.py``) and evaluated by the
frozen ``scripts/v3_archetype_plan_probe.py`` inside an uncommitted
product-publication transaction, the way ``scripts/v3_publish_derived_products.py``
runs them.
"""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Production shape on 2026-10-22: one archetype generation of ~198.5M systems
# and two search generations of the same systems (the old one is purged only
# after go-live).
PRODUCTION_SYSTEMS = 198_500_000
SEARCH_GENERATIONS = 2
FIXTURE_SYSTEMS = 24_000
FIRST_SYSTEM_ID = 42
DENSE_ANCHOR = (0.0, 0.0, 0.0)
GALAXY_PAGE = "galaxy_wide_development_page_24"
# Planner-relevant server settings of the production database
# (docs/operations/v3-postgres-server-settings.md, applied 2026-10-19).
PRODUCTION_PLANNER_SETTINGS = {
    "effective_cache_size": "128GB",
    "work_mem": "32MB",
}

# The galaxy-wide page as release 0dddc78d emitted it (ranking_sql.py before
# this fix). Kept verbatim so the regression is proven against the exact SQL
# that timed out in production.
RELEASE_0DDDC78D_GALAXY_PAGE_SQL = (
    "WITH summary_window AS (\n"
    "    SELECT sum.*\n"
    "    FROM v3_app.system_archetype_summary sum\n"
    "    ORDER BY sum.weighted_potential DESC NULLS LAST, sum.system_id64 ASC\n"
    "    LIMIT 10000\n"
    ")\n"
    "SELECT s.*,\n"
    "       sum.best_colony_potential AS primary_score,\n"
    "       s.confidence AS ranking_confidence,\n"
    "       (s.confidence * s.completeness) AS uncertainty_factor,\n"
    "       sum.primary_archetype AS summary_primary_archetype,\n"
    "       sum.secondary_archetype AS summary_secondary_archetype,\n"
    "       sum.best_colony_potential AS summary_best_colony_potential,\n"
    "       sum.archetype_confidence AS summary_archetype_confidence,\n"
    "       sum.weighted_potential AS weighted_potential\n"
    "FROM summary_window sum\n"
    "JOIN v3_app.system_search s ON s.system_id64 = sum.system_id64\n"
    "ORDER BY sum.weighted_potential DESC NULLS LAST, s.system_id64 ASC\n"
    "LIMIT $1 OFFSET $2"
)

_SEARCH_OVERRIDES = {
    "system_id64": "n",
    "name": "'Plan Probe ' || n",
    "x_ly": "{x}",
    "y_ly": "{y}",
    "z_ly": "{z}",
    "position_ly": "cube(ARRAY[{x}, {y}, {z}])",
    "main_star_class": "CASE WHEN mod(n, 97) = 0 THEN 'O' ELSE 'K' END",
}
# Deterministic spread: x/z across +-1,200 ly, y across +-120 ly.
_COORDINATES = {
    "x": "(mod(n * 7919, 24001) - 12000)::double precision / 10",
    "y": "(mod(n * 104729, 2401) - 1200)::double precision / 10",
    "z": "(mod(n * 15485863, 24001) - 12000)::double precision / 10",
}
_ARCHETYPE_PRIMES = (7919, 104729, 1299709, 15485863, 179424673, 2147483647, 6700417, 27644437)


def _archetype_overrides() -> dict[str, str]:
    from tests.test_v3_derived_product_publication import ARCHETYPES

    overrides = {
        "system_id64": "n",
        "weighted_potential": "mod(n * 2654435761, 1000000)::double precision / 10000",
    }
    for key, prime in zip(ARCHETYPES, _ARCHETYPE_PRIMES, strict=True):
        overrides[f"{key}_score"] = f"mod(n * {prime}, 101)::smallint"
        overrides[f"{key}_weighted_e4"] = f"mod(n * {prime}, 1000001)::integer"
    return overrides


def _copy_seed_row(connection, table: str, generation, systems: int, overrides: dict[str, str]) -> None:
    from psycopg import sql

    columns = [row[0] for row in connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='v3_derived' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    ).fetchall()]
    select = [
        sql.SQL(overrides[name].format(**_COORDINATES)) if name in overrides
        else sql.Identifier("t", name)
        for name in columns
    ]
    connection.execute(sql.SQL(
        "INSERT INTO v3_derived.{} ({}) SELECT {} "
        "FROM v3_derived.{} t CROSS JOIN generate_series(%s::bigint, %s::bigint) n "
        "WHERE t.derived_generation_id=%s AND t.system_id64=%s"
    ).format(
        sql.Identifier(table),
        sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(select),
        sql.Identifier(table),
    ), (FIRST_SYSTEM_ID + 1, FIRST_SYSTEM_ID + systems - 1, generation, FIRST_SYSTEM_ID))


def _seed_generation(connection, *, systems: int, products: tuple[str, ...], publish: bool):
    from tests import test_v3_derived_product_publication as fixture

    generation = fixture._insert_generation(connection)
    fixture._seed_rating(connection, generation, FIRST_SYSTEM_ID)
    connection.execute(
        """
        INSERT INTO v3_derived.system_rating_vector (
            derived_generation_id, system_id64, chunk_ordinal,
            loaded_body_count, physical_body_count, subtype_projection_sha256,
            potential, quality, quality_min, quality_max, completeness, confidence
        ) SELECT derived_generation_id, n, chunk_ordinal,
                 loaded_body_count, physical_body_count, subtype_projection_sha256,
                 potential, quality, quality_min, quality_max, completeness, confidence
            FROM v3_derived.system_rating_vector CROSS JOIN generate_series(%s::bigint, %s::bigint) n
           WHERE derived_generation_id=%s AND system_id64=%s
        """,
        (FIRST_SYSTEM_ID + 1, FIRST_SYSTEM_ID + systems - 1, generation, FIRST_SYSTEM_ID),
    )
    fixture._make_ready(connection, generation)
    if publish:
        assert fixture._publish_generation(connection, generation) == 1
    for code in products:
        fixture._register_product(connection, generation, code)
    if "system_search" in products:
        fixture._insert_search_row(connection, generation, FIRST_SYSTEM_ID)
        _copy_seed_row(connection, "system_search", generation, systems, _SEARCH_OVERRIDES)
    if "system_archetype" in products:
        fixture._insert_archetype_row(connection, generation, FIRST_SYSTEM_ID)
        _copy_seed_row(connection, "system_archetype", generation, systems, _archetype_overrides())
    connection.execute(
        "UPDATE v3_meta.derived_product SET lifecycle_state='READY', "
        "validation_receipt=%s::jsonb, validation_sha256=%s, validated_at=transaction_timestamp() "
        "WHERE derived_generation_id=%s",
        (json.dumps({"status": "VERIFIED"}), fixture.HASH, generation),
    )
    return generation


def build_two_generation_database(connection, *, systems: int = FIXTURE_SYSTEMS) -> dict[str, Any]:
    """Seed the production shape: an older search-only generation that is not
    current, plus the current PUBLISHED generation whose Finder products are
    READY/VERIFIED and not yet published (the publisher's starting state)."""
    from tests import test_v3_derived_product_publication as fixture

    for name in (*fixture.PRE_015, "015_v3_derived_product_publication.sql"):
        connection.execute((fixture.MIGRATIONS / name).read_text(encoding="utf-8"))
    # Imported statistics must not be replaced by autovacuum mid-test.
    for relation in (
        "v3_derived.system_search", "v3_derived.system_archetype",
        "v3_meta.current_derived_generation", "v3_meta.derived_generation",
        "v3_meta.derived_product",
    ):
        connection.execute(f"ALTER TABLE {relation} SET (autovacuum_enabled = false)")
    old_generation = _seed_generation(
        connection, systems=systems, products=("system_search",), publish=False,
    )
    final_insert_at = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    generation = _seed_generation(
        connection, systems=systems, products=("system_search", "system_archetype"), publish=True,
    )
    final_insert_at = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    connection.execute("VACUUM (ANALYZE) v3_derived.system_search")
    connection.execute("VACUUM (ANALYZE) v3_derived.system_archetype")
    key = connection.execute(
        "SELECT generation_key FROM v3_meta.derived_generation WHERE derived_generation_id=%s",
        (generation,),
    ).fetchone()[0]
    return {
        "generation_id": str(generation),
        "generation_key": key,
        "old_generation_id": str(old_generation),
        "final_insert_at": final_insert_at - timedelta(seconds=1),
        "systems": systems,
    }


def import_production_statistics(connection, *, meta_analyzed: bool) -> dict[str, float]:
    """Make every Finder relation and index plan as production-sized.

    ``reltuples`` is set to the production row count while ``relpages`` stays
    the real page count, so the planner's density x current-pages estimate is
    the production row count. Partial indexes keep their real fraction of the
    table. Column statistics come from the real ANALYZE (two equally sized
    search generations, one archetype generation)."""
    targets = {
        "system_archetype": float(PRODUCTION_SYSTEMS),
        "system_search": float(PRODUCTION_SYSTEMS * SEARCH_GENERATIONS),
    }
    imported: dict[str, float] = {}
    for table, production_rows in targets.items():
        table_tuples = connection.execute(
            "SELECT reltuples FROM pg_class WHERE oid = %s::regclass",
            (f"v3_derived.{table}",),
        ).fetchone()[0]
        assert table_tuples > 0
        relations = connection.execute(
            """
            SELECT c.relname, c.reltuples, pg_relation_size(c.oid) / current_setting('block_size')::int
              FROM pg_class c
             WHERE c.oid = %s::regclass
                OR c.oid IN (SELECT indexrelid FROM pg_index WHERE indrelid = %s::regclass)
            """,
            (f"v3_derived.{table}", f"v3_derived.{table}"),
        ).fetchall()
        for relname, tuples, pages in relations:
            scaled = round(production_rows * float(tuples) / float(table_tuples))
            connection.execute(
                "SELECT pg_restore_relation_stats('schemaname', 'v3_derived', 'relname', %s::text, "
                "'relpages', %s::integer, 'reltuples', %s::real, 'relallvisible', %s::integer)",
                (relname, int(pages), float(scaled), int(pages) if relname == table else 0),
            )
            imported[relname] = float(scaled)
    for table in ("current_derived_generation", "derived_generation", "derived_product"):
        if meta_analyzed:
            connection.execute(f"ANALYZE v3_meta.{table}")
        else:
            connection.execute("SELECT pg_clear_relation_stats('v3_meta', %s)", (table,))
    return imported


def generate_statements(dense_anchor=DENSE_ANCHOR) -> dict[str, Any]:
    """Run the operator's statement generator against this checkout's API."""
    sys.path.insert(0, str(ROOT / "apps/api/src"))
    try:
        from scripts.v3_plan_probe_statements import build_statements_document
    finally:
        sys.path.pop(0)
    return build_statements_document(tuple(dense_anchor))


def begin_publication(connection, generation_id: str) -> None:
    """Publish both products in the caller's open transaction, as the publisher does."""
    for code in ("system_search", "system_archetype"):
        connection.execute(
            "SELECT v3_meta.publish_derived_product(%s, %s, 'plan-probe-test')",
            (generation_id, code),
        )
    for name, value in PRODUCTION_PLANNER_SETTINGS.items():
        connection.execute("SELECT set_config(%s, %s, true)", (name, value))
    connection.execute("SET LOCAL plan_cache_mode = 'force_generic_plan'")
    connection.execute("SET LOCAL statement_timeout = '60s'")


def generic_plan(connection, statement: dict[str, Any], *, analyze: bool) -> dict[str, Any]:
    from psycopg import sql as pg_sql

    name = pg_sql.Identifier("galaxy_window_check")
    types = pg_sql.SQL(", ").join(pg_sql.SQL(value) for value in statement["param_sql_types"])
    prepare = "PREPARE {} ({}) AS " if statement["param_sql_types"] else "PREPARE {} AS "
    connection.execute(pg_sql.SQL(prepare).format(name, types) + pg_sql.SQL(statement["sql"]))
    options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    literals = pg_sql.SQL(", ").join(pg_sql.Literal(value) for value in statement["params"])
    execute = "EXECUTE {} ({})" if statement["params"] else "EXECUTE {}"
    try:
        row = connection.execute(
            pg_sql.SQL("EXPLAIN (" + options + ") " + execute).format(name, literals)
        ).fetchone()
    finally:
        connection.execute(pg_sql.SQL("DEALLOCATE {}").format(name))
    value = row[0]
    return json.loads(value) if isinstance(value, str) else value


def _nodes(node: dict[str, Any]):
    yield node
    for child in node.get("Plans") or []:
        yield from _nodes(child)


@pytest.fixture(scope="module")
def production_shaped_database():
    """One seeded database per module; each test imports its own statistics."""
    from tests.ratings_v4_pg_fixture import canonical_database

    with canonical_database() as database:
        connection = database[0]
        yield connection, build_two_generation_database(connection)


def _galaxy_statement(document: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in document["statements"] if item["name"] == GALAXY_PAGE]
    assert len(matches) == 1
    return matches[0]


def _window_rows(connection, statement: dict[str, Any]) -> list[tuple[int, float]]:
    from psycopg import sql as pg_sql

    rows = connection.execute(
        pg_sql.SQL("SELECT system_id64, weighted_potential FROM ({}) page").format(
            pg_sql.SQL(statement["sql"].replace("$1", "%s").replace("$2", "%s"))
        ),
        statement["params"],
    ).fetchall()
    return [(int(row[0]), float(row[1])) for row in rows]


def _probe(connection, seeded: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    from scripts import v3_archetype_plan_probe as probe

    with connection.transaction(force_rollback=True):
        begin_publication(connection, seeded["generation_id"])
        receipt = probe.run_plan_probe(
            connection,
            document,
            generation_id=seeded["generation_id"],
            search_final_insert_at=seeded["final_insert_at"],
            archetype_final_insert_at=seeded["final_insert_at"],
            dense_anchor_cell={
                "cell_key": "fixture-dense",
                "coordinates": dict(zip("xyz", DENSE_ANCHOR, strict=True)),
            },
            allow_unpublished=True,
        )
    # Nothing was committed: the products are still unpublished.
    assert connection.execute(
        "SELECT count(*) FROM v3_meta.derived_product "
        "WHERE derived_generation_id=%s AND published_at IS NOT NULL",
        (seeded["generation_id"],),
    ).fetchone()[0] == 0
    return receipt


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.parametrize("meta_analyzed", [False, True], ids=["meta-never-analyzed", "meta-analyzed"])
def test_galaxy_window_is_index_ordered_at_production_scale(
    production_shaped_database, meta_analyzed: bool,
) -> None:
    from scripts import v3_archetype_plan_probe as probe

    connection, seeded = production_shaped_database
    imported = import_production_statistics(connection, meta_analyzed=meta_analyzed)
    assert imported["system_archetype"] == PRODUCTION_SYSTEMS
    assert imported["system_search"] == PRODUCTION_SYSTEMS * SEARCH_GENERATIONS
    document = generate_statements()
    fixed = _galaxy_statement(document)
    released = {**fixed, "sql": RELEASE_0DDDC78D_GALAXY_PAGE_SQL}
    assert fixed["sql"] != released["sql"]
    assert fixed["params"] == released["params"]

    with connection.transaction(force_rollback=True):
        begin_publication(connection, seeded["generation_id"])

        # Release 0dddc78d: the generation reaches the archetype heap only
        # through the view join, so the window sorts a whole-generation scan.
        old_plan = generic_plan(connection, released, analyze=True)
        old_nodes = list(_nodes(old_plan[0]["Plan"]))
        assert not any(
            node.get("Index Name") == "system_archetype_summary_weighted" for node in old_nodes
        )
        assert any(
            node.get("Node Type") == "Sort"
            and any(
                child.get("Relation Name") == "system_archetype"
                and child.get("Plan Rows", 0) > 10 * 10_000
                for child in _nodes(node)
            )
            for node in old_nodes
        )
        old_failures = {
            item["name"]
            for item in probe.evaluate_plan_assertions(released, old_plan, generation_count=2)
            if not item["passed"]
        }
        assert "galaxy_window_summary_index" in old_failures

        # The fixed SQL pins the published generation, so the summary index
        # supplies the window order with no whole-generation sort.
        new_plan = generic_plan(connection, fixed, analyze=True)
        new_nodes = list(_nodes(new_plan[0]["Plan"]))
        windows = [
            node for node in new_nodes
            if node.get("Index Name") == "system_archetype_summary_weighted"
        ]
        assert windows
        assert all(node["Actual Rows"] * node["Actual Loops"] <= 10_000 for node in windows)
        assert all(
            node.get("Plan Rows", 0) <= 10_000
            for node in new_nodes if node.get("Node Type") in {"Sort", "Incremental Sort"}
        )
        assert all(
            item["passed"]
            for item in probe.evaluate_plan_assertions(fixed, new_plan, generation_count=2)
        )

        # Same rows in the same order as the released SQL.
        assert _window_rows(connection, fixed) == _window_rows(connection, released)


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_every_probe_statement_passes_in_the_publication_transaction(
    production_shaped_database,
) -> None:
    """The production statistics state: the pointer table (and the other
    v3_meta tables) never analyzed, as the 2026-10-22 production generic plan
    showed (1,330 estimated rows for current_derived_generation)."""
    connection, seeded = production_shaped_database
    import_production_statistics(connection, meta_analyzed=False)
    document = generate_statements()
    assert len(document["statements"]) == 80
    receipt = _probe(connection, seeded, document)
    assert receipt["search_generations"]["count"] == SEARCH_GENERATIONS
    assert receipt["failures"] == [], json.dumps(receipt["failures"], default=str)[:4000]
    assert receipt["status"] == "passed"
    assert len(receipt["statements"]) == 80


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_analyzed_meta_tables_only_trip_the_frozen_no_seq_scan_rule(
    production_shaped_database,
) -> None:
    """Records a boundary of the frozen probe, not of the ranking SQL: once
    the one-page v3_meta tables carry statistics, PostgreSQL reads them with
    a Seq Scan, which anchored_candidate_gist_only refuses anywhere in the
    two candidate-bounded anchored plans. Every other statement still passes."""
    connection, seeded = production_shaped_database
    import_production_statistics(connection, meta_analyzed=True)
    receipt = _probe(connection, seeded, generate_statements())
    failed = {(item["statement"], item["assertion"]) for item in receipt["failures"]}
    assert failed == {
        ("anchored_filtered_o_star_dense_page_24", "anchored_candidate_gist_only"),
        ("anchored_development_dense_page_24", "anchored_candidate_gist_only"),
    }
    for statement in receipt["statements"]:
        if any(not item["passed"] for item in statement["assertions"]):
            seq_scans = [
                node for node in _nodes(statement["plan"][0]["Plan"])
                if node.get("Node Type") == "Seq Scan"
            ]
            assert seq_scans
            assert {node["Relation Name"] for node in seq_scans} <= {
                "current_derived_generation", "derived_generation", "derived_product",
            }
