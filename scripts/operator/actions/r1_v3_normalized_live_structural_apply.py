#!/usr/bin/env python3
"""One-shot, fail-closed live apply for the additive R1 normalized-V3 shell."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import NoReturn

CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE = "edfinder_v3_phase4c_full_20260827_r5"
EXPECTED_DB_USER = "edfinder_v3"
MIGRATION_NAME = "r1_v3/001_structural_shell.sql"
EXPECTED_BLOB_SHA = "26d1ef3d4ae343159ba62281102f2143ccff7fb8"
EXPECTED_R1_SCHEMAS = ["r1_cache", "r1_meta", "r1_plan"]
EXPECTED_RELATIONS = {
    "r1_cache|system_capability_current|v",
    "r1_meta|capability_generation|r",
    "r1_meta|current_capability_generation|r",
    "r1_meta|mechanics_revision|r",
    "r1_meta|model_revision|r",
    "r1_meta|programme_revision|r",
    "r1_plan|plan_allocation|r",
    "r1_plan|plan_assessment|r",
    "r1_plan|plan_node|r",
    "r1_plan|plan_revision|r",
    "r1_plan|saved_plan|r",
}
ZERO_ROW_RELATIONS = [
    "r1_meta.mechanics_revision",
    "r1_meta.model_revision",
    "r1_meta.programme_revision",
    "r1_meta.capability_generation",
    "r1_meta.current_capability_generation",
    "r1_plan.saved_plan",
    "r1_plan.plan_revision",
    "r1_plan.plan_node",
    "r1_plan.plan_allocation",
    "r1_plan.plan_assessment",
    "r1_cache.system_capability_current",
]


def fail(message: str) -> NoReturn:
    raise SystemExit(f"STOP: {message}")


def docker_psql_base() -> list[str]:
    inspect = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER], text=True))[0]
    if not inspect.get("State", {}).get("Running"):
        fail("normalized V3 container is not running")

    env: dict[str, str] = {}
    for item in inspect.get("Config", {}).get("Env", []):
        if "=" in item:
            key, value = item.split("=", 1)
            env[key] = value

    user = env.get("POSTGRES_USER") or "postgres"
    if user != EXPECTED_DB_USER:
        fail(f"unexpected normalized V3 database user {user!r}")
    password = env.get("POSTGRES_PASSWORD") or ""

    base = ["docker", "exec"]
    if password:
        base += ["-e", f"PGPASSWORD={password}"]
    base += [
        CONTAINER,
        "psql",
        "-X",
        "-h",
        "127.0.0.1",
        "-U",
        user,
        "-d",
        DATABASE,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-F",
        "|",
    ]
    return base


def query(base: list[str], sql: str) -> list[str]:
    wrapped = "BEGIN READ ONLY; " + sql.rstrip().rstrip(";") + "; COMMIT;"
    lines = subprocess.check_output(base + ["-c", wrapped], text=True, stderr=subprocess.STDOUT).splitlines()
    return [line for line in lines if line not in {"BEGIN", "COMMIT"}]


def verify_preconditions(base: list[str]) -> tuple[int, str, str]:
    ident = query(
        base,
        "SELECT current_database(),current_user,pg_is_in_recovery(),pg_size_pretty(pg_database_size(current_database()))",
    )
    print("pre_apply_target_identity:", ident)
    if len(ident) != 1 or not ident[0].startswith(f"{DATABASE}|{EXPECTED_DB_USER}|f|"):
        fail("target identity mismatch")

    required = query(
        base,
        "SELECT to_regclass('v3_meta.canonical_generation')::text,"
        "to_regclass('v3_identity.account')::text,"
        "to_regclass('v3_meta.schema_migration')::text",
    )
    if required != ["v3_meta.canonical_generation|v3_identity.account|v3_meta.schema_migration"]:
        fail("normalized V3 authority relation mismatch")

    authority_types = set(
        query(
            base,
            """
            SELECT n.nspname,c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull
            FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE a.attnum>0 AND NOT a.attisdropped AND (
              (n.nspname='v3_identity' AND c.relname='account' AND a.attname='account_id') OR
              (n.nspname='v3_meta' AND c.relname='canonical_generation' AND a.attname='generation_id')
            )
            ORDER BY n.nspname,c.relname,a.attname
            """,
        )
    )
    expected_types = {
        "v3_identity|account|account_id|uuid|t",
        "v3_meta|canonical_generation|generation_id|uuid|t",
    }
    if authority_types != expected_types:
        fail(f"authority type mismatch: {sorted(authority_types)!r}")

    ledger_columns = query(
        base,
        """
        SELECT a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull
        FROM pg_attribute a
        JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='v3_meta' AND c.relname='schema_migration'
          AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
    )
    expected_ledger = [
        "1|migration_name|text|t",
        "2|migration_sha256|bytea|t",
        "3|applied_at|timestamp with time zone|t",
    ]
    if ledger_columns != expected_ledger:
        fail(f"migration ledger shape mismatch: {ledger_columns!r}")

    existing_schemas = query(
        base,
        "SELECT nspname FROM pg_namespace WHERE nspname IN ('r1_meta','r1_cache','r1_plan') ORDER BY nspname",
    )
    if existing_schemas:
        fail(f"R1 schemas already exist: {existing_schemas!r}")

    ledger_existing = query(
        base,
        f"SELECT count(*) FROM v3_meta.schema_migration WHERE migration_name='{MIGRATION_NAME}'",
    )
    if ledger_existing != ["0"]:
        fail("R1 structural migration is already ledgered")

    canonical_before = query(base, "SELECT count(*) FROM v3_meta.canonical_generation")[0]
    accounts_before = query(base, "SELECT count(*) FROM v3_identity.account")[0]
    ledger_before = int(query(base, "SELECT count(*) FROM v3_meta.schema_migration")[0])
    print(
        "pre_apply_counts:",
        {
            "canonical_generation": canonical_before,
            "account": accounts_before,
            "schema_migration": ledger_before,
        },
    )
    return ledger_before, canonical_before, accounts_before


def build_atomic_sql(source: str, migration_sha256: str) -> str:
    if not source.startswith("BEGIN;\n"):
        fail("migration no longer begins with BEGIN;")
    stripped = source.rstrip()
    if not stripped.endswith("COMMIT;"):
        fail("migration no longer ends with COMMIT;")

    body = stripped[: -len("COMMIT;")].rstrip()
    original_without_begin = body[len("BEGIN;\n") :]
    prelude = """BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
LOCK TABLE v3_meta.schema_migration IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM v3_meta.schema_migration WHERE migration_name = 'r1_v3/001_structural_shell.sql') THEN
    RAISE EXCEPTION 'R1 structural migration is already ledgered';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN ('r1_meta','r1_cache','r1_plan')) THEN
    RAISE EXCEPTION 'R1 schema already exists; refusing partial/repeated apply';
  END IF;
END
$$;
"""
    ledger = f"""

INSERT INTO v3_meta.schema_migration (migration_name, migration_sha256)
VALUES ('{MIGRATION_NAME}', decode('{migration_sha256}', 'hex'));
COMMIT;
"""
    return prelude + original_without_begin + ledger


def apply_atomic(base: list[str], atomic_sql: str) -> None:
    proc = subprocess.run(
        base,
        input=atomic_sql.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        output = proc.stdout.decode("utf-8", "replace")
        print(output)
        fail(f"atomic migration failed with exit code {proc.returncode}; transaction rolled back")
    print("atomic_apply_psql_result: success")


def verify_postconditions(
    base: list[str],
    migration_sha256: str,
    ledger_before: int,
    canonical_before: str,
    accounts_before: str,
) -> None:
    schemas_after = query(
        base,
        "SELECT nspname FROM pg_namespace WHERE nspname IN ('r1_meta','r1_cache','r1_plan') ORDER BY nspname",
    )
    if schemas_after != EXPECTED_R1_SCHEMAS:
        fail(f"post-apply R1 schema set mismatch: {schemas_after!r}")

    ledger_row = query(
        base,
        f"SELECT migration_name,encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='{MIGRATION_NAME}'",
    )
    if ledger_row != [f"{MIGRATION_NAME}|{migration_sha256}"]:
        fail(f"post-apply ledger row mismatch: {ledger_row!r}")

    canonical_after = query(base, "SELECT count(*) FROM v3_meta.canonical_generation")[0]
    accounts_after = query(base, "SELECT count(*) FROM v3_identity.account")[0]
    ledger_after = int(query(base, "SELECT count(*) FROM v3_meta.schema_migration")[0])
    if canonical_after != canonical_before or accounts_after != accounts_before:
        fail("upstream V3 row counts changed unexpectedly")
    if ledger_after != ledger_before + 1:
        fail(f"ledger count did not increase by exactly one: {ledger_before}->{ledger_after}")

    relations = set(
        query(
            base,
            """
            SELECT n.nspname,c.relname,c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('r1_meta','r1_cache','r1_plan')
              AND c.relkind IN ('r','v')
            ORDER BY n.nspname,c.relname
            """,
        )
    )
    if relations != EXPECTED_RELATIONS:
        fail(f"post-apply R1 relation set mismatch: {sorted(relations)!r}")

    for relation in ZERO_ROW_RELATIONS:
        count = query(base, f"SELECT count(*) FROM {relation}")[0]
        if count != "0":
            fail(f"expected zero rows in {relation}, got {count}")

    cap_schemas = query(base, "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'r1_cap_%' ORDER BY nspname")
    if cap_schemas:
        fail(f"capability physical schema unexpectedly exists: {cap_schemas!r}")

    print(
        "post_apply_counts:",
        {
            "canonical_generation": canonical_after,
            "account": accounts_after,
            "schema_migration": ledger_after,
        },
    )
    print("post_apply_r1_schemas:", schemas_after)
    print("post_apply_relation_count:", len(relations))
    print("post_apply_all_r1_rows_zero: true")
    print("capability_generation_built: false")
    print("finder_cutover_performed: false")
    print("legacy_or_v3_data_deleted: false")
    print("live_structural_apply_result: passed")


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: r1_v3_normalized_live_structural_apply.py <uploaded-migration.sql>")

    migration_path = Path(sys.argv[1])
    expected_sha256 = os.environ.get("MIGRATION_SHA256", "")
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        fail("MIGRATION_SHA256 is missing or invalid")

    source_bytes = migration_path.read_bytes()
    actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        fail(f"uploaded migration SHA256 mismatch: {actual_sha256}")
    print("uploaded_migration_sha256_verified:", actual_sha256)
    print("migration_git_blob_pin:", EXPECTED_BLOB_SHA)

    source = source_bytes.decode("utf-8")
    base = docker_psql_base()
    ledger_before, canonical_before, accounts_before = verify_preconditions(base)
    atomic_sql = build_atomic_sql(source, actual_sha256)
    print("atomic_transaction_sha256:", hashlib.sha256(atomic_sql.encode("utf-8")).hexdigest())
    apply_atomic(base, atomic_sql)
    verify_postconditions(base, actual_sha256, ledger_before, canonical_before, accounts_before)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
