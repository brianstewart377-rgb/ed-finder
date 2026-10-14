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
is PostgreSQL 18 before creating anything. The default comparison mode writes
only to the ``scratch`` schema of that database. ``--migration-sql`` creates a
randomly named temporary database on the same verified disposable server,
applies the prerequisite migrations and supplied SQL there, and drops that
temporary database in a ``finally`` block. Neither mode reads production.

Usage::

    EDFINDER_DISPOSABLE_DSN=postgresql://user:pass@127.0.0.1:55418/db \\
        python scripts/dev/measure_wide_archetype_footprint.py --rows 200000 > footprint.json
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.v3_system_archetype as archetype_builder  # noqa: E402
from scripts.operator.lib import f2d_evidence  # noqa: E402
from scripts.operator.lib.f2d_operator_identity import (  # noqa: E402
    OperatorIdentityError,
    compute_operator_code_sha256,
)
from shared_contracts import v3_system_archetype_model as archetype_model  # noqa: E402

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
# RFC 1918 and IPv6 unique-local ranges: what a disposable container network uses.
# Documentation/TEST-NET ranges and every global address stay refused.
DISPOSABLE_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
LOOPBACK_ADDRESSES = {"127.0.0.1": "127.0.0.1", "localhost": "127.0.0.1", "::1": "::1"}
# libpq fills omitted parameters from these; any of them could re-route the connection.
AMBIENT_ROUTING_VARS = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE")
REQUIRED_SERVER_MAJOR = 18
# The only database this script may write to: the repository's disposable local
# validation service (the same name tests/ratings_v4_pg_fixture.py insists on).
ALLOWED_DBNAMES = frozenset({"ratings_v4_validation"})
GENERATION_ID = "a7076522-0000-4000-8000-000000000001"
MIGRATION_PREREQUISITES = (
    "001_v3_baseline.sql",
    "003_ratings_v4_derived.sql",
    "004_v3_search_spatial_clusters.sql",
    "006_v3_derived_product_lifecycle.sql",
)
MIGRATIONS = ROOT / "sql" / "v3" / "migrations"
FINAL_INDEX_NAMES = frozenset(
    {
        "system_archetype_pkey",
        "system_archetype_summary_weighted",
        *(
            f"system_archetype_{key}_{tier}_weighted"
            for key in ARCHETYPE_KEYS
            for tier in ("b", "a", "s")
        ),
    }
)
TIER_INDEX_NAMES = FINAL_INDEX_NAMES - {
    "system_archetype_pkey",
    "system_archetype_summary_weighted",
}
BUILTIN_FRACTIONS = {
    key: {"60": 0.168, "76": 0.020, "88": 0.0019}
    for key in ARCHETYPE_KEYS
}
MEASUREMENT_DATABASE_PREFIX = "wide_archetype_measure_"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


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
        # Checked here as well as in normalize_fractions(), so this expression can
        # never be built from an unvalidated mapping, whatever the caller.
        if not isinstance(floors, dict) or any(str(f) not in floors for f in (60, 76, 88)):
            raise ValueError("the 'fractions' distribution needs floors 60, 76 and 88")
        try:
            f60, f76, f88 = (float(floors[str(floor)]) for floor in (60, 76, 88))
        except (TypeError, ValueError):
            raise ValueError("the 'fractions' distribution needs numeric floors") from None
        if not 1.0 >= f60 >= f76 >= f88 >= 0.0:
            raise ValueError("the 'fractions' distribution needs 1 >= f60 >= f76 >= f88 >= 0")
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


def _parse_address(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return ipaddress.ip_address(value.split("/", 1)[0])
    except ValueError:
        return None


ATTESTED_SERVER_ADDRESS_ENV = "EDFINDER_DISPOSABLE_SERVER_ADDRESS"


def attested_server_address() -> str | None:
    """The disposable container address the orchestrator attests, if any.

    The caller that owns the disposable service (the CI lane, the capacity
    measurement workflow) inspects its own service container and exports the
    container's network address here. It is the only way a non-loopback server
    address is accepted: a private address alone, or a client/server pair on the
    same /16, is not proof that the server is the local container - a TCP relay
    on a private LAN presents exactly that pair.
    """
    value = os.environ.get(ATTESTED_SERVER_ADDRESS_ENV, "").strip()
    return value or None


def server_address_is_disposable(
    server_addr: object,
    client_addr: object = None,
    attested_addr: object = None,
) -> bool:
    """True for a loopback server, or for exactly the attested disposable container.

    The client side is already pinned to a loopback host by disposable_conninfo().
    A disposable PostgreSQL that runs as a container behind a published loopback
    port reports its own bridge address (e.g. 172.18.0.2) in inet_server_addr()
    and sees the bridge gateway (e.g. 172.18.0.1) in inet_client_addr(). That
    case is accepted only when the orchestrator attested that exact server
    address (ATTESTED_SERVER_ADDRESS_ENV, from its own container inspection),
    the address is RFC 1918 / ULA, and the client address is a non-loopback
    private address on the same /16. Public and documentation ranges, an
    unattested or differently attested address, and a loopback client (an SSH
    or TCP forward to another server) are all refused.
    """
    server = _parse_address(server_addr)
    if server is None:
        return False
    if server.is_loopback:
        return True
    attested = _parse_address(attested_addr)
    if attested is None or attested != server:
        return False
    if not any(server in network for network in DISPOSABLE_PRIVATE_NETWORKS):
        return False
    client = _parse_address(client_addr)
    if client is None or client.is_loopback or client.version != server.version:
        return False
    if not any(client in network for network in DISPOSABLE_PRIVATE_NETWORKS):
        return False
    prefix = 16 if server.version == 4 else 64
    return ipaddress.ip_network(f"{server}/{prefix}", strict=False) == ipaddress.ip_network(
        f"{client}/{prefix}", strict=False
    )


def assert_disposable_server(conn: psycopg.Connection) -> int:
    """Fail closed unless connected to a loopback or same-bridge container PostgreSQL 18 holding the allowlisted disposable database."""
    server_addr, client_addr, version_num, dbname = conn.execute(
        "SELECT host(inet_server_addr()), host(inet_client_addr()), "
        "current_setting('server_version_num')::int, current_database()"
    ).fetchone()
    if not server_address_is_disposable(server_addr, client_addr, attested_server_address()):
        raise ValueError(
            f"connected server address {server_addr!r} (client {client_addr!r}) is not loopback "
            f"or the attested disposable container ({ATTESTED_SERVER_ADDRESS_ENV}); refusing to write"
        )
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


def normalize_fractions(
    fractions: dict[str, object],
) -> tuple[dict[str, dict[str, float]], str, float]:
    """Validate per-key floor fractions; return them canonical, with digest and Σ_all.

    Raises ValueError with the operator-facing message on any malformed input, so a
    bad file stops with this script's own words rather than a traceback. The capacity
    gate re-computes the digest from the governed calibration evidence and refuses
    the receipt unless the two match, so a stale or substituted file cannot pass as a
    measured histogram.
    """
    missing = [key for key in ARCHETYPE_KEYS if key not in fractions]
    if missing:
        raise ValueError(f"--fractions-json is missing archetype keys: {', '.join(missing)}")
    normalized: dict[str, dict[str, float]] = {}
    for key in ARCHETYPE_KEYS:
        floors = fractions[key]
        if not isinstance(floors, dict):
            raise ValueError(f"--fractions-json {key!r} must be an object of floor fractions")
        missing_floors = [str(floor) for floor in (60, 76, 88) if str(floor) not in floors]
        if missing_floors:
            raise ValueError(
                f"--fractions-json {key!r} is missing floor keys: {', '.join(missing_floors)}"
            )
        try:
            values = [float(floors[str(floor)]) for floor in (60, 76, 88)]
        except (TypeError, ValueError):
            raise ValueError(f"--fractions-json {key!r} floor fractions must be numbers") from None
        if not all(0.0 <= v <= 1.0 for v in values) or not values[0] >= values[1] >= values[2]:
            raise ValueError(f"--fractions-json {key!r} must give 1 >= f60 >= f76 >= f88 >= 0")
        normalized[key] = {"60": values[0], "76": values[1], "88": values[2]}
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sigma_all = round(sum(sum(v.values()) for v in normalized.values()), 6)
    return normalized, digest, sigma_all


def _ceil_ratio(numerator: int, denominator: int) -> int:
    """Return an exact positive integer ceiling (receipt arithmetic is integral)."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("receipt byte arithmetic needs non-negative bytes and a positive divisor")
    return (numerator + denominator - 1) // denominator


def per_row_costs(
    *,
    heap_bytes: int,
    primary_key_bytes: int,
    weighted_index_bytes: int,
    tier_index_bytes: int,
    rows: int,
    tier_entries: int,
) -> dict[str, int]:
    """Compute the four gate inputs without rounding an intermediate value.

    ``sigma_all`` is ``tier_entries / rows``.  Consequently
    ``tier bytes / rows / sigma_all`` is exactly ``tier bytes / tier_entries``;
    reducing the expression this way avoids a binary-float receipt boundary.
    """
    if rows <= 0 or tier_entries <= 0:
        raise ValueError("the final measurement needs rows and at least one tier entry")
    return {
        "heap_bytes_per_row": _ceil_ratio(heap_bytes, rows),
        "primary_key_bytes_per_row": _ceil_ratio(primary_key_bytes, rows),
        "weighted_index_bytes_per_row": _ceil_ratio(weighted_index_bytes, rows),
        "tier_index_bytes_per_row_per_unit_fraction": _ceil_ratio(
            tier_index_bytes, tier_entries
        ),
    }


def archetype_fixed_cost(
    *,
    heap_bytes: int,
    text_bytes_stored: int,
    primary_key_bytes: int,
    weighted_index_bytes: int,
    rows: int,
) -> int:
    """Return the integral fixed per-row cost with variable text removed.

    Migration 011 rejects the design prose's literal ``paradise``/``paradise``
    fill because a non-null secondary archetype must differ from the primary.
    Measuring the real fill's text octets and subtracting them from the heap
    realizes the intended text-free fixed term without weakening that CHECK.
    """
    if text_bytes_stored < 0 or text_bytes_stored > heap_bytes:
        raise ValueError("stored archetype text bytes must fit within the measured heap")
    return _ceil_ratio(
        heap_bytes - text_bytes_stored + primary_key_bytes + weighted_index_bytes,
        rows,
    )


def validate_archetype_footprint_receipt(receipt: object) -> dict[str, object]:
    """Validate a sealed final-migration receipt for the capacity gate."""
    if not isinstance(receipt, dict):
        raise ValueError("archetype footprint receipt must be a JSON object")
    body = dict(receipt)
    seal = body.pop("content_sha256", None)
    if not isinstance(seal, str) or SHA256_RE.fullmatch(seal) is None:
        raise ValueError("archetype footprint receipt content_sha256 is malformed")
    if f2d_evidence.canonical_sha256(body) != seal:
        raise ValueError("archetype footprint receipt seal does not verify")
    if receipt.get("capacity_gate_eligible") is not True:
        raise ValueError("archetype footprint receipt is not capacity-gate eligible")
    if receipt.get("score_distribution_source") != "measured-histogram":
        raise ValueError("archetype footprint receipt is not from a measured histogram")
    for field in (
        "heap_bytes_per_row",
        "primary_key_bytes_per_row",
        "weighted_index_bytes_per_row",
        "tier_index_bytes_per_row_per_unit_fraction",
        "archetype_fixed_bytes_per_row",
    ):
        value = receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"archetype footprint receipt {field} must be a positive integer")
    for field in (
        "migration_011_sha256",
        "fractions_sha256",
        "f2d_operator_code_sha256",
    ):
        value = receipt.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            raise ValueError(f"archetype footprint receipt {field} must be lowercase SHA-256")
    _require_costs_derive_from_measurements(receipt)
    return receipt


def _receipt_int(receipt: dict[str, object], field: str, *, minimum: int) -> int:
    value = receipt.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"archetype footprint receipt {field} must be an integer >= {minimum}")
    return value


def _require_costs_derive_from_measurements(receipt: dict[str, object]) -> None:
    """Recompute every gate cost from the receipt's raw measurements.

    The capacity gate trusts these five per-row costs to size irreversible
    builds, so a sealed receipt is accepted only when each one equals what the
    measured rows, heap, stored text and per-index sizes produce (the same
    arithmetic the measurement used), never on the strength of its seal alone.
    """
    rows = _receipt_int(receipt, "rows", minimum=1)
    if receipt.get("row_count") != rows:
        raise ValueError("archetype footprint receipt row_count must equal rows")
    heap_bytes = _receipt_int(receipt, "heap_bytes", minimum=1)
    text_bytes_stored = _receipt_int(receipt, "text_bytes_stored", minimum=0)

    index_sizes = receipt.get("per_index_bytes")
    if not isinstance(index_sizes, dict) or set(index_sizes) != FINAL_INDEX_NAMES:
        raise ValueError(
            "archetype footprint receipt per_index_bytes must name exactly the designed indexes"
        )
    for name, size in index_sizes.items():
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"archetype footprint receipt per_index_bytes.{name} is invalid")
    tier_bytes = sum(index_sizes[name] for name in TIER_INDEX_NAMES)
    if receipt.get("tier_index_bytes") != tier_bytes:
        raise ValueError("archetype footprint receipt tier_index_bytes does not sum the tier indexes")

    seeded = receipt.get("seeded_fractions")
    if not isinstance(seeded, dict) or set(seeded) != set(ARCHETYPE_KEYS):
        raise ValueError("archetype footprint receipt seeded_fractions must cover every archetype")
    tier_entries = 0
    for key in ARCHETYPE_KEYS:
        floors = seeded[key]
        if not isinstance(floors, dict) or set(floors) != {"60", "76", "88"}:
            raise ValueError(f"archetype footprint receipt seeded_fractions.{key} is malformed")
        for floor, fraction in floors.items():
            if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
                raise ValueError(
                    f"archetype footprint receipt seeded_fractions.{key}.{floor} is invalid"
                )
            # The measurement records count / rows; recover the exact count.
            count = round(fraction * rows)
            if count < 0 or count > rows or count / rows != fraction:
                raise ValueError(
                    f"archetype footprint receipt seeded_fractions.{key}.{floor} is not a row count"
                )
            tier_entries += count
    if tier_entries <= 0 or receipt.get("sigma_all") != tier_entries / rows:
        raise ValueError("archetype footprint receipt sigma_all does not match its tier counts")

    expected = per_row_costs(
        heap_bytes=heap_bytes,
        primary_key_bytes=index_sizes["system_archetype_pkey"],
        weighted_index_bytes=index_sizes["system_archetype_summary_weighted"],
        tier_index_bytes=tier_bytes,
        rows=rows,
        tier_entries=tier_entries,
    )
    expected["archetype_fixed_bytes_per_row"] = archetype_fixed_cost(
        heap_bytes=heap_bytes,
        text_bytes_stored=text_bytes_stored,
        primary_key_bytes=index_sizes["system_archetype_pkey"],
        weighted_index_bytes=index_sizes["system_archetype_summary_weighted"],
        rows=rows,
    )
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(
                f"archetype footprint receipt {field} is not derived from its measurements"
            )


def capacity_gate_eligible(*, final_migration: bool, distribution_source: str) -> bool:
    return final_migration and distribution_source == "measured-histogram"


def migration_sql_sha256(migration_path: Path) -> str:
    return hashlib.sha256(migration_path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class _SyntheticInput:
    potential: tuple[int, ...]
    quality: tuple[int, ...]
    opportunity_groups: tuple[tuple[int, int, int], ...]
    signature: tuple[bool, ...]


def _signature(scored: dict[str, object]) -> tuple[bool, ...]:
    return tuple(
        int(scored[f"{key}_score"]) >= floor
        for key in ARCHETYPE_KEYS
        for floor in (60, 76, 88)
    )


def _candidate(
    potential: tuple[int, ...],
    quality: tuple[int, ...],
    groups: tuple[tuple[int, int, int], ...],
) -> _SyntheticInput:
    vector = archetype_model.SystemVectorRow(
        system_id64=1,
        potential=potential,
        quality=quality,
        quality_min=quality,
        quality_max=quality,
        completeness=(10_000,) * 7,
        confidence=(10_000,) * 7,
    )
    return _SyntheticInput(
        potential=potential,
        quality=quality,
        opportunity_groups=groups,
        signature=_signature(archetype_model.score_raw_system(vector, groups)),
    )


def _synthetic_catalog() -> tuple[_SyntheticInput, ...]:
    """Build a deterministic library of raw model inputs spanning the tier space."""
    rng = random.Random(20261010)
    candidates: list[_SyntheticInput] = []
    # Include smooth all-economy profiles as well as independent economy shapes.
    for value in range(0, 101, 5):
        for count in (0, 1, 4, 6, 8):
            groups = tuple((ordinal, count, count * 100) for ordinal in range(1, 8) if count)
            candidates.append(_candidate((value,) * 7, (100,) * 7, groups))
    for _ in range(4096):
        potential = tuple(rng.randrange(0, 101) for _ in range(7))
        quality = tuple(rng.randrange(35, 101) for _ in range(7))
        groups = []
        for ordinal in range(1, 8):
            count = rng.choices((0, 1, 4, 6, 8), weights=(30, 25, 20, 15, 10))[0]
            if count:
                local = rng.randrange(45, 101)
                groups.append((ordinal, count, count * local))
        candidates.append(_candidate(potential, quality, tuple(groups)))
    # De-duplicate signatures. For footprint work one stable representative of a
    # requested tier shape is preferable to an arbitrary random representative.
    return tuple({candidate.signature: candidate for candidate in candidates}.values())


def _synthetic_inputs(
    rows: int, fractions: dict[str, dict[str, float]]
) -> list[_SyntheticInput]:
    """Choose raw rows whose scores best match the requested cumulative bands.

    The model's archetypes share economy anchors, so not every arbitrary 24-bit
    tier vector is physically realizable.  Selection is therefore from real raw
    rows scored by ``score_raw_system``; the receipt records the realized tier
    fractions and sigma, never the requested values, for size normalization.
    """
    catalog = _synthetic_catalog()
    target = tuple(
        fractions[key][str(floor)]
        for key in ARCHETYPE_KEYS
        for floor in (60, 76, 88)
    )
    # Frank-Wolfe projection finds a mixture of physically realizable raw rows
    # whose 24 marginal floor fractions are closest to the requested histogram.
    # It avoids pretending independently fabricated score columns came from the
    # canonical model when shared economy anchors make some joint patterns
    # impossible (notably Flexible has only scores 0/25/50/75/100).
    zero_index = next(
        index for index, candidate in enumerate(catalog)
        if not any(candidate.signature)
    )
    weights = [0.0] * len(catalog)
    weights[zero_index] = 1.0
    realized = [0.0] * len(target)
    for iteration in range(1, 4001):
        gradient = [actual - wanted for actual, wanted in zip(realized, target, strict=True)]
        selected = min(
            range(len(catalog)),
            key=lambda candidate_index: sum(
                gradient[index] * catalog[candidate_index].signature[index]
                for index in range(len(target))
            ),
        )
        step = 2.0 / (iteration + 2)
        realized = [
            (1.0 - step) * actual + step * catalog[selected].signature[index]
            for index, actual in enumerate(realized)
        ]
        weights = [(1.0 - step) * weight for weight in weights]
        weights[selected] += step
    counts = [int(weight * rows) for weight in weights]
    remainder = rows - sum(counts)
    order = sorted(
        range(len(catalog)),
        key=lambda index: (-(weights[index] * rows - counts[index]), index),
    )
    for index in order[:remainder]:
        counts[index] += 1
    result = [
        candidate
        for candidate, count in zip(catalog, counts, strict=True)
        for _ in range(count)
    ]
    random.Random(20261010).shuffle(result)
    return result


def _copy_rows(conn: psycopg.Connection, table: str, columns: tuple[str, ...], rows) -> None:
    command = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(*table.split(".")),
        sql.SQL(",").join(sql.Identifier(column) for column in columns),
    )
    with conn.cursor().copy(command) as copy:
        for row in rows:
            copy.write_row(row)


def _seed_measurement_source(
    conn: psycopg.Connection,
    rows: int,
    fractions: dict[str, dict[str, float]],
) -> str:
    """Seed raw Ratings-shaped rows; Archetype rows are written only by the builder."""
    zero_hash = b"\0" * 32
    source_run_id = uuid4()
    canonical_generation_id = uuid4()
    generation_id = uuid4()
    policy_id = conn.execute(
        """INSERT INTO v3_source.source(source_code,display_name,authority_class)
             VALUES ('wide_measurement','Wide measurement','REFERENCE_CURATED')
             RETURNING source_id"""
    ).fetchone()[0]
    rights_id = conn.execute(
        """INSERT INTO v3_source.source_rights_policy(
               source_id,policy_version,rights_class,retention_class,
               distribution_allowed,effective_at)
             VALUES (%s,'measurement-1','CANONICAL_ELIGIBLE','disposable',false,now())
             RETURNING rights_policy_id""",
        (policy_id,),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO v3_source.source_run(
               source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
               run_state,idempotency_key,is_complete_snapshot,started_at,completed_at,
               importer_version,importer_code_sha256,importer_config_sha256,
               normalizer_version,normalizer_sha256)
             VALUES (%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',
                     'wide-measurement',true,now(),now(),'measurement',%s,%s,
                     'measurement',%s)""",
        (source_run_id, policy_id, rights_id, zero_hash, zero_hash, zero_hash),
    )
    conn.execute(
        """INSERT INTO v3_meta.canonical_generation(
               generation_id,generation_key,relation_schema,lifecycle_state,
               manifest_sha256,build_source_run_id,validation_completed_at,published_at)
             VALUES (%s,'measurement','v3_gen_measurement','PUBLISHED',%s,%s,now(),now())""",
        (canonical_generation_id, zero_hash, source_run_id),
    )
    conn.execute(
        """INSERT INTO v3_meta.current_canonical_generation(
               singleton,generation_id,publication_sequence,published_at)
             VALUES (true,%s,1,now())""",
        (canonical_generation_id,),
    )
    generation_key = "wide_measurement"
    manifest = {
        "canonical_schema": "v3_gen_measurement",
        "measurement": "wide-archetype-footprint",
    }
    manifest_text = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    conn.execute(
        """INSERT INTO v3_meta.derived_generation(
               derived_generation_id,canonical_generation_id,
               canonical_publication_sequence,generation_key,mechanics_version,
               scorer_version,adapter_version,manifest,manifest_sha256,
               expected_systems,expected_bodies)
             VALUES (%s,%s,1,%s,'measurement','measurement','measurement',
                     %s::jsonb,%s,%s,0)""",
        (
            generation_id,
            canonical_generation_id,
            generation_key,
            manifest_text,
            hashlib.sha256(manifest_text.encode()).digest(),
            rows,
        ),
    )
    inputs = _synthetic_inputs(rows, fractions)
    for ordinal, start in enumerate(range(0, rows, 1000)):
        chunk = inputs[start : start + 1000]
        conn.execute(
            """INSERT INTO v3_derived.build_chunk(
                   derived_generation_id,chunk_ordinal,source_projection_sha256,
                   canonical_input_sha256,content_sha256,systems,canonical_bodies,
                   physical_bodies,eligible_opportunities)
                 VALUES (%s,%s,%s,%s,%s,%s,0,0,0)""",
            (generation_id, ordinal, zero_hash, zero_hash, zero_hash, len(chunk)),
        )
        vector_rows = []
        body_rows = []
        opportunity_rows = []
        for offset, synthetic in enumerate(chunk, start=start + 1):
            identifier = offset * 7919
            max_count = max((group[1] for group in synthetic.opportunity_groups), default=0)
            vector_rows.append(
                (
                    generation_id,
                    identifier,
                    ordinal,
                    max_count,
                    max_count,
                    zero_hash,
                    list(synthetic.potential),
                    list(synthetic.quality),
                    list(synthetic.quality),
                    list(synthetic.quality),
                    [10_000] * 7,
                    [10_000] * 7,
                )
            )
            for body_pk in range(1, max_count + 1):
                body_rows.append(
                    (
                        generation_id,
                        identifier,
                        body_pk,
                        body_pk,
                        "Star",
                        None,
                        None,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        body_pk == 1,
                        None,
                        False,
                        False,
                        None,
                    )
                )
            for economy_ordinal, count, local_sum in synthetic.opportunity_groups:
                local_score = local_sum // count
                for body_pk in range(1, count + 1):
                    opportunity_rows.append(
                        (
                            generation_id,
                            identifier,
                            body_pk,
                            economy_ordinal,
                            True,
                            False,
                            local_score,
                            100,
                            100,
                            100,
                            1.0,
                            1.0,
                        )
                    )
        _copy_rows(conn, "v3_derived.system_rating_vector", (
            "derived_generation_id", "system_id64", "chunk_ordinal",
            "loaded_body_count", "physical_body_count", "subtype_projection_sha256",
            "potential", "quality", "quality_min", "quality_max", "completeness",
            "confidence",
        ), vector_rows)
        if body_rows:
            _copy_rows(conn, "v3_derived.body_mechanics", (
                "derived_generation_id", "system_id64", "body_pk", "source_body_id64",
                "body_class", "spectral_class", "luminosity_class", "rings",
                "biologicals", "geologicals", "volcanism", "terraformable",
                "tidally_locked", "is_main_star", "reserve_level",
                "usable_ground_opportunity", "subtype_present", "subtype_observed_at",
            ), body_rows)
        if opportunity_rows:
            _copy_rows(conn, "v3_derived.economy_opportunity", (
                "derived_generation_id", "system_id64", "body_pk", "economy_ordinal",
                "native", "modifier", "local_score", "specialisation_quality",
                "specialisation_min", "specialisation_max", "completeness", "confidence",
            ), opportunity_rows)
    conn.execute(
        """INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,
               manifest_sha256,expected_rows)
             VALUES (%s,'system_search','measurement-search','{}'::jsonb,%s,%s)""",
        (generation_id, b"\1" * 32, rows),
    )
    conn.execute(
        """UPDATE v3_meta.derived_product
              SET lifecycle_state='READY',validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validation_sha256=%s,validated_at=now()
            WHERE derived_generation_id=%s AND product_code='system_search'""",
        (b"\2" * 32, generation_id),
    )
    return generation_key


def _final_index_sizes(conn: psycopg.Connection) -> dict[str, int]:
    rows = conn.execute(
        """SELECT i.relname,pg_relation_size(i.oid)
             FROM pg_index x
             JOIN pg_class i ON i.oid=x.indexrelid
             JOIN pg_class t ON t.oid=x.indrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='v3_derived' AND t.relname='system_archetype'
            ORDER BY i.relname"""
    ).fetchall()
    sizes = {str(name): int(size) for name, size in rows}
    missing = sorted(FINAL_INDEX_NAMES - sizes.keys())
    unexpected = sorted(sizes.keys() - FINAL_INDEX_NAMES)
    if missing or unexpected or len(sizes) != 26:
        raise ValueError(
            "final system_archetype relation must have exactly the 26 designed indexes; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return sizes


def _measure_final_migration(
    conn: psycopg.Connection,
    *,
    migration_path: Path,
    rows: int,
    fractions: dict[str, dict[str, float]],
    fractions_sha256: str,
    distribution_source: str,
    f2d_operator_code_sha256: str,
) -> dict[str, object]:
    migration_bytes = migration_path.read_bytes()
    applied_migration_sha256 = hashlib.sha256(migration_bytes).hexdigest()
    try:
        migration_text = migration_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("--migration-sql must be UTF-8 SQL") from exc
    for name in MIGRATION_PREREQUISITES:
        conn.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
    conn.execute(migration_text)
    # This check occurs both index-first and after the incremental builder fill.
    _final_index_sizes(conn)
    generation_key = _seed_measurement_source(conn, rows, fractions)
    generation, state, manifest_sha = archetype_builder.register_product(conn, generation_key)
    if state != "BUILDING":
        raise ValueError("measurement Archetype product did not register BUILDING")
    while True:
        built = archetype_builder.build_available(
            conn, generation, manifest_sha, max_chunks=1
        )
        if not built["chunks_written"]:
            break
    conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='VALIDATING',source_receipt='{}'::jsonb,
                  content_sha256=%s
            WHERE derived_generation_id=%s""",
        (b"\3" * 32, generation.identifier),
    )
    conn.execute(
        """UPDATE v3_meta.derived_generation
              SET lifecycle_state='READY',validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validated_at=now()
            WHERE derived_generation_id=%s""",
        (generation.identifier,),
    )
    receipt = archetype_builder.validate_product(conn, generation, manifest_sha)
    if receipt.get("status") != "VERIFIED":
        raise ValueError("part-1 Archetype builder validation did not verify the measurement fill")
    conn.execute("VACUUM ANALYZE v3_derived.system_archetype")
    index_sizes = _final_index_sizes(conn)
    row_count, heap_bytes, text_bytes_stored = conn.execute(
        """SELECT count(*),pg_table_size('v3_derived.system_archetype'::regclass),
                  COALESCE(SUM(
                      octet_length(primary_archetype)
                      + COALESCE(octet_length(secondary_archetype),0)
                  ),0)
             FROM v3_derived.system_archetype"""
    ).fetchone()
    row_count = int(row_count)
    heap_bytes = int(heap_bytes)
    text_bytes_stored = int(text_bytes_stored)
    if row_count != rows:
        raise ValueError(f"builder wrote {row_count} rows, expected {rows}")
    counts = conn.execute(
        "SELECT "
        + ",".join(
            f"count(*) FILTER (WHERE {key}_score >= {floor})"
            for key in ARCHETYPE_KEYS
            for floor in (60, 76, 88)
        )
        + " FROM v3_derived.system_archetype"
    ).fetchone()
    tier_entries = sum(int(value) for value in counts)
    if tier_entries <= 0:
        raise ValueError("synthetic distribution produced no tier-index entries")
    seeded_fractions: dict[str, dict[str, float]] = {}
    count_index = 0
    for key in ARCHETYPE_KEYS:
        seeded_fractions[key] = {}
        for floor in (60, 76, 88):
            seeded_fractions[key][str(floor)] = int(counts[count_index]) / row_count
            count_index += 1
    primary_bytes = index_sizes["system_archetype_pkey"]
    weighted_bytes = index_sizes["system_archetype_summary_weighted"]
    tier_bytes = sum(index_sizes[name] for name in TIER_INDEX_NAMES)
    costs = per_row_costs(
        heap_bytes=heap_bytes,
        primary_key_bytes=primary_bytes,
        weighted_index_bytes=weighted_bytes,
        tier_index_bytes=tier_bytes,
        rows=row_count,
        tier_entries=tier_entries,
    )
    return {
        "capacity_gate_eligible": capacity_gate_eligible(
            final_migration=True, distribution_source=distribution_source
        ),
        "score_distribution_source": distribution_source,
        "migration_011_path": str(migration_path),
        "migration_011_sha256": applied_migration_sha256,
        "fractions_canonical": fractions,
        "fractions_sha256": fractions_sha256,
        "seeded_fractions": seeded_fractions,
        "sigma_all": tier_entries / row_count,
        "rows": row_count,
        "row_count": row_count,
        "heap_bytes": heap_bytes,
        "text_bytes_stored": text_bytes_stored,
        "per_index_bytes": index_sizes,
        "tier_index_bytes": tier_bytes,
        "archetype_fixed_bytes_per_row": archetype_fixed_cost(
            heap_bytes=heap_bytes,
            text_bytes_stored=text_bytes_stored,
            primary_key_bytes=primary_bytes,
            weighted_index_bytes=weighted_bytes,
            rows=row_count,
        ),
        "f2d_operator_code_sha256": f2d_operator_code_sha256,
        **costs,
    }


def _run_final_migration_mode(
    conninfo: dict[str, str],
    *,
    migration_path: Path,
    rows: int,
    fractions: dict[str, dict[str, float]],
    fractions_sha256: str,
    distribution_source: str,
    f2d_operator_code_sha256: str,
) -> dict[str, object]:
    database = MEASUREMENT_DATABASE_PREFIX + uuid4().hex
    with psycopg.connect(**conninfo, autocommit=True) as admin:
        assert_disposable_server(admin)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            measured_conninfo = {**conninfo, "dbname": database}
            with psycopg.connect(**measured_conninfo, autocommit=True) as conn:
                address, client, major = conn.execute(
                    "SELECT host(inet_server_addr()),host(inet_client_addr()),"
                    "current_setting('server_version_num')::int"
                ).fetchone()
                if (
                    not server_address_is_disposable(address, client, attested_server_address())
                    or int(major) // 10000 != 18
                ):
                    raise ValueError(
                        "temporary measurement database is not loopback or the attested "
                        "disposable container on PostgreSQL 18"
                    )
                result = _measure_final_migration(
                    conn,
                    migration_path=migration_path,
                    rows=rows,
                    fractions=fractions,
                    fractions_sha256=fractions_sha256,
                    distribution_source=distribution_source,
                    f2d_operator_code_sha256=f2d_operator_code_sha256,
                )
                result["server_version_num"] = int(major)
                return result
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )


def _emit_json(value: dict[str, object], output_path: Path | None) -> None:
    """Write JSON atomically when requested, retaining the historical stdout form."""
    if output_path is None:
        json.dump(value, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return
    if output_path.is_symlink():
        raise ValueError("--output must not be a symlink")
    temporary = output_path.with_name(f".{output_path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(f2d_evidence.canonical_json(value))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--rows", type=int, default=200_000, help="synthetic rows to build (default 200000)")
    parser.add_argument(
        "--migration-sql",
        help=(
            "Path to the final 011 migration. Applies its prerequisites in a new "
            "temporary disposable database, then fills the real wide relation "
            "through the canonical Archetype builder."
        ),
    )
    parser.add_argument(
        "--fractions-json",
        help=(
            "Path to a JSON object {archetype_key: {'60': f, '76': f, '88': f}} of REAL per-key "
            "tier fractions (from the governed calibration probe's histogram). When given, the "
            "v4 layout's scores are drawn to match those fractions instead of the declared "
            "synthetic bell distribution, and the receipt records the source as 'measured-histogram'."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="atomically write the receipt here instead of printing it",
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
        try:
            fractions_canonical, fractions_sha256, sigma_all = normalize_fractions(fractions)
        except ValueError as exc:
            sys.exit(str(exc))
        fractions = fractions_canonical
    if args.migration_sql:
        migration_path = Path(args.migration_sql)
        if not migration_path.is_file():
            sys.exit("--migration-sql must name a readable SQL file")
        if fractions is None:
            fractions, fractions_sha256, sigma_all = normalize_fractions(BUILTIN_FRACTIONS)
            distribution_source = "synthetic-builtin"
        else:
            distribution_source = "measured-histogram"
        try:
            operator_identity = compute_operator_code_sha256(ROOT)
            final_receipt = _run_final_migration_mode(
                _disposable_conninfo_from_env(),
                migration_path=migration_path,
                rows=args.rows,
                fractions=fractions,
                fractions_sha256=fractions_sha256,
                distribution_source=distribution_source,
                f2d_operator_code_sha256=operator_identity,
            )
            final_receipt = f2d_evidence.seal(final_receipt)
            _emit_json(final_receipt, args.output)
        except (OSError, OperatorIdentityError, psycopg.Error, ValueError) as exc:
            sys.exit(str(exc))
        return
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
    try:
        _emit_json(out, args.output)
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
