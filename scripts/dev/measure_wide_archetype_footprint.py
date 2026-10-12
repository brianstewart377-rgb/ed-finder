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
* ``v4_weighted_key_tier_partials`` — the layout the F2d design adopted after review
  round 5: eight stored ``<key>_weighted_e4 integer`` columns (score x confidence x
  completeness in 1e-4 units, the canonical picked-ranking key) and, per key, three
  partial ``(generation, <key>_weighted_e4 DESC, system_id64)`` indexes under the
  exposed tier floors ``WHERE <key>_score >= 60 / 76 / 88``, plus the primary key and
  the ``weighted_potential`` index; bell-shaped distribution, per-floor fractions
  reported;
* ``v3_partial_ge60_score_sysid`` — the earlier partial score-ordered layout: eight partial
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
import hashlib
import json
import os
import sys
from pathlib import Path
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


def _ddl(table: str, weighted_keys: bool = False) -> str:
    cols: list[str] = []
    for key in ARCHETYPE_KEYS:
        cols.append(f"{key}_score smallint NOT NULL CHECK ({key}_score BETWEEN 0 AND 100)")
        cols.append(f"{key}_tier char(1) NOT NULL CHECK ({key}_tier IN ('S','A','B','C','D'))")
        cols.append(f"{key}_confidence real NOT NULL CHECK ({key}_confidence BETWEEN 0 AND 1)")
    if weighted_keys:
        # score x confidence x completeness in 1e-4 units (0..1,000,000): the exact
        # canonical picked-ranking key the F2d design stores per archetype.
        for key in ARCHETYPE_KEYS:
            cols.append(f"{key}_weighted_e4 integer NOT NULL CHECK ({key}_weighted_e4 BETWEEN 0 AND 1000000)")
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


# Fractional parts of the golden ratio and of sqrt(2): irrational steps, so the Weyl
# sequence frac(n * step + offset) is equidistributed for every archetype's offset.
WEYL_STEP = "0.61803398874989484820"
WEYL_KEY_OFFSET = 0.41421356237309504880
# The bell layouts still draw from random(); seeding it makes those runs reproducible
# too (INSERT ... SELECT runs in one backend, so the seed governs every draw).
RANDOM_SEED = 0.42


def _score_expr(index: int, distribution: str, floors: dict[str, float] | None = None) -> str:
    if distribution == "uniform":
        return f"((g.n * {97 + index * 13}) %% 101)"
    if distribution == "bell":
        uniforms = "+".join(["random()"] * 12)
        return f"LEAST(100, GREATEST(0, round(45 + 15 * (({uniforms}) - 6))))::int"
    if distribution == "fractions":
        if floors is None:
            raise ValueError("the 'fractions' distribution needs per-floor probabilities")
        f60, f76, f88 = (float(floors[str(floor)]) for floor in (60, 76, 88))
        # Deterministic, not random(): this path produces the capacity receipt, so the
        # same migration and histogram must give the same rows and the same index
        # bytes on every run. A Weyl sequence over the row number gives each row a
        # position u in [0, 1) -- equidistributed, so the share of rows below any f
        # matches f to within about 1/rows -- and u picks the band; the score inside
        # the band is a fixed function of the row number. The realized fractions are
        # still measured and reported (fraction_ge*_by_key).
        u = (
            f"mod(g.n * {WEYL_STEP}::numeric + {(index * WEYL_KEY_OFFSET) % 1:.20f}::numeric, 1)"
        )
        return (
            "(CASE"
            f" WHEN {u} < {f88} THEN 88 + ((g.n * 7 + {index}) %% 13)"
            f" WHEN {u} < {f76} THEN 76 + ((g.n * 11 + {index}) %% 12)"
            f" WHEN {u} < {f60} THEN 60 + ((g.n * 13 + {index}) %% 16)"
            f" ELSE ((g.n * 17 + {index}) %% 60) END)::int"
        )
    raise ValueError(f"unknown distribution {distribution!r}")


def _fill(conn: psycopg.Connection, table: str, rows: int, distribution: str = "uniform",
          weighted_keys: bool = False, fractions: dict[str, dict[str, float]] | None = None) -> None:
    key_array = "ARRAY[" + ", ".join(f"'{key}'" for key in ARCHETYPE_KEYS) + "]"
    # Inner query draws every score once (the bell distribution uses random()), so the
    # derived tier and weighted key of a row always agree with its score.
    inner_cols = ["g.n AS n"]
    for index, key in enumerate(ARCHETYPE_KEYS):
        inner_cols.append(
            f"{_score_expr(index, distribution, fractions.get(key) if fractions else None)} AS s_{key}"
        )
        inner_cols.append(f"round(((g.n * {31 + index}) %% 1000000) / 1000000.0, 6) AS c_{key}")
    inner_cols.append("0.5 + ((g.n * 53) %% 1000) / 2000.0 AS completeness")
    inner = f"SELECT {', '.join(inner_cols)} FROM generate_series(1, %s) AS g(n)"
    select: list[str] = [f"'{GENERATION_ID}'::uuid", "d.n::bigint * 7919", "'v3-archetype-4'"]
    for key in ARCHETYPE_KEYS:
        select.append(f"d.s_{key}::smallint")
        select.append(_tier(f"d.s_{key}"))
        select.append(f"d.c_{key}::real")
    if weighted_keys:
        for key in ARCHETYPE_KEYS:
            select.append(f"round(d.s_{key} * d.c_{key} * d.completeness * 10000)::integer")
    best = "((d.n * 97) %% 101)"
    secondary = f"CASE WHEN d.n %% 11 = 0 THEN NULL ELSE ({key_array})[1 + ((d.n + 3) %% 8)] END"
    select.extend(
        [
            f"({key_array})[1 + (d.n %% 8)]",
            secondary,
            f"{best}::smallint",
            _tier(best),
            "round(((d.n * 17) %% 1000000) / 1000000.0, 6)::real",
            f"{best} * (((d.n * 17) %% 1000000) / 1000000.0)",
            "'2026-10-10T00:00:00Z'::timestamptz",
        ]
    )
    conn.execute(
        f"INSERT INTO scratch.{table} SELECT {', '.join(select)} FROM ({inner}) AS d",
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
    parser.add_argument(
        "--fractions-json",
        help=(
            "Path to a JSON object {archetype_key: {'60': f, '76': f, '88': f}} of REAL per-key "
            "tier fractions (from the governed calibration probe's histogram). When given, the "
            "v4 layout's scores are drawn to match those fractions instead of the declared "
            "synthetic bell distribution, and the receipt records the source as 'measured-histogram'."
        ),
    )
    args = parser.parse_args()
    if args.rows < 1000 or args.rows > 5_000_000:
        sys.exit("--rows must be between 1000 and 5000000")
    fractions: dict[str, dict[str, float]] | None = None
    fractions_canonical: dict[str, dict[str, float]] | None = None
    fractions_sha256: str | None = None
    sigma_all: float | None = None
    if args.fractions_json:
        try:
            parsed = json.loads(Path(args.fractions_json).read_text(encoding="utf-8"))
        except OSError as exc:
            sys.exit(f"--fractions-json could not be read: {exc}")
        except json.JSONDecodeError as exc:
            sys.exit(f"--fractions-json is not valid JSON: {exc}")
        if not isinstance(parsed, dict):
            sys.exit("--fractions-json must be a JSON object keyed by archetype")
        fractions = parsed
        missing = [key for key in ARCHETYPE_KEYS if key not in fractions]
        if missing:
            sys.exit(f"--fractions-json is missing archetype keys: {', '.join(missing)}")
        normalized: dict[str, dict[str, float]] = {}
        for key in ARCHETYPE_KEYS:
            floors = fractions[key]
            # Validated before indexing, so a malformed file stops with this script's
            # own message instead of a KeyError or TypeError traceback.
            if not isinstance(floors, dict):
                sys.exit(f"--fractions-json {key!r} must be an object of floor fractions")
            missing_floors = [str(floor) for floor in (60, 76, 88) if str(floor) not in floors]
            if missing_floors:
                sys.exit(
                    f"--fractions-json {key!r} is missing floor keys: {', '.join(missing_floors)}"
                )
            try:
                values = [float(floors[str(floor)]) for floor in (60, 76, 88)]
            except (TypeError, ValueError):
                sys.exit(f"--fractions-json {key!r} floor fractions must be numbers")
            if not all(0.0 <= v <= 1.0 for v in values) or not values[0] >= values[1] >= values[2]:
                sys.exit(f"--fractions-json {key!r} must give 1 >= f60 >= f76 >= f88 >= 0")
            normalized[key] = {"60": values[0], "76": values[1], "88": values[2]}
        # The capacity gate trusts this receipt's provenance, so record the exact
        # probabilities used and their digest. The gate re-computes this digest from the
        # governed calibration evidence and refuses the receipt unless the two match, so a
        # stale or substituted JSON file cannot pass as a measured histogram.
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        fractions_canonical = normalized
        fractions_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        sigma_all = round(sum(sum(v.values()) for v in normalized.values()), 6)
    out: dict[str, object] = {
        # The built-in layouts are comparison evidence, not the capacity input. Their
        # DDL predates the final no-pick index (which adds a trailing system_id64),
        # and they create every index AFTER the fill -- a compact bulk build --
        # whereas migration 011 creates them on the empty relation and the builder
        # inserts 198.5 M rows incrementally, which splits pages and lowers
        # occupancy. Either difference understates production bytes, so no receipt
        # from this path may satisfy the capacity gate; only the final-migration
        # path (F2d PR1), which applies 011 itself before a chunked fill, may.
        "capacity_gate_eligible": False,
        "capacity_gate_ineligible_reason": (
            "built-in comparison layout: pre-final index DDL and indexes built after "
            "the fill; the capacity gate requires the final-migration path"
        ),
        "score_distribution_source": "measured-histogram" if fractions else "declared-synthetic-bell",
        "fractions_json": args.fractions_json,
        "fractions_canonical": fractions_canonical if fractions else None,
        "fractions_sha256": fractions_sha256 if fractions else None,
        "sigma_all": sigma_all if fractions else None,
        "rows": args.rows,
        "sampling": "fractions: deterministic Weyl bands; bell: random() after setseed",
        "random_seed": RANDOM_SEED,
        "method": (
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
        # (layout, index column template, trailing columns, partial predicates, distribution, weighted columns)
        layouts = (
            ("v1_with_system_id64", "{key}_score", ", system_id64", ("",), "uniform", False),
            ("v2_score_only", "{key}_score", "", ("",), "uniform", False),
            ("v3_partial_ge60_score_sysid", "{key}_score", ", system_id64", (" WHERE {key}_score >= 60",), "bell", False),
            # The F2d layout adopted after review round 5: the canonical weighted key is
            # stored per archetype and indexed under each exposed tier floor, so the
            # picked ranking is served in canonical order by a bounded index scan.
            ("v4_weighted_key_tier_partials", "{key}_weighted_e4", ", system_id64",
             (" WHERE {key}_score >= 60", " WHERE {key}_score >= 76", " WHERE {key}_score >= 88"), "bell", True),
        )
        for layout, column, trailing, predicates, distribution, weighted_keys in layouts:
            table = f"wide_archetype_{layout}"
            conn.execute(f"DROP TABLE IF EXISTS scratch.{table}")
            conn.execute(_ddl(table, weighted_keys))
            conn.execute(f"SELECT setseed({RANDOM_SEED})")
            layout_fractions = fractions if (weighted_keys and fractions) else None
            _fill(
                conn, table, args.rows,
                "fractions" if layout_fractions else distribution,
                weighted_keys, layout_fractions,
            )
            for key in ARCHETYPE_KEYS:
                for ordinal, predicate in enumerate(predicates):
                    # Keep names under PostgreSQL's 63-character identifier limit.
                    conn.execute(
                        f"CREATE INDEX wa_{layout}_{key}_{ordinal} ON scratch.{table} "
                        f"(derived_generation_id, {column.format(key=key)} DESC{trailing}){predicate.format(key=key)}"
                    )
            conn.execute(
                f"CREATE INDEX wa_{layout}_weighted ON scratch.{table} (derived_generation_id, weighted_potential DESC)"
            )
            conn.execute(f"VACUUM ANALYZE scratch.{table}")
            report = _sizes(conn, table)
            report["score_distribution"] = "fractions" if layout_fractions else distribution
            for floor in (60, 76, 88):
                report[f"fraction_ge{floor}_by_key"] = {
                    key: round(count / args.rows, 4)
                    for key, count in zip(
                        ARCHETYPE_KEYS,
                        conn.execute(
                            "SELECT " + ", ".join(
                                f"count(*) FILTER (WHERE {key}_score >= {floor})" for key in ARCHETYPE_KEYS
                            )
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
