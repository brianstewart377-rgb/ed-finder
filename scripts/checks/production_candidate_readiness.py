#!/usr/bin/env python3
"""Read-only PostgreSQL 18 production-candidate readiness audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "sql" / "migration-manifest.txt"
TARGET_RATING_VERSION = "3.4"

FULL_BUILD_DATASETS = (
    "grid",
    "ratings_v3_4",
    "topology",
    "economy_pair_synergy",
    "archetypes",
    "regional_analysis",
    "station_body_links",
    "clusters",
    "materialized_views",
)

RUNTIME_TABLES = (
    "journal_events", "body_scan_facts", "journal_import_staging",
    "evidence_records", "derived_features", "observed_facts",
    "exploration_facts", "exploration_visits", "exploration_expedition_routes",
    "powerplay_observations", "commander_powerplay_events", "routes", "route_events",
    "app_users", "web_sessions",
)


class AuditError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--receipt-file", required=True, type=Path)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, type=Path)
    parser.add_argument("--full", action="store_true", help="Run exact, potentially expensive scans.")
    parser.add_argument("--statement-timeout", default="30s")
    return parser.parse_args(argv)


def validate_inputs(args: argparse.Namespace) -> None:
    if not args.database_url:
        raise AuditError("missing --database-url or DATABASE_URL")
    if any(ch in args.database_url for ch in "\r\n\0"):
        raise AuditError("database URL contains unsafe control characters")
    try:
        parsed = urlsplit(args.database_url)
    except ValueError as exc:
        raise AuditError("invalid PostgreSQL database URL") from exc
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise AuditError("database URL must be an explicit postgres/postgresql URL with host and database")
    if not re.fullmatch(r"[1-9][0-9]*(ms|s|min|h)", args.statement_timeout):
        raise AuditError("statement timeout must be a positive PostgreSQL duration")
    if not args.manifest.is_file():
        raise AuditError(f"migration manifest not found: {args.manifest}")
    if args.receipt_file.exists() and not args.receipt_file.is_file():
        raise AuditError("receipt path exists and is not a regular file")


def redacted_target(database_url: str) -> dict[str, object]:
    parsed = urlsplit(database_url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "database": parsed.path.lstrip("/"),
        "credentials_redacted": True,
    }


def parse_manifest(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) > 2 or not parts[0] or (len(parts) == 2 and parts[1] not in {"auto", "manual"}):
            raise AuditError(f"invalid migration manifest entry at line {line_number}")
        filename, mode = parts[0], parts[1] if len(parts) == 2 else "auto"
        if filename in seen or Path(filename).name != filename:
            raise AuditError(f"unsafe or duplicate migration manifest entry at line {line_number}")
        migration = path.parent / filename
        if not migration.is_file():
            raise AuditError(f"manifest migration file missing: {filename}")
        entries.append({"filename": filename, "mode": mode, "checksum_sha256": hashlib.sha256(migration.read_bytes()).hexdigest()})
        seen.add(filename)
    if not entries:
        raise AuditError("migration manifest contains no entries")
    return entries


def compare_migrations(manifest: list[dict[str, str]], ledger: list[tuple[str, str, str]]) -> dict[str, object]:
    if len({row[0] for row in ledger}) != len(ledger):
        raise AuditError("migration ledger returned duplicate filenames")
    recorded = {filename: {"checksum_sha256": checksum, "apply_mode": mode} for filename, checksum, mode in ledger}
    pending_auto, pending_manual, mismatches = [], [], []
    for entry in manifest:
        actual = recorded.get(entry["filename"])
        if actual is None:
            (pending_manual if entry["mode"] == "manual" else pending_auto).append(entry["filename"])
        elif actual["checksum_sha256"] != entry["checksum_sha256"]:
            mismatches.append({"filename": entry["filename"], "expected": entry["checksum_sha256"], "recorded": actual["checksum_sha256"]})
    extras = sorted(set(recorded) - {entry["filename"] for entry in manifest})
    return {"status": "pass" if not pending_auto and not pending_manual and not mismatches and not extras else "fail", "pending_automatic": pending_auto, "pending_manual": pending_manual, "checksum_mismatches": mismatches, "ledger_only_entries": extras}


def scalar(cur, sql: str, params: tuple[object, ...] = ()) -> object:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def relation_exists(cur, name: str) -> bool:
    return bool(scalar(cur, "SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",)))


def estimated_rows(cur, name: str) -> int:
    return int(scalar(cur, "SELECT GREATEST(c.reltuples::bigint, 0) FROM pg_class c WHERE c.oid = to_regclass(%s)", (f"public.{name}",)))


def table_metric(cur, name: str, full: bool) -> dict[str, object]:
    if not relation_exists(cur, name):
        return {"presence": "missing", "row_count": None, "count_method": "unavailable"}
    if full:
        return {"presence": "present", "row_count": int(scalar(cur, f'SELECT COUNT(*) FROM "{name}"')), "count_method": "exact"}
    return {"presence": "present", "row_count": estimated_rows(cur, name), "count_method": "catalog_estimate"}


def optional_exact(cur, name: str, sql: str) -> dict[str, object]:
    if not relation_exists(cur, name):
        return {"presence": "missing", "value": None}
    return {"presence": "present", "value": int(scalar(cur, sql))}


def collect(cur, full: bool) -> dict[str, object]:
    base = {name: table_metric(cur, name, full) for name in ("systems", "bodies", "stations", "body_rings")}
    # Backlog predicates match the builders/invariant contracts. Their partial indexes
    # make the safe profile bounded; --full additionally makes base counts exact.
    rating_coverage = (
        optional_exact(cur, "ratings", "SELECT COUNT(*) FROM systems s LEFT JOIN ratings r ON r.system_id64=s.id64 WHERE s.has_body_data=TRUE AND (r.system_id64 IS NULL OR r.rating_version IS DISTINCT FROM '3.4')")
        if full else {"presence": "present" if relation_exists(cur, "ratings") else "missing", "value": None, "count_method": "skipped_in_safe_profile"}
    )
    def full_backlog(name: str, sql: str) -> dict[str, object]:
        if not relation_exists(cur, name):
            return {"presence": "missing", "value": None, "count_method": "unavailable"}
        if not full:
            return {"presence": "present", "value": None, "count_method": "skipped_in_safe_profile"}
        return {"presence": "present", "value": int(scalar(cur, sql)), "count_method": "exact"}

    derived: dict[str, object] = {
        "grid": {"classification": "full_build_required", "grid_cell_id_backlog": int(scalar(cur, "SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")), "macro_grid_id_backlog": int(scalar(cur, "SELECT COUNT(*) FROM systems WHERE macro_grid_id IS NULL"))},
        "ratings_v3_4": {"classification": "full_build_required", **rating_coverage, "rating_dirty_backlog": int(scalar(cur, "SELECT COUNT(*) FROM systems WHERE rating_dirty=TRUE"))},
        "topology": {"classification": "full_build_required", **table_metric(cur, "system_slot_topology", full), "missing_for_ratings": full_backlog("system_slot_topology", "SELECT COUNT(*) FROM ratings r LEFT JOIN system_slot_topology t ON t.system_id64=r.system_id64 WHERE t.system_id64 IS NULL")},
        "economy_pair_synergy": {"classification": "full_build_required", **table_metric(cur, "economy_pair_synergy", full), "distinct_systems": (int(scalar(cur, "SELECT COUNT(DISTINCT system_id64) FROM economy_pair_synergy")) if full and relation_exists(cur, "economy_pair_synergy") else None), "constants": table_metric(cur, "pair_synergy_constants", full)},
        "archetypes": {"classification": "full_build_required", "scores": table_metric(cur, "system_archetype_scores", full), "traits": table_metric(cur, "system_archetype_traits", full), **optional_exact(cur, "system_archetype_scores", "SELECT COUNT(*) FROM system_archetype_scores WHERE dirty=TRUE"), "missing_scores_for_ratings": full_backlog("system_archetype_scores", "SELECT COUNT(*) FROM ratings r LEFT JOIN system_archetype_scores a ON a.system_id64=r.system_id64 WHERE a.system_id64 IS NULL"), "missing_traits_for_scores": full_backlog("system_archetype_traits", "SELECT COUNT(*) FROM system_archetype_scores a LEFT JOIN system_archetype_traits t ON t.system_id64=a.system_id64 WHERE t.system_id64 IS NULL")},
        "regional_analysis": {"classification": "full_build_required", **table_metric(cur, "system_regional_analysis", full), "missing_for_positioned_systems": full_backlog("system_regional_analysis", "SELECT COUNT(*) FROM systems s LEFT JOIN system_regional_analysis r ON r.system_id64=s.id64 WHERE s.x IS NOT NULL AND s.y IS NOT NULL AND s.z IS NOT NULL AND r.system_id64 IS NULL")},
        "station_body_links": {"classification": "full_build_required", **table_metric(cur, "station_body_links", full), "required_backfill": full_backlog("station_body_links", "SELECT COUNT(*) FROM stations st LEFT JOIN station_body_links l ON l.station_id=st.id WHERE st.body_name IS NOT NULL AND l.station_id IS NULL")},
        "clusters": {"classification": "full_build_required", **table_metric(cur, "cluster_summary", full), "cluster_dirty_backlog": int(scalar(cur, "SELECT COUNT(*) FROM systems WHERE cluster_dirty=TRUE")), "summary_dirty_backlog": optional_exact(cur, "cluster_summary", "SELECT COUNT(*) FROM cluster_summary WHERE dirty=TRUE")},
    }
    views = {}
    for name in ("mv_map_regions", "mv_map_heatmap_200ly", "mv_map_heatmap_500ly", "mv_map_heatmap_1000ly", "mv_map_timeline_month", "mv_archetype_rankings"):
        if not relation_exists(cur, name):
            views[name] = {"presence": "missing", "populated": None}
        else:
            views[name] = {"presence": "present", "populated": bool(scalar(cur, "SELECT relispopulated FROM pg_class WHERE oid=to_regclass(%s)", (f"public.{name}",)))}
    derived["materialized_views"] = {"classification": "full_build_required", "objects": views}
    runtime = {name: {"classification": "runtime_feature_population", **table_metric(cur, name, full)} for name in RUNTIME_TABLES}
    return {"base_data": base, "full_build": derived, "runtime_features": runtime}


def determine_readiness(report: dict[str, object]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if report["postgresql"]["major_version"] != 18:
        reasons.append("PostgreSQL major version is not 18")
    migrations = report["migrations"]
    if migrations["status"] != "pass":
        reasons.append("migration ledger does not exactly match the manifest")
    derived = report["data"]["full_build"]
    for key in ("grid_cell_id_backlog", "macro_grid_id_backlog"):
        if derived["grid"][key] != 0:
            reasons.append(f"grid {key} is non-zero")
    if derived["ratings_v3_4"].get("value") not in (0, None) or derived["ratings_v3_4"]["rating_dirty_backlog"] != 0:
        reasons.append("ratings v3.4 backlog is non-zero")
    if derived["archetypes"].get("value") not in (0, None): reasons.append("archetype dirty backlog is non-zero")
    if derived["clusters"]["cluster_dirty_backlog"] != 0: reasons.append("cluster dirty backlog is non-zero")
    if derived["clusters"].get("summary_dirty_backlog", {}).get("value") not in (0, None): reasons.append("cluster summary dirty backlog is non-zero")
    for name in FULL_BUILD_DATASETS:
        value = derived[name]
        if value.get("presence") == "missing": reasons.append(f"required dataset {name} is missing")
    for name in ("topology", "economy_pair_synergy", "regional_analysis", "station_body_links", "clusters"):
        if derived[name].get("presence") == "missing": reasons.append(f"required dataset {name} is missing")
    if derived["ratings_v3_4"].get("presence") == "missing": reasons.append("required dataset ratings is missing")
    if derived["archetypes"]["scores"].get("presence") == "missing" or derived["archetypes"]["traits"].get("presence") == "missing":
        reasons.append("required archetype scores or traits are missing")
    if report["profile"] == "production_safe":
        reasons.append("heavy coverage checks remain pending; run --full in an approved window")
    else:
        for dataset, metric in (("topology", "missing_for_ratings"), ("archetypes", "missing_scores_for_ratings"), ("archetypes", "missing_traits_for_scores"), ("regional_analysis", "missing_for_positioned_systems"), ("station_body_links", "required_backfill")):
            state = derived[dataset].get(metric)
            if state is None:
                reasons.append(f"{dataset} {metric} was not checked")
            elif state.get("value") not in (0, None):
                reasons.append(f"{dataset} {metric} is non-zero")
    for name, state in derived["materialized_views"]["objects"].items():
        if state["presence"] != "present" or not state["populated"]: reasons.append(f"materialized view {name} is missing or unpopulated")
    return ("ready" if not reasons else "not_ready", reasons)


def run_audit(args: argparse.Namespace) -> dict[str, object]:
    validate_inputs(args)
    manifest = parse_manifest(args.manifest)
    options = f"-c default_transaction_read_only=on -c statement_timeout={args.statement_timeout} -c lock_timeout=5s -c application_name=production_candidate_readiness"
    conn = psycopg2.connect(args.database_url, options=options)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            if scalar(cur, "SHOW transaction_read_only") != "on":
                raise AuditError("database session did not enter read-only mode")
            version_num = int(scalar(cur, "SHOW server_version_num"))
            version = str(scalar(cur, "SELECT version()"))
            size = int(scalar(cur, "SELECT pg_database_size(current_database())"))
            if not relation_exists(cur, "schema_migrations"):
                raise AuditError("required schema_migrations ledger is missing")
            cur.execute("SELECT filename, checksum_sha256, apply_mode FROM schema_migrations ORDER BY filename")
            migrations = compare_migrations(manifest, cur.fetchall())
            report: dict[str, object] = {
                "schema_version": 1, "audit": "v3_postgresql18_production_candidate_readiness",
                "generated_at": datetime.now(timezone.utc).isoformat(), "read_only": True,
                "profile": "full" if args.full else "production_safe", "target": redacted_target(args.database_url),
                "postgresql": {"version": version, "major_version": version_num // 10000, "database_size_bytes": size},
                "migrations": migrations, "data": collect(cur, args.full),
            }
            report["readiness"], report["blocking_reasons"] = determine_readiness(report)
            conn.rollback()
            return report
    finally:
        conn.close()


def write_receipt(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def print_human(report: dict[str, object], receipt: Path) -> None:
    pg = report["postgresql"]
    print("ED-Finder V3 production-candidate readiness audit")
    print(f"  Result       : {report['readiness']}")
    print(f"  Profile      : {report['profile']}")
    print(f"  PostgreSQL   : {pg['version']}")
    print(f"  Database size: {pg['database_size_bytes']:,} bytes")
    migration = report["migrations"]
    print(f"  Migrations   : auto pending={len(migration['pending_automatic'])}, manual pending={len(migration['pending_manual'])}, checksum mismatches={len(migration['checksum_mismatches'])}")
    print("  Base data:")
    for name, state in report["data"]["base_data"].items():
        count = "unavailable" if state["row_count"] is None else f"{state['row_count']:,}"
        print(f"    {name}: {state['presence']}, rows={count} ({state['count_method']})")
    print("  Full-build datasets:")
    for name, state in report["data"]["full_build"].items():
        print(f"    {name}: {json.dumps(state, sort_keys=True)}")
    print("  Runtime/feature-populated datasets (population is nonblocking):")
    for name, state in report["data"]["runtime_features"].items():
        count = "unavailable" if state["row_count"] is None else f"{state['row_count']:,}"
        print(f"    {name}: {state['presence']}, rows={count} ({state['count_method']})")
    for reason in report["blocking_reasons"]: print(f"  BLOCKED      : {reason}")
    print(f"  Receipt      : {receipt}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        report = run_audit(args)
        write_receipt(args.receipt_file, report)
        print_human(report, args.receipt_file)
        return 0 if report["readiness"] == "ready" else 1
    except (AuditError, psycopg2.Error, OSError, ValueError) as exc:
        print(f"production_candidate_readiness: failed closed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
