#!/usr/bin/env bash
set -euo pipefail

# This is deliberately a read-only, stopped preflight. It must not grow a
# deployment command until every item below has reviewed V3 authority.
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/v3-application-deploy-preflight/v1","status":"stopped","failures":["python3_unavailable"],"service_changes_performed":false,"filesystem_writes_performed":false,"database_access_performed":false}'
    exit 78
fi

exec python3 - <<'PY'
from __future__ import annotations

import json
import socket
import subprocess


EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
REQUIRED_FACTS = sorted(
    {
        "accepted_prior_digest_release_and_receipt_compatible_with_current_database",
        "approved_external_secret_and_nonsecret_config_mount_authority_per_service",
        "approved_ghcr_pull_authentication_authority",
        "authoritative_current_schema_migrations_identity_receipt_source",
        "durable_release_manifest_deploy_receipt_and_rollback_history_storage",
        "exact_application_service_keys_container_names_and_recreate_allowlist",
        "explicit_postgresql18_redis_nats_and_edge_preservation_targets",
        "host_cpu_platform_for_release_images",
        "required_application_data_log_and_receipt_mounts",
        "reviewed_v3_compose_project_config_path_and_bundle_installation_method",
        "reviewed_web_api_network_alias_upstream_loopback_port_and_tls_edge_wiring",
        "reviewed_origin_public_health_openapi_session_and_svelte_smoke_authority",
    }
)


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


short_host = socket.gethostname().split(".")[0]
fqdn_result = run(["hostname", "-f"])
fqdn = fqdn_result.stdout.strip()
failures = ["deployment_topology_authority_incomplete"]
if short_host != EXPECTED_HOST or fqdn_result.returncode != 0 or fqdn != EXPECTED_FQDN:
    failures.append("unexpected_host_identity")

receipt = {
    "schema_version": "ed-finder/v3-application-deploy-preflight/v1",
    "operation": "v3-application-deploy-preflight",
    "status": "stopped",
    "host": {"short": short_host, "fqdn": fqdn},
    "required_facts": REQUIRED_FACTS,
    "failures": sorted(failures),
    "authorized_recreate_targets": [],
    "database_access_performed": False,
    "migrations_performed": False,
    "service_changes_performed": False,
    "filesystem_writes_performed": False,
    "env_files_read": False,
    "private_keys_read": False,
}
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
raise SystemExit(78)
PY
