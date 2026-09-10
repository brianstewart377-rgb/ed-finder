#!/usr/bin/env python3
"""Derive the reviewed V3 production schema identity from the V3 lineage manifest.

The V3 production database runs an independent PostgreSQL 18 lineage that is
deliberately separate from the canonical V2 ``sql/migration-manifest.txt``
ordered set. This helper turns that lineage into the exact document the
production deployer validates, so the identity is derived and reproducible
instead of hand-written.

Each entry records the migration name exactly as ``v3_meta.schema_migration``
stores it, alongside the repository path holding the bytes, because the
historical applier named some rows by basename and one by path.

The output contains no secret material: a database identity, file paths and
checksums only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_IDENTITY_SCHEMA = "ed-finder/v3-production-schema-identity/v1"
V3_MANIFEST_PATH = "sql/v3/migration-manifest.txt"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_NAME = "edfinder_v3_phase4c_full_20260827_r5"
DATABASE_USER = "edfinder_v3"
DATABASE_IDENTITY = {
    "container": POSTGRES_CONTAINER,
    "database_name": DATABASE_NAME,
    "database_user": DATABASE_USER,
    "application_host": POSTGRES_CONTAINER,
    "server_address": "local",
    "server_port": 5432,
}
# The applied ledger naming the codebase already accepts, plus the reviewed
# repository location of the V3 lineage sources.
MANIFEST_LEDGER_NAME = re.compile(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql\Z")
MANIFEST_PATH = re.compile(
    r"(?:v3/migrations/|r[0-9]+_v3/)[0-9]{3}_[a-z0-9_]+\.sql\Z"
)
MAX_ENTRIES = 512


class SchemaIdentityError(RuntimeError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def derive_entries(root: Path = ROOT) -> list[dict[str, str]]:
    manifest_path = root / V3_MANIFEST_PATH
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise SchemaIdentityError("unable to read the V3 migration manifest") from exc

    entries: list[dict[str, str]] = []
    ledger_names: set[str] = set()
    for raw_line in manifest_bytes.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        checksum, first_separator, remainder = line.partition("  ")
        ledger_name, second_separator, path = remainder.partition("  ")
        if (
            not first_separator
            or not second_separator
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or not MANIFEST_LEDGER_NAME.fullmatch(ledger_name)
            or not MANIFEST_PATH.fullmatch(path)
            or ledger_name in ledger_names
        ):
            raise SchemaIdentityError(f"unsafe V3 migration manifest entry: {line!r}")
        source = root / "sql" / path
        if not source.is_file() or source.is_symlink():
            raise SchemaIdentityError(f"V3 migration source is missing: sql/{path}")
        digest = _sha256(source.read_bytes())
        if digest != checksum:
            raise SchemaIdentityError(f"V3 migration checksum drift: sql/{path}")
        ledger_names.add(ledger_name)
        entries.append(
            {
                "path": f"sql/{path}",
                "ledger_name": ledger_name,
                "mode": "auto",
                "sha256": digest,
            }
        )
    if not entries or len(entries) > MAX_ENTRIES:
        raise SchemaIdentityError("V3 migration manifest entry count is invalid")
    return entries


def migration_set_identity(entries: list[dict[str, str]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + _sha256(canonical)


def build(
    root: Path = ROOT, evidence: str = (
        "reviewed 2026-09-10 production inventory receipt and the live "
        "v3_meta.schema_migration ledger read under BEGIN READ ONLY"
    ),
) -> dict[str, Any]:
    entries = derive_entries(root)
    return {
        "schema_version": SCHEMA_IDENTITY_SCHEMA,
        "database_identity": dict(DATABASE_IDENTITY),
        "migration_set_identity": migration_set_identity(entries),
        "migration_set_entries": entries,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()
    try:
        document = build()
    except SchemaIdentityError as exc:
        print(f"schema identity derivation failed: {exc}", file=sys.stderr)
        return 78
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(payload)
    else:
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output} sha256={_sha256(payload.encode())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
