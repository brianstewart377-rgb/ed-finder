#!/usr/bin/env python3
"""Fail-closed, application-only V3 live-checkpoint deployment boundary."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = ROOT / "deploy/v3-live-checkpoint/target-authority.json"
DEFAULT_COMPOSE = ROOT / "deploy/v3-live-checkpoint/compose.yml"
TARGET_SCHEMA = "ed-finder/v3-live-checkpoint-target-authority/v1"
RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-deployment-receipt/v1"
CURRENT_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-current-receipt/v1"
SCHEMA_RECEIPT_SCHEMA = "ed-finder/v3-live-checkpoint-schema-identity/v1"
PROJECT = "edfinder-v3-checkpoint"
TARGET_HOSTNAME = "vmi3542235"
TARGET_FQDN = "vmi3542235.contaboserver.net"
SERVICES = ("api", "web")
CONTAINERS = {
    "api": "edfinder-v3-checkpoint-api",
    "web": "edfinder-v3-checkpoint-web",
}
APP_NETWORK = "edfinder-v3-checkpoint-app"
RESOURCE_LIMITS = {
    "api": {"cpus": "1.50", "memory": "1536m", "pids": 256},
    "web": {"cpus": "0.50", "memory": "512m", "pids": 128},
}
RUNNER_SERVICES = {
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service",
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service",
    "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service",
}
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
LOOPBACK_ORIGIN = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})\Z")
MAX_JSON_BYTES = 1024 * 1024
MAX_SMOKE_BYTES = 2 * 1024 * 1024


class DeploymentError(ValueError):
    pass


class OperationFailed(DeploymentError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__("deployment operation failed")
        self.receipt = receipt


def load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise DeploymentError(f"{description} exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except DeploymentError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(
            f"unable to read {description}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"{description} must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentError(
            f"unable to checksum artifact: {type(exc).__name__}"
        ) from exc
    return digest.hexdigest()


def verify_checksum(document: Path, checksum: Path) -> str:
    try:
        fields = checksum.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise DeploymentError(f"unable to read checksum: {type(exc).__name__}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != document.name:
        raise DeploymentError("checksum must name only the adjacent manifest basename")
    expected = fields[0]
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise DeploymentError("checksum is not 64 lowercase hexadecimal characters")
    if sha256_file(document) != expected:
        raise DeploymentError("manifest checksum mismatch")
    return expected


def load_manifest_tool() -> Any:
    path = ROOT / "scripts/release/v3_release_manifest.py"
    spec = importlib.util.spec_from_file_location("v3_release_manifest", path)
    if spec is None or spec.loader is None:
        raise DeploymentError("release manifest verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_authority(authority: dict[str, Any]) -> list[str]:
    if authority.get("schema_version") != TARGET_SCHEMA:
        raise DeploymentError("unsupported target authority schema")
    target = authority.get("target")
    contract = authority.get("application_contract")
    external = authority.get("external_authority")
    if not isinstance(target, dict) or target.get("production") is not False:
        raise DeploymentError("target must be explicitly non-production")
    if (
        target.get("provider") != "contabo"
        or target.get("classification") != "live-checkpoint"
    ):
        raise DeploymentError("unexpected live-checkpoint target")
    if target.get("hostname") != TARGET_HOSTNAME or target.get("fqdn") != TARGET_FQDN:
        raise DeploymentError("unexpected Contabo host identity authority")
    if not isinstance(contract, dict) or contract.get("compose_project") != PROJECT:
        raise DeploymentError("unexpected Compose project authority")
    if contract.get("network") != APP_NETWORK or contract.get("named_volumes") != []:
        raise DeploymentError("checkpoint network/volume authority is invalid")
    service_contract = contract.get("services")
    if not isinstance(service_contract, dict) or set(service_contract) != set(SERVICES):
        raise DeploymentError(
            "application service allowlist must be exactly api and web"
        )
    for service, container in CONTAINERS.items():
        item = service_contract.get(service)
        if not isinstance(item, dict) or item.get("container_name") != container:
            raise DeploymentError(f"unexpected {service} container authority")
        if {key: item.get(key) for key in RESOURCE_LIMITS[service]} != RESOURCE_LIMITS[
            service
        ]:
            raise DeploymentError(f"unexpected {service} resource limit authority")
    runtime = authority.get("observed_runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime.get("runner_services", [])) != RUNNER_SERVICES
    ):
        raise DeploymentError("exact three-runner preservation authority is missing")
    status = authority.get("status")
    blockers = authority.get("blockers")
    if status not in {"authorized", "stopped"} or not isinstance(blockers, list):
        raise DeploymentError("target authority status/blockers are invalid")
    if status == "stopped":
        if not blockers or any(
            not isinstance(item, str) or not item for item in blockers
        ):
            raise DeploymentError("stopped target authority requires exact blockers")
        return sorted(set(blockers))
    if blockers:
        raise DeploymentError("authorized target authority cannot retain blockers")
    runtime_networks = runtime.get("docker_networks")
    if (
        not isinstance(runtime.get("container_runtime"), str)
        or not runtime["container_runtime"].strip()
        or not isinstance(runtime.get("compose"), str)
        or not runtime["compose"].strip()
        or not isinstance(runtime_networks, list)
        or APP_NETWORK not in runtime_networks
    ):
        raise DeploymentError(
            "authorized target requires proven Docker, Compose and app network facts"
        )
    required_external = {
        "api_env_file",
        "api_env_owner_uid",
        "api_env_mode",
        "database_source_authority",
        "schema_identity_receipt",
        "schema_identity_receipt_sha256",
        "origin_bind",
        "edge_route_authority",
        "receipt_directory",
        "receipt_owner_uid",
        "receipt_mode",
        "ghcr_pull_authority",
        "docker_config_directory",
        "docker_config_owner_uid",
        "docker_config_mode",
        "docker_context",
    }
    if not isinstance(external, dict) or set(external) != required_external:
        raise DeploymentError("external authority fields are incomplete")
    integer_authorities = {
        "api_env_owner_uid",
        "receipt_owner_uid",
        "docker_config_owner_uid",
    }
    string_authorities = required_external - integer_authorities
    if any(
        not isinstance(external[key], str) or not external[key].strip()
        for key in string_authorities
    ) or any(
        not isinstance(external[key], int) or external[key] < 0
        for key in integer_authorities
    ):
        raise DeploymentError("every external deployment authority must be explicit")
    for key in ("api_env_mode", "receipt_mode", "docker_config_mode"):
        if not re.fullmatch(r"0[0-7]{3}", external[key]):
            raise DeploymentError(
                "external file modes must be four-digit octal strings"
            )
    if not re.fullmatch(r"[0-9a-f]{64}", external["schema_identity_receipt_sha256"]):
        raise DeploymentError("schema identity receipt checksum authority is invalid")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", external["docker_context"]):
        raise DeploymentError("Docker context authority is invalid")
    match = LOOPBACK_ORIGIN.fullmatch(external["origin_bind"])
    if match is None or int(match.group(1)) > 65535:
        raise DeploymentError("origin authority must be an exact loopback HTTP origin")
    return []


def stopped_receipt(authority: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    target = (
        authority.get("target") if isinstance(authority.get("target"), dict) else {}
    )
    return {
        "schema_version": RECEIPT_SCHEMA,
        "operation": "v3-application-live-checkpoint-deploy",
        "status": "stopped",
        "target": {
            "provider": target.get("provider", "unknown"),
            "classification": target.get("classification", "live-checkpoint"),
            "production": False,
            "hostname": target.get("hostname", "unknown"),
        },
        "failures": sorted(set(failures)),
        "authorized_recreate_targets": list(SERVICES),
        "changed_resources": [],
        "database_access_performed": False,
        "migrations_performed": False,
        "service_changes_performed": False,
        "image_pulls_performed": False,
        "filesystem_writes_performed": False,
        "env_files_read": False,
        "private_keys_read": False,
    }


def validate_release_inputs(
    *,
    mode: str,
    candidate_path: Path,
    candidate_checksum: Path,
    current_schema_path: Path,
    database_source_authority: str,
    rollback_path: Path | None,
    rollback_checksum: Path | None,
    prior_receipt_path: Path | None,
    rollback_run_id: str | None = None,
) -> dict[str, Any]:
    manifest_tool = load_manifest_tool()
    candidate_sum = verify_checksum(candidate_path, candidate_checksum)
    candidate = load_json(candidate_path, "candidate manifest")
    schema_receipt = load_json(current_schema_path, "schema identity receipt")
    if (
        set(schema_receipt)
        != {
            "schema_version",
            "database_source_authority",
            "migration_set_identity",
            "captured_at",
        }
        or schema_receipt.get("schema_version") != SCHEMA_RECEIPT_SCHEMA
    ):
        raise DeploymentError("unsupported schema identity receipt")
    if schema_receipt.get("database_source_authority") != database_source_authority:
        raise DeploymentError("schema receipt does not match database source authority")
    captured_at = schema_receipt.get("captured_at")
    try:
        if not isinstance(captured_at, str):
            raise ValueError
        datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise DeploymentError("schema identity receipt timestamp is invalid")
    current_schema = schema_receipt.get("migration_set_identity")
    if not isinstance(current_schema, str) or not SHA256.fullmatch(current_schema):
        raise DeploymentError("schema identity receipt has no valid migration identity")
    try:
        manifest_tool.validate_manifest(
            candidate, purpose="deploy", current_migration_set=current_schema
        )
    except manifest_tool.ManifestError as exc:
        raise DeploymentError(f"candidate manifest rejected: {exc}") from exc
    if candidate.get("rollback", {}).get("application_only_eligible") is not True:
        raise DeploymentError(
            "candidate must be eligible as the receipt-backed next rollback release"
        )

    if mode == "bootstrap":
        if any(
            value is not None
            for value in (rollback_path, rollback_checksum, prior_receipt_path)
        ):
            raise DeploymentError("bootstrap must not claim a prior release or receipt")
        rollback_identity: dict[str, Any] = {"kind": "predeploy_absence"}
    else:
        if (
            rollback_path is None
            or rollback_checksum is None
            or prior_receipt_path is None
        ):
            raise DeploymentError(
                "upgrade requires a prior manifest, checksum and durable receipt"
            )
        rollback_sum = verify_checksum(rollback_path, rollback_checksum)
        rollback = load_json(rollback_path, "rollback manifest")
        prior = load_json(prior_receipt_path, "prior deployment receipt")
        prior_target = prior.get("target")
        prior_smoke = prior.get("smoke")
        if (
            prior.get("schema_version") != RECEIPT_SCHEMA
            or prior.get("mode") not in {"bootstrap", "upgrade"}
            or not isinstance(prior_target, dict)
            or prior_target.get("production") is not False
            or prior_target.get("provider") != "contabo"
            or prior_target.get("classification") != "live-checkpoint"
            or prior_target.get("hostname") != TARGET_HOSTNAME
            or prior.get("compose_project") != PROJECT
            or prior.get("migration_set_identity") != current_schema
            or prior.get("changed_resources")
            != [CONTAINERS[service] for service in SERVICES]
            or not isinstance(prior_smoke, dict)
            or set(prior_smoke)
            != {"/", "/api/health", "/openapi.json", "/api/auth/session"}
            or any(
                not isinstance(outcome, dict)
                or not 200 <= outcome.get("status", 0) < 300
                for outcome in prior_smoke.values()
            )
            or prior.get("database_mutation_performed") is not False
            or prior.get("infrastructure_changes_performed") is not False
        ):
            raise DeploymentError("prior deployment receipt target/schema is invalid")
        try:
            manifest_tool.validate_manifest(
                rollback, purpose="rollback", current_migration_set=current_schema
            )
        except manifest_tool.ManifestError as exc:
            raise DeploymentError(f"rollback manifest rejected: {exc}") from exc
        if candidate.get("git_sha") == rollback.get("git_sha"):
            raise DeploymentError("candidate cannot be its own rollback")
        expected_prior = {
            "status": "accepted",
            "source_sha": rollback.get("git_sha"),
            "images": rollback.get("images"),
            "manifest_sha256": rollback_sum,
        }
        if rollback_run_id is not None:
            if not RUN_ID.fullmatch(rollback_run_id):
                raise DeploymentError("rollback release run ID is invalid")
            expected_prior["release_run_id"] = rollback_run_id
        if any(prior.get(key) != value for key, value in expected_prior.items()):
            raise DeploymentError(
                "prior receipt does not authenticate the rollback release"
            )
        rollback_identity = {
            "kind": "accepted_release",
            "source_sha": rollback["git_sha"],
            "images": rollback["images"],
            "manifest_sha256": rollback_sum,
        }
        if rollback_run_id is not None:
            rollback_identity["release_run_id"] = rollback_run_id
    return {
        "candidate": candidate,
        "candidate_sha256": candidate_sum,
        "current_schema": current_schema,
        "rollback": rollback_identity,
    }


def compose_environment(
    authority: dict[str, Any], release: dict[str, Any]
) -> dict[str, str]:
    external = authority["external_authority"]
    match = LOOPBACK_ORIGIN.fullmatch(external["origin_bind"])
    assert match is not None
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "DOCKER_CONFIG": external["docker_config_directory"],
        "DOCKER_CONTEXT": external["docker_context"],
        "COMPOSE_PROJECT_NAME": PROJECT,
        "V3_CHECKPOINT_API_IMAGE": release["images"]["backend"],
        "V3_CHECKPOINT_WEB_IMAGE": release["images"]["web"],
        "V3_CHECKPOINT_SOURCE_SHA": release["git_sha"],
        "V3_CHECKPOINT_API_ENV_FILE": external["api_env_file"],
        "V3_CHECKPOINT_ORIGIN_BIND": f"127.0.0.1:{match.group(1)}",
    }


def command_plan(compose_path: Path, env: dict[str, str]) -> list[list[str]]:
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose_path)]
    return [
        ["docker", "pull", env["V3_CHECKPOINT_API_IMAGE"]],
        ["docker", "pull", env["V3_CHECKPOINT_WEB_IMAGE"]],
        [
            *base,
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "--pull",
            "never",
            *SERVICES,
        ],
    ]


def rollback_plan(
    compose_path: Path,
    mode: str,
    env: dict[str, str],
    rollback: dict[str, Any],
) -> tuple[list[list[str]], dict[str, str]]:
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose_path)]
    if mode == "bootstrap":
        return [
            [*base, "stop", *SERVICES],
            [*base, "rm", "--force", "--stop", *SERVICES],
        ], env
    prior_env = {
        **env,
        "V3_CHECKPOINT_API_IMAGE": rollback["images"]["backend"],
        "V3_CHECKPOINT_WEB_IMAGE": rollback["images"]["web"],
        "V3_CHECKPOINT_SOURCE_SHA": rollback["source_sha"],
    }
    return command_plan(compose_path, prior_env), prior_env


def run_command(
    argv: list[str], *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError(f"command unavailable or timed out: {argv[0]}") from exc
    if result.returncode != 0:
        raise DeploymentError(f"bounded command failed: {argv[0]} {argv[1]}")
    return result


def validate_host_files(authority: dict[str, Any], compose_path: Path) -> None:
    target = authority["target"]
    if socket.gethostname().split(".")[0] != target["hostname"]:
        raise DeploymentError("host short identity does not match authority")
    if socket.getfqdn() != target["fqdn"]:
        raise DeploymentError("host FQDN does not match authority")
    if os.uname().machine != target["architecture"]:
        raise DeploymentError("host architecture does not match release platform")
    observed_capacity = authority.get("observed_capacity")
    if not isinstance(observed_capacity, dict):
        raise DeploymentError("audited host capacity is missing")
    if (os.cpu_count() or 0) < observed_capacity.get("logical_cpus", 0):
        raise DeploymentError(
            "host CPU capacity is below the audited checkpoint baseline"
        )
    try:
        memory_facts = {
            line.split(":", 1)[0]: int(line.split()[1])
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:"))
        }
        memory_total = memory_facts["MemTotal"]
        memory_available = memory_facts["MemAvailable"]
    except (OSError, KeyError, ValueError) as exc:
        raise DeploymentError("unable to verify host memory capacity") from exc
    if memory_total < observed_capacity.get("memory_total_kib", 0):
        raise DeploymentError("host memory is below the audited checkpoint baseline")
    app_memory_limit_kib = (1536 + 512) * 1024
    if memory_available < app_memory_limit_kib:
        raise DeploymentError("host cannot currently satisfy checkpoint memory limits")
    external = authority["external_authority"]
    api_env = Path(external["api_env_file"])
    if not api_env.is_absolute() or not api_env.is_file() or api_env.is_symlink():
        raise DeploymentError("authorized api_env_file is missing or unsafe")
    api_stat = api_env.stat()
    if (
        api_stat.st_uid != external["api_env_owner_uid"]
        or stat.filemode(api_stat.st_mode)[-9:]
        != stat.filemode(int(external["api_env_mode"], 8))[-9:]
    ):
        raise DeploymentError("authorized api_env_file ownership/mode mismatch")
    schema_path = Path(external["schema_identity_receipt"])
    if (
        not schema_path.is_absolute()
        or not schema_path.is_file()
        or schema_path.is_symlink()
    ):
        raise DeploymentError("authorized schema_identity_receipt is missing or unsafe")
    if sha256_file(schema_path) != external["schema_identity_receipt_sha256"]:
        raise DeploymentError("schema identity receipt checksum mismatch")
    receipt_dir = Path(external["receipt_directory"])
    if (
        not receipt_dir.is_absolute()
        or not receipt_dir.is_dir()
        or receipt_dir.is_symlink()
    ):
        raise DeploymentError("durable receipt directory is missing")
    receipt_stat = receipt_dir.stat()
    if (
        receipt_stat.st_uid != external["receipt_owner_uid"]
        or stat.filemode(receipt_stat.st_mode)[-9:]
        != stat.filemode(int(external["receipt_mode"], 8))[-9:]
    ):
        raise DeploymentError("durable receipt directory ownership/mode mismatch")
    docker_config = Path(external["docker_config_directory"])
    if (
        not docker_config.is_absolute()
        or not docker_config.is_dir()
        or docker_config.is_symlink()
    ):
        raise DeploymentError("authorized Docker config directory is missing or unsafe")
    docker_stat = docker_config.stat()
    if (
        docker_stat.st_uid != external["docker_config_owner_uid"]
        or stat.filemode(docker_stat.st_mode)[-9:]
        != stat.filemode(int(external["docker_config_mode"], 8))[-9:]
    ):
        raise DeploymentError("authorized Docker config ownership/mode mismatch")
    if not compose_path.is_file():
        raise DeploymentError("reviewed Compose file is missing")
    if sha256_file(compose_path) != authority["application_contract"].get(
        "compose_sha256"
    ):
        raise DeploymentError("reviewed Compose checksum does not match authority")


def validate_host_runtime(
    compose_path: Path,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
) -> None:
    runner(["docker", "compose", "version"], env=env)
    compose_base = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--file",
        str(compose_path),
        "config",
    ]
    rendered_services = runner([*compose_base, "--services"], env=env)
    if set(rendered_services.stdout.split()) != set(SERVICES):
        raise DeploymentError("rendered Compose service allowlist is invalid")
    rendered_volumes = runner([*compose_base, "--volumes"], env=env)
    if rendered_volumes.stdout.strip():
        raise DeploymentError("rendered Compose unexpectedly manages volumes")
    rendered_images = runner([*compose_base, "--images"], env=env)
    expected_images = {
        env["V3_CHECKPOINT_API_IMAGE"],
        env["V3_CHECKPOINT_WEB_IMAGE"],
    }
    if set(rendered_images.stdout.split()) != expected_images:
        raise DeploymentError("rendered Compose images are not exact release digests")
    runner(["docker", "network", "inspect", APP_NETWORK], env=env)
    active_runners = runner(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--state=active",
            "--plain",
            "--no-legend",
            "actions.runner.*.service",
        ],
        env=env,
    )
    active_runner_names = {
        line.split()[0]
        for line in active_runners.stdout.splitlines()
        if line.strip().startswith("actions.runner.")
    }
    if active_runner_names != RUNNER_SERVICES:
        raise DeploymentError("active runner topology differs from exact authority")
    for service in sorted(RUNNER_SERVICES):
        runner(["systemctl", "is-active", "--quiet", service], env=env)
    project_containers = runner(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.Names}}",
        ],
        env=env,
    )
    names = {
        line.strip() for line in project_containers.stdout.splitlines() if line.strip()
    }
    if not names.issubset(set(CONTAINERS.values())):
        raise DeploymentError("target project contains a non-allowlisted resource")
    project_volumes = runner(
        [
            "docker",
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.Name}}",
        ],
        env=env,
    )
    if project_volumes.stdout.strip():
        raise DeploymentError("target project contains a managed volume")


def verify_pulled_image(
    image: str,
    source_sha: str,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    result = runner(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            '{{json .RepoDigests}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
        ],
        env=env,
    )
    repo_digests, separator, revision = result.stdout.strip().partition("|")
    try:
        digests = json.loads(repo_digests)
    except json.JSONDecodeError as exc:
        raise DeploymentError("pulled image digest inspection is invalid") from exc
    if not separator or image not in digests or revision != source_sha:
        raise DeploymentError("pulled image digest/build identity mismatch")


def inspect_container(container: str, env: dict[str, str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["docker", "container", "inspect", container],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError("unable to inspect allowlisted app container") from exc
    if result.returncode != 0:
        return None
    try:
        documents = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeploymentError("container inspection returned invalid JSON") from exc
    if not isinstance(documents, list) or len(documents) != 1:
        raise DeploymentError("container inspection returned an invalid result")
    return documents[0]


def verify_origin_state(origin: str, mode: str) -> None:
    match = LOOPBACK_ORIGIN.fullmatch(origin)
    if match is None:
        raise DeploymentError("origin authority is invalid")
    port = int(match.group(1))
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1)
    try:
        if mode == "bootstrap":
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise DeploymentError(
                    "bootstrap origin listener is already occupied"
                ) from exc
        elif probe.connect_ex(("127.0.0.1", port)) != 0:
            raise DeploymentError("upgrade origin listener is not reachable")
    finally:
        probe.close()


def verify_app_containers(
    env: dict[str, str], source_sha: str, expected_images: dict[str, str]
) -> None:
    for service, container in CONTAINERS.items():
        document = inspect_container(container, env)
        role = "backend" if service == "api" else "web"
        if (
            document is None
            or document.get("Config", {}).get("Image") != expected_images[role]
        ):
            raise DeploymentError("running app container image identity mismatch")
        if (
            document.get("Config", {})
            .get("Labels", {})
            .get("org.opencontainers.image.revision")
            != source_sha
        ):
            raise DeploymentError("running app container build identity mismatch")
        labels = document.get("Config", {}).get("Labels", {})
        if (
            labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != service
        ):
            raise DeploymentError("running app container Compose identity mismatch")
        if document.get("State", {}).get("Running") is not True:
            raise DeploymentError("allowlisted app container is not running")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def get_origin(origin: str, path: str) -> tuple[int, bytes, str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    request = urllib.request.Request(
        origin + path, headers={"Accept": "application/json,text/html"}
    )
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(MAX_SMOKE_BYTES + 1)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError) as exc:
        raise DeploymentError(f"origin smoke failed for {path}") from exc
    if not 200 <= status < 300 or len(body) > MAX_SMOKE_BYTES:
        raise DeploymentError(f"origin smoke rejected for {path}")
    return status, body, content_type


def smoke_origin(origin: str, source_sha: str) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    for path in ("/", "/api/health", "/openapi.json", "/api/auth/session"):
        status, body, content_type = get_origin(origin, path)
        outcomes[path] = {"status": status, "bytes": len(body)}
        if path == "/":
            if "text/html" not in content_type.lower() or b"<html" not in body.lower():
                raise DeploymentError("root smoke is not the Svelte HTML application")
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DeploymentError(f"origin smoke JSON is invalid for {path}") from exc
        if not isinstance(payload, dict):
            raise DeploymentError(f"origin smoke payload is invalid for {path}")
        if path == "/api/health" and not (
            payload.get("status") == "ok"
            and payload.get("database") == "connected"
            and payload.get("build_sha") == source_sha
        ):
            raise DeploymentError("health smoke build/database identity mismatch")
        if path == "/openapi.json" and not (
            isinstance(payload.get("paths"), dict)
            and "/api/health" in payload["paths"]
            and "/api/auth/session" in payload["paths"]
        ):
            raise DeploymentError("OpenAPI smoke lacks required route identity")
        if path == "/api/auth/session" and payload.get("authenticated") is not False:
            raise DeploymentError("anonymous session smoke is not anonymous")
    return outcomes


def persist_receipt(directory: Path, receipt: dict[str, Any]) -> Path:
    data = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    identity = (
        f"{receipt['source_sha']}-{receipt['release_run_id']}-"
        f"{receipt['manifest_sha256']}"
    )
    final = directory / f"{identity}.json"
    checksum = directory / f"{identity}.json.sha256"
    if final.exists() or checksum.exists():
        raise OSError("immutable deployment receipt identity already exists")
    digest = hashlib.sha256(data).hexdigest()
    checksum_data = f"{digest}  {final.name}\n".encode()
    pointer_data = (
        json.dumps(
            {
                "schema_version": CURRENT_RECEIPT_SCHEMA,
                "receipt_file": final.name,
                "receipt_sha256": digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    current = directory / "current.json"
    if current.is_symlink():
        raise OSError("current deployment receipt pointer is unsafe")
    previous_current = current.read_bytes() if current.exists() else None
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    temporaries: list[Path] = []
    final_created = False
    checksum_created = False
    current_replaced = False

    def staged(data_to_write: bytes, prefix: str) -> Path:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=prefix, delete=False
        ) as handle:
            path = Path(handle.name)
            temporaries.append(path)
            handle.write(data_to_write)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    try:
        receipt_temporary = staged(data, ".v3-receipt-")
        checksum_temporary = staged(checksum_data, ".v3-checksum-")
        current_temporary = staged(pointer_data, ".v3-current-")
        os.replace(receipt_temporary, final)
        temporaries.remove(receipt_temporary)
        final_created = True
        os.replace(checksum_temporary, checksum)
        temporaries.remove(checksum_temporary)
        checksum_created = True
        os.fsync(directory_fd)
        os.replace(current_temporary, current)
        temporaries.remove(current_temporary)
        current_replaced = True
        os.fsync(directory_fd)
        return final
    except OSError:
        # current.json is the acceptance commit point. Restore its previous
        # state and remove incomplete immutable artifacts before app rollback.
        if current_replaced:
            if previous_current is None:
                current.unlink(missing_ok=True)
            else:
                restore_temporary = staged(previous_current, ".v3-current-restore-")
                os.replace(restore_temporary, current)
                temporaries.remove(restore_temporary)
        if checksum_created:
            checksum.unlink(missing_ok=True)
        if final_created:
            final.unlink(missing_ok=True)
        os.fsync(directory_fd)
        raise
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
        os.close(directory_fd)


def persist_failure_receipt(directory: Path, receipt: dict[str, Any]) -> Path:
    data = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    identity = (
        f"failed-{receipt['source_sha']}-{receipt['release_run_id']}-"
        f"{receipt['manifest_sha256']}-{attempt}"
    )
    final = directory / f"{identity}.json"
    if final.exists():
        raise OSError("immutable failure receipt identity already exists")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".v3-failure-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final)
        temporary = None
        os.fsync(directory_fd)
        return final
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(directory_fd)


def load_current_receipt(directory: Path) -> Path:
    pointer = load_json(
        directory / "current.json", "current deployment receipt pointer"
    )
    if set(pointer) != {"schema_version", "receipt_file", "receipt_sha256"}:
        raise DeploymentError("current deployment receipt pointer shape is invalid")
    if pointer.get("schema_version") != CURRENT_RECEIPT_SCHEMA:
        raise DeploymentError("current deployment receipt pointer schema is invalid")
    receipt_file = pointer.get("receipt_file")
    receipt_sha = pointer.get("receipt_sha256")
    if not isinstance(receipt_file, str) or not re.fullmatch(
        r"[0-9a-f]{40}-[1-9][0-9]{0,19}-[0-9a-f]{64}\.json", receipt_file
    ):
        raise DeploymentError("current deployment receipt filename is invalid")
    if not isinstance(receipt_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", receipt_sha
    ):
        raise DeploymentError("current deployment receipt checksum is invalid")
    receipt_path = directory / receipt_file
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise DeploymentError("current deployment receipt is missing or unsafe")
    if sha256_file(receipt_path) != receipt_sha:
        raise DeploymentError("current deployment receipt checksum mismatch")
    if verify_checksum(receipt_path, Path(f"{receipt_path}.sha256")) != receipt_sha:
        raise DeploymentError("current deployment receipt sidecar mismatch")
    return receipt_path


def acquire_deployment_lock(directory: Path) -> Any:
    try:
        handle = (directory / "deploy.lock").open("a+", encoding="utf-8")
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        try:
            handle.close()
        except UnboundLocalError:
            pass
        raise DeploymentError("live-checkpoint deployment lock is unavailable") from exc
    return handle


def release_deployment_lock(handle: Any) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def verify_bootstrap_absence(
    env: dict[str, str],
    origin: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    for container in CONTAINERS.values():
        listed = runner(
            [
                "docker",
                "ps",
                "--all",
                "--filter",
                f"name=^/{container}$",
                "--format",
                "{{.Names}}",
            ],
            env=env,
        )
        if listed.stdout.strip():
            raise DeploymentError("bootstrap requires proven predeploy app absence")
    verify_origin_state(origin, "bootstrap")


def operation_receipt(
    *,
    authority: dict[str, Any],
    args: argparse.Namespace,
    release_info: dict[str, Any],
    status: str,
    changed_resources: list[str],
    smokes: dict[str, Any],
    rollback: dict[str, Any],
) -> dict[str, Any]:
    candidate = release_info["candidate"]
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "mode": args.mode,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sha": candidate["git_sha"],
        "release_run_id": args.candidate_run_id,
        "images": candidate["images"],
        "manifest_sha256": release_info["candidate_sha256"],
        "migration_set_identity": release_info["current_schema"],
        "target": {
            "provider": "contabo",
            "classification": "live-checkpoint",
            "production": False,
            "hostname": authority["target"]["hostname"],
        },
        "compose_project": PROJECT,
        "changed_resources": changed_resources,
        "smoke": smokes,
        "rollback": rollback,
        "database_access_performed": status == "accepted",
        "database_mutation_performed": False,
        "migrations_performed": False,
        "infrastructure_changes_performed": False,
        "service_changes_performed": status == "accepted",
        "image_pulls_performed": status == "accepted",
        "filesystem_writes_performed": True,
        "env_file_consumed_by_compose": status == "accepted",
        "private_keys_read": False,
    }


def execute(
    args: argparse.Namespace,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    authority = load_json(args.authority, "target authority")
    blockers = validate_authority(authority)
    if blockers:
        raise DeploymentError("target authority stopped: " + ",".join(blockers))
    external = authority["external_authority"]
    if args.candidate_run_id is None or not RUN_ID.fullmatch(args.candidate_run_id):
        raise DeploymentError("candidate release run ID is required")
    if args.mode == "bootstrap" and args.rollback_run_id is not None:
        raise DeploymentError("bootstrap must not claim a rollback release run")
    if args.mode == "upgrade" and (
        args.rollback_run_id is None or not RUN_ID.fullmatch(args.rollback_run_id)
    ):
        raise DeploymentError("upgrade requires a rollback release run ID")
    receipt_directory = Path(external["receipt_directory"])
    validate_host_files(authority, args.compose)
    deployment_lock = acquire_deployment_lock(receipt_directory)
    release_info: dict[str, Any] | None = None
    image_pull_attempted = False
    pulled_images: list[str] = []
    service_mutation_attempted = False
    runtime_validation_started = False
    smokes: dict[str, Any] = {}
    try:
        prior_receipt_path = (
            load_current_receipt(receipt_directory) if args.mode == "upgrade" else None
        )
        release_info = validate_release_inputs(
            mode=args.mode,
            candidate_path=args.candidate,
            candidate_checksum=args.candidate_checksum,
            current_schema_path=Path(external["schema_identity_receipt"]),
            database_source_authority=external["database_source_authority"],
            rollback_path=args.rollback,
            rollback_checksum=args.rollback_checksum,
            prior_receipt_path=prior_receipt_path,
            rollback_run_id=args.rollback_run_id,
        )
        candidate = release_info["candidate"]
        env = compose_environment(authority, candidate)
        runtime_validation_started = True
        validate_host_runtime(args.compose, env, runner)
        if args.mode == "bootstrap":
            if (receipt_directory / "current.json").exists():
                raise DeploymentError("bootstrap requires proven prior receipt absence")
            verify_bootstrap_absence(env, external["origin_bind"], runner)
        else:
            rollback = release_info["rollback"]
            verify_app_containers(env, rollback["source_sha"], rollback["images"])
            smoke_origin(external["origin_bind"], rollback["source_sha"])
            verify_origin_state(external["origin_bind"], "upgrade")

        plan = command_plan(args.compose, env)
        for command in plan[:2]:
            image_pull_attempted = True
            runner(command, env=env)
            verify_pulled_image(command[-1], candidate["git_sha"], env, runner)
            pulled_images.append(command[-1])
        if args.mode == "upgrade":
            rollback = release_info["rollback"]
            for image in rollback["images"].values():
                image_pull_attempted = True
                runner(["docker", "pull", image], env=env)
                verify_pulled_image(image, rollback["source_sha"], env, runner)
                pulled_images.append(image)
        service_mutation_attempted = True
        runner(plan[2], env=env)
        verify_app_containers(env, candidate["git_sha"], candidate["images"])
        smokes = smoke_origin(external["origin_bind"], candidate["git_sha"])
        receipt = operation_receipt(
            authority=authority,
            args=args,
            release_info=release_info,
            status="accepted",
            changed_resources=[CONTAINERS[service] for service in SERVICES],
            smokes=smokes,
            rollback=release_info["rollback"],
        )
        persist_receipt(receipt_directory, receipt)
        return receipt
    except Exception as original:
        # A failure before release validation has no authenticated candidate
        # identity, but the lock file write still has to be reported truthfully.
        if release_info is None:
            failure_receipt = stopped_receipt(authority, [type(original).__name__])
            failure_receipt.update(
                filesystem_writes_performed=True,
                deployment_lock_acquired=True,
            )
            raise OperationFailed(failure_receipt) from original
        rollback_outcome: dict[str, Any] = {
            "identity": release_info["rollback"],
            "attempted": False,
            "status": "not-required",
        }
        if service_mutation_attempted:
            rollback_outcome.update(attempted=True, status="started")
            try:
                commands, rollback_env = rollback_plan(
                    args.compose, args.mode, env, release_info["rollback"]
                )
                for command in commands:
                    runner(command, env=rollback_env)
                if args.mode == "bootstrap":
                    verify_bootstrap_absence(
                        rollback_env, external["origin_bind"], runner
                    )
                else:
                    rollback = release_info["rollback"]
                    verify_app_containers(
                        rollback_env, rollback["source_sha"], rollback["images"]
                    )
                    smoke_origin(external["origin_bind"], rollback["source_sha"])
                rollback_outcome["status"] = "verified"
            except Exception as rollback_error:
                rollback_outcome.update(
                    status="failed", failure=type(rollback_error).__name__
                )
        failure_receipt = operation_receipt(
            authority=authority,
            args=args,
            release_info=release_info,
            status="failed",
            changed_resources=(
                [CONTAINERS[service] for service in SERVICES]
                if service_mutation_attempted
                else []
            ),
            smokes=smokes,
            rollback=rollback_outcome,
        )
        failure_receipt.update(
            failure=type(original).__name__,
            image_pull_attempted=image_pull_attempted,
            image_pulls_performed=(
                True if pulled_images else None if image_pull_attempted else False
            ),
            image_pulls_may_have_been_performed=image_pull_attempted,
            pulled_images_verified=pulled_images,
            service_mutation_attempted=service_mutation_attempted,
            service_changes_performed=service_mutation_attempted,
            database_access_may_have_been_performed=service_mutation_attempted,
            env_file_consumed_by_compose=False,
            env_file_may_have_been_consumed_by_compose=runtime_validation_started,
        )
        try:
            failure_path = persist_failure_receipt(receipt_directory, failure_receipt)
            failure_receipt["durable_failure_receipt"] = failure_path.name
        except OSError:
            failure_receipt["durable_failure_receipt"] = None
            failure_receipt["receipt_persistence"] = "failed"
        raise OperationFailed(failure_receipt) from original
    finally:
        release_deployment_lock(deployment_lock)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    result.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    result.add_argument("--mode", choices=("bootstrap", "upgrade"), default="bootstrap")
    result.add_argument("--candidate", type=Path)
    result.add_argument("--candidate-checksum", type=Path)
    result.add_argument("--candidate-run-id")
    result.add_argument("--rollback", type=Path)
    result.add_argument("--rollback-checksum", type=Path)
    result.add_argument("--rollback-run-id")
    result.add_argument("--authority-gate", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authority: dict[str, Any] = {}
    try:
        authority = load_json(args.authority, "target authority")
        blockers = validate_authority(authority)
        if blockers:
            print(json.dumps(stopped_receipt(authority, blockers), sort_keys=True))
            return 78
        if args.authority_gate:
            print(
                json.dumps(
                    {
                        "schema_version": RECEIPT_SCHEMA,
                        "status": "authority-verified",
                        "target": authority["target"],
                        "service_changes_performed": False,
                        "filesystem_writes_performed": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.candidate is None or args.candidate_checksum is None:
            raise DeploymentError("candidate manifest and checksum are required")
        receipt = execute(args)
    except OperationFailed as exc:
        print(json.dumps(exc.receipt, sort_keys=True), file=sys.stdout)
        return 78
    except DeploymentError as exc:
        print(
            json.dumps(stopped_receipt(authority, [str(exc)]), sort_keys=True),
            file=sys.stdout,
        )
        return 78
    except Exception as exc:
        print(
            json.dumps(
                stopped_receipt(authority, [f"internal_failure:{type(exc).__name__}"]),
                sort_keys=True,
            ),
            file=sys.stdout,
        )
        return 78
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
