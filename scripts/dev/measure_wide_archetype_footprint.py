"""Measure the wide-row ``system_archetype`` footprint on a DISPOSABLE PostgreSQL 18.

This is the measurement behind the Finder capacity decision
(``docs/operations/v3-finder-capacity-decision-2026-10-10.md``) and the F2d design
(``docs/superpowers/specs/2026-10-10-v3-finder-f2d-wide-archetype-and-product-attachment-design.md``,
sections 3.1/3.3/3.4). It builds the design's one-row-per-system DDL (foreign keys
to other relations omitted) in a scratch schema, fills it with N synthetic rows of
realistic shape, creates the indexes for two layouts, ``VACUUM ANALYZE``s, and
reports bytes per row for the heap and every index plus a linear extrapolation to
the production system count.

Layouts measured:

* ``v1_with_system_id64`` — eight ``(generation, <key>_score DESC, system_id64)``
  indexes (every entry unique; no B-tree deduplication);
* ``v2_score_only`` — eight ``(generation, <key>_score DESC)`` indexes (B-tree
  deduplication collapses the 101 distinct score values into posting lists).

Both layouts share the primary key and the ``weighted_potential`` index.

Safety: the DSN comes only from ``EDFINDER_DISPOSABLE_DSN`` and must point at a
loopback host; the script refuses anything else. It writes only to the ``scratch``
schema of that database and never reads production.

Usage::

    EDFINDER_DISPOSABLE_DSN=postgresql://user:pass@127.0.0.1:55418/db \\
        python scripts/dev/measure_wide_archetype_footprint.py --rows 200000 > footprint.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlsplit

import psycopg

PROD_SYSTEMS = 198_500_000
ARCHETYPE_KEYS = (
    "paradise",
    "mining_hub",
    "manufacturing_hub",
    "megacomplex",
    "research_hub",
    "stronghold",
    "population_capital",
    "flexible",
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
GENERATION_ID = "a7076522-0000-4000-8000-000000000001"


def _tier(expr: str) -> str:
    return (
        f"CASE WHEN {expr} >= 88 THEN 'S' WHEN {expr} >= 76 THEN 'A' "
        f"WHEN {expr} >= 60 THEN 'B' WHEN {expr} >= 45 THEN 'C' ELSE 'D' END"
    )


def _ddl(table: str) -> str:
    cols: list[str] = []
    for key in ARCHETYPE_KEYS:
        cols.append(f"{key}_score smallint NOT NULL CHECK ({key}_score BETWEEN 0 AND 100)")
        cols.append(f"{key}_tier char(1) NOT NULL CHECK ({key}_tier IN ('S','A','B','C','D'))")
        cols.append(f"{key}_confidence real NOT NULL CHECK ({key}_confidence BETWEEN 0 AND 1)")
    key_list = ", ".join(f"'{key}'" for key in ARCHETYPE_KEYS)
    return f"""
CREATE TABLE scratch.{table} (
    derived_generation_id uuid NOT NULL,
    system_id64 bigint NOT NULL CHECK (system_id64 >= 0),
    archetype_version text NOT NULL CHECK (length(archetype_version) BETWEEN 1 AND 128),
    {", ".join(cols)},
    primary_archetype text NOT NULL CHECK (primary_archetype IN ({key_list})),
    secondary_archetype text CHECK (secondary_archetype IS NULL OR secondary_archetype IN ({key_list})),
    best_colony_potential smallint NOT NULL CHECK (best_colony_potential BETWEEN 0 AND 100),
    best_tier char(1) NOT NULL CHECK (best_tier IN ('S','A','B','C','D')),
    archetype_confidence real NOT NULL CHECK (archetype_confidence BETWEEN 0 AND 1),
    weighted_potential double precision NOT NULL CHECK (weighted_potential BETWEEN 0 AND 100),
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (derived_generation_id, system_id64),
    CHECK (secondary_archetype IS NULL OR secondary_archetype <> primary_archetype)
)"""


def _fill(conn: psycopg.Connection, table: str, rows: int) -> None:
    key_array = "ARRAY[" + ", ".join(f"'{key}'" for key in ARCHETYPE_KEYS) + "]"
    select: list[str] = [f"'{GENERATION_ID}'::uuid", "g.n::bigint * 7919", "'v3-archetype-4'"]
    for index, _key in enumerate(ARCHETYPE_KEYS):
        score = f"((g.n * {97 + index * 13}) %% 101)"
        select.append(f"{score}::smallint")
        select.append(_tier(score))
        select.append(f"round(((g.n * {31 + index}) %% 1000000) / 1000000.0, 6)::real")
    best = "((g.n * 97) %% 101)"
    secondary = f"CASE WHEN g.n %% 11 = 0 THEN NULL ELSE ({key_array})[1 + ((g.n + 3) %% 8)] END"
    select.extend(
        [
            f"({key_array})[1 + (g.n %% 8)]",
            secondary,
            f"{best}::smallint",
            _tier(best),
            "round(((g.n * 17) %% 1000000) / 1000000.0, 6)::real",
            f"{best} * (((g.n * 17) %% 1000000) / 1000000.0)",
            "'2026-10-10T00:00:00Z'::timestamptz",
        ]
    )
    conn.execute(
        f"INSERT INTO scratch.{table} SELECT {', '.join(select)} FROM generate_series(1, %s) AS g(n)",
        (rows,),
    )


def _sizes(conn: psycopg.Connection, table: str) -> dict[str, object]:
    table_bytes, index_bytes, total_bytes, rows = conn.execute(
        "SELECT pg_table_size(c.oid), pg_indexes_size(c.oid), pg_total_relation_size(c.oid), "
        f"(SELECT count(*) FROM scratch.{table}) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'scratch' AND c.relname = %s",
        (table,),
    ).fetchone()
    per_index = conn.execute(
        "SELECT i.relname, pg_relation_size(i.oid) FROM pg_index x "
        "JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = 'scratch' AND t.relname = %s ORDER BY i.relname",
        (table,),
    ).fetchall()
    avg_tuple = conn.execute(f"SELECT avg(pg_column_size(t.*)) FROM scratch.{table} t").fetchone()[0]
    scale = PROD_SYSTEMS / rows
    return {
        "rows": rows,
        "table_bytes": table_bytes,
        "index_bytes": index_bytes,
        "total_bytes": total_bytes,
        "avg_tuple_bytes": float(avg_tuple),
        "table_bytes_per_row": round(table_bytes / rows, 1),
        "index_bytes_per_row": round(index_bytes / rows, 1),
        "total_bytes_per_row": round(total_bytes / rows, 1),
        "indexes": {
            name: {"bytes": size, "bytes_per_row": round(size / rows, 1)} for name, size in per_index
        },
        "extrapolated_prod": {
            "systems": PROD_SYSTEMS,
            "table_gb": round(table_bytes * scale / 1e9, 1),
            "index_gb": round(index_bytes * scale / 1e9, 1),
            "total_gb": round(total_bytes * scale / 1e9, 1),
        },
    }


def _disposable_dsn() -> str:
    dsn = os.environ.get("EDFINDER_DISPOSABLE_DSN", "")
    if not dsn:
        sys.exit("EDFINDER_DISPOSABLE_DSN is required (disposable local PostgreSQL only)")
    host = urlsplit(dsn).hostname or ""
    if host not in LOOPBACK_HOSTS:
        sys.exit(f"refusing non-loopback host {host!r}: this script runs only against a disposable local database")
    return dsn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--rows", type=int, default=200_000, help="synthetic rows to build (default 200000)")
    args = parser.parse_args()
    if args.rows < 1000 or args.rows > 5_000_000:
        sys.exit("--rows must be between 1000 and 5000000")
    out: dict[str, object] = {"rows": args.rows, "method": (
        "design DDL in scratch schema, synthetic rows, indexes per layout, VACUUM ANALYZE, "
        "pg_table_size/pg_indexes_size, linear extrapolation to 198.5 M systems"
    )}
    with psycopg.connect(_disposable_dsn(), autocommit=True) as conn:
        out["postgres"] = conn.execute("SELECT version()").fetchone()[0]
        conn.execute("CREATE SCHEMA IF NOT EXISTS scratch")
        for layout, trailing in (("v1_with_system_id64", ", system_id64"), ("v2_score_only", "")):
            table = f"wide_archetype_{layout}"
            conn.execute(f"DROP TABLE IF EXISTS scratch.{table}")
            conn.execute(_ddl(table))
            _fill(conn, table, args.rows)
            for key in ARCHETYPE_KEYS:
                conn.execute(
                    f"CREATE INDEX {table}_{key} ON scratch.{table} "
                    f"(derived_generation_id, {key}_score DESC{trailing})"
                )
            conn.execute(
                f"CREATE INDEX {table}_weighted ON scratch.{table} (derived_generation_id, weighted_potential DESC)"
            )
            conn.execute(f"VACUUM ANALYZE scratch.{table}")
            out[layout] = _sizes(conn, table)
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
