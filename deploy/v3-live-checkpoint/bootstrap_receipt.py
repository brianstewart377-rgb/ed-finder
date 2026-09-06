#!/usr/bin/env python3
"""Build sanitized provisioning/schema/target receipts from observed facts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TARGET_SCHEMA = "ed-finder/v3-live-checkpoint-target-authority/v1"
SCHEMA_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-schema-identity/v2"
PROVISION_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-provisioning-receipt/v1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
GHCR_IMAGE = re.compile(
    r"ghcr\.io/brianstewart377-rgb/ed-finder/v3-(?:backend|web)@sha256:[0-9a-f]{64}\Z"
)


class ReceiptError(ValueError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReceiptError(f"{path.name} must contain an object")
    return value


def atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.chmod(mode)
    temporary.replace(path)


def load_release_tool(bundle_root: Path) -> Any:
    path = bundle_root / "scripts/release/v3_release_manifest.py"
    spec = importlib.util.spec_from_file_location("v3_release_manifest", path)
    if spec is None or spec.loader is None:
        raise ReceiptError("release migration identity tool is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--schema-path", type=Path, required=True)
    parser.add_argument("--schema-write-path", type=Path)
    parser.add_argument("--refresh-schema", action="store_true")
    args = parser.parse_args()

    if not SHA.fullmatch(args.source_sha):
        raise ReceiptError("source SHA must be 40 lowercase hexadecimal characters")
    facts = load_object(args.facts)
    required = {
        "mode",
        "hostname",
        "fqdn",
        "architecture",
        "captured_at",
        "docker_version",
        "compose_version",
        "psql_version",
        "postgres_version",
        "postgres_image",
        "postgres_image_digest",
        "postgres_image_id",
        "ghcr_proof_image",
        "ghcr_proof_mode",
        "runner_services",
        "alternative_container_clis_present",
        "docker_networks",
        "docker_volumes",
        "container_names",
        "api_env_file",
        "owner_uid",
        "receipt_directory",
        "docker_config_directory",
        "docker_context",
        "origin_bind",
        "edge_route_authority",
        "observed_capacity",
        "tcp_listeners",
    }
    if set(facts) != required:
        raise ReceiptError("observed facts have an unexpected shape")
    if (
        facts["hostname"] != "vmi3542235"
        or facts["fqdn"] != "vmi3542235.contaboserver.net"
    ):
        raise ReceiptError("observed host is not the bounded Contabo checkpoint")
    if facts["architecture"] != "x86_64":
        raise ReceiptError("observed host architecture is not x86_64")
    if facts["mode"] not in {"check", "provision"}:
        raise ReceiptError("observed operation mode is invalid")
    expected_runners = {
        "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service",
        "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service",
        "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service",
    }
    if set(facts["runner_services"]) != expected_runners:
        raise ReceiptError("exactly three allowlisted runner services must be active")
    if facts["alternative_container_clis_present"] != []:
        raise ReceiptError(
            "alternative container CLIs are outside checkpoint authority"
        )
    if facts["ghcr_proof_mode"] not in {"anonymous", "secret-backed"}:
        raise ReceiptError("GHCR proof mode is invalid")
    ghcr_image = facts["ghcr_proof_image"]
    if not isinstance(ghcr_image, str) or (
        ghcr_image and not GHCR_IMAGE.fullmatch(ghcr_image)
    ):
        raise ReceiptError("GHCR proof image is outside the application allowlist")
    if facts["ghcr_proof_mode"] == "anonymous" and not ghcr_image:
        raise ReceiptError(
            "anonymous GHCR authority requires an exact-digest pull proof"
        )
    captured = datetime.strptime(facts["captured_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    now = datetime.now(timezone.utc)
    if captured > now + timedelta(minutes=5) or now - captured > timedelta(hours=24):
        raise ReceiptError(
            "schema identity capture is outside the deployment freshness window"
        )

    if facts["postgres_image"] != "postgres:18":
        raise ReceiptError("PostgreSQL image contract must be postgres:18")
    if not isinstance(facts["postgres_image_digest"], str) or not re.fullmatch(
        r"(?:docker\.io/library/)?postgres@sha256:[0-9a-f]{64}",
        facts["postgres_image_digest"],
    ):
        raise ReceiptError("observed PostgreSQL repository digest is invalid")
    if not isinstance(facts["postgres_image_id"], str) or not SHA256.fullmatch(
        facts["postgres_image_id"]
    ):
        raise ReceiptError("observed PostgreSQL image ID is invalid")
    version_contracts = {
        "docker_version": r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+._a-zA-Z0-9]*)?",
        "compose_version": r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+._a-zA-Z0-9]*)?",
        "psql_version": r"psql \(PostgreSQL\) 18(?:\.[0-9]+)?(?: \([^\r\n]+\))?",
        "postgres_version": r"18(?:\.[0-9]+)?(?: [^\r\n]+)?",
    }
    for field, pattern in version_contracts.items():
        if not isinstance(facts[field], str) or not re.fullmatch(pattern, facts[field]):
            raise ReceiptError(f"observed {field} is invalid")

    fixed_facts = {
        "api_env_file": "/var/lib/edfinder-v3-checkpoint/api.env",
        "receipt_directory": "/var/lib/edfinder-v3-checkpoint/deployment-receipts",
        "docker_config_directory": "/var/lib/edfinder-v3-checkpoint/docker-config",
        "docker_context": "v3-live-checkpoint-local",
        "origin_bind": "http://127.0.0.1:18080",
        "edge_route_authority": (
            "non-production HTTP vhost vmi3542235.contaboserver.net proxies only "
            "to http://127.0.0.1:18080"
        ),
    }
    if any(facts[field] != expected for field, expected in fixed_facts.items()):
        raise ReceiptError(
            "observed path, context, origin, or edge authority is invalid"
        )
    owner_uid = facts["owner_uid"]
    if (
        not isinstance(owner_uid, int)
        or isinstance(owner_uid, bool)
        or not 1 <= owner_uid < 2**31
    ):
        raise ReceiptError("operator owner UID must identify an unprivileged account")

    networks = facts["docker_networks"]
    allowed_networks = {
        "bridge",
        "host",
        "none",
        "edfinder-v3-checkpoint-app",
        "edfinder-v3-checkpoint-data",
    }
    if (
        not isinstance(networks, list)
        or set(networks) != allowed_networks
        or len(networks) != len(allowed_networks)
    ):
        raise ReceiptError("observed Docker network set is not exact")
    volumes = facts["docker_volumes"]
    if volumes != ["edfinder_v3_checkpoint_postgres_data"]:
        raise ReceiptError("observed Docker volume set is not exact")
    containers = facts["container_names"]
    allowed_container_sets = (
        {"edfinder-v3-checkpoint-postgres"},
        {
            "edfinder-v3-checkpoint-postgres",
            "edfinder-v3-checkpoint-api",
            "edfinder-v3-checkpoint-web",
        },
    )
    if (
        not isinstance(containers, list)
        or set(containers) not in allowed_container_sets
        or len(containers) != len(set(containers))
    ):
        raise ReceiptError("observed Docker container set is not exact")

    listeners = facts["tcp_listeners"]
    if (
        not isinstance(listeners, list)
        or listeners != sorted(set(listeners))
        or any(
            not isinstance(listener, str)
            or len(listener) > 128
            or not re.fullmatch(r"[^\s/@]+:[0-9]{1,5}", listener)
            or int(listener.rsplit(":", 1)[1]) > 65535
            for listener in listeners
        )
    ):
        raise ReceiptError("observed TCP listener facts are invalid")
    capacity = facts["observed_capacity"]
    capacity_keys = {
        "logical_cpus",
        "cpu_model",
        "memory_total_kib",
        "memory_available_kib",
        "swap_total_kib",
        "root_bytes",
        "root_available_bytes",
        "root_filesystem",
    }
    if not isinstance(capacity, dict) or set(capacity) != capacity_keys:
        raise ReceiptError("observed capacity facts have an invalid shape")
    numeric_capacity = capacity_keys - {"cpu_model", "root_filesystem"}
    if any(
        not isinstance(capacity[field], int)
        or isinstance(capacity[field], bool)
        or capacity[field] < 0
        for field in numeric_capacity
    ):
        raise ReceiptError("observed capacity values are invalid")
    if capacity["logical_cpus"] < 2 or capacity["memory_total_kib"] < 2 * 1024 * 1024:
        raise ReceiptError("observed capacity is below the checkpoint minimum")
    if (
        not isinstance(capacity["cpu_model"], str)
        or not 1 <= len(capacity["cpu_model"]) <= 256
    ):
        raise ReceiptError("observed CPU model is invalid")
    if not isinstance(capacity["root_filesystem"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.+-]{1,32}", capacity["root_filesystem"]
    ):
        raise ReceiptError("observed root filesystem is invalid")

    release_tool = load_release_tool(args.bundle_root)
    migrations = release_tool.migration_set(args.bundle_root)
    schema_receipt = {
        "schema_version": SCHEMA_RECEIPT_SCHEMA,
        "database_source_authority": (
            "fresh persistent non-production PostgreSQL 18; current repository "
            "migrations plus checkpoint-synthetic-v1 only"
        ),
        "database_identity": {
            "database_name": "edfinder_v3_checkpoint",
            "server_address": "172.30.54.2",
            "server_port": 5432,
        },
        "migration_set_identity": migrations["identity"],
        "migration_set_entries": migrations["entries"],
        "captured_at": facts["captured_at"],
    }
    if args.refresh_schema:
        schema_source = args.schema_write_path or args.schema_path
        atomic_json(schema_source, schema_receipt)
    else:
        if args.schema_write_path is not None:
            raise ReceiptError("schema write path is only valid when refreshing")
        existing = load_object(args.schema_path)
        if existing != schema_receipt:
            raise ReceiptError(
                "stored schema identity receipt is stale or does not match this bundle"
            )
        schema_source = args.schema_path
    schema_sha = hashlib.sha256(schema_source.read_bytes()).hexdigest()

    template = load_object(
        args.bundle_root / "deploy/v3-live-checkpoint/target-authority.json"
    )
    if template.get("schema_version") != TARGET_SCHEMA:
        raise ReceiptError("target authority template schema is unsupported")
    candidate = dict(template)
    candidate["status"] = "authorized"
    candidate["observed_at"] = facts["captured_at"]
    candidate["observed_capacity"] = facts["observed_capacity"]
    runtime = dict(candidate["observed_runtime"])
    runtime.update(
        {
            "container_runtime": facts["docker_version"],
            "compose": facts["compose_version"],
            "container_names": facts["container_names"],
            "docker_networks": facts["docker_networks"],
            "docker_volumes": facts["docker_volumes"],
            "alternative_container_clis_present": facts[
                "alternative_container_clis_present"
            ],
            "runner_services": sorted(facts["runner_services"]),
            "checkpoint_directories_found_under_opt_srv_var_lib": [
                "/var/lib/edfinder-v3-checkpoint"
            ],
        }
    )
    runtime["tcp_listeners"] = facts["tcp_listeners"]
    candidate["observed_runtime"] = runtime
    compose = args.bundle_root / "deploy/v3-live-checkpoint/compose.yml"
    application = dict(candidate["application_contract"])
    application["compose_sha256"] = hashlib.sha256(compose.read_bytes()).hexdigest()
    candidate["application_contract"] = application
    candidate["external_authority"] = {
        "api_env_file": facts["api_env_file"],
        "api_env_owner_uid": facts["owner_uid"],
        "api_env_mode": "0600",
        "database_source_authority": schema_receipt["database_source_authority"],
        "schema_identity_receipt": str(args.schema_path),
        "schema_identity_receipt_sha256": schema_sha,
        "origin_bind": facts["origin_bind"],
        "edge_route_authority": facts["edge_route_authority"],
        "receipt_directory": facts["receipt_directory"],
        "receipt_owner_uid": facts["owner_uid"],
        "receipt_mode": "0700",
        "ghcr_pull_authority": (
            f"anonymous exact-digest pull proven for {facts['ghcr_proof_image']} "
            "using the target-local Docker config"
            if facts["ghcr_proof_mode"] == "anonymous"
            else "secret-backed GHCR login authority installed in the target-local Docker config; canonical deploy re-proves each allowlisted exact-digest pull"
        ),
        "docker_config_directory": facts["docker_config_directory"],
        "docker_config_owner_uid": facts["owner_uid"],
        "docker_config_mode": "0700",
        "docker_context": facts["docker_context"],
    }
    candidate["blockers"] = []

    receipt = {
        "schema_version": PROVISION_RECEIPT_SCHEMA,
        "operation": "v3-live-checkpoint-host-bootstrap",
        "status": "accepted",
        "mode": facts["mode"],
        "source_sha": args.source_sha,
        "target": {
            "provider": "contabo",
            "classification": "live-checkpoint",
            "production": False,
            "hostname": facts["hostname"],
            "fqdn": facts["fqdn"],
            "architecture": facts["architecture"],
        },
        "captured_at": facts["captured_at"],
        "runner_services_preserved": sorted(facts["runner_services"]),
        "runtime": {
            "docker": facts["docker_version"],
            "compose": facts["compose_version"],
            "psql": facts["psql_version"],
            "postgres": facts["postgres_version"],
            "postgres_image": facts["postgres_image"],
            "postgres_image_digest": facts["postgres_image_digest"],
            "postgres_image_id": facts["postgres_image_id"],
        },
        "database": {
            "classification": "synthetic_non_production",
            "persistent": True,
            "fixture": "checkpoint-synthetic-v1",
            "migration_set_identity": migrations["identity"],
            "production_data_used": False,
        },
        "network": {
            "application": "edfinder-v3-checkpoint-app",
            "database": "edfinder-v3-checkpoint-data",
            "origin": facts["origin_bind"],
            "edge": facts["edge_route_authority"],
        },
        "ghcr_pull": {
            "status": (
                "exact_digest_pull_proven"
                if facts["ghcr_proof_mode"] == "anonymous"
                else "secret_backed_authority_installed"
            ),
            "mode": facts["ghcr_proof_mode"],
            "image": facts["ghcr_proof_image"] or None,
        },
        "secret_values_emitted": False,
        "production_mutations_performed": False,
        "production_data_accessed": False,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(args.output_dir / "target-authority-candidate.json", candidate)
    atomic_json(args.output_dir / "provisioning-receipt.json", receipt)
    schema_output = args.output_dir / "schema-identity-receipt.json"
    shutil.copyfile(schema_source, schema_output)
    schema_output.chmod(0o600)
    (args.output_dir / "schema-identity-receipt.json.sha256").write_text(
        f"{schema_sha}  schema-identity-receipt.json\n", encoding="utf-8"
    )
    (args.output_dir / "schema-identity-receipt.json.sha256").chmod(0o600)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"bootstrap receipt generation stopped: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(78) from exc
