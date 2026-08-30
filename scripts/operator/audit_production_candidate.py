#!/usr/bin/env python3
"""Fail-closed, read-only readiness audit for an existing production candidate DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "sql" / "migration-manifest.txt"
TARGET_RATING_VERSION = "3.4"

# These are populated by application features or live/user input. Their emptiness is
# not evidence that the one-time canonical warehouse build is incomplete.
INVENTORY_ONLY_TABLES = (
    "journal_events",
    "body_scan_facts",
    "body_slot_predictions",
    "buildability_analysis",
    "colony_simulations",
    "observed_facts",
    "journal_import_staging",
    "evidence_records",
    "derived_features",
    "rule_proposals",
    "rule_decisions",
    "exploration_facts",
    "exploration_visits",
    "exploration_expedition_routes",
    "exploration_body_completeness",
    "exobiology_sales",
    "exobiology_organisms",
    "codex_observations",
    "powerplay_observations",
    "commander_powerplay_events",
    "commander_powerplay_state",
    "powerplay_cycles",
    "routes",
    "route_events",
    "app_users",
    "web_sessions",
    "oauth_login_states",
)


@dataclass(frozen=True)
class Migration:
    filename: str
    mode: str
    checksum: str


def load_manifest(path: Path) -> list[Migration]:
    migrations: list[Migration] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        filename, separator, mode = line.partition("|")
        mode = mode if separator else "auto"
        if mode not in {"auto", "manual"} or not filename.endswith(".sql"):
            raise ValueError(f"invalid migration manifest entry: {raw!r}")
        migration_path = path.parent / filename
        if not migration_path.is_file():
            raise ValueError(f"manifested migration is missing: {filename}")
        checksum = hashlib.sha256(migration_path.read_bytes()).hexdigest()
        migrations.append(Migration(filename, mode, checksum))
    if not migrations:
        raise ValueError("migration manifest is empty")
    return migrations


class Reader:
    def __init__(self, connection: Any):
        self.connection = connection

    def one(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("audit query unexpectedly returned no row")
        return row[0]

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

    def relation_kind(self, name: str) -> str | None:
        return self.one(
            "SELECT (SELECT c.relkind::text FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relname=%s)",
            (name,),
        )

    def count(self, name: str) -> int:
        # All names passed here are constants owned by this file.
        return int(self.one(f'SELECT COUNT(*)::bigint FROM public."{name}"'))


def _relation(reader: Reader, name: str, *, classification: str) -> dict[str, Any]:
    kind = reader.relation_kind(name)
    if kind is None:
        return {"name": name, "classification": classification, "present": False, "row_count": None}
    result = {"name": name, "classification": classification, "present": True, "row_count": reader.count(name)}
    if kind == "m":
        result["populated"] = bool(
            reader.one("SELECT relispopulated FROM pg_catalog.pg_class WHERE oid=to_regclass('public.' || %s)", (name,))
        )
    return result


def _metric(reader: Reader, name: str, query: str, dependencies: tuple[str, ...], *, required: bool = True) -> dict[str, Any]:
    missing = [relation for relation in dependencies if reader.relation_kind(relation) is None]
    if missing:
        return {"name": name, "classification": "required_build" if required else "optional", "present": False,
                "missing_relations": missing}
    values = reader.rows(query)
    # Metric SQL always returns key/value pairs; avoiding cursor metadata keeps fakes simple.
    data = {str(key): int(value) for key, value in values}
    return {"name": name, "classification": "required_build" if required else "optional", "present": True, **data}


def migration_audit(reader: Reader, migrations: list[Migration]) -> dict[str, Any]:
    if reader.relation_kind("schema_migrations") is None:
        return {"ledger_present": False, "pending_auto": [m.filename for m in migrations if m.mode == "auto"],
                "pending_manual": [m.filename for m in migrations if m.mode == "manual"], "checksum_mismatches": [],
                "unexpected_ledger_entries": []}
    ledger = {name: checksum for name, checksum in reader.rows(
        "SELECT filename, checksum_sha256 FROM public.schema_migrations ORDER BY filename"
    )}
    expected = {m.filename: m for m in migrations}
    return {
        "ledger_present": True,
        "pending_auto": [m.filename for m in migrations if m.mode == "auto" and m.filename not in ledger],
        "pending_manual": [m.filename for m in migrations if m.mode == "manual" and m.filename not in ledger],
        "checksum_mismatches": [m.filename for m in migrations if m.filename in ledger and ledger[m.filename] != m.checksum],
        "unexpected_ledger_entries": sorted(set(ledger) - set(expected)),
        "applied_count": len(ledger),
        "manifest_count": len(migrations),
    }


REQUIRED_METRICS = (
    ("grid", ("systems",), "SELECT 'eligible'::text, COUNT(*)::bigint FROM systems WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL UNION ALL SELECT 'missing', COUNT(*) FROM systems WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL AND (grid_cell_id IS NULL OR macro_grid_id IS NULL)"),
    ("ratings", ("systems", "ratings"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM systems WHERE has_body_data UNION ALL SELECT 'rows', COUNT(*) FROM ratings r JOIN systems s ON s.id64=r.system_id64 WHERE s.has_body_data UNION ALL SELECT 'wrong_version', COUNT(*) FROM ratings r JOIN systems s ON s.id64=r.system_id64 WHERE s.has_body_data AND r.rating_version IS DISTINCT FROM '3.4' UNION ALL SELECT 'dirty', COUNT(*) FROM systems WHERE has_body_data AND rating_dirty"),
    ("topology", ("systems", "ratings", "system_slot_topology"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM ratings r JOIN systems s ON s.id64=r.system_id64 WHERE s.has_body_data AND r.rating_version='3.4' UNION ALL SELECT 'rows', COUNT(*) FROM system_slot_topology"),
    ("economy_pair_synergy", ("systems", "ratings", "system_slot_topology", "economy_pair_synergy"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM ratings r JOIN systems s ON s.id64=r.system_id64 WHERE s.has_body_data AND r.rating_version='3.4' UNION ALL SELECT 'source_built', COUNT(*) FROM system_slot_topology UNION ALL SELECT 'rows', COUNT(*) FROM economy_pair_synergy UNION ALL SELECT 'covered', COUNT(DISTINCT system_id64) FROM economy_pair_synergy"),
    ("archetypes", ("systems", "ratings", "system_archetype_scores", "system_archetype_traits"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM ratings r JOIN systems s ON s.id64=r.system_id64 WHERE s.has_body_data AND r.rating_version='3.4' UNION ALL SELECT 'scores', COUNT(*) FROM system_archetype_scores UNION ALL SELECT 'traits', COUNT(*) FROM system_archetype_traits UNION ALL SELECT 'dirty', COUNT(*) FROM system_archetype_scores WHERE dirty"),
    ("regional_analysis", ("systems", "system_regional_analysis"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM systems WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL UNION ALL SELECT 'rows', COUNT(*) FROM system_regional_analysis"),
    ("station_body_links", ("stations", "station_body_links"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM stations WHERE body_name IS NOT NULL AND btrim(body_name) <> '' UNION ALL SELECT 'covered', COUNT(DISTINCT station_id) FROM station_body_links WHERE association_status='confirmed' AND body_id IS NOT NULL"),
    ("clusters", ("systems", "cluster_summary"), "SELECT 'eligible'::text, COUNT(*)::bigint FROM systems WHERE has_body_data UNION ALL SELECT 'rows', COUNT(*) FROM cluster_summary UNION ALL SELECT 'dirty_rows', COUNT(*) FROM cluster_summary WHERE dirty UNION ALL SELECT 'system_dirty', COUNT(*) FROM systems WHERE has_body_data AND cluster_dirty"),
)


def blockers_for(report: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if report["server"]["version_num"] // 10000 != 18:
        blockers.append("PostgreSQL server major version is not 18")
    migrations = report["migrations"]
    if not migrations["ledger_present"]:
        blockers.append("migration ledger is missing")
    for key in ("pending_auto", "pending_manual", "checksum_mismatches", "unexpected_ledger_entries"):
        if migrations[key]:
            blockers.append(f"migration {key.replace('_', ' ')}: {len(migrations[key])}")
    for table in report["base_tables"]:
        if not table["present"]:
            blockers.append(f"required base table missing: {table['name']}")
    for metric in report["required_builds"]:
        if not metric["present"]:
            blockers.append(f"required build missing or unreadable: {metric['name']}")
            continue
        if metric["name"] == "grid" and metric["missing"]:
            blockers.append(f"grid assignments missing: {metric['missing']}")
        elif metric["name"] == "ratings" and (metric["rows"] != metric["eligible"] or metric["wrong_version"] or metric["dirty"]):
            blockers.append("ratings v3.4 build incomplete")
        elif metric["name"] == "archetypes" and (metric["scores"] != metric["eligible"] or metric["traits"] != metric["eligible"] or metric["dirty"]):
            blockers.append("archetype build incomplete")
        elif metric["name"] == "clusters" and (metric["dirty_rows"] or metric["system_dirty"]):
            blockers.append("cluster build has dirty backlog")
        elif metric["name"] == "economy_pair_synergy":
            if metric["source_built"] < metric["eligible"]:
                blockers.append("economy_pair_synergy source build incomplete")
            if metric["covered"] < metric["eligible"]:
                blockers.append("economy_pair_synergy coverage incomplete")
        elif metric["name"] not in {"grid", "ratings", "archetypes", "clusters"}:
            built = metric.get("rows", metric.get("covered", 0))
            if built < metric["eligible"]:
                blockers.append(f"{metric['name']} coverage incomplete")
    for view in report["materialized_views"]:
        if not view["present"] or not view.get("populated", False):
            blockers.append(f"materialized view unavailable: {view['name']}")
    return blockers


def run_audit(connection: Any, manifest: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    connection.set_session(readonly=True, autocommit=False)
    reader = Reader(connection)
    if reader.one("SHOW transaction_read_only") != "on":
        raise RuntimeError("database did not honor read-only transaction mode")
    report: dict[str, Any] = {
        "audit_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "server": {"version": reader.one("SHOW server_version"), "version_num": int(reader.one("SHOW server_version_num")),
                   "database_size_bytes": int(reader.one("SELECT pg_database_size(current_database())"))},
        "migrations": migration_audit(reader, load_manifest(manifest)),
        "base_tables": [_relation(reader, name, classification="required_base") for name in ("systems", "bodies", "stations", "body_rings")],
        "base_coverage": [
            _metric(reader, "body_system_coverage", "SELECT 'systems_with_bodies'::text, COUNT(DISTINCT system_id64)::bigint FROM bodies UNION ALL SELECT 'systems_flagged', COUNT(*) FROM systems WHERE has_body_data", ("systems", "bodies"), required=False),
            _metric(reader, "station_system_coverage", "SELECT 'systems_with_stations'::text, COUNT(DISTINCT system_id64)::bigint FROM stations UNION ALL SELECT 'station_rows', COUNT(*) FROM stations", ("stations",), required=False),
            _metric(reader, "ring_system_coverage", "SELECT 'systems_with_rings'::text, COUNT(DISTINCT system_id64)::bigint FROM body_rings UNION ALL SELECT 'ring_rows', COUNT(*) FROM body_rings", ("body_rings",), required=False),
        ],
        "required_builds": [_metric(reader, name, query, dependencies) for name, dependencies, query in REQUIRED_METRICS],
        "materialized_views": [_relation(reader, name, classification="required_build") for name in ("mv_map_regions", "mv_map_heatmap_200ly", "mv_map_heatmap_500ly", "mv_map_heatmap_1000ly", "mv_map_timeline_month", "mv_archetype_rankings")],
        "runtime_feature_tables": [_relation(reader, name, classification="inventory_only") for name in INVENTORY_ONLY_TABLES],
    }
    report["blockers"] = blockers_for(report)
    report["ready"] = not report["blockers"]
    connection.rollback()
    return report


def render_human(report: dict[str, Any]) -> str:
    state = "READY" if report["ready"] else "NOT READY"
    lines = [f"Production candidate: {state}", f"PostgreSQL {report['server']['version']} ({report['server']['database_size_bytes']} bytes)",
             f"Read-only audit: {report['read_only']}"]
    migration = report["migrations"]
    lines.append(f"Migrations: pending auto={len(migration['pending_auto'])}, manual={len(migration['pending_manual'])}, checksum mismatches={len(migration['checksum_mismatches'])}")
    for relation in report["base_tables"] + report["materialized_views"]:
        lines.append(f"{relation['classification']} {relation['name']}: " + (f"{relation['row_count']} rows" if relation["present"] else "MISSING"))
    for metric in report["required_builds"]:
        values = ", ".join(f"{k}={v}" for k, v in metric.items() if k not in {"name", "classification", "present"})
        lines.append(f"required_build {metric['name']}: {values or 'MISSING'}")
    for metric in report.get("base_coverage", []):
        values = ", ".join(f"{k}={v}" for k, v in metric.items() if k not in {"name", "classification", "present"})
        lines.append(f"base_coverage {metric['name']}: {values or 'MISSING'}")
    for item in report["runtime_feature_tables"]:
        lines.append(f"inventory_only {item['name']}: " + (f"present, {item['row_count']} rows" if item["present"] else "missing (reported, not a population blocker)"))
    lines.extend(f"BLOCKER: {blocker}" for blocker in report["blockers"])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="Explicit PostgreSQL DSN (or DATABASE_URL).")
    parser.add_argument("--compose", action="store_true", help="Resolve DATA_INVARIANTS_DATABASE_URL from docker compose config without starting services.")
    parser.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.yml")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", help="Emit JSON only, suitable for a durable receipt.")
    parser.add_argument("--json-output", type=Path, help="Also write the JSON receipt to this path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.compose and args.database_url:
        print("ERROR: choose either explicit DATABASE_URL or --compose", file=sys.stderr)
        return 2
    if args.compose:
        try:
            completed = subprocess.run(
                ["docker", "compose", "-f", str(args.compose_file), "config", "--format", "json"],
                check=True, capture_output=True, text=True,
            )
            config = json.loads(completed.stdout)
            args.database_url = config["services"]["maintenance"]["environment"]["DATA_INVARIANTS_DATABASE_URL"]
        except Exception:
            args.database_url = ""
    if not args.database_url:
        print("ERROR: DATABASE_URL or --database-url is required; no database was contacted", file=sys.stderr)
        return 2
    try:
        connection = psycopg2.connect(args.database_url, connect_timeout=10, application_name="edfinder-production-candidate-audit")
        try:
            report = run_audit(connection, args.manifest)
        finally:
            connection.close()
        payload = json.dumps(report, indent=2, sort_keys=True)
        if args.json_output:
            args.json_output.write_text(payload + "\n", encoding="utf-8")
        print(payload if args.json else render_human(report))
        return 0 if report["ready"] else 1
    except Exception as exc:  # fail closed; intentionally never echo DSNs or exception text
        failure = {"audit_version": 1, "ready": False, "read_only": True,
                   "error": exc.__class__.__name__, "blockers": ["audit execution failed"]}
        payload = json.dumps(failure, indent=2, sort_keys=True)
        if args.json_output:
            try:
                args.json_output.write_text(payload + "\n", encoding="utf-8")
            except OSError:
                pass
        if args.json:
            print(payload)
        print(f"ERROR: production-candidate audit failed ({exc.__class__.__name__}); no credentials shown", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
