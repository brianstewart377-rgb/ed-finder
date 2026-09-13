#!/usr/bin/env python3
"""Authenticate a reviewed production migration plan before apply."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_REPOSITORY = "brianstewart377-rgb/ed-finder"
WORKFLOW_PATH = ".github/workflows/v3-production-schema-migration.yml"
RECEIPT_SCHEMA = "ed-finder/v3-production-migration-receipt/v1"
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
TIMESTAMP = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z\Z")
MAX_JSON = 2 * 1024 * 1024


class PlanError(ValueError):
    pass


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PlanError(f"{module_name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON:
            raise PlanError(f"{label} is oversized or unsafe")
        value = json.loads(path.read_text(encoding="utf-8"))
    except PlanError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"unable to read {label}") from exc
    if not isinstance(value, dict):
        raise PlanError(f"{label} must be an object")
    return value


def desired_digest(entries: list[dict[str, str]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_run(run: dict[str, Any], *, run_id: str, source_sha: str) -> None:
    head_repository = run.get("head_repository") or {}
    checks = {
        "run_id": str(run.get("id", "")) == run_id,
        "canonical_repository": isinstance(head_repository, dict)
        and str(head_repository.get("full_name", "")).casefold()
        == CANONICAL_REPOSITORY.casefold(),
        "canonical_workflow": run.get("path") == WORKFLOW_PATH,
        "manual_dispatch": run.get("event") == "workflow_dispatch",
        "successful_run": run.get("status") == "completed"
        and run.get("conclusion") == "success",
        "main_head": run.get("head_branch") == "main",
        "exact_source": run.get("head_sha") == source_sha,
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    if failures:
        raise PlanError("migration plan run provenance failed: " + ",".join(failures))


def validate_receipt(
    receipt: dict[str, Any], authority: dict[str, Any], desired: list[dict[str, str]],
    *, run_id: str, source_sha: str,
) -> None:
    expected_keys = {
        "schema_version", "operation", "status", "created_at", "source_sha",
        "workflow_run_id", "target", "desired_ledger_sha256",
        "schema_identity_sha256", "schema_identity_before_sha256",
        "schema_identity_after_sha256", "schema_identity_updated",
        "prior_release_compatibility_verified", "applied_before", "pending",
        "applied_now", "database_access_performed", "database_writes_performed",
        "migrations_performed", "service_changes_performed", "edge_recreated",
        "protected_resources_changed", "failures",
    }
    if set(receipt) != expected_keys:
        raise PlanError("migration plan receipt shape is invalid")
    external = authority.get("external_authority")
    transition = authority.get("schema_transition")
    if not isinstance(external, dict) or not isinstance(transition, dict):
        raise PlanError("migration target authority shape is invalid")
    before = receipt.get("schema_identity_before_sha256")
    allowed_before = {
        transition.get("from_schema_identity_sha256"),
        external.get("schema_identity_sha256"),
    }
    fixed = {
        "schema_version": receipt.get("schema_version") == RECEIPT_SCHEMA,
        "operation": receipt.get("operation") == "production-migration",
        "status": receipt.get("status") == "planned",
        "created_at": bool(TIMESTAMP.fullmatch(str(receipt.get("created_at", "")))),
        "source_sha": receipt.get("source_sha") == source_sha,
        "workflow_run_id": receipt.get("workflow_run_id") == run_id,
        "target": receipt.get("target") == {
            "production": True, "hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN,
        },
        "desired_ledger": receipt.get("desired_ledger_sha256")
        == desired_digest(desired),
        "target_identity": receipt.get("schema_identity_sha256")
        == external.get("schema_identity_sha256"),
        "identity_before": before in allowed_before,
        "identity_unchanged": receipt.get("schema_identity_after_sha256") == before
        and receipt.get("schema_identity_updated") is False,
        "rollback_verified": receipt.get("prior_release_compatibility_verified") is True,
        "applied_now": receipt.get("applied_now") == [],
        "database_read": receipt.get("database_access_performed") is True,
        "database_writes": receipt.get("database_writes_performed") is False,
        "migrations": receipt.get("migrations_performed") is False,
        "services": receipt.get("service_changes_performed") is False,
        "edge": receipt.get("edge_recreated") is False,
        "protected": receipt.get("protected_resources_changed") is False,
        "failures": receipt.get("failures") == [],
    }
    failures = sorted(name for name, passed in fixed.items() if not passed)
    if failures:
        raise PlanError("migration plan receipt validation failed: " + ",".join(failures))
    applied = receipt.get("applied_before")
    pending = receipt.get("pending")
    if not isinstance(applied, list) or not isinstance(pending, list):
        raise PlanError("migration plan lineage split is invalid")
    if applied + pending != desired:
        raise PlanError("migration plan does not bind the exact committed lineage")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if not RUN_ID.fullmatch(arguments.run_id):
            raise PlanError("migration plan run ID is invalid")
        if not SOURCE_SHA.fullmatch(arguments.source_sha):
            raise PlanError("migration plan source SHA is invalid")
        token = os.environ.get("GITHUB_TOKEN", "")
        release_run = _load(
            "v3_release_run", ROOT / "scripts/release/v3_release_run.py"
        )
        run = release_run.fetch_run(CANONICAL_REPOSITORY, arguments.run_id, token)
        validate_run(run, run_id=arguments.run_id, source_sha=arguments.source_sha)
        receipt = load_json(arguments.receipt, "migration plan receipt")
        authority = load_json(arguments.authority, "migration target authority")
        deployer = _load(
            "v3_production_deploy", ROOT / "scripts/operator/v3_production_deploy.py"
        )
        deployer.validate_authority(authority)
        identity = _load(
            "v3_schema_identity", ROOT / "scripts/operator/v3_schema_identity.py"
        )
        desired = identity.derive_entries(ROOT)
        validate_receipt(
            receipt, authority, desired, run_id=arguments.run_id,
            source_sha=arguments.source_sha,
        )
    except Exception as exc:
        print(f"reviewed migration plan rejected: {exc}", file=sys.stderr)
        return 78
    print(json.dumps({
        "status": "reviewed-plan-verified", "plan_run_id": arguments.run_id,
        "source_sha": arguments.source_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
