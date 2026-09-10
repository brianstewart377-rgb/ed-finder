"""Fail-closed runner for the independent ED-Finder V3 migration lineage."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "sql" / "v3" / "migration-manifest.txt"
MIGRATION_DIR = ROOT / "sql" / "v3" / "migrations"
EXPECTED_BASELINE_NAME = "001_v3_baseline.sql"
EXPECTED_BASELINE_SHA256 = (
    "ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e"
)
EXPECTED_FIRST_POST_BASELINE = "002_v3_accounts_identity.sql"
MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.-]*)$")


class MigrationError(RuntimeError):
    """Raised when the V3 lineage cannot be applied safely."""


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    sha256: str
    path: Path


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = MANIFEST_LINE.fullmatch(line)
        if match is None:
            raise MigrationError(
                f"invalid V3 manifest line {line_number}: expected '<sha256>  <name>'"
            )
        expected_sha, name = match.groups()
        migration_path = MIGRATION_DIR / name
        if not migration_path.is_file():
            raise MigrationError(f"missing V3 migration: {migration_path}")
        actual_sha = sha256_bytes(migration_path.read_bytes())
        if actual_sha != expected_sha:
            raise MigrationError(
                f"checksum mismatch for {name}: expected {expected_sha}, got {actual_sha}"
            )
        entries.append(ManifestEntry(name=name, sha256=actual_sha, path=migration_path))

    names = [entry.name for entry in entries]
    if len(names) != len(set(names)):
        raise MigrationError("V3 manifest contains duplicate migration names")
    if not entries or entries[0].name != EXPECTED_BASELINE_NAME:
        raise MigrationError("V3 manifest must begin with 001_v3_baseline.sql")
    if entries[0].sha256 != EXPECTED_BASELINE_SHA256:
        raise MigrationError("frozen V3 baseline SHA-256 does not match its authority")
    if len(entries) < 2 or entries[1].name != EXPECTED_FIRST_POST_BASELINE:
        raise MigrationError(
            "002_v3_accounts_identity.sql must be the first post-baseline V3 migration"
        )
    return entries


def strip_baseline_transaction(sql: str) -> str:
    """Remove only the frozen baseline's outer transaction for atomic ledgering."""
    begin_matches = list(re.finditer(r"(?m)^BEGIN;\s*$", sql))
    commit_matches = list(re.finditer(r"(?m)^COMMIT;\s*$", sql))
    if len(begin_matches) != 1 or len(commit_matches) != 1:
        raise MigrationError("frozen baseline must contain one outer BEGIN/COMMIT pair")
    begin = begin_matches[0]
    commit = commit_matches[0]
    if begin.start() >= commit.start() or sql[commit.end() :].strip():
        raise MigrationError("frozen baseline transaction boundary is not outermost")
    return sql[: begin.start()] + sql[begin.end() : commit.start()] + sql[commit.end() :]


async def user_relation_count(conn: asyncpg.Connection) -> int:
    value = await conn.fetchval(
        """
        SELECT count(*)
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname !~ '^pg_toast'
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
        """
    )
    return int(value)


async def non_relation_user_object_count(conn: asyncpg.Connection) -> int:
    """Count user residue not represented by pg_class relations."""
    value = await conn.fetchval(
        """
        WITH user_namespaces AS (
            SELECT oid, nspname
            FROM pg_namespace
            WHERE nspname = 'public'
               OR (
                    nspname NOT IN ('pg_catalog', 'information_schema')
                    AND nspname !~ '^pg_(toast|temp|toas_temp)'
               )
        )
        SELECT
            (SELECT count(*) FROM user_namespaces WHERE nspname <> 'public')
          + (SELECT count(*)
             FROM pg_proc AS procedure
             JOIN user_namespaces AS namespace
               ON namespace.oid = procedure.pronamespace)
          + (SELECT count(*)
             FROM pg_type AS type_row
             JOIN user_namespaces AS namespace
               ON namespace.oid = type_row.typnamespace
             WHERE type_row.typrelid = 0
               AND type_row.typtype IN ('c', 'd', 'e', 'm', 'r'))
          + (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql')
        """
    )
    return int(value)


async def ledger_rows(conn: asyncpg.Connection) -> dict[str, str]:
    ledger_exists = await conn.fetchval(
        "SELECT to_regclass('v3_meta.schema_migration') IS NOT NULL"
    )
    if not ledger_exists:
        return {}
    rows = await conn.fetch(
        """
        SELECT migration_name, encode(migration_sha256, 'hex') AS migration_sha256
        FROM v3_meta.schema_migration
        ORDER BY migration_name
        """
    )
    return {str(row["migration_name"]): str(row["migration_sha256"]) for row in rows}


def validate_ledger(
    ledger: dict[str, str],
    entries: Sequence[ManifestEntry],
) -> None:
    manifest = {entry.name: entry.sha256 for entry in entries}
    unknown = sorted(set(ledger) - set(manifest))
    if unknown:
        raise MigrationError(f"V3 ledger contains migrations absent from manifest: {unknown}")
    for name, applied_sha in ledger.items():
        if applied_sha != manifest[name]:
            raise MigrationError(
                f"applied V3 migration checksum differs from manifest: {name}"
            )
    applied_names = [entry.name for entry in entries if entry.name in ledger]
    if applied_names != [entry.name for entry in entries[: len(applied_names)]]:
        raise MigrationError("V3 ledger is not a contiguous manifest prefix")


async def apply_entry(
    conn: asyncpg.Connection,
    entry: ManifestEntry,
) -> None:
    sql = entry.path.read_text(encoding="utf-8")
    if entry.name == EXPECTED_BASELINE_NAME:
        sql = strip_baseline_transaction(sql)

    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '30s'")
        await conn.execute("SET LOCAL statement_timeout = '1h'")
        await conn.execute(sql)
        ledger_exists = await conn.fetchval(
            "SELECT to_regclass('v3_meta.schema_migration') IS NOT NULL"
        )
        if not ledger_exists:
            raise MigrationError(f"{entry.name} did not establish the V3 ledger")
        await conn.execute(
            """
            INSERT INTO v3_meta.schema_migration(migration_name, migration_sha256)
            VALUES ($1, decode($2, 'hex'))
            """,
            entry.name,
            entry.sha256,
        )


async def run_migrations(
    *,
    dsn: str,
    mode: str,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, object]:
    entries = load_manifest(manifest_path)
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    applied_now: list[str] = []
    try:
        server_version_num = str(await conn.fetchval("SHOW server_version_num"))
        if not re.fullmatch(r"18\d{4}", server_version_num):
            raise MigrationError(
                f"V3 migrations require PostgreSQL 18, got {server_version_num}"
            )

        await conn.execute(
            "SELECT pg_advisory_lock(hashtext('edfinder-v3-migration-lineage'))"
        )
        try:
            relations_before = await user_relation_count(conn)
            non_relation_objects_before = await non_relation_user_object_count(conn)
            ledger = await ledger_rows(conn)
            if mode == "bootstrap-empty":
                if relations_before != 0 or non_relation_objects_before != 0 or ledger:
                    raise MigrationError(
                        "bootstrap-empty requires a database with no user objects"
                    )
            elif mode == "upgrade":
                if EXPECTED_BASELINE_NAME not in ledger:
                    raise MigrationError(
                        "upgrade requires the frozen baseline in the V3 ledger"
                    )
            else:
                raise MigrationError(f"unsupported explicit V3 migration mode: {mode}")

            validate_ledger(ledger, entries)
            for entry in entries:
                if entry.name in ledger:
                    continue
                if entry.name == EXPECTED_BASELINE_NAME and mode != "bootstrap-empty":
                    raise MigrationError("the V3 baseline can only be applied to an empty database")
                await apply_entry(conn, entry)
                ledger[entry.name] = entry.sha256
                applied_now.append(entry.name)

            final_ledger = await ledger_rows(conn)
            validate_ledger(final_ledger, entries)
            expected_ledger = {entry.name: entry.sha256 for entry in entries}
            if final_ledger != expected_ledger:
                raise MigrationError("V3 migration run ended with an incomplete ledger")
            relations_after = await user_relation_count(conn)
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock(hashtext('edfinder-v3-migration-lineage'))"
            )
    finally:
        await conn.close()

    return {
        "format": "edfinder-v3-migration-receipt/v1",
        "mode": mode,
        "postgresql_version_num": server_version_num,
        "baseline_sha256": EXPECTED_BASELINE_SHA256,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "manifest": [
            {"name": entry.name, "sha256": entry.sha256} for entry in entries
        ],
        "applied_now": applied_now,
        "ledger": final_ledger,
        "user_relations_before": relations_before,
        "non_relation_user_objects_before": non_relation_objects_before,
        "user_relations_after": relations_after,
        "v2_lineage_used": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply only the independent ED-Finder V3 PostgreSQL 18 lineage.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("bootstrap-empty", "upgrade"),
        help="Explicit V3 mode; bootstrap-empty refuses any pre-existing user relation.",
    )
    parser.add_argument(
        "--database-url-env",
        default="EDFINDER_V3_DATABASE_URL",
        help="Environment variable containing the DSN; the DSN is never printed.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument("--receipt", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dsn = os.environ.get(args.database_url_env, "").strip()
    if not dsn:
        raise SystemExit(f"missing database URL environment variable: {args.database_url_env}")
    try:
        receipt = asyncio.run(
            run_migrations(dsn=dsn, mode=args.mode, manifest_path=args.manifest)
        )
    except (MigrationError, asyncpg.PostgresError) as exc:
        raise SystemExit(f"V3 migration refused: {exc}") from exc

    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt is not None:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
