#!/usr/bin/env python3
"""Offline, read-only inventory tooling for a PostgreSQL custom-format dump.

This Phase-1 tool lists archive metadata only.  It never restores or extracts
rows and deliberately exposes no option for a database connection string.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RETAINED_NAME = "edfinder_20260823T021001Z.dump"
RETAINED_SIZE = 75_931_356_521
RETAINED_SHA256 = "20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1"
TARGET_POSTGRES_MAJOR = 18
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
SAFE_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$.,() \[\]]{0,255}$")
TOC_LINE = re.compile(r"^\s*(\d+);\s+(\d+)\s+(\d+)\s+(.+?)\s*$")
VERSION_NUMBER = re.compile(r"(\d+)(?:\.\d+)?")
ARCHIVE_VERSION = re.compile(
    r"^;\s*(?:Dumped from database|Dumped by pg_dump) version:\s*(\d+)(?:\.\d+)?",
    re.MULTILINE,
)
SOURCE_VERSION = re.compile(
    r"^;\s*Dumped from database version:\s*(\d+(?:\.\d+)?)", re.MULTILINE
)
DUMP_TOOL_VERSION = re.compile(
    r"^;\s*Dumped by pg_dump version:\s*(\d+(?:\.\d+)?)", re.MULTILINE
)

# Longest first because pg_restore descriptors contain spaces.
DESCRIPTORS = (
    "MATERIALIZED VIEW DATA",
    "MATERIALIZED VIEW",
    "TABLE ATTACH",
    "TABLE DATA",
    "FK CONSTRAINT",
    "CHECK CONSTRAINT",
    "SEQUENCE OWNED BY",
    "SEQUENCE SET",
    "DEFAULT ACL",
    "PUBLICATION TABLE",
    "DATABASE PROPERTIES",
    "BLOB COMMENTS",
    "BLOB METADATA",
    "BLOBS",
    "PROCEDURAL LANGUAGE",
    "FOREIGN DATA WRAPPER",
    "FOREIGN SERVER",
    "USER MAPPING",
    "TEXT SEARCH CONFIGURATION",
    "TEXT SEARCH DICTIONARY",
    "TEXT SEARCH PARSER",
    "TEXT SEARCH TEMPLATE",
    "ROW SECURITY",
    "POLICY",
    "TRIGGER",
    "CONSTRAINT",
    "INDEX ATTACH",
    "INDEX",
    "DEFAULT",
    "SEQUENCE",
    "VIEW",
    "TABLE",
    "TYPE",
    "DOMAIN",
    "FUNCTION",
    "PROCEDURE",
    "AGGREGATE",
    "OPERATOR",
    "CAST",
    "COLLATION",
    "CONVERSION",
    "EXTENSION",
    "SCHEMA",
    "COMMENT",
    "ACL",
    "EVENT TRIGGER",
    "PUBLICATION",
    "SUBSCRIPTION",
)


class InventoryError(RuntimeError):
    """A fail-closed validation error safe to show to an operator."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_local_file(value: str) -> Path:
    if "://" in value or value.startswith(("postgres:", "postgresql:")):
        raise InventoryError(
            "dump must be an explicitly supplied local filesystem path"
        )
    path = Path(value).expanduser()
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise InventoryError("dump path is not readable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise InventoryError("dump must be a non-symlink regular file")
    return path.resolve(strict=True)


def _safe_output_dir(value: str, dump: Path) -> Path:
    if "://" in value:
        raise InventoryError("output directory must be local")
    candidate = Path(value).expanduser()
    if candidate == Path("/") or candidate.resolve(strict=False) in {ROOT, dump.parent}:
        raise InventoryError("refusing broad or source-adjacent output directory")
    # Existing symlinks anywhere in the path can redirect supposedly local evidence.
    probe = candidate.absolute()
    for parent in (probe, *probe.parents):
        if parent.exists() and parent.is_symlink():
            raise InventoryError("output path must not contain symlinks")
    if candidate.exists():
        if not candidate.is_dir() or any(candidate.iterdir()):
            raise InventoryError("output directory must be new or empty")
    else:
        candidate.mkdir(mode=0o700, parents=True)
    return candidate.resolve(strict=True)


def _run_pg_restore(
    pg_restore: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [pg_restore, *arguments],
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
    )


def _tool_major(version_output: str) -> int:
    match = VERSION_NUMBER.search(version_output)
    if not match:
        raise InventoryError("could not determine pg_restore version")
    return int(match.group(1))


def _numeric_version(pattern: re.Pattern[str], text: str, label: str) -> str:
    match = pattern.search(text)
    if not match:
        raise InventoryError(f"archive listing omits {label}")
    return match.group(1)


def _archive_major(listing: str) -> int:
    versions = [int(value) for value in ARCHIVE_VERSION.findall(listing)]
    if not versions:
        raise InventoryError("archive listing omits PostgreSQL source/tool version")
    return max(versions)


def verify_version_relationship(tool_major: int, archive_major: int) -> None:
    if archive_major < 10 or archive_major > TARGET_POSTGRES_MAJOR:
        raise InventoryError(
            "archive PostgreSQL major is outside the reviewed 10-18 range"
        )
    if tool_major < archive_major:
        raise InventoryError(
            "pg_restore is older than the pg_dump that created the archive"
        )
    if tool_major > TARGET_POSTGRES_MAJOR:
        raise InventoryError(
            "pg_restore is newer than the reviewed PostgreSQL 18 target"
        )


def _safe_ident(value: str, label: str) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise InventoryError(f"archive contains an unsupported {label} identifier")
    return value


def _safe_object_name(value: str) -> str:
    if not SAFE_OBJECT_NAME.fullmatch(value):
        raise InventoryError("archive contains an unsupported object identifier")
    return value


def parse_toc(listing: str) -> list[dict[str, Any]]:
    """Parse pg_restore's stable TOC text without evaluating archive content."""
    objects: list[dict[str, Any]] = []
    for raw_line in listing.splitlines():
        if not raw_line or raw_line.startswith(";"):
            continue
        match = TOC_LINE.fullmatch(raw_line)
        if not match:
            raise InventoryError("unrecognised pg_restore listing line")
        dump_id, catalog_oid, object_oid, tail = match.groups()
        descriptor = next(
            (
                kind
                for kind in DESCRIPTORS
                if tail == kind or tail.startswith(kind + " ")
            ),
            None,
        )
        if descriptor is None:
            raise InventoryError("archive contains an unsupported object descriptor")
        fields = tail[len(descriptor) :].strip().split()
        schema: str | None = None
        name: str | None = None
        # The final field is archive owner and is intentionally discarded.
        if descriptor == "SCHEMA":
            if len(fields) < 3 or fields[0] != "-":
                raise InventoryError("malformed SCHEMA listing entry")
            name = _safe_ident(fields[1], "object")
        elif descriptor not in {
            "BLOBS",
            "BLOB COMMENTS",
            "BLOB METADATA",
            "DATABASE PROPERTIES",
        }:
            if len(fields) < 3:
                raise InventoryError("malformed archive object listing entry")
            schema = _safe_ident(fields[0], "schema") if fields[0] != "-" else None
            if descriptor in {
                "CONSTRAINT",
                "FK CONSTRAINT",
                "CHECK CONSTRAINT",
                "TRIGGER",
            }:
                name = _safe_object_name(fields[2])
            elif descriptor in {"FUNCTION", "PROCEDURE", "AGGREGATE"}:
                name = _safe_object_name(" ".join(fields[1:-1]))
            elif descriptor in {"COMMENT", "ACL", "DEFAULT ACL"}:
                name = _safe_object_name(" ".join(fields[1:-1]))
            else:
                name = _safe_object_name(fields[1])
        objects.append(
            {
                "toc_id": int(dump_id),
                "catalog_oid": int(catalog_oid),
                "object_oid": int(object_oid),
                "object_type": descriptor,
                "schema": schema,
                "name": name,
            }
        )
    if not objects:
        raise InventoryError("archive listing contained no inventory objects")
    return sorted(objects, key=lambda item: item["toc_id"])


def _registry_lookup(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from scripts.migration.legacy_object_registry import (
        DumpObject,
        classify_object,
        load_registry,
    )

    registry = load_registry()
    joined: list[dict[str, Any]] = []
    for item in objects:
        match = classify_object(
            registry,
            DumpObject(
                object_type=item["object_type"],
                schema=item["schema"] or "",
                name=item["name"] or "",
            ),
        )
        joined.append(
            {
                **item,
                **(
                    match
                    if match is not None
                    else {
                        "classification": "unclassified",
                        "rationale": "No exact or narrowly reviewed registry rule matched.",
                        "authoritative_source_or_rebuild": None,
                        "candidate_key_columns": [],
                        "relationship_columns": [],
                        "row_content_inspection_permitted": False,
                        "proposed_disposition": "block",
                    }
                ),
            }
        )
    return joined


def _dump_identity(path: Path, retained: bool) -> dict[str, Any]:
    size = path.stat().st_size
    checksum = _sha256(path)
    if retained and (path.name, size, checksum) != (
        RETAINED_NAME,
        RETAINED_SIZE,
        RETAINED_SHA256,
    ):
        raise InventoryError("dump does not match the reviewed retained-vault identity")
    return {
        "filename": path.name,
        "size_bytes": size,
        "sha256": checksum,
        "evidence_kind": "retained-vault-verified"
        if retained
        else "synthetic-or-test-acknowledged",
    }


def _write_receipts(output: Path, payload: dict[str, Any]) -> None:
    json_path = output / "legacy-inventory.json"
    markdown_path = output / "legacy-inventory.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    blockers = payload["unclassified_blockers"]
    lines = [
        "# Legacy dump object inventory",
        "",
        "> Phase 1 metadata only. No retained data rows were inspected, and record completeness is unproven.",
        "",
        f"- Evidence kind: `{payload['dump']['evidence_kind']}`",
        f"- Dump filename: `{payload['dump']['filename']}`",
        f"- Dump size: `{payload['dump']['size_bytes']}` bytes",
        f"- Dump SHA-256: `{payload['dump']['sha256']}`",
        f"- pg_restore major: `{payload['tools']['pg_restore_major']}`",
        f"- pg_restore version: `{payload['tools']['pg_restore_version']}`",
        f"- pg_dump version: `{payload['tools']['pg_dump_version']}`",
        f"- Source database version: `{payload['tools']['source_database_version']}`",
        f"- Archive PostgreSQL major: `{payload['tools']['archive_major']}`",
        f"- Unclassified blockers: `{len(blockers)}`",
        "",
        "| TOC | Object | Type | Class | Proposed disposition | Rationale |",
        "|---:|---|---|---|---|---|",
    ]
    for item in payload["objects"]:
        qualified = (
            ".".join(filter(None, (item.get("schema"), item.get("name"))))
            or "(archive-level)"
        )
        cells = [
            str(item["toc_id"]),
            qualified,
            item["object_type"],
            item["classification"],
            item["proposed_disposition"],
            item["rationale"],
        ]
        lines.append(
            "| " + " | ".join(value.replace("|", "\\|") for value in cells) + " |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    hashes = {path.name: _sha256(path) for path in (json_path, markdown_path)}
    (output / "receipt-hashes.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def inventory(args: argparse.Namespace) -> int:
    dump = _regular_local_file(args.dump)
    output = _safe_output_dir(args.output_dir, dump)
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise InventoryError("pg_restore is required")
    version = _run_pg_restore(pg_restore, "--version")
    if version.returncode:
        raise InventoryError("pg_restore --version failed")
    listed = _run_pg_restore(pg_restore, "--list", os.fspath(dump))
    if listed.returncode:
        raise InventoryError("pg_restore rejected the dump as a custom-format archive")
    tool_major = _tool_major(version.stdout)
    archive_major = _archive_major(listed.stdout)
    verify_version_relationship(tool_major, archive_major)
    objects = _registry_lookup(parse_toc(listed.stdout))
    blockers = [
        {key: item[key] for key in ("toc_id", "object_type", "schema", "name")}
        for item in objects
        if item["classification"] == "unclassified"
    ]
    payload = {
        "receipt_version": 1,
        "phase": 1,
        "dump": _dump_identity(dump, args.retained_vault),
        "tools": {
            "pg_restore_major": tool_major,
            "pg_restore_version": _numeric_version(
                VERSION_NUMBER, version.stdout, "pg_restore version"
            ),
            "pg_dump_version": _numeric_version(
                DUMP_TOOL_VERSION, listed.stdout, "pg_dump version"
            ),
            "source_database_version": _numeric_version(
                SOURCE_VERSION, listed.stdout, "source database version"
            ),
            "archive_major": archive_major,
        },
        "objects": objects,
        "unclassified_blockers": blockers,
        "limitations": [
            "No table rows or SQL bodies were inspected.",
            "No retained dump was inspected unless evidence_kind is retained-vault-verified.",
            "Record completeness remains unproven until an authorized Phase 2 inspection.",
        ],
    }
    _write_receipts(output, payload)
    if args.proposal_template:
        proposal = {
            "schema_version": "legacy-selective-extraction-manifest/v1",
            "manifest_id": "owner_review_required",
            "dump_sha256": payload["dump"]["sha256"],
            "tables": [],
            "owner_approval": {
                "owner": "",
                "decision": "not_approved",
                "approved_at": "",
                "scope": "",
            },
            "abort_conditions": [],
            "rollback_conditions": [],
        }
        (output / "extraction-manifest.proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 2 if blockers else 0


def _command(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _unprivileged_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1024 and 65535")
    return port


def inspection_plan(args: argparse.Namespace) -> int:
    dump = _regular_local_file(args.dump)
    _dump_identity(dump, args.retained_vault)
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise InventoryError("pg_restore is required")
    version = _run_pg_restore(pg_restore, "--version")
    listed = _run_pg_restore(pg_restore, "--list", os.fspath(dump))
    if version.returncode or listed.returncode:
        raise InventoryError("pg_restore could not validate the custom-format dump")
    verify_version_relationship(
        _tool_major(version.stdout), _archive_major(listed.stdout)
    )
    host = args.host
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise InventoryError("inspection target must be explicitly loopback-only")
    username = _safe_ident(args.username, "role")
    if re.search(r"(?i)(prod|production|edfinder)", username):
        raise InventoryError("inspection role must not use a production-like name")
    from scripts.migration.extraction_manifest import load_registry, validate_manifest

    manifest_path = _regular_local_file(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InventoryError("manifest is not valid JSON") from exc
    validate_manifest(manifest, load_registry())
    tables = sorted(entry["source_table"] for entry in manifest["tables"])
    database = f"legacy_inspection_{secrets.token_hex(6)}"
    instance = Path("/tmp") / f"legacy-inspection-{secrets.token_hex(6)}"
    data_dir = instance / "data"
    common = ["--host", host, "--port", str(args.port), "--username", username]
    table_flags = [part for table in tables for part in ("--table", table)]
    commands = [
        _command(["mkdir", "--mode=700", os.fspath(instance)]),
        _command(
            [
                "initdb",
                "--no-locale",
                "--encoding=UTF8",
                "--auth=trust",
                "--username",
                username,
                "--pgdata",
                os.fspath(data_dir),
            ]
        ),
        _command(
            [
                "pg_ctl",
                "--pgdata",
                os.fspath(data_dir),
                "--options",
                f"-h {host} -p {args.port}",
                "--wait",
                "start",
            ]
        ),
        _command(["createdb", *common, database]),
        _command(
            [
                "pg_restore",
                "--schema-only",
                "--no-owner",
                "--no-privileges",
                *table_flags,
                *common,
                "--dbname",
                database,
                os.fspath(dump),
            ]
        ),
        _command(
            [
                "pg_restore",
                "--data-only",
                "--no-owner",
                "--no-privileges",
                *table_flags,
                *common,
                "--dbname",
                database,
                os.fspath(dump),
            ]
        ),
        _command(
            ["pg_ctl", "--pgdata", os.fspath(data_dir), "--mode=fast", "--wait", "stop"]
        ),
    ]
    print("# PRINTED PLAN ONLY — DO NOT EXECUTE WITHOUT PHASE 2 OWNER AUTHORIZATION")
    print(
        "# Schema-only is first; data is limited to the manifest's exact table allowlist."
    )
    print("# Phase 1 cannot certify record completeness.")
    print("\n".join(commands))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="write sanitized dump object receipts")
    inv.add_argument("--dump", required=True)
    inv.add_argument("--output-dir", required=True)
    mode = inv.add_mutually_exclusive_group(required=True)
    mode.add_argument("--retained-vault", action="store_true")
    mode.add_argument("--synthetic-or-test-dump", action="store_true")
    inv.add_argument("--proposal-template", action="store_true")
    inv.set_defaults(handler=inventory)
    plan = sub.add_parser(
        "inspection-plan", help="print, but never execute, a disposable plan"
    )
    plan.add_argument("--dump", required=True)
    plan.add_argument("--manifest", required=True)
    plan.add_argument("--host", required=True)
    plan.add_argument("--port", type=_unprivileged_port, required=True)
    plan.add_argument("--username", default="legacy_inspector")
    plan_mode = plan.add_mutually_exclusive_group(required=True)
    plan_mode.add_argument("--retained-vault", action="store_true")
    plan_mode.add_argument("--synthetic-or-test-dump", action="store_true")
    plan.set_defaults(handler=inspection_plan)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return args.handler(args)
    except (InventoryError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
