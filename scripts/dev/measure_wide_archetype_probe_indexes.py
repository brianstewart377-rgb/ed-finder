"""Compare score-index layouts for the Finder slice 1c bounded probe on a DISPOSABLE PostgreSQL 18.

Builds one wide-row-shaped scratch table of N rows with a bell-shaped integer score
(mean ≈ 45, sd ≈ 15) and, for each index layout, runs the bounded probe
``WHERE score >= 60 ORDER BY score DESC, system_id64 LIMIT 10001`` under
``EXPLAIN (ANALYZE, BUFFERS)``, reporting the plan shape, rows read, planning and
execution time, and index bytes per row. The layouts are those discussed in the F2d
design (section 3.3): deduplicated ``(gen, score DESC)``, full
``(gen, score DESC, system_id64)``, and the partial
``(gen, score DESC, system_id64) WHERE score >= 60``.

Safety: identical to ``measure_wide_archetype_footprint.py`` — the DSN comes only from
``EDFINDER_DISPOSABLE_DSN``, must name the loopback ``ratings_v4_validation`` service
with no libpq overrides, and the server must be PostgreSQL 18; writes go only to the
``scratch`` schema.

Usage::

    EDFINDER_DISPOSABLE_DSN=postgresql://user:pass@127.0.0.1:55418/ratings_v4_validation \\
        python scripts/dev/measure_wide_archetype_probe_indexes.py --rows 1000000 > probe.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_wide_archetype_footprint import (  # noqa: E402
    GENERATION_ID,
    _disposable_conninfo_from_env,
    assert_disposable_server,
)

LAYOUTS = {
    "dedup_score_only": "CREATE INDEX probe_ix ON scratch.probe (gen, score DESC)",
    "full_score_sysid": "CREATE INDEX probe_ix ON scratch.probe (gen, score DESC, system_id64)",
    "partial_ge60_score_sysid": (
        "CREATE INDEX probe_ix ON scratch.probe (gen, score DESC, system_id64) WHERE score >= 60"
    ),
}
PROBE = (
    "SELECT system_id64, score FROM scratch.probe WHERE gen = %s AND score >= 60 "
    "ORDER BY score DESC, system_id64 LIMIT 10001"
)


def _plan_nodes(plan: dict, acc: list[str]) -> list[str]:
    label = plan["Node Type"]
    if "Index Name" in plan:
        label += f" {plan['Index Name']}"
    acc.append(f"{label} rows={plan.get('Actual Rows')}")
    for child in plan.get("Plans", []):
        _plan_nodes(child, acc)
    return acc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--repeats", type=int, default=4, help="runs per layout; first is cold-ish, median of the rest is warm")
    args = parser.parse_args()
    if args.rows < 20_000 or args.rows > 5_000_000:
        sys.exit("--rows must be between 20000 and 5000000")
    if args.repeats < 2 or args.repeats > 20:
        sys.exit("--repeats must be between 2 and 20")
    out: dict[str, object] = {"rows": args.rows, "probe_sql": PROBE}
    with psycopg.connect(**_disposable_conninfo_from_env(), autocommit=True) as conn:
        try:
            out["server_version_num"] = assert_disposable_server(conn)
        except ValueError as exc:
            sys.exit(str(exc))
        conn.execute("CREATE SCHEMA IF NOT EXISTS scratch")
        conn.execute("DROP TABLE IF EXISTS scratch.probe")
        uniforms = "+".join(["random()"] * 12)
        conn.execute(
            "CREATE TABLE scratch.probe AS SELECT %s::uuid AS gen, (g.n::bigint * 7919) AS system_id64, "
            f"LEAST(100, GREATEST(0, round(45 + 15 * (({uniforms}) - 6))))::smallint AS score "
            "FROM generate_series(1, %s) AS g(n)",
            (GENERATION_ID, args.rows),
        )
        conn.execute("ALTER TABLE scratch.probe ADD PRIMARY KEY (gen, system_id64)")
        ge88, ge76, ge60, top, top_rows = conn.execute(
            "SELECT count(*) FILTER (WHERE score >= 88), count(*) FILTER (WHERE score >= 76), "
            "count(*) FILTER (WHERE score >= 60), max(score), "
            "(SELECT count(*) FROM scratch.probe p WHERE p.score = (SELECT max(score) FROM scratch.probe)) "
            "FROM scratch.probe"
        ).fetchone()
        out["distribution"] = {"ge88": ge88, "ge76": ge76, "ge60": ge60, "max_score": top, "rows_at_max_score": top_rows,
                               "fraction_ge60": round(ge60 / args.rows, 4)}
        for name, ddl in LAYOUTS.items():
            conn.execute("DROP INDEX IF EXISTS scratch.probe_ix")
            conn.execute(ddl)
            conn.execute("VACUUM ANALYZE scratch.probe")
            size = conn.execute("SELECT pg_relation_size('scratch.probe_ix')").fetchone()[0]
            timings = []
            plan = None
            for _ in range(args.repeats):
                (explained,) = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + PROBE, (GENERATION_ID,)).fetchone()
                root = explained[0]
                timings.append((root["Planning Time"], root["Execution Time"]))
                plan = root["Plan"]
            warm = sorted(p + e for p, e in timings[1:])
            out[name] = {
                "index_bytes": size,
                "index_bytes_per_row": round(size / args.rows, 1),
                "plan_nodes": _plan_nodes(plan, []),
                "first_run_ms": {"planning": round(timings[0][0], 2), "execution": round(timings[0][1], 2)},
                "warm_median_wall_ms": round(warm[len(warm) // 2], 2),
            }
        conn.execute("DROP TABLE scratch.probe")
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
