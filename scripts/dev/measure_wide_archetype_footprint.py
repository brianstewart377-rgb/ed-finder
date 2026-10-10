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
  deduplication collapses the 101 distinct score values into posting lists);
* ``v3_partial_ge60_score_sysid`` — the layout the F2d design adopted: eight partial
  ``(generation, <key>_score DESC, system_id64) WHERE <key>_score >= 60`` indexes.
  Its size scales with the fraction of rows scoring >= 60, so this variant is filled
  with a bell-shaped score distribution (mean ~45, sd ~15; the same shape as
  ``measure_wide_archetype_probe_indexes.py``) and reports that fraction per key;
  the first two variants keep the uniform distribution so their numbers stay
  comparable with the 2026-10-10 evidence.

Both layouts share the primary key and the ``weighted_potential`` index.

Safety: the DSN comes only from ``EDFINDER_DISPOSABLE_DSN``; it must be a plain
``postgresql://`` URI with no query string or fragment (so no ``hostaddr``,
``service`` or other libpq overrides can redirect it), it must name the
disposable ``ratings_v4_validation`` database (the same allowlist the repository's
PostgreSQL test fixture enforces; a production database reached through a loopback
tunnel is refused by name and re-checked with ``current_database()`` after
connecting), its effective libpq ``host``
must be a loopback address and ``hostaddr`` may not be set; ambient libpq routing
variables (``PGHOST``, ``PGHOSTADDR``, ``PGPORT``, ``PGSERVICE``, ``PGSERVICEFILE``,
``PGDATABASE``) must be unset; the connection is opened from the validated
keyword dictionary with ``hostaddr`` pinned to the loopback address, and after
connecting the script verifies ``inet_server_addr()`` is loopback and the server
is PostgreSQL 18 before creating anything. It writes only to the ``scratch``
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
from psycopg.conninfo import conninfo_to_dict

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
LOOPBACK_ADDRESSES = {"127.0.0.1": "127.0.0.1", "localhost": "127.0.0.1", "::1": "::1"}
# libpq fills omitted parameters from these; any of them could re-route the connection.
AMBIENT_ROUTING_VARS = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE")
REQUIRED_SERVER_MAJOR = 18
# The only database this script may write to: the repository's disposable local
# validation service (the same name tests/ratings_v4_pg_fixture.py insists on).
ALLOWED_DBNAMES = frozenset({"ratings_v4_validation"})
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


def _score_expr(index: int, distribution: str) -> str:
    if distribution == "uniform":
        return f"((g.n * {97 + index * 13}) %% 101)"
    if distribution == "bell":
        uniforms = "+".join(["random()"] * 12)
        return f"LEAST(100, GREATEST(0, round(45 + 15 * (({uniforms}) - 6))))::int"
    raise ValueError(f"unknown distribution {distribution!r}")


def _fill(conn: psycopg.Connection, table: str, rows: int, distribution: str = "uniform") -> None:
    key_array = "ARRAY[" + ", ".join(f"'{key}'" for key in ARCHETYPE_KEYS) + "]"
    select: list[str] = [f"'{GENERATION_ID}'::uuid", "g.n::bigint * 7919", "'v3-archetype-4'"]
    for index, _key in enumerate(ARCHETYPE_KEYS):
        score = _score_expr(index, distribution)
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


def disposable_conninfo(dsn: str) -> dict[str, str]:
    """Validate a disposable loopback DSN and return the libpq keywords to connect with.

    Fails closed on anything that could redirect the connection away from the
    loopback host the URI authority names: a non-postgresql scheme, a query
    string or fragment (``?hostaddr=…``, ``?service=…`` and the like), a
    missing or non-loopback effective ``host``, or any ``hostaddr``/``service``
    keyword surviving parsing.
    """
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgresql", "postgres"}:
        raise ValueError("EDFINDER_DISPOSABLE_DSN must be a postgresql:// URI")
    if parts.query or parts.fragment:
        raise ValueError("EDFINDER_DISPOSABLE_DSN may not carry a query string or fragment (libpq overrides refused)")
    keywords = {key: str(value) for key, value in conninfo_to_dict(dsn).items() if value is not None}
    if "hostaddr" in keywords or "service" in keywords or "passfile" in keywords:
        raise ValueError("EDFINDER_DISPOSABLE_DSN resolved a hostaddr/service/passfile override; refused")
    host = keywords.get("host", "")
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"refusing non-loopback host {host!r}: this script runs only against a disposable local database")
    if keywords.get("dbname") not in ALLOWED_DBNAMES:
        raise ValueError(
            f"refusing database {keywords.get('dbname')!r}: only the disposable "
            f"{sorted(ALLOWED_DBNAMES)} service may be measured"
        )
    ambient = [name for name in AMBIENT_ROUTING_VARS if os.environ.get(name)]
    if ambient:
        raise ValueError(f"refusing to run with ambient libpq routing variables set: {', '.join(ambient)}")
    # Pin the address explicitly so neither PGHOSTADDR nor name resolution can redirect it.
    keywords["hostaddr"] = LOOPBACK_ADDRESSES[host]
    return keywords


def assert_disposable_server(conn: psycopg.Connection) -> int:
    """Fail closed unless connected to the loopback-addressed, allowlisted disposable database on PostgreSQL 18."""
    server_addr, version_num, dbname = conn.execute(
        "SELECT host(inet_server_addr()), current_setting('server_version_num')::int, current_database()"
    ).fetchone()
    if server_addr not in {"127.0.0.1", "::1"}:
        raise ValueError(f"connected server address {server_addr!r} is not loopback; refusing to write")
    if dbname not in ALLOWED_DBNAMES:
        raise ValueError(f"connected database {dbname!r} is not the disposable validation service; refusing to write")
    if version_num // 10000 != REQUIRED_SERVER_MAJOR:
        raise ValueError(
            f"connected server is PostgreSQL {version_num // 10000}, not {REQUIRED_SERVER_MAJOR}; "
            "the capacity measurement is only valid on the production major"
        )
    return version_num


def _disposable_conninfo_from_env() -> dict[str, str]:
    dsn = os.environ.get("EDFINDER_DISPOSABLE_DSN", "")
    if not dsn:
        sys.exit("EDFINDER_DISPOSABLE_DSN is required (disposable local PostgreSQL only)")
    try:
        return disposable_conninfo(dsn)
    except ValueError as exc:
        sys.exit(str(exc))


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
    with psycopg.connect(**_disposable_conninfo_from_env(), autocommit=True) as conn:
        try:
            out["server_version_num"] = assert_disposable_server(conn)
        except ValueError as exc:
            sys.exit(str(exc))
        out["postgres"] = conn.execute("SELECT version()").fetchone()[0]
        conn.execute("CREATE SCHEMA IF NOT EXISTS scratch")
        layouts = (
            ("v1_with_system_id64", ", system_id64", "", "uniform"),
            ("v2_score_only", "", "", "uniform"),
            ("v3_partial_ge60_score_sysid", ", system_id64", " WHERE {key}_score >= 60", "bell"),
        )
        for layout, trailing, predicate, distribution in layouts:
            table = f"wide_archetype_{layout}"
            conn.execute(f"DROP TABLE IF EXISTS scratch.{table}")
            conn.execute(_ddl(table))
            _fill(conn, table, args.rows, distribution)
            for key in ARCHETYPE_KEYS:
                conn.execute(
                    f"CREATE INDEX {table}_{key} ON scratch.{table} "
                    f"(derived_generation_id, {key}_score DESC{trailing}){predicate.format(key=key)}"
                )
            conn.execute(
                f"CREATE INDEX {table}_weighted ON scratch.{table} (derived_generation_id, weighted_potential DESC)"
            )
            conn.execute(f"VACUUM ANALYZE scratch.{table}")
            report = _sizes(conn, table)
            report["score_distribution"] = distribution
            report["fraction_ge60_by_key"] = {
                key: round(count / args.rows, 4)
                for key, count in zip(
                    ARCHETYPE_KEYS,
                    conn.execute(
                        "SELECT " + ", ".join(f"count(*) FILTER (WHERE {key}_score >= 60)" for key in ARCHETYPE_KEYS)
                        + f" FROM scratch.{table}"
                    ).fetchone(),
                    strict=True,
                )
            }
            out[layout] = report
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
