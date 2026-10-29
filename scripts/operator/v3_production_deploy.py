#!/usr/bin/env python3
"""Fail-closed, production-in-place V3 application promotion.

This production authority is intentionally separate from the Contabo checkpoint.
It never builds, resolves dependencies, pulls source, runs migrations, or owns
PostgreSQL, Redis, NATS, the public-auth edge, Octopus, or unrelated containers.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
DEFAULT_COMPOSE = ROOT / "deploy/v3-production/compose.yml"
TARGET_SCHEMA = "ed-finder/v3-production-target-authority/v1"
SCHEMA_IDENTITY_SCHEMA = "ed-finder/v3-production-schema-identity/v1"
SCHEMA_TRANSITION_SCHEMA = "ed-finder/v3-production-schema-transition/v1"
RELEASE_COMPATIBILITY_SCHEMA = (
    "ed-finder/v3-production-accepted-release-schema-compatibility/v1"
)
RECEIPT_SCHEMA = "ed-finder/v3-production-deployment-receipt/v1"
CURRENT_SCHEMA = "ed-finder/v3-production-current-release/v1"
PROJECT = "edfinder-v3-production"
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
EXPECTED_ARCH = "x86_64"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
# The retained production database identity, adopted from the reviewed
# 2026-09-10 inventory of the running release rather than from an aspirational
# name. That container exposes exactly one application role and one application
# database, and the reviewed ledger lives in that database.
DATABASE_NAME = "edfinder_v3_phase4c_full_20260827_r5"
DATABASE_USER = "edfinder_v3"
LEGACY_API = "edfinder-v3-api"
LEGACY_ORIGIN = "edfinder-v3-proxy"
PUBLIC_EDGE = "edfinder-v3-public-auth-edge"
LOCAL_DOCKER_ENDPOINT = "unix:///var/run/docker.sock"
SLOTS = ("blue", "green")
SERVICES = tuple(f"{kind}-{slot}" for slot in SLOTS for kind in ("api", "web"))
CONTAINERS = {
    f"{kind}-{slot}": f"edfinder-v3-production-{kind}-{slot}"
    for slot in SLOTS for kind in ("api", "web")
}
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
MODE = re.compile(r"0[0-7]{3}\Z")
MAX_JSON = 2 * 1024 * 1024
MAX_SMOKE = 4 * 1024 * 1024
MAX_ENV_FILE = 256 * 1024
MAX_REGISTRY_TOKEN = 64 * 1024
MAX_CONTAINERS = 256
COMMAND_TIMEOUT = 120
PROCESS_TERMINATION_GRACE = 5
READINESS_TIMEOUT = 120.0
CANCELLATION_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
LEDGER_SQL = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT json_build_object(
  'database_name', current_database(),
  'server_address', COALESCE(inet_server_addr()::text, 'local'),
  'server_port', COALESCE(inet_server_port(), current_setting('port')::int),
  'transaction_read_only', current_setting('transaction_read_only'),
  'migrations', COALESCE((
    SELECT json_agg(
      json_build_object(
        'filename', migration_name,
        'checksum_sha256', encode(migration_sha256, 'hex')
      )
       ORDER BY applied_at, migration_name
    ) FROM v3_meta.schema_migration
  ), '[]'::json)
)::text;
COMMIT;
""".strip()


# Owner decision 2026-10-14: 016 is mandatory even before registration.
F2D_REQUIRED_MIGRATIONS = ("014", "010", "011", "013", "015", "016")
F2D_ATTESTATION_FIELDS = frozenset({
    "ranking_version", "ranking_sha256", "f2d_operator_code_sha256",
    "minimum_schema_compatible_image", "rollback_targets",
})
BACKEND_IMAGE = re.compile(
    r"ghcr\.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:[0-9a-f]{64}\Z"
)
F2D_GENERATION = {
    "generation_key": "ratings_v4_prod_p4_parallel_v1",
    "derived_generation_id": "cfc25d36-3bc7-4011-a465-d6460eaaf826",
    "publication_sequence": 1,
    "state": "PUBLISHED",
}
# Fixed, parameterized psql variables; no operator text becomes SQL syntax.
F2D_GENERATION_SQL = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT json_build_object(
  'generation_key', g.generation_key,
  'derived_generation_id', g.derived_generation_id::text,
  'publication_sequence', p.publication_sequence,
  'state', g.lifecycle_state,
  'finder_products', COALESCE((
    SELECT json_agg(json_build_object(
      'product_code', product_code,
      'lifecycle_state', lifecycle_state,
      'validation_status', validation_receipt ->> 'status',
      'published_at', published_at
    ) ORDER BY product_code)
    FROM v3_meta.derived_product
    WHERE derived_generation_id = :'generation_id'::uuid
      AND product_code IN ('system_search', 'system_archetype')
  ), '[]'::json)
)::text
FROM v3_meta.current_derived_generation p
JOIN v3_meta.derived_generation g USING (derived_generation_id)
WHERE p.singleton;
COMMIT;
""".strip()


# Execute only the actual publication resolver's AST from the pinned image,
# with an in-memory connection. No imports of application startup, real database
# calls, product registration or publication are involved in this contract check.
F2D_IMAGE_CONTRACT_PROGRAM = r"""
import ast
import asyncio
import __future__
import json
from pathlib import Path
from edfinder_api.ranking.profile import RANKING_VERSION, ranking_sha256

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

source = Path('/app/local_search.py').read_text()
if len(source) > 2 * 1024 * 1024:
    raise SystemExit('publication resolver source exceeds bound')
nodes = [node for node in ast.parse(source).body
         if isinstance(node, ast.AsyncFunctionDef) and node.name == '_current_derived_generation']
if len(nodes) != 1:
    raise SystemExit('publication resolver absent')
namespace = {'HTTPException': HTTPException,
             '_REQUIRED_FINDER_PRODUCTS': ('system_search', 'system_archetype')}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<image-publication-resolver>', 'exec',
             flags=__future__.annotations.compiler_flag), namespace)

class Connection:
    def __init__(self, products):
        self.products = products
    async def fetchrow(self, *args):
        return {'derived_generation_id': 'fixture', 'publication_sequence': 1}
    async def fetch(self, *args):
        return self.products

async def verify():
    products = [dict(product_code=code, lifecycle_state='READY', published_at=None,
                     archetype_version='fixture', archetype_manifest_sha256='fixture',
                     archetype_model_sha256='fixture', model_file_sha256='fixture')
                for code in ('system_search', 'system_archetype')]
    resolver = namespace['_current_derived_generation']
    for rows in ([], products):
        try:
            await resolver(Connection(rows))
        except HTTPException as exc:
            if exc.status_code != 503:
                raise SystemExit('publication resolver refusal contract mismatch')
        else:
            raise SystemExit('publication resolver accepted unavailable products')
    for product in products:
        product['published_at'] = 'fixture'
    resolved = await resolver(Connection(products))
    if resolved.get('derived_generation_id') != 'fixture':
        raise SystemExit('publication resolver published contract mismatch')

asyncio.run(verify())
print(json.dumps({'ranking_version': RANKING_VERSION, 'ranking_sha256': ranking_sha256(),
                 'publication_gate': True}))
""".strip()


class DeploymentError(ValueError):
    pass


class OperationFailed(DeploymentError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__("production promotion failed")
        self.receipt = receipt


class OperationCancelled(DeploymentError):
    def __init__(self, signum: int):
        self.signum = signum
        super().__init__(f"operation_cancelled:{signal.Signals(signum).name}")


class CancellationController:
    """Turn the first termination signal into one catchable deployment failure."""

    def __init__(self) -> None:
        self.received: int | None = None
        self.commit_started = False
        self.previous: dict[int, Any] = {}

    def handler(self, signum: int, _frame: Any) -> None:
        if self.commit_started or self.received is not None:
            return
        self.received = signum
        # Rollback, failure-receipt persistence, and cleanup must not be
        # interrupted by repeated cancellation signals.
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)
        raise OperationCancelled(signum)

    def mark_commit_started(self) -> None:
        # Cutover has already passed every verification gate. From this point
        # the small atomic receipt transaction must finish without interruption.
        self.commit_started = True
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)


_CANCELLATION_CONTROLLER: CancellationController | None = None
_PREMUTATION_FAILURE_RECEIPT_DIR: Path | None = None


@contextlib.contextmanager
def controlled_cancellation() -> Any:
    global _CANCELLATION_CONTROLLER
    controller = CancellationController()
    prior_controller = _CANCELLATION_CONTROLLER
    _CANCELLATION_CONTROLLER = controller
    try:
        for handled in CANCELLATION_SIGNALS:
            controller.previous[handled] = signal.getsignal(handled)
            signal.signal(handled, controller.handler)
        yield controller
    finally:
        for handled, previous in controller.previous.items():
            signal.signal(handled, previous)
        _CANCELLATION_CONTROLLER = prior_controller


@contextlib.contextmanager
def cancellation_blocked() -> Any:
    if _CANCELLATION_CONTROLLER is None or not hasattr(signal, "pthread_sigmask"):
        yield
        return
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, CANCELLATION_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def terminate_and_reap(process: subprocess.Popen[str]) -> None:
    if _CANCELLATION_CONTROLLER is not None:
        # Once child cleanup starts, no later signal may interrupt the bounded
        # TERM/KILL/reap sequence and leak a Docker/Compose subprocess.
        for handled in CANCELLATION_SIGNALS:
            signal.signal(handled, signal.SIG_IGN)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=PROCESS_TERMINATION_GRACE)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.communicate()


def run_command(
    argv: list[str], *, env: dict[str, str] | None = None, input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process: subprocess.Popen[str] | None = None
    try:
        # A pending cancellation is delivered only after Popen returns and the
        # new process-group leader is assigned to ``process``.
        with cancellation_blocked():
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
        stdout, stderr = process.communicate(
            input=input_text, timeout=COMMAND_TIMEOUT
        )
    except OperationCancelled:
        if process is not None:
            terminate_and_reap(process)
        raise
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            terminate_and_reap(process)
        raise DeploymentError("bounded command failed: TimeoutExpired") from exc
    except OSError as exc:
        if process is not None:
            terminate_and_reap(process)
        raise DeploymentError(f"bounded command failed: {type(exc).__name__}") from exc
    except BaseException:
        if process is not None:
            terminate_and_reap(process)
        raise
    assert process is not None
    result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    if result.returncode != 0:
        raise DeploymentError(f"bounded command failed: {Path(argv[0]).name}")
    return result


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON or path.is_symlink():
            raise DeploymentError(f"{label} is oversized or unsafe")
        value = json.loads(path.read_text(encoding="utf-8"))
    except DeploymentError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"unable to read {label}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"{label} must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentError("unable to checksum file") from exc
    return digest.hexdigest()


def verify_checksum(document: Path, sidecar: Path) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise DeploymentError("unable to read checksum") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != document.name:
        raise DeploymentError("checksum must name only the adjacent manifest basename")
    if not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
        raise DeploymentError("checksum must be 64 lowercase hexadecimal characters")
    if sha256_file(document) != fields[0]:
        raise DeploymentError("manifest checksum mismatch")
    return fields[0]


def manifest_tool() -> Any:
    path = ROOT / "scripts/release/v3_release_manifest.py"
    spec = importlib.util.spec_from_file_location("v3_release_manifest", path)
    if spec is None or spec.loader is None:
        raise DeploymentError("release manifest verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def purge_state_tool() -> Any:
    """Load the shared fence under the deployment launcher's isolated Python."""
    path = ROOT / "scripts/operator/lib/v3_purge_state.py"
    spec = importlib.util.spec_from_file_location("v3_purge_state", path)
    if spec is None or spec.loader is None:
        raise DeploymentError("purge_state_helper_unavailable")
    module = importlib.util.module_from_spec(spec)
    # Admission itself must not create a __pycache__ before the fence passes.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def require_purge_clear(
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    tool = purge_state_tool()

    def execute(sql: str) -> str:
        return runner(
            ["docker", "exec", POSTGRES_CONTAINER, "psql", "-X", "--no-psqlrc",
             "--no-password", "--tuples-only", "--no-align", "--quiet",
             "--set", "ON_ERROR_STOP=1", "--username", DATABASE_USER,
             "--dbname", DATABASE_NAME, "--host", "/var/run/postgresql",
             "--command", sql],
            env=env,
        ).stdout

    try:
        return tool.check(execute)
    except tool.PurgeStateError as exc:
        raise DeploymentError(str(exc)) from exc


def stopped_receipt(
    authority: dict[str, Any], failures: list[str], *, operation: str = "production-promotion",
) -> dict[str, Any]:
    target = authority.get("target") if isinstance(authority.get("target"), dict) else {}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "operation": operation,
        "status": "stopped",
        "target": {
            "production": True,
            "hostname": target.get("hostname", EXPECTED_HOST),
            "fqdn": target.get("fqdn", EXPECTED_FQDN),
        },
        "failures": failures,
        "database_access_performed": False,
        "database_writes_performed": False,
        "migrations_performed": False,
        "application_data_writes_performed": False,
        "image_pulls_performed": False,
        "service_changes_performed": False,
        "edge_recreated": False,
        "protected_resources_changed": False,
        "filesystem_writes_performed": operation
        in {"production-preflight", "production-promotion"},
        "env_files_read": False,
        "env_contents_recorded": False,
        "private_keys_read": False,
    }
    if operation == "production-preflight":
        receipt["filesystem_write_scope"] = "ephemeral-operation-bundle-only"
    return receipt


def validate_authority(value: dict[str, Any]) -> list[str]:
    if value.get("schema_version") != TARGET_SCHEMA:
        raise DeploymentError("unsupported production target authority")
    target = value.get("target")
    if not isinstance(target, dict) or target != {
        "provider": "mevspace", "classification": "production", "production": True,
        "hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN, "architecture": EXPECTED_ARCH,
    }:
        raise DeploymentError("exact production target identity authority is invalid")
    contract = value.get("application_contract")
    if not isinstance(contract, dict):
        raise DeploymentError("production application contract is missing")
    if contract.get("compose_project") != PROJECT or contract.get("slots") != list(SLOTS):
        raise DeploymentError("production Compose project/slot authority is invalid")
    if contract.get("services") != list(SERVICES):
        raise DeploymentError("production service allowlist is invalid")
    if contract.get("containers") != [CONTAINERS[item] for item in SERVICES]:
        raise DeploymentError("production container allowlist is invalid")
    if contract.get("named_volumes") != []:
        raise DeploymentError("production application Compose must not own volumes")
    preservation = value.get("preservation_contract")
    if not isinstance(preservation, dict) or preservation.get("never_recreate_or_remove") is not True:
        raise DeploymentError("production preservation contract is invalid")
    required = {PUBLIC_EDGE, POSTGRES_CONTAINER, "edfinder-v3-support-redis", "edfinder-v3-support-nats"}
    if set(preservation.get("exact_containers", [])) != required:
        raise DeploymentError("production exact preservation allowlist is invalid")
    status = value.get("status")
    blockers = value.get("blockers")
    if status not in {"stopped", "authorized"} or not isinstance(blockers, list):
        raise DeploymentError("production authority status is invalid")
    if status == "stopped":
        if not blockers or any(not isinstance(item, str) or not item for item in blockers):
            raise DeploymentError("stopped production authority requires concrete blockers")
        return sorted(set(blockers))
    if blockers:
        raise DeploymentError("authorized production authority cannot retain blockers")
    external = value.get("external_authority")
    if not isinstance(external, dict) or any(item is None for item in external.values()):
        raise DeploymentError("authorized production external authority is incomplete")
    capacity = value.get("reviewed_capacity")
    if (
        not isinstance(capacity, dict)
        or not isinstance(capacity.get("logical_cpus"), int)
        or capacity["logical_cpus"] < 12
        or not isinstance(capacity.get("memory_available_kib"), int)
        or capacity["memory_available_kib"] < 15 * 1024 * 1024
        or capacity.get("blue_green_peak")
        != {"cpus": "6.00", "memory": "10240m"}
    ):
        raise DeploymentError("reviewed production blue/green capacity is insufficient")
    if external.get("active_origin_bind") != "127.0.0.1:58080" or external.get("staging_origin_bind") != "127.0.0.1:58081":
        raise DeploymentError("production origin authority is invalid")
    if external.get("public_origin") != "https://ed-finder.app":
        raise DeploymentError("production public origin authority is invalid")
    if external.get("edge_route_authority") != {
        "strategy": "verified-loopback-blue-green-port-swap",
        "edge_container": PUBLIC_EDGE,
        "active_origin_bind": "127.0.0.1:58080",
        "evidence": "reviewed-production-inventory-receipt",
    }:
        raise DeploymentError("production unchanged-edge cutover authority is invalid")
    network_allowlist = external.get("application_network_allowed_containers")
    if (
        not isinstance(network_allowlist, list)
        or not network_allowlist
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", item)
            for item in network_allowlist
        )
        or len(network_allowlist) != len(set(network_allowlist))
    ):
        raise DeploymentError("production application network allowlist is invalid")
    if external.get("docker_context") != "default":
        raise DeploymentError("production Docker context authority must be default")
    for key in ("api_env_owner_uid", "receipt_owner_uid", "schema_identity_owner_uid"):
        if not isinstance(external.get(key), int) or external[key] < 0:
            raise DeploymentError(f"{key} is invalid")
    for key in ("api_env_mode", "receipt_mode", "schema_identity_mode"):
        if not isinstance(external.get(key), str) or not MODE.fullmatch(external[key]):
            raise DeploymentError(f"{key} is invalid")
    if (
        external["api_env_mode"] != "0600"
        or external["schema_identity_mode"] != "0600"
        or external["receipt_mode"] != "0700"
    ):
        raise DeploymentError("production secret/schema/receipt modes are not restrictive")
    if not re.fullmatch(r"[0-9a-f]{64}", str(external.get("schema_identity_sha256", ""))):
        raise DeploymentError("production schema identity checksum authority is invalid")
    transition = value.get("schema_transition")
    if (
        not isinstance(transition, dict)
        or set(transition) != {
            "schema_version", "from_schema_identity_sha256",
            "from_migration_set_identity", "to_migration_set_identity", "evidence",
        }
        or transition.get("schema_version") != SCHEMA_TRANSITION_SCHEMA
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(transition.get("from_schema_identity_sha256", ""))
        )
        or not SHA256.fullmatch(str(transition.get("from_migration_set_identity", "")))
        or not SHA256.fullmatch(str(transition.get("to_migration_set_identity", "")))
        or transition["from_migration_set_identity"] == transition["to_migration_set_identity"]
    ):
        raise DeploymentError("production schema transition authority is invalid")
    validate_evidence_text(transition.get("evidence"), "production schema transition")
    compatibility = value.get("accepted_release_schema_compatibility")
    validate_release_compatibility_shape(compatibility)
    observed = value.get("observed_runtime", {})
    accepted = observed.get("accepted_promotion", {}) if isinstance(observed, dict) else {}
    if (
        compatibility["source_sha"] != accepted.get("source_sha")
        or compatibility["release_run_id"] != str(accepted.get("release_run_id", ""))
        or compatibility["images"] != {
            "backend": observed.get("api_image"), "web": observed.get("web_image")
        }
        or transition["to_migration_set_identity"]
        not in compatibility["compatible_migration_sets"]
    ):
        raise DeploymentError("accepted release compatibility does not bind observed production")
    return []


def validate_evidence_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise DeploymentError(f"{label} lacks bounded reviewed evidence")
    if re.search(
        r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)",
        value,
    ) or re.search(r"(?i)[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@", value):
        raise DeploymentError(f"{label} evidence contains secret-like text")


def validate_release_compatibility_shape(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) - F2D_ATTESTATION_FIELDS != {
            "schema_version", "source_sha", "release_run_id", "manifest_sha256",
            "images", "compatible_migration_sets", "evidence",
        }
        or value.get("schema_version") != RELEASE_COMPATIBILITY_SCHEMA
        or not re.fullmatch(r"[0-9a-f]{40}", str(value.get("source_sha", "")))
        or not RUN_ID.fullmatch(str(value.get("release_run_id", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("manifest_sha256", "")))
        or not isinstance(value.get("images"), dict)
        or set(value["images"]) != {"backend", "web"}
        or any(not isinstance(image, str) for image in value["images"].values())
        or not isinstance(value.get("compatible_migration_sets"), list)
        or not value["compatible_migration_sets"]
        or any(not isinstance(item, str) or not SHA256.fullmatch(item) for item in value["compatible_migration_sets"])
        or value["compatible_migration_sets"] != sorted(set(value["compatible_migration_sets"]))
    ):
        raise DeploymentError("accepted release schema compatibility authority is invalid")
    validate_evidence_text(value.get("evidence"), "accepted release compatibility")
    present = F2D_ATTESTATION_FIELDS.intersection(value)
    if present and present != F2D_ATTESTATION_FIELDS:
        missing = ",".join(sorted(F2D_ATTESTATION_FIELDS - present))
        raise DeploymentError("f2d_attestation_partial_group:" + missing)
    if not present:
        return
    version = value["ranking_version"]
    if (
        not isinstance(version, str) or not version.strip() or version != version.strip()
        or len(version) > 128 or any(ord(char) < 32 for char in version)
    ):
        raise DeploymentError("f2d_attestation_invalid:ranking_version")
    for field in ("ranking_sha256", "f2d_operator_code_sha256"):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
            raise DeploymentError("f2d_attestation_invalid:" + field)
    if not BACKEND_IMAGE.fullmatch(value["images"]["backend"]):
        raise DeploymentError("f2d_attestation_invalid:images.backend")
    minimum = value["minimum_schema_compatible_image"]
    if not isinstance(minimum, str) or not BACKEND_IMAGE.fullmatch(minimum):
        raise DeploymentError("f2d_attestation_invalid:minimum_schema_compatible_image")
    targets = value["rollback_targets"]
    if (
        not isinstance(targets, list) or not 1 <= len(targets) <= 64
        or any(not isinstance(image, str) or not BACKEND_IMAGE.fullmatch(image) for image in targets)
        or len(set(targets)) != len(targets) or targets[0] != minimum
    ):
        raise DeploymentError("f2d_attestation_invalid:rollback_targets")


def is_f2d_release(
    candidate: dict[str, Any], schema: dict[str, Any], attestation: object = None,
) -> bool:
    # validate_candidate already proves candidate compatibility with this exact
    # installed schema. 015 means every subsequent candidate needs this gate;
    # removing an optional dispatch value cannot bypass it.
    return attestation is not None or any(
        Path(item["path"]).name.startswith("015_")
        for item in schema.get("migration_set_entries", [])
    )


def registered_f2d_migrations() -> list[dict[str, str]]:
    path = ROOT / "sql/v3/migration-manifest.txt"
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON:
            raise DeploymentError("f2d_migration_manifest_invalid")
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DeploymentError("f2d_migration_manifest_unavailable") from exc
    if len(payload) > MAX_JSON:
        raise DeploymentError("f2d_migration_manifest_invalid")
    entries = []
    for line in payload.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if (
            len(parts) != 3 or not re.fullmatch(r"[0-9a-f]{64}", parts[0])
            or not re.fullmatch(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql", parts[1])
            or not re.fullmatch(r"(?:v3/migrations/|r[0-9]+_v3/)[0-9]{3}_[a-z0-9_]+\.sql", parts[2])
        ):
            raise DeploymentError("f2d_migration_manifest_invalid")
        entries.append({"ledger_name": parts[1], "path": "sql/" + parts[2],
                        "mode": "auto", "sha256": parts[0]})
    if not 1 <= len(entries) <= 512 or len({item["ledger_name"] for item in entries}) != len(entries):
        raise DeploymentError("f2d_migration_manifest_invalid")
    return entries


def validate_f2d_migrations(
    schema: dict[str, Any], registered_entries: list[dict[str, str]],
) -> None:
    applied = {item["ledger_name"]: item["sha256"] for item in schema["migration_set_entries"]}
    required = []
    for number in F2D_REQUIRED_MIGRATIONS:
        matches = [item for item in registered_entries
                   if Path(item["path"]).name.startswith(number + "_")
                   and item["path"].startswith("sql/v3/migrations/")]
        if len(matches) != 1:
            raise DeploymentError("required_migration_not_registered:" + number)
        required.append((number, matches[0]))
    # Check registration first, so the intentional missing-016 stop is explicit.
    for number, item in required:
        if item["ledger_name"] not in applied:
            raise DeploymentError("required_migration_not_applied:" + number)
        if applied[item["ledger_name"]] != item["sha256"]:
            raise DeploymentError("required_migration_hash_mismatch:" + number)


def validate_f2d_attestation(
    attestation: object, candidate: dict[str, Any], candidate_sum: str,
    run_id: str, schema: dict[str, Any],
) -> None:
    if not isinstance(attestation, dict):
        raise DeploymentError("f2d_release_attestation_required")
    validate_release_compatibility_shape(attestation)
    if not F2D_ATTESTATION_FIELDS.issubset(attestation):
        raise DeploymentError("f2d_release_attestation_required")
    if (
        attestation["source_sha"] != candidate["git_sha"]
        or attestation["release_run_id"] != run_id
        or attestation["manifest_sha256"] != candidate_sum
        or attestation["images"] != candidate["images"]
        or schema["migration_set_identity"] not in attestation["compatible_migration_sets"]
    ):
        raise DeploymentError("f2d_release_attestation_identity_mismatch")
    # The accepted authority later feeds validate_prior_runtime for every
    # migration apply without allow_incompatible_running_image, so the running
    # backend must be a rollback target or no later migration can apply.
    if attestation["images"]["backend"] not in attestation["rollback_targets"]:
        raise DeploymentError("f2d_attestation_invalid:rollback_targets")


def validate_f2d_boundary(
    attestation: dict[str, Any], previous: dict[str, Any],
) -> None:
    minimum = previous.get("minimum_schema_compatible_image")
    if minimum is None:
        minimum = attestation["images"]["backend"]
    if attestation["minimum_schema_compatible_image"] != minimum:
        raise DeploymentError("f2d_minimum_schema_compatible_image_mismatch")


def f2d_generation_rule(accepted_release: object = None) -> str:
    # The release being replaced is authority, never the candidate dispatch.
    # Only the first F2d cutover must precede product registration (design 8.1).
    if accepted_release is not None:
        validate_release_compatibility_shape(accepted_release)
        if F2D_ATTESTATION_FIELDS.issubset(accepted_release):
            return "accepted-f2d-release-allowed-product-states"
    return "first-f2d-cutover-empty-finder-products"


def validate_f2d_generation(observed: object, accepted_release: object = None) -> None:
    if not isinstance(observed, dict):
        raise DeploymentError("f2d_current_generation_mismatch")
    for field, expected in F2D_GENERATION.items():
        if observed.get(field) != expected or type(observed.get(field)) is not type(expected):
            raise DeploymentError("f2d_current_generation_mismatch:" + field)
    products = observed.get("finder_products")
    if f2d_generation_rule(accepted_release) == "first-f2d-cutover-empty-finder-products":
        if products != []:
            raise DeploymentError("finder_products_already_registered_on_parallel_v1")
        return
    if not isinstance(products, list) or len(products) > 2:
        raise DeploymentError("f2d_finder_products_invalid")
    seen = set()
    for product in products:
        if not isinstance(product, dict) or set(product) != {
            "product_code", "lifecycle_state", "validation_status", "published_at",
        }:
            raise DeploymentError("f2d_finder_products_invalid")
        code = product["product_code"]
        if not isinstance(code, str) or code not in {"system_search", "system_archetype"} or code in seen:
            raise DeploymentError("f2d_finder_products_invalid")
        seen.add(code)
        published_at = product["published_at"]
        if published_at is not None and (not isinstance(published_at, str) or not published_at.strip()):
            raise DeploymentError("f2d_finder_products_invalid")
        state = product["lifecycle_state"]
        if state == "FAILED":
            raise DeploymentError("f2d_finder_product_failed:" + code)
        if state == "READY":
            if product["validation_status"] != "VERIFIED":
                raise DeploymentError("f2d_finder_product_validation_unverified:" + code)
        elif state == "BUILDING":
            if published_at is not None:
                raise DeploymentError("f2d_finder_product_building_published:" + code)
        else:
            raise DeploymentError("f2d_finder_product_state_invalid:" + code)


def verify_f2d_generation(
    env: dict[str, str], runner: Callable[..., Any], accepted_release: object = None,
    receipt_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = runner(
        ["docker", "exec", "-i", POSTGRES_CONTAINER, "psql", "-X", "--no-password",
         "--tuples-only", "--no-align", "--quiet", "--set", "ON_ERROR_STOP=1",
         "--set", "generation_id=" + F2D_GENERATION["derived_generation_id"],
         "--username", DATABASE_USER, "--dbname", DATABASE_NAME],
        env=env, input_text=F2D_GENERATION_SQL,
    )
    if len(result.stdout.encode()) > MAX_JSON:
        raise DeploymentError("f2d_generation_response_invalid")
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise DeploymentError("f2d_generation_response_invalid") from exc
    if isinstance(observed, dict) and receipt_observation is not None:
        receipt_observation.update(observed)
    validate_f2d_generation(observed, accepted_release)
    return observed


def trim_rollback_targets(images: list[str], minimum: str) -> list[str]:
    if minimum not in images:
        raise DeploymentError("minimum_schema_compatible_image_not_recorded")
    return images[images.index(minimum):]


def require_f2d_rollback_image(image: str, attestation: dict[str, Any]) -> None:
    targets = trim_rollback_targets(
        attestation["rollback_targets"], attestation["minimum_schema_compatible_image"],
    )
    if image not in targets:
        raise DeploymentError("f2d_rollback_image_incompatible")


def reviewed_accepted_rollback(
    manifest: dict[str, Any], run_id: str, checksum: str, schema: dict[str, Any],
    accepted: dict[str, Any] | None,
) -> bool:
    """True only for the accepted release's own artifact under reviewed compatibility.

    A compatible migration applied after a release (019-021 after a031c2da)
    leaves that release's sealed manifest naming only its build-time schema.
    The reviewed authority attests the newer identity; validate_prior_runtime
    already admits the running release on exactly this binding, and the
    rollback selection uses the same rule for the same artifact.
    """
    if accepted is None:
        return False
    validate_release_compatibility_shape(accepted)
    return (
        accepted["source_sha"] == manifest.get("git_sha")
        and accepted["release_run_id"] == run_id
        and accepted["manifest_sha256"] == checksum
        and accepted["images"] == manifest.get("images")
        and schema["migration_set_identity"] in accepted["compatible_migration_sets"]
    )


def select_f2d_rollback(
    directory: Path, attestation: dict[str, Any], schema: dict[str, Any],
    candidate: dict[str, Any], accepted: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    # Prefer immutable artifacts in the root-owned receipt store, verified with
    # basename-bound checksum sidecars. If none is compatible, the same
    # operation's already authenticated, checksum-bound candidate may provide
    # the first F2d recovery image. Both sources must satisfy the rollback
    # boundary and manifest validation; the incompatible running image cannot.
    paths = []
    for path in directory.glob("*.release.json"):
        paths.append(path)
        if len(paths) > 512:
            raise DeploymentError("f2d_rollback_artifact_inventory_exceeds_bound")
    tool = manifest_tool()
    for image in reversed(attestation["rollback_targets"]):
        for path in sorted(paths):
            match = re.fullmatch(r"([0-9a-f]{40})-([1-9][0-9]{0,19})-([0-9a-f]{64})\.release\.json", path.name)
            if not match:
                continue
            sidecar = Path(str(path) + ".sha256")
            if path.is_symlink() or sidecar.is_symlink():
                raise DeploymentError("f2d_rollback_artifact_path_unsafe")
            checksum = verify_checksum(path, sidecar)
            manifest = load_json(path, "F2d rollback artifact")
            if checksum != match[3] or manifest.get("git_sha") != match[1]:
                raise DeploymentError("f2d_rollback_artifact_identity_mismatch")
            if manifest.get("images", {}).get("backend") != image:
                continue
            require_f2d_rollback_image(image, attestation)
            try:
                tool.validate_manifest(manifest, purpose="rollback",
                                       current_migration_set=schema["migration_set_identity"])
            except tool.ManifestError as exc:
                if not reviewed_accepted_rollback(manifest, match[2], checksum, schema, accepted):
                    raise DeploymentError("f2d_rollback_artifact_schema_incompatible") from exc
                try:
                    # Still a valid, application-only rollback-eligible release.
                    tool.validate_manifest(manifest, purpose="rollback-candidate",
                                           current_migration_set=None)
                except tool.ManifestError as eligibility:
                    raise DeploymentError("f2d_rollback_artifact_schema_incompatible") from eligibility
            return manifest, "recorded_artifact"
    targets = trim_rollback_targets(
        attestation["rollback_targets"], attestation["minimum_schema_compatible_image"],
    )
    if candidate["images"]["backend"] in targets:
        try:
            tool.validate_manifest(candidate, purpose="rollback",
                                   current_migration_set=schema["migration_set_identity"])
        except tool.ManifestError as exc:
            raise DeploymentError("f2d_rollback_artifact_schema_incompatible") from exc
        return candidate, "authenticated_candidate"
    raise DeploymentError("compatible_rollback_artifact_not_recorded")


def f2d_rollback_receipt(manifest: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "kind": ("recorded-schema-compatible-release" if source == "recorded_artifact"
                 else "authenticated-candidate-schema-compatible-release"),
        "source": source, "source_sha": manifest["git_sha"],
        "images": manifest["images"], "schema_compatible": True,
        **({"image_verification": "candidate-pull-verify-step-before-cutover"}
           if source == "authenticated_candidate" else {}),
    }


def exact_host_guard(runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if socket.gethostname().split(".")[0] != EXPECTED_HOST:
        raise DeploymentError("unexpected production hostname")
    fqdn = runner(["hostname", "-f"]).stdout.strip()
    if fqdn != EXPECTED_FQDN or runner(["uname", "-m"]).stdout.strip() != EXPECTED_ARCH:
        raise DeploymentError("unexpected production FQDN or architecture")


def secure_path(path: Path, uid: int, mode: str, *, directory: bool) -> None:
    if not path.is_absolute() or path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise DeploymentError("authorized production path is missing or unsafe")
    details = path.stat()
    if details.st_uid != uid or stat.S_IMODE(details.st_mode) != int(mode, 8):
        raise DeploymentError("authorized production path ownership/mode mismatch")


def live_capacity_guard() -> dict[str, int]:
    memory_available_kib: int | None = None
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as memory_file:
            for line in memory_file:
                key, separator, value = line.partition(":")
                fields = value.split()
                if separator and key == "MemAvailable" and fields and fields[0].isdigit():
                    memory_available_kib = int(fields[0])
                    break
        filesystem = os.statvfs("/")
    except OSError as exc:
        raise DeploymentError("live production capacity inspection failed") from exc
    logical_cpus = os.cpu_count()
    root_available_bytes = filesystem.f_bavail * filesystem.f_frsize
    if (
        logical_cpus is None
        or logical_cpus < 12
        or memory_available_kib is None
        or memory_available_kib < 15 * 1024 * 1024
        or root_available_bytes < 10 * 1024 * 1024 * 1024
    ):
        raise DeploymentError("live production blue/green capacity is insufficient")
    return {
        "logical_cpus": logical_cpus,
        "memory_available_kib": memory_available_kib,
        "root_available_bytes": root_available_bytes,
    }


def base_env(external: dict[str, Any]) -> dict[str, str]:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C", "LC_ALL": "C", "DOCKER_CONTEXT": external["docker_context"],
    }


def docker_context_guard(env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    context = json.loads(runner(["docker", "context", "inspect", env["DOCKER_CONTEXT"]], env=env).stdout)
    if not isinstance(context, list) or len(context) != 1:
        raise DeploymentError("Docker context inspection is ambiguous")
    endpoint = ((context[0].get("Endpoints") or {}).get("docker") or {}).get("Host")
    if endpoint != LOCAL_DOCKER_ENDPOINT:
        raise DeploymentError("Docker context is not the local rootful daemon")


def container_snapshot(names: set[str], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(names):
        raw = runner(["docker", "inspect", "--format", "{{.Id}}\t{{.State.Running}}", name], env=env).stdout.strip().split("\t")
        if len(raw) != 2 or not re.fullmatch(r"[0-9a-f]{64}", raw[0]) or raw[1] != "true":
            raise DeploymentError(f"protected container unavailable: {name}")
        result[name] = raw[0]
    return result


def all_container_snapshot(
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]
) -> dict[str, str]:
    output = runner(
        [
            "docker", "ps", "--all", "--no-trunc", "--format",
            "{{.Names}}\t{{.ID}}\t{{.State}}",
        ],
        env=env,
    ).stdout
    result: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", fields[0]):
            raise DeploymentError("complete container inventory is malformed")
        if not re.fullmatch(r"[0-9a-f]{64}", fields[1]):
            raise DeploymentError("complete container identity is malformed")
        result[fields[0]] = fields[1] + ":" + fields[2]
    if not result:
        raise DeploymentError("complete container inventory is empty")
    return result


def verify_unrelated_snapshot(
    before: dict[str, str], controlled: set[str], env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    after = all_container_snapshot(env, runner)
    expected = {key: value for key, value in before.items() if key not in controlled}
    observed = {key: after.get(key) for key in expected}
    if observed != expected:
        raise DeploymentError("unrelated production container identity/state changed")


def verify_snapshot(before: dict[str, str], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if container_snapshot(set(before), env, runner) != before:
        raise DeploymentError("protected production container identity changed")


def validate_network(
    external: dict[str, Any], schema: dict[str, Any], managed_slots: set[str],
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    raw = runner(
        ["docker", "network", "inspect", external["application_network"]], env=env
    ).stdout
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError("production application network inspection invalid") from exc
    if not isinstance(values, list) or len(values) != 1:
        raise DeploymentError("production application network inspection ambiguous")
    value = values[0]
    if (
        value.get("Name") != external["application_network"]
        or value.get("Driver") != "bridge"
        or value.get("Scope") != "local"
        or value.get("Internal") is not False
        or value.get("Ingress") is not False
    ):
        raise DeploymentError("production application network is not an external local bridge")
    attachments = value.get("Containers")
    if not isinstance(attachments, dict):
        raise DeploymentError("production application network attachments invalid")
    names = sorted(
        item.get("Name") for item in attachments.values()
        if isinstance(item, dict) and isinstance(item.get("Name"), str)
    )
    allowed = external.get("application_network_allowed_containers")
    if not isinstance(allowed, list) or not allowed:
        raise DeploymentError("production application network attachment authority is invalid")
    if not managed_slots <= set(SLOTS):
        raise DeploymentError("production application network slot authority is invalid")
    if len(names) != len(set(names)):
        raise DeploymentError("production application network attachments are duplicated")
    database_container = schema["database_identity"]["container"]
    if database_container not in names:
        raise DeploymentError("production database is not attached to the authorized app network")
    # The retained database and the reviewed baseline must be attached, and a
    # managed slot must be attached while it is managed. Anything else attached
    # fails. The legacy api is deliberately no longer permitted: bootstrap has
    # been accepted, so it has no role, and leaving its name permitted would keep
    # a hole in the authority for a container that no longer exists.
    required = {database_container}
    for slot in sorted(managed_slots):
        required.add(CONTAINERS[f"api-{slot}"])
        required.add(CONTAINERS[f"web-{slot}"])
    if not required <= set(names) <= (set(allowed) | required):
        raise DeploymentError("production application network attachment authority drifted")


def published_port_bindings(
    protected_ports: set[int], env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[int, list[dict[str, Any]]]:
    """Return every Docker binding for a protected host port without deduping."""
    if not protected_ports or any(not 1 <= port <= 65535 for port in protected_ports):
        raise DeploymentError("protected port inventory request is invalid")
    names = runner(
        ["docker", "ps", "--no-trunc", "--format", "{{.Names}}"], env=env
    ).stdout.splitlines()
    if (
        len(names) > MAX_CONTAINERS
        or len(names) != len(set(names))
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) for name in names)
    ):
        raise DeploymentError("running container inventory is malformed")
    bindings: dict[int, list[dict[str, Any]]] = {
        port: [] for port in protected_ports
    }
    for name in names:
        raw = runner(
            [
                "docker", "inspect", "--format",
                "{{json .NetworkSettings.Ports}}", name,
            ],
            env=env,
        ).stdout
        try:
            mappings = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeploymentError("published port inventory is malformed") from exc
        if not isinstance(mappings, dict):
            raise DeploymentError("published port inventory is malformed")
        for target, host_bindings in mappings.items():
            match = re.fullmatch(r"([0-9]{1,5})/(tcp|udp)", str(target))
            if match is None or not 1 <= int(match.group(1)) <= 65535:
                raise DeploymentError("published port inventory is malformed")
            if host_bindings is None:
                continue
            if not isinstance(host_bindings, list):
                raise DeploymentError("published port inventory is malformed")
            for host_binding in host_bindings:
                if not isinstance(host_binding, dict) or set(host_binding) != {
                    "HostIp", "HostPort"
                }:
                    raise DeploymentError("published port inventory is malformed")
                host_ip = host_binding["HostIp"]
                host_port = host_binding["HostPort"]
                if (
                    not isinstance(host_ip, str)
                    or not 0 < len(host_ip) <= 64
                    or not isinstance(host_port, str)
                    or not host_port.isdigit()
                    or not 1 <= int(host_port) <= 65535
                ):
                    raise DeploymentError("published port inventory is malformed")
                observed_host_port = int(host_port)
                if observed_host_port in protected_ports:
                    bindings[observed_host_port].append(
                        {
                            "container": name,
                            "bind_address": host_ip,
                            "host_port": observed_host_port,
                            "container_port": int(match.group(1)),
                            "protocol": match.group(2),
                        }
                    )
    return bindings


def listening_addresses(
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]
) -> dict[int, list[str]]:
    output = runner(["ss", "-H", "-lnt"], env=env).stdout
    listeners: dict[int, list[str]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            raise DeploymentError("production listener inventory is malformed")
        address, separator, raw_port = fields[3].rpartition(":")
        if (
            not separator
            or not raw_port.isdigit()
            or not 1 <= int(raw_port) <= 65535
            or not address
        ):
            raise DeploymentError("production listener inventory is malformed")
        normalized = address.removeprefix("[").removesuffix("]")
        listeners.setdefault(int(raw_port), []).append(normalized)
    return listeners


def verify_exact_origin_bindings(
    active_owner: str, staging_owner: str | None, env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    listeners = listening_addresses(env, runner)
    bindings = published_port_bindings({58080, 58081}, env, runner)
    active_bindings = bindings[58080]
    staging_bindings = bindings[58081]
    if (
        len(active_bindings) != 1
        or active_bindings[0]["container"] != active_owner
        or active_bindings[0]["bind_address"] != "127.0.0.1"
        or active_bindings[0]["protocol"] != "tcp"
    ):
        raise DeploymentError("production active origin ownership drifted")
    active_listeners = listeners.get(58080, [])
    if not active_listeners:
        raise DeploymentError("production active origin listener is missing")
    if any(address != "127.0.0.1" for address in active_listeners):
        raise DeploymentError("production active origin listener is not exact loopback")
    staging_listeners = listeners.get(58081, [])
    if staging_owner is None:
        if staging_bindings or staging_listeners:
            raise DeploymentError("production staging origin port is already owned")
    elif (
        len(staging_bindings) != 1
        or staging_bindings[0]["container"] != staging_owner
        or staging_bindings[0]["bind_address"] != "127.0.0.1"
        or staging_bindings[0]["protocol"] != "tcp"
        or not staging_listeners
        or any(address != "127.0.0.1" for address in staging_listeners)
    ):
        raise DeploymentError("production staging origin ownership drifted")


def verify_origin_ownership(
    mode: str, prior_slot: str | None, env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    active_owner = LEGACY_ORIGIN if mode == "bootstrap" else (
        CONTAINERS[f"web-{prior_slot}"] if prior_slot in SLOTS else "invalid"
    )
    verify_exact_origin_bindings(active_owner, None, env, runner)


def verify_edge_routes_to_active_origin() -> None:
    origin_status, origin_body, _ = get("http://127.0.0.1:58080", "/api/health")
    public_status, public_body, _ = get("https://ed-finder.app", "/api/health")
    if (
        origin_status != 200
        or public_status != 200
        or origin_body != public_body
        or len(origin_body) > MAX_SMOKE
    ):
        raise DeploymentError("production edge-to-loopback route authority is unproved")


def wait_for_preserved_edge_route() -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT
    while time.monotonic() < deadline:
        try:
            verify_edge_routes_to_active_origin()
            status, _body, _content_type = get(
                "http://127.0.0.1:58080", "/api/v1/auth/session"
            )
            if status == 200:
                return
        except DeploymentError:
            pass
        time.sleep(2)
    raise DeploymentError("preserved production origin readiness timed out")


def validate_compose(compose: Path, authority: dict[str, Any], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    if sha256_file(compose) != authority["application_contract"]["compose_sha256"]:
        raise DeploymentError("production Compose checksum mismatch")
    compose_env = {
        **env,
        "V3_PRODUCTION_API_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "0" * 64,
        "V3_PRODUCTION_WEB_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "1" * 64,
        "V3_PRODUCTION_SOURCE_SHA": "0" * 40,
        "V3_PRODUCTION_API_ENV_FILE": authority["external_authority"]["api_env_file"],
        "V3_PRODUCTION_ORIGIN_BIND": authority["external_authority"]["staging_origin_bind"],
        "V3_PRODUCTION_APP_NETWORK": authority["external_authority"]["application_network"],
    }
    base = ["docker", "compose", "--project-name", PROJECT, "--file", str(compose)]
    services = runner([*base, "config", "--services"], env=compose_env).stdout.split()
    volumes = runner([*base, "config", "--volumes"], env=compose_env).stdout.split()
    # Compose reports services in its own order (observed: alphabetical), so this
    # is a check about the exact set of app-only slots, not their declared order.
    # The declared order is still enforced against the authority contract.
    if sorted(services) != sorted(SERVICES) or volumes:
        raise DeploymentError("rendered production Compose escapes app-only authority")


def validate_schema_file(path: Path, expected_sha: str) -> dict[str, Any]:
    if sha256_file(path) != expected_sha:
        raise DeploymentError("production schema identity checksum mismatch")
    value = load_json(path, "production schema identity")
    expected_keys = {"schema_version", "database_identity", "migration_set_identity", "migration_set_entries", "evidence"}
    if set(value) != expected_keys or value.get("schema_version") != SCHEMA_IDENTITY_SCHEMA:
        raise DeploymentError("production schema identity shape is invalid")
    identity = value.get("database_identity")
    if identity != {
        "container": POSTGRES_CONTAINER,
        "database_name": DATABASE_NAME,
        "database_user": DATABASE_USER,
        "application_host": POSTGRES_CONTAINER,
        "server_address": "local",
        "server_port": 5432,
    }:
        raise DeploymentError("production database identity is invalid")
    entries = value.get("migration_set_entries")
    if not isinstance(entries, list) or not entries:
        raise DeploymentError("production schema identity has no entries")
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "ledger_name", "mode", "sha256"}:
            raise DeploymentError("production schema entry shape is invalid")
        # The V3 lineage nests its sources, and the applied ledger name is not
        # always derivable from the path: the historical applier recorded two
        # rows by basename and one by path, so both are carried explicitly.
        if (
            not re.fullmatch(r"sql/(?:v3/migrations/|r[0-9]+_v3/)[0-9]{3}_[a-z0-9_]+\.sql", str(item["path"]))
            or not re.fullmatch(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql", str(item["ledger_name"]))
            or item["mode"] not in {"auto", "manual"}
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"]))
        ):
            raise DeploymentError("production schema entry is invalid")
    if len({item["path"] for item in entries}) != len(entries) or len(
        {item["ledger_name"] for item in entries}
    ) != len(entries):
        raise DeploymentError("production schema entries are duplicated")
    evidence = value.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise DeploymentError("production schema identity lacks reviewed evidence")
    if re.search(
        r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)",
        evidence,
    ) or re.search(r"(?i)[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@", evidence):
        raise DeploymentError("production schema evidence contains secret-like text")
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    calculated = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if value.get("migration_set_identity") != calculated:
        raise DeploymentError("production schema identity is inconsistent")
    return value


def database_identity_from_env(
    path: Path, *, on_read: Callable[[], None] | None = None,
) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeploymentError("unable to read verified production API env snapshot") from exc
    if on_read is not None:
        on_read()
    assignments: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == "DATABASE_URL":
            assignments.append(raw_value.strip())
    if len(assignments) != 1:
        raise DeploymentError("production API env must contain exactly one DATABASE_URL")
    value = assignments[0]
    if (
        not value
        or value[0] in {"'", '"'}
        or "$" in value
        or "`" in value
        or any(character.isspace() for character in value)
    ):
        raise DeploymentError("production DATABASE_URL must be one unquoted literal")
    try:
        parsed = urllib.parse.urlsplit(value)
        database_name = urllib.parse.unquote(parsed.path.removeprefix("/"))
        username = urllib.parse.unquote(parsed.username or "")
        password = parsed.password
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise DeploymentError("production DATABASE_URL identity is invalid") from exc
    if (
        parsed.scheme not in {"postgresql", "postgres"}
        or username != DATABASE_USER
        or not password
        or parsed.hostname != POSTGRES_CONTAINER
        or port not in {None, 5432}
        or database_name != DATABASE_NAME
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentError("production DATABASE_URL does not target retained PostgreSQL")
    return {
        "container": POSTGRES_CONTAINER,
        "database_name": database_name,
        "database_user": username,
        "application_host": parsed.hostname,
        "server_address": "local",
        "server_port": port or 5432,
    }


def verify_live_schema(schema: dict[str, Any], env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    result = runner(
        ["docker", "exec", POSTGRES_CONTAINER, "psql", "-X", "--no-password", "--tuples-only", "--no-align", "--quiet", "--field-separator", "\t", "--set", "ON_ERROR_STOP=1", "--username", DATABASE_USER, "--dbname", DATABASE_NAME, "--command", LEDGER_SQL],
        env=env,
    )
    if len(result.stdout.encode("utf-8")) > MAX_JSON:
        raise DeploymentError("production migration ledger output exceeds size limit")
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise DeploymentError("production migration ledger returned invalid JSON") from exc
    if not isinstance(observed, dict) or set(observed) != {
        "database_name", "server_address", "server_port",
        "transaction_read_only", "migrations",
    }:
        raise DeploymentError("production migration ledger returned invalid shape")
    ledger = observed["migrations"]
    if (
        not isinstance(ledger, list)
        or any(
            not isinstance(item, dict)
            or set(item) != {"filename", "checksum_sha256"}
            or not re.fullmatch(r"(?:r[0-9]+_v3/)?[0-9]{3}_[a-z0-9_]+\.sql", str(item["filename"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["checksum_sha256"]))
            for item in ledger
        )
        or len({item["filename"] for item in ledger}) != len(ledger)
    ):
        raise DeploymentError("production migration ledger entries are invalid")
    expected = [
        {
            "filename": item["ledger_name"],
            "checksum_sha256": item["sha256"],
        }
        for item in schema["migration_set_entries"]
    ]
    if (
        observed["database_name"] != DATABASE_NAME
        or observed["server_address"] != "local"
        or observed["server_port"] != 5432
        or observed["transaction_read_only"] != "on"
        or ledger != expected
    ):
        raise DeploymentError("production_migration_authority_absent_or_schema_incompatible")


def validate_candidate(
    candidate_path: Path, checksum_path: Path, schema: dict[str, Any]
) -> tuple[dict[str, Any], str, bytes]:
    checksum = verify_checksum(candidate_path, checksum_path)
    try:
        candidate_bytes = candidate_path.read_bytes()
        candidate = json.loads(candidate_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError("unable to freeze candidate manifest") from exc
    if (
        not isinstance(candidate, dict)
        or hashlib.sha256(candidate_bytes).hexdigest() != checksum
    ):
        raise DeploymentError("candidate manifest changed during validation")
    tool = manifest_tool()
    try:
        tool.validate_manifest(candidate, purpose="deploy", current_migration_set=schema["migration_set_identity"])
    except tool.ManifestError as exc:
        raise DeploymentError(f"candidate manifest is not production-schema compatible: {exc}") from exc
    if candidate.get("rollback", {}).get("application_only_eligible") is not True:
        raise DeploymentError("candidate is not eligible as an application-only rollback release")
    return candidate, checksum, candidate_bytes


def compose_env(external: dict[str, Any], release: dict[str, Any], env_file: Path, origin: str, docker_env: dict[str, str]) -> dict[str, str]:
    return {
        **docker_env,
        "V3_PRODUCTION_API_IMAGE": release["images"]["backend"],
        "V3_PRODUCTION_WEB_IMAGE": release["images"]["web"],
        "V3_PRODUCTION_SOURCE_SHA": release["git_sha"],
        "V3_PRODUCTION_API_ENV_FILE": str(env_file),
        "V3_PRODUCTION_ORIGIN_BIND": origin,
        "V3_PRODUCTION_APP_NETWORK": external["application_network"],
    }


def compose_base(compose: Path) -> list[str]:
    return ["docker", "compose", "--project-name", PROJECT, "--file", str(compose)]


def verify_image(image: str, sha: str, env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    raw = runner(["docker", "image", "inspect", "--format", "{{json .}}", image], env=env).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError("pulled image inspection is invalid") from exc
    labels = (value.get("Config") or {}).get("Labels") or {}
    digests = value.get("RepoDigests") or []
    if labels.get("org.opencontainers.image.revision") != sha or image not in digests:
        raise DeploymentError("pulled image digest/build SHA verification failed")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def get(origin: str, path: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(origin + path, headers={"User-Agent": "edfinder-v3-production-promote/1"})
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect
        ).open(request, timeout=10) as response:
            body = response.read(MAX_SMOKE + 1)
            return response.status, body, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_SMOKE + 1), exc.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise DeploymentError("origin request failed") from exc


def post(origin: str, path: str, body: dict[str, Any]) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        origin + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "edfinder-v3-production-promote/1"},
    )
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect
        ).open(request, timeout=10) as response:
            return response.status, response.read(MAX_SMOKE + 1), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read(MAX_SMOKE + 1), exc.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise DeploymentError("origin request failed") from exc


def f2d_behavioural_probes(
    origin: str, outcomes: list[dict[str, Any]], generation: dict[str, Any] | None = None,
) -> None:
    # Match the actual publication resolver, including a later rollout's
    # unfinished products. Once both are published, valid bounds must return 200.
    products = {row["product_code"]: row for row in (generation or {}).get("finder_products", [])}
    unavailable = []
    for code in ("system_archetype", "system_search"):
        product = products.get(code)
        if product is None:
            unavailable.append(code + "=MISSING")
        elif product["lifecycle_state"] != "READY":
            unavailable.append(code + "=" + product["lifecycle_state"])
        elif product["published_at"] is None:
            unavailable.append(code + "=READY-unpublished")
    valid_status = 503 if unavailable else 200
    pairs = [
        ("GET", "/api/archetypes/rankings?archetype=paradise&offset=9999&limit=1", None, valid_status),
        ("GET", "/api/archetypes/rankings?archetype=paradise&offset=9999&limit=2", None, 422),
        ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 1}, valid_status),
        ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 2}, 422),
    ]
    expected_not_ready = (
        "Finder ranking products are not available for the published generation "
        "(" + ", ".join(unavailable) + ")."
    )
    for method, path, body, expected in pairs:
        reason_verified = None
        try:
            status, payload, _ = get(origin, path) if body is None else post(origin, path, body)
            if len(payload) > MAX_SMOKE:
                status = None
            if expected == 503:
                try:
                    parsed = json.loads(payload)
                    reason_verified = isinstance(parsed, dict) and parsed.get("detail") == expected_not_ready
                except (ValueError, UnicodeError):
                    reason_verified = False
        except DeploymentError:
            status = None
        outcomes.append({"method": method, "path": path, "body": body,
                         "status": status, "expected_status": expected,
                         "not_ready_reason_verified": reason_verified})
    if any(row["status"] != row["expected_status"]
           or row["expected_status"] == 503 and row["not_ready_reason_verified"] is not True
           for row in outcomes):
        raise DeploymentError("behavioural_probe_pairs_failed")


def _exact_integral_bound(value: object, expected: int) -> bool:
    if type(value) is int:
        return value == expected
    return type(value) is float and value.is_integer() and value == expected


def verify_f2d_openapi_contract(origin: str) -> dict[str, Any]:
    status, payload, _ = get(origin, "/openapi.json")
    if status != 200 or len(payload) > MAX_SMOKE:
        raise DeploymentError("f2d_openapi_contract_invalid:response")
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise DeploymentError("f2d_openapi_contract_invalid:json") from exc
    if not isinstance(document, dict):
        raise DeploymentError("f2d_openapi_contract_invalid:document")

    def resolve(value: object) -> dict[str, Any]:
        seen: set[str] = set()
        for _ in range(16):
            if not isinstance(value, dict):
                raise DeploymentError("f2d_openapi_contract_invalid:schema")
            if "$ref" not in value:
                return value
            reference = value["$ref"]
            if (
                not isinstance(reference, str) or len(reference) > 512
                or not reference.startswith("#/components/") or reference in seen
            ):
                raise DeploymentError("f2d_openapi_contract_invalid:reference")
            seen.add(reference)
            value = document
            for component in reference[2:].split("/"):
                component = component.replace("~1", "/").replace("~0", "~")
                if not isinstance(value, dict) or component not in value:
                    raise DeploymentError("f2d_openapi_contract_invalid:reference")
                value = value[component]
        raise DeploymentError("f2d_openapi_contract_invalid:reference_depth")

    try:
        paths = resolve(document.get("paths"))
        ranking = resolve(resolve(paths["/api/archetypes/rankings"])["get"])
        parameters = ranking["parameters"]
        if not isinstance(parameters, list) or not 1 <= len(parameters) <= 128:
            raise DeploymentError("f2d_openapi_contract_invalid:parameters")
        query: dict[str, dict[str, Any]] = {}
        for item in parameters:
            parameter = resolve(item)
            if parameter.get("in") != "query":
                continue
            name = parameter.get("name")
            if not isinstance(name, str) or name in query:
                raise DeploymentError("f2d_openapi_contract_invalid:parameters")
            query[name] = resolve(parameter.get("schema"))
        floor = query["min_score"]
        if floor.get("type") != "integer" or floor.get("enum") != [60, 76, 88]:
            raise DeploymentError("f2d_openapi_contract_invalid:min_score")
        search = resolve(resolve(paths["/api/local/search"])["post"])
        request = resolve(search["requestBody"])
        body = resolve(request["content"]["application/json"]["schema"])
        properties = resolve(body.get("properties"))
        bounds = {
            "ranking.limit": (query["limit"], 1, 500),
            "ranking.offset": (query["offset"], 0, 9999),
            "search.size": (resolve(properties["size"]), 1, 500),
            "search.from": (resolve(properties["from"]), 0, 2_147_483_647),
        }
        recorded: dict[str, Any] = {"min_score": [60, 76, 88]}
        for field, (schema, minimum, maximum) in bounds.items():
            # FastAPI's OpenAPI model types body-schema bounds as float, so a
            # request-body field serves `500.0` where a query parameter serves
            # `500`. Both are the same JSON Schema number; accept an integral
            # float only when it equals the exact expected bound (never bool).
            if (
                schema.get("type") != "integer"
                or not _exact_integral_bound(schema.get("minimum"), minimum)
                or not _exact_integral_bound(schema.get("maximum"), maximum)
            ):
                raise DeploymentError("f2d_openapi_contract_invalid:" + field)
            recorded[field] = {"minimum": minimum, "maximum": maximum}
    except (KeyError, TypeError) as exc:
        raise DeploymentError("f2d_openapi_contract_invalid:shape") from exc
    return {"status": status, "contracts": recorded}


def verify_f2d_image_contract(
    slot: str, attestation: dict[str, Any], env: dict[str, str], runner: Callable[..., Any],
) -> None:
    container = CONTAINERS[f"api-{slot}"]
    image = runner(["docker", "inspect", "--format", "{{.Config.Image}}", container], env=env).stdout.strip()
    if image != attestation["images"]["backend"]:
        raise DeploymentError("f2d_deployed_image_identity_mismatch")
    result = runner(
        ["docker", "exec", "-i", "--env", "PYTHONDONTWRITEBYTECODE=1", container,
         "/app/.venv/bin/python", "-"], env=env, input_text=F2D_IMAGE_CONTRACT_PROGRAM,
    )
    if len(result.stdout.encode()) > MAX_JSON:
        raise DeploymentError("f2d_deployed_ranking_identity_invalid")
    try:
        identity = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise DeploymentError("f2d_deployed_ranking_identity_invalid") from exc
    if identity != {"ranking_version": attestation["ranking_version"],
                    "ranking_sha256": attestation["ranking_sha256"], "publication_gate": True}:
        raise DeploymentError("f2d_deployed_ranking_identity_mismatch")


def verify_f2d_rejections(origin: str) -> list[dict[str, Any]]:
    requests = [
        ("GET", "/api/archetypes/rankings?archetype=paradise&galaxy_region=1", None),
        ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development",
                                      "body_filters": {"elw_count": {"min": 1}}, "size": 1}),
    ]
    outcomes = []
    for method, path, body in requests:
        status, payload, _ = get(origin, path) if body is None else post(origin, path, body)
        outcomes.append({"method": method, "path": path, "body": body,
                         "status": status, "expected_status": 422})
        if status != 422 or len(payload) > MAX_SMOKE:
            raise DeploymentError("f2d_hard_filter_rejection_failed")
    return outcomes


def smoke(origin: str, sha: str) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    bodies: dict[str, bytes] = {}
    for path in ("/", "/api/health", "/openapi.json", "/api/v1/auth/session"):
        status, body, content_type = get(origin, path)
        if not 200 <= status < 300 or len(body) > MAX_SMOKE:
            raise DeploymentError(f"smoke failed: {path}")
        outcomes[path] = {"status": status, "bytes": len(body), "content_type": content_type[:128]}
        bodies[path] = body
    try:
        health = json.loads(bodies["/api/health"])
        session = json.loads(bodies["/api/v1/auth/session"])
        openapi = json.loads(bodies["/openapi.json"])
    except json.JSONDecodeError as exc:
        raise DeploymentError("smoke JSON response invalid") from exc
    if health.get("status") != "ok" or health.get("database") != "connected" or health.get("build_sha") != sha:
        raise DeploymentError("health release identity mismatch")
    if session.get("authenticated") is not False or session.get("user") is not None:
        raise DeploymentError("anonymous session smoke failed")
    paths = openapi.get("paths") if isinstance(openapi, dict) else None
    if not isinstance(paths, dict) or not {
        "/api/health",
        "/api/v1/auth/session",
    }.issubset(paths):
        raise DeploymentError("OpenAPI smoke routes missing")
    marker = f'name="edfinder-build-sha" content="{sha}"'.encode()
    if bodies["/"].count(marker) != 1:
        raise DeploymentError("Svelte HTML release identity mismatch")
    return outcomes


def wait_ready(origin: str, sha: str) -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT
    while time.monotonic() < deadline:
        try:
            status, body, _ = get(origin, "/api/health")
            value = json.loads(body)
            if status == 200 and value.get("status") == "ok" and value.get("database") == "connected" and value.get("build_sha") == sha:
                return
        except (DeploymentError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise DeploymentError("candidate readiness timed out")


def load_current(directory: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    pointer = load_json(directory / "current.json", "current production release pointer")
    if set(pointer) != {"schema_version", "receipt_file", "receipt_sha256", "manifest_file", "manifest_sha256"} or pointer.get("schema_version") != CURRENT_SCHEMA:
        raise DeploymentError("current production release pointer is invalid")
    for key in ("receipt_file", "manifest_file"):
        if not isinstance(pointer[key], str) or Path(pointer[key]).name != pointer[key]:
            raise DeploymentError("current production release filename is unsafe")
    if not re.fullmatch(
        r"[0-9a-f]{40}-[1-9][0-9]{0,19}-[0-9a-f]{64}\.json",
        pointer["receipt_file"],
    ) or pointer["manifest_file"] != pointer["receipt_file"].removesuffix(
        ".json"
    ) + ".release.json":
        raise DeploymentError("current production release filename is invalid")
    receipt_path = directory / pointer["receipt_file"]
    manifest_path = directory / pointer["manifest_file"]
    receipt_sidecar = Path(str(receipt_path) + ".sha256")
    manifest_sidecar = Path(str(manifest_path) + ".sha256")
    if any(
        path.is_symlink()
        for path in (receipt_path, manifest_path, receipt_sidecar, manifest_sidecar)
    ):
        raise DeploymentError("current production release path is unsafe")
    if (
        sha256_file(receipt_path) != pointer["receipt_sha256"]
        or sha256_file(manifest_path) != pointer["manifest_sha256"]
        or verify_checksum(receipt_path, receipt_sidecar) != pointer["receipt_sha256"]
        or verify_checksum(manifest_path, manifest_sidecar) != pointer["manifest_sha256"]
    ):
        raise DeploymentError("current production release checksum mismatch")
    receipt = load_json(receipt_path, "accepted production receipt")
    manifest = load_json(manifest_path, "accepted production manifest")
    if (
        receipt.get("schema_version") != RECEIPT_SCHEMA
        or receipt.get("status") != "accepted"
        or receipt.get("target", {}).get("hostname") != EXPECTED_HOST
        or receipt.get("target", {}).get("fqdn") != EXPECTED_FQDN
        or receipt.get("target", {}).get("production") is not True
        or receipt.get("compose_project") != PROJECT
        or receipt.get("source_sha") != manifest.get("git_sha")
        or receipt.get("images") != manifest.get("images")
        or receipt.get("manifest_sha256") != pointer["manifest_sha256"]
        or not RUN_ID.fullmatch(str(receipt.get("release_run_id", "")))
    ):
        raise DeploymentError("accepted production receipt does not bind its release")
    return receipt, manifest, manifest_path


def validate_prior_runtime(
    receipt: dict[str, Any], manifest: dict[str, Any], schema: dict[str, Any],
    env: dict[str, str], runner: Callable[..., subprocess.CompletedProcess[str]],
    compatibility: dict[str, Any] | None = None,
    *, allow_incompatible_running_image: bool = False,
) -> str:
    if compatibility and "minimum_schema_compatible_image" in compatibility and not allow_incompatible_running_image:
        validate_release_compatibility_shape(compatibility)
        require_f2d_rollback_image(manifest["images"]["backend"], compatibility)
    slot = receipt.get("active_slot")
    recorded_migration_set = receipt.get("migration_set_identity")
    if slot not in SLOTS or not SHA256.fullmatch(str(recorded_migration_set or "")):
        raise DeploymentError("prior accepted production receipt is invalid")
    tool = manifest_tool()
    try:
        tool.validate_manifest(
            manifest,
            purpose="rollback",
            current_migration_set=recorded_migration_set,
        )
    except tool.ManifestError as exc:
        raise DeploymentError("prior accepted release did not support its recorded schema") from exc
    current_migration_set = schema["migration_set_identity"]
    if current_migration_set != recorded_migration_set:
        try:
            tool.validate_manifest(
                manifest, purpose="rollback", current_migration_set=current_migration_set
            )
        except tool.ManifestError:
            validate_release_compatibility_shape(compatibility)
            assert compatibility is not None
            if (
                compatibility["source_sha"] != receipt.get("source_sha")
                or compatibility["release_run_id"] != str(receipt.get("release_run_id", ""))
                or compatibility["manifest_sha256"] != receipt.get("manifest_sha256")
                or compatibility["images"] != receipt.get("images")
                or compatibility["images"] != manifest.get("images")
                or current_migration_set not in compatibility["compatible_migration_sets"]
            ):
                raise DeploymentError(
                    "prior accepted release lacks reviewed compatibility with current schema"
                )
    for image in manifest["images"].values():
        verify_image(image, manifest["git_sha"], env, runner)
    for service in (f"api-{slot}", f"web-{slot}"):
        raw = runner(
            [
                "docker", "inspect", "--format",
                "{{.State.Running}}\t{{.Config.Image}}\t"
                "{{index .Config.Labels \"org.opencontainers.image.revision\"}}",
                CONTAINERS[service],
            ],
            env=env,
        ).stdout.strip().split("\t")
        expected_image = manifest["images"][
            "backend" if service.startswith("api-") else "web"
        ]
        if raw != ["true", expected_image, manifest["git_sha"]]:
            raise DeploymentError("prior accepted application container drifted")
    smoke("http://127.0.0.1:58080", manifest["git_sha"])
    return slot


def persist_accepted(
    directory: Path, receipt: dict[str, Any], manifest_bytes: bytes
) -> None:
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    stem = f"{receipt['source_sha']}-{receipt['release_run_id']}-{receipt['manifest_sha256']}"
    receipt_name = stem + ".json"
    manifest_name = stem + ".release.json"
    receipt_sidecar = receipt_name + ".sha256"
    manifest_sidecar = manifest_name + ".sha256"
    for name in (
        receipt_name, manifest_name, receipt_sidecar, manifest_sidecar,
        "current.json",
    ):
        if Path(name).name != name:
            raise DeploymentError("unsafe receipt identity")
    current_path = directory / "current.json"
    if current_path.is_symlink():
        raise DeploymentError("current production release pointer is unsafe")
    try:
        prior_pointer = current_path.read_bytes() if current_path.exists() else None
    except OSError as exc:
        raise DeploymentError("unable to preserve current production release pointer") from exc
    if prior_pointer is not None and len(prior_pointer) > MAX_JSON:
        raise DeploymentError("current production release pointer is oversized")

    def atomic(name: str, data: bytes) -> None:
        handle, temp_name = tempfile.mkstemp(prefix=".v3-production-", dir=directory)
        try:
            os.fchmod(handle, 0o600)
            with os.fdopen(handle, "wb") as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.replace(temp_name, directory / name)
        finally:
            try: os.unlink(temp_name)
            except FileNotFoundError: pass

    def fsync_directory() -> None:
        directory_handle = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_handle)
        finally:
            os.close(directory_handle)

    if any(
        (directory / name).exists()
        for name in (receipt_name, manifest_name, receipt_sidecar, manifest_sidecar)
    ):
        raise DeploymentError("immutable production receipt identity already exists")
    created: list[str] = []
    pointer_replaced = False
    try:
        atomic(receipt_name, receipt_bytes)
        created.append(receipt_name)
        atomic(manifest_name, manifest_bytes)
        created.append(manifest_name)
        atomic(
            receipt_sidecar,
            f"{hashlib.sha256(receipt_bytes).hexdigest()}  {receipt_name}\n".encode(),
        )
        created.append(receipt_sidecar)
        atomic(
            manifest_sidecar,
            f"{hashlib.sha256(manifest_bytes).hexdigest()}  {manifest_name}\n".encode(),
        )
        created.append(manifest_sidecar)
        pointer = {
            "schema_version": CURRENT_SCHEMA,
            "receipt_file": receipt_name,
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "manifest_file": manifest_name,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }
        fsync_directory()
        atomic(
            "current.json",
            (json.dumps(pointer, sort_keys=True, indent=2) + "\n").encode(),
        )
        pointer_replaced = True
        fsync_directory()
    except Exception:
        pointer_restored = not pointer_replaced
        if pointer_replaced:
            try:
                if prior_pointer is None:
                    current_path.unlink()
                else:
                    atomic("current.json", prior_pointer)
                fsync_directory()
                pointer_restored = True
            except Exception as restore_error:
                raise DeploymentError(
                    "accepted production pointer restoration failed; candidate artifacts retained"
                ) from restore_error
        if pointer_restored:
            for name in reversed(created):
                try:
                    (directory / name).unlink()
                except OSError:
                    pass
        try:
            fsync_directory()
        except OSError:
            pass
        raise


def persist_failure(directory: Path, receipt: dict[str, Any]) -> str:
    data = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = (
        f"failed-{receipt.get('source_sha', 'unknown')}-"
        f"{receipt.get('release_run_id', 'unknown')}-{stamp}-{os.getpid()}.json"
    )
    if Path(basename).name != basename:
        raise DeploymentError("unsafe failure receipt identity")
    path = directory / basename
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    sidecar = Path(str(path) + ".sha256")
    checksum = hashlib.sha256(data).hexdigest()
    sidecar.write_text(f"{checksum}  {basename}\n", encoding="utf-8")
    os.chmod(sidecar, 0o600)
    return basename


def freeze_env(
    source: Path, directory: Path, expected_uid: int, expected_mode: str,
) -> tuple[Path, tuple[int, int, int, int, int, str]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != expected_uid
            or stat.S_IMODE(before.st_mode) != int(expected_mode, 8)
        ):
            raise DeploymentError("authorized production API env file is unsafe")
        if before.st_size > MAX_ENV_FILE:
            raise DeploymentError("authorized production API env file exceeds size limit")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        current = source.lstat()
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_uid)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_uid)
            or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise DeploymentError("authorized production API env file changed while opening")
    finally:
        os.close(descriptor)
    fingerprint = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode,
        before.st_uid, hashlib.sha256(data).hexdigest(),
    )
    handle, name = tempfile.mkstemp(prefix=".v3-production-env-", dir=directory)
    os.fchmod(handle, 0o600)
    with os.fdopen(handle, "wb") as output:
        output.write(data); output.flush(); os.fsync(output.fileno())
    return Path(name), fingerprint


def verify_env_unchanged(
    source: Path, fingerprint: tuple[int, int, int, int, int, str],
) -> None:
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_ENV_FILE:
            raise DeploymentError("authorized production API env file is unsafe")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        current = source.lstat()
    finally:
        os.close(descriptor)
    observed = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode,
        before.st_uid, digest.hexdigest(),
    )
    stable = (
        before.st_dev, before.st_ino, before.st_size, before.st_mode, before.st_uid
    ) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mode, after.st_uid
    )
    if (
        observed != fingerprint
        or not stable
        or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise DeploymentError("authorized production API env file changed during promotion")


def acquire_lock(directory: Path) -> Any:
    handle = (directory / "deploy.lock").open("a+", encoding="utf-8")
    os.fchmod(handle.fileno(), 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise DeploymentError("production deployment lock unavailable") from exc
    return handle


def validate_runtime_directory(supplied: Path) -> Path:
    runtime_directory = supplied.resolve()
    if (
        not supplied.is_absolute()
        or supplied != runtime_directory
        or supplied.is_symlink()
        or not runtime_directory.is_dir()
        or runtime_directory.stat().st_uid != os.geteuid()
        or stat.S_IMODE(runtime_directory.stat().st_mode) != 0o700
    ):
        raise DeploymentError("private production operation runtime directory is unsafe")
    return runtime_directory


def promote(args: argparse.Namespace, authority: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = run_command) -> dict[str, Any]:
    global _PREMUTATION_FAILURE_RECEIPT_DIR
    _PREMUTATION_FAILURE_RECEIPT_DIR = None
    external = authority["external_authority"]
    receipt_operation = (
        "production-preflight" if args.operation == "preflight" else "production-promotion"
    )
    env = base_env(external)
    exact_host_guard(runner)
    docker_context_guard(env, runner)
    if args.operation == "promote":
        # Before reading application secrets, opening the deployment lock,
        # creating receipts, pulling an image or changing any container.
        try:
            require_purge_clear(env, runner)
        except DeploymentError as exc:
            receipt = stopped_receipt(authority, [str(exc)])
            receipt.update(database_access_performed=True, filesystem_writes_performed=False)
            raise OperationFailed(receipt) from exc
    secure_path(Path(external["api_env_file"]), external["api_env_owner_uid"], external["api_env_mode"], directory=False)
    receipt_dir = Path(external["receipt_directory"])
    secure_path(receipt_dir, external["receipt_owner_uid"], external["receipt_mode"], directory=True)
    # Only an exact verified host and receipt store may receive a durable
    # pre-mutation cancellation receipt.
    _PREMUTATION_FAILURE_RECEIPT_DIR = receipt_dir
    schema_path = Path(external["schema_identity_file"])
    secure_path(
        schema_path, external["schema_identity_owner_uid"],
        external["schema_identity_mode"], directory=False,
    )
    validate_compose(args.compose, authority, env, runner)
    schema = validate_schema_file(schema_path, external["schema_identity_sha256"])
    network_slots: set[str] = set()
    if args.mode == "upgrade":
        network_receipt, _network_manifest, _network_path = load_current(receipt_dir)
        network_active_slot = network_receipt.get("active_slot")
        if network_active_slot not in SLOTS:
            raise DeploymentError("accepted production network slot is invalid")
        network_slots.add(network_active_slot)
    validate_network(external, schema, network_slots, env, runner)
    live_capacity = live_capacity_guard()
    env_files_read = False
    preflight_database_access_attempted = False
    preflight_database_access_performed = False
    rollback_artifact: dict[str, Any] | None = None
    f2d_generation: dict[str, Any] = {}
    generation_rule: str | None = None

    def mark_env_file_read() -> None:
        nonlocal env_files_read
        env_files_read = True

    try:
        api_database_identity = database_identity_from_env(
            Path(external["api_env_file"]), on_read=mark_env_file_read
        )
        if api_database_identity != schema["database_identity"]:
            raise DeploymentError(
                "production API database target does not match schema authority"
            )
        candidate, candidate_sum, candidate_bytes = validate_candidate(
            args.candidate, args.candidate_checksum, schema
        )
        if not RUN_ID.fullmatch(args.candidate_run_id or ""):
            raise DeploymentError("authenticated candidate release run ID required")
        attestation_path = getattr(args, "candidate_attestation", None)
        if attestation_path is None:
            adjacent = args.candidate.parent / "f2d-release-attestation.json"
            if adjacent.exists() or adjacent.is_symlink():
                attestation_path = adjacent
        f2d_attestation = None if attestation_path is None else load_json(attestation_path, "F2d candidate attestation")
        f2d_release = is_f2d_release(candidate, schema, f2d_attestation)
        if f2d_release:
            validate_f2d_migrations(schema, registered_f2d_migrations())
            validate_f2d_attestation(f2d_attestation, candidate, candidate_sum, args.candidate_run_id, schema)
            validate_f2d_boundary(f2d_attestation, authority["accepted_release_schema_compatibility"])
            generation_rule = f2d_generation_rule(authority["accepted_release_schema_compatibility"])
            if args.mode != "upgrade":
                raise DeploymentError("f2d_release_requires_receipt_backed_upgrade")
        protected = set(authority["preservation_contract"]["exact_containers"])
        protected_before = container_snapshot(protected, env, runner)
        all_before = all_container_snapshot(env, runner)

        if args.mode == "bootstrap":
            prior_slot_for_preflight = None
            if set(CONTAINERS.values()) & set(all_before):
                raise DeploymentError("bootstrap requires production slot absence")
            for legacy_name in (LEGACY_API, LEGACY_ORIGIN):
                if not all_before.get(legacy_name, "").endswith(":running"):
                    raise DeploymentError(
                        "bootstrap requires running legacy application services"
                    )
        else:
            prior_for_preflight, prior_manifest_for_preflight, _ = load_current(
                receipt_dir
            )
            prior_slot_for_preflight = validate_prior_runtime(
                prior_for_preflight, prior_manifest_for_preflight, schema, env, runner,
                authority["accepted_release_schema_compatibility"],
                allow_incompatible_running_image=True,
            )
        verify_origin_ownership(args.mode, prior_slot_for_preflight, env, runner)
        verify_edge_routes_to_active_origin()

        if args.operation == "preflight":
            preflight_database_access_attempted = True
            verify_live_schema(schema, env, runner)
            preflight_database_access_performed = True
            if f2d_release:
                f2d_generation = verify_f2d_generation(
                    env, runner, authority["accepted_release_schema_compatibility"], f2d_generation,
                )
                rollback_manifest, rollback_source = select_f2d_rollback(
                    receipt_dir, f2d_attestation, schema, candidate,
                    authority["accepted_release_schema_compatibility"],
                )
                rollback_artifact = f2d_rollback_receipt(rollback_manifest, rollback_source)
                # The first F2d candidate may exist only in the registry. Its
                # images are pulled and verified by promote before cutover.
                if rollback_source == "recorded_artifact":
                    for image in rollback_manifest["images"].values():
                        verify_image(image, rollback_manifest["git_sha"], env, runner)
            verify_snapshot(protected_before, env, runner)
            verify_unrelated_snapshot(all_before, set(), env, runner)
            live_capacity = live_capacity_guard()
            return {
                **stopped_receipt(authority, [], operation="production-preflight"),
                "status": "preflight-passed", "mode": args.mode,
                "source_sha": candidate["git_sha"], "release_run_id": args.candidate_run_id,
                "manifest_sha256": candidate_sum, "migration_set_identity": schema["migration_set_identity"],
                "images": candidate["images"],
                "rollback_compatible": args.mode == "upgrade",
                **({"accepted_release_schema_compatibility": f2d_attestation,
                    "rollback": rollback_artifact, "f2d_generation": f2d_generation,
                    "f2d_generation_rule": generation_rule}
                   if f2d_release else {}),
                "live_capacity": live_capacity,
                "database_access_performed": True,
                "env_files_read": True,
            }
        if args.runtime_directory is None:
            raise DeploymentError("private production operation runtime directory required")
        runtime_directory = validate_runtime_directory(args.runtime_directory)
        lock = acquire_lock(receipt_dir)
    except OperationFailed:
        raise
    except Exception as exc:
        failure = (
            str(exc)
            if isinstance(exc, DeploymentError)
            else f"internal_failure:{type(exc).__name__}"
        )
        receipt = stopped_receipt(authority, [failure], operation=receipt_operation)
        receipt["env_files_read"] = env_files_read
        if generation_rule is not None:
            receipt.update(f2d_generation=f2d_generation, f2d_generation_rule=generation_rule)
        if rollback_artifact is not None:
            receipt["f2d_rollback_artifact"] = rollback_artifact
        if preflight_database_access_attempted:
            receipt.update(
                database_access_performed=(
                    True if preflight_database_access_performed else None
                ),
                database_access_may_have_been_performed=(
                    not preflight_database_access_performed
                ),
            )
        raise OperationFailed(receipt) from exc

    snapshot: Path | None = None
    docker_config: str | None = None
    mutation_started = False
    cutover_started = False
    image_pull_attempted = False
    pulled_images: list[str] = []
    database_verified = False
    prior_receipt: dict[str, Any] | None = None
    prior_manifest: dict[str, Any] | None = None
    target_slot = "blue"
    f2d_probe_statuses: list[dict[str, Any]] = []
    f2d_image_contract: dict[str, Any] | None = None
    rollback_manifest: dict[str, Any] | None = None
    try:
        live_capacity = live_capacity_guard()
        verify_live_schema(schema, env, runner)
        database_verified = True
        if f2d_release:
            f2d_generation = verify_f2d_generation(
                env, runner, authority["accepted_release_schema_compatibility"], f2d_generation,
            )
            rollback_manifest, rollback_source = select_f2d_rollback(
                receipt_dir, f2d_attestation, schema, candidate,
                authority["accepted_release_schema_compatibility"],
            )
            rollback_artifact = f2d_rollback_receipt(rollback_manifest, rollback_source)
            if rollback_source == "recorded_artifact":
                for image in rollback_manifest["images"].values():
                    verify_image(image, rollback_manifest["git_sha"], env, runner)
        current_path = receipt_dir / "current.json"
        if args.mode == "bootstrap":
            if current_path.exists():
                raise DeploymentError("bootstrap requires no accepted production release")
            prior_slot = None
        else:
            prior_receipt, prior_manifest, _ = load_current(receipt_dir)
            prior_slot = validate_prior_runtime(
                prior_receipt, prior_manifest, schema, env, runner,
                authority["accepted_release_schema_compatibility"],
                allow_incompatible_running_image=True,
            )
            if prior_manifest.get("git_sha") == candidate.get("git_sha"):
                raise DeploymentError("candidate cannot be its own prior release")
            target_slot = "green" if prior_slot == "blue" else "blue"
        validate_network(
            external, schema, {prior_slot} if prior_slot is not None else set(),
            env, runner,
        )
        verify_origin_ownership(args.mode, prior_slot, env, runner)
        verify_edge_routes_to_active_origin()
        snapshot, fingerprint = freeze_env(
            Path(external["api_env_file"]), runtime_directory,
            external["api_env_owner_uid"], external["api_env_mode"],
        )
        if database_identity_from_env(snapshot) != schema["database_identity"]:
            raise DeploymentError("frozen production API database target does not match schema authority")
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        if (
            args.registry_token_file is None
            or not args.registry_token_file.is_file()
            or args.registry_token_file.is_symlink()
            or not isinstance(args.registry_username, str)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.registry_username)
        ):
            raise DeploymentError("ephemeral production registry authority is missing")
        token_details = args.registry_token_file.stat(follow_symlinks=False)
        if (
            token_details.st_uid != os.geteuid()
            or stat.S_IMODE(token_details.st_mode) != 0o600
            or token_details.st_nlink != 1
        ):
            # Report the observed metadata: these are not secrets, and without
            # them a rejection here is impossible to diagnose from the receipt.
            raise DeploymentError(
                "ephemeral registry token path is unsafe"
                f" (uid={token_details.st_uid} euid={os.geteuid()}"
                f" mode={stat.S_IMODE(token_details.st_mode):04o}"
                f" nlink={token_details.st_nlink})"
            )
        if args.registry_token_file.stat().st_size > MAX_REGISTRY_TOKEN:
            raise DeploymentError("ephemeral registry token exceeds size limit")
        token = args.registry_token_file.read_text(encoding="utf-8").strip()
        if not token or "\n" in token or "\r" in token:
            raise DeploymentError("ephemeral registry token is invalid")
        docker_config = tempfile.mkdtemp(
            prefix=".v3-production-docker-", dir=runtime_directory
        )
        os.chmod(docker_config, 0o700)
        env["DOCKER_CONFIG"] = docker_config
        runner(
            [
                "docker", "login", "ghcr.io", "--username",
                args.registry_username, "--password-stdin",
            ],
            env=env,
            input_text=token + "\n",
        )
        token = ""
        for image in candidate["images"].values():
            image_pull_attempted = True
            runner(["docker", "pull", image], env=env)
            verify_image(image, candidate["git_sha"], env, runner)
            pulled_images.append(image)
        release_env = compose_env(external, candidate, snapshot, external["staging_origin_bind"], env)
        base = compose_base(args.compose)
        selected = [f"api-{target_slot}", f"web-{target_slot}"]
        mutation_started = True
        runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", *selected], env=release_env)
        wait_ready("http://" + external["staging_origin_bind"], candidate["git_sha"])
        staging_smoke = smoke("http://" + external["staging_origin_bind"], candidate["git_sha"])
        if f2d_release:
            verify_f2d_image_contract(target_slot, f2d_attestation, env, runner)
            f2d_image_contract = verify_f2d_openapi_contract("http://" + external["staging_origin_bind"])
            f2d_image_contract["hard_filter_rejections"] = verify_f2d_rejections("http://" + external["staging_origin_bind"])
        active_owner = LEGACY_ORIGIN if args.mode == "bootstrap" else CONTAINERS[
            f"web-{prior_slot}"
        ]
        verify_exact_origin_bindings(
            active_owner, CONTAINERS[f"web-{target_slot}"], env, runner
        )
        verify_snapshot(protected_before, env, runner)
        controlled = {CONTAINERS[item] for item in selected}
        verify_unrelated_snapshot(all_before, controlled, env, runner)
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        verify_live_schema(schema, env, runner)
        staged_slots = {target_slot}
        if prior_slot is not None:
            staged_slots.add(prior_slot)
        validate_network(external, schema, staged_slots, env, runner)

        if f2d_release:
            # Recheck the applicable product-state rule immediately before switching.
            f2d_generation = verify_f2d_generation(
                env, runner, authority["accepted_release_schema_compatibility"], f2d_generation,
            )
        cutover_started = True
        if args.mode == "bootstrap":
            runner(["docker", "stop", LEGACY_ORIGIN], env=env)
        else:
            assert prior_slot is not None
            runner([*base, "stop", f"web-{prior_slot}"], env=release_env)
        active_env = compose_env(external, candidate, snapshot, external["active_origin_bind"], env)
        runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", f"web-{target_slot}"], env=active_env)
        wait_ready("http://" + external["active_origin_bind"], candidate["git_sha"])
        verify_exact_origin_bindings(
            CONTAINERS[f"web-{target_slot}"], None, env, runner
        )
        active_smoke = smoke("http://" + external["active_origin_bind"], candidate["git_sha"])
        if f2d_release:
            f2d_behavioural_probes("http://" + external["active_origin_bind"], f2d_probe_statuses, f2d_generation)
        public_smoke = smoke(external["public_origin"], candidate["git_sha"])
        verify_live_schema(schema, env, runner)
        verify_env_unchanged(Path(external["api_env_file"]), fingerprint)
        verify_snapshot(protected_before, env, runner)
        controlled.add(LEGACY_ORIGIN if args.mode == "bootstrap" else CONTAINERS[f"web-{prior_slot}"])
        if args.mode == "upgrade":
            assert prior_slot is not None
            runner([*base, "stop", f"api-{prior_slot}"], env=active_env)
            controlled.add(CONTAINERS[f"api-{prior_slot}"])
            runner(
                [*base, "rm", "--force", f"api-{prior_slot}", f"web-{prior_slot}"],
                env=active_env,
            )
        else:
            runner(["docker", "stop", LEGACY_API], env=env)
            controlled.add(LEGACY_API)
        validate_network(external, schema, {target_slot}, env, runner)
        verify_unrelated_snapshot(all_before, controlled, env, runner)
        changed_resources = [CONTAINERS[item] for item in selected]
        if args.mode == "bootstrap":
            changed_resources.extend([LEGACY_API, LEGACY_ORIGIN])
        else:
            assert prior_slot is not None
            changed_resources.extend(
                [CONTAINERS[f"api-{prior_slot}"], CONTAINERS[f"web-{prior_slot}"]]
            )
        receipt = {
            "schema_version": RECEIPT_SCHEMA, "operation": "production-promotion", "status": "accepted",
            "mode": args.mode, "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": authority["target"], "compose_project": PROJECT, "active_slot": target_slot,
            "source_sha": candidate["git_sha"], "release_run_id": args.candidate_run_id,
            "images": candidate["images"], "manifest_sha256": candidate_sum,
            "migration_set_identity": schema["migration_set_identity"],
            "changed_resources": changed_resources,
            "preserved_resources": protected_before, "staging_smoke": staging_smoke,
            "live_capacity": live_capacity,
            "active_smoke": active_smoke, "public_smoke": public_smoke,
            **({"accepted_release_schema_compatibility": f2d_attestation,
                "f2d_generation": f2d_generation, "f2d_generation_rule": generation_rule,
                "f2d_image_contract": f2d_image_contract,
                "f2d_behavioural_probes": f2d_probe_statuses,
                "minimum_schema_compatible_image": f2d_attestation["minimum_schema_compatible_image"],
                "rollback_targets": trim_rollback_targets(f2d_attestation["rollback_targets"], f2d_attestation["minimum_schema_compatible_image"]),
                "incompatible_rollback_images": [prior_manifest["images"]["backend"]]
                    if prior_manifest["images"]["backend"] not in f2d_attestation["rollback_targets"] else [],
                } if f2d_release else {}),
            "rollback": {"kind": "none-first-promotion"} if prior_receipt is None else {
                "kind": "prior-accepted-immutable-release", "source_sha": prior_receipt["source_sha"],
                "release_run_id": prior_receipt["release_run_id"], "schema_compatible": True,
            },
            "database_access_performed": True, "database_writes_performed": False,
            "migrations_performed": False, "application_data_writes_performed": False,
            "image_pulls_performed": True, "service_changes_performed": True,
            "edge_recreated": False, "protected_resources_changed": False,
            "filesystem_writes_performed": True, "env_contents_recorded": False,
            "env_files_read": True,
            "private_keys_read": False,
        }
        if f2d_release:
            receipt["rollback"] = rollback_artifact
        if _CANCELLATION_CONTROLLER is not None:
            _CANCELLATION_CONTROLLER.mark_commit_started()
        persist_accepted(receipt_dir, receipt, candidate_bytes)
        return receipt
    except Exception as original:
        rollback = {"attempted": False, "status": "not-required"}
        if mutation_started:
            rollback = {"attempted": True, "status": "started"}
            try:
                base = compose_base(args.compose)
                candidate_env = compose_env(external, candidate, snapshot or Path(external["api_env_file"]), external["staging_origin_bind"], env)
                runner([*base, "stop", f"web-{target_slot}", f"api-{target_slot}"], env=candidate_env)
                runner([*base, "rm", "--force", f"web-{target_slot}", f"api-{target_slot}"], env=candidate_env)
                if cutover_started and args.mode == "bootstrap":
                    runner(["docker", "start", LEGACY_API], env=env)
                    runner(["docker", "start", LEGACY_ORIGIN], env=env)
                    wait_for_preserved_edge_route()
                    rollback = {"attempted": True, "status": "verified", "kind": "first-cutover-abort-to-preserved-origin", "accepted_release_rollback": False}
                elif cutover_started and prior_receipt is not None and prior_manifest is not None:
                    verify_live_schema(schema, env, runner)
                    recovery_manifest = rollback_manifest if f2d_release else prior_manifest
                    if f2d_release:
                        require_f2d_rollback_image(recovery_manifest["images"]["backend"], f2d_attestation)
                        for image in recovery_manifest["images"].values():
                            verify_image(image, recovery_manifest["git_sha"], env, runner)
                    rollback_tool = manifest_tool()
                    rollback_tool.validate_manifest(
                        recovery_manifest,
                        purpose="rollback",
                        current_migration_set=schema["migration_set_identity"],
                    )
                    prior_slot = prior_receipt["active_slot"]
                    prior_env = compose_env(external, recovery_manifest, snapshot or Path(external["api_env_file"]), external["active_origin_bind"], env)
                    runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", f"api-{prior_slot}", f"web-{prior_slot}"], env=prior_env)
                    wait_ready("http://" + external["active_origin_bind"], recovery_manifest["git_sha"])
                    smoke("http://" + external["active_origin_bind"], recovery_manifest["git_sha"])
                    smoke(external["public_origin"], recovery_manifest["git_sha"])
                    verify_snapshot(protected_before, env, runner)
                    rollback = {"attempted": True, "status": "verified", "kind": "prior-accepted-immutable-release", "source_sha": recovery_manifest["git_sha"], "schema_compatible": True}
                    if f2d_release:
                        rollback.update(f2d_rollback_receipt(recovery_manifest, rollback_source))
                else:
                    rollback = {"attempted": True, "status": "verified", "kind": "candidate-stage-removed"}
            except Exception as rollback_error:
                rollback = {"attempted": True, "status": "failed", "failure": type(rollback_error).__name__}
        failure = str(original) if isinstance(original, DeploymentError) else type(original).__name__
        resource_drift = failure in {
            "protected production container identity changed",
            "unrelated production container identity/state changed",
        }
        receipt = stopped_receipt(authority, [failure])
        if rollback_artifact is not None:
            receipt["f2d_rollback_artifact"] = rollback_artifact
        receipt.update(
            status="failed", source_sha=candidate["git_sha"], release_run_id=args.candidate_run_id,
            manifest_sha256=candidate_sum, migration_set_identity=schema["migration_set_identity"],
            database_access_performed=True if database_verified else None,
            database_access_may_have_been_performed=not database_verified,
            image_pull_attempted=image_pull_attempted,
            image_pulls_performed=(
                True if pulled_images else None if image_pull_attempted else False
            ),
            pulled_images_verified=pulled_images,
            service_changes_performed=None if mutation_started else False,
            service_changes_may_have_been_performed=mutation_started,
            **({"accepted_release_pointer_reconciliation_required":
                rollback.get("status") == "verified" and cutover_started
                and rollback.get("source_sha") != prior_receipt.get("source_sha")}
               if f2d_release and prior_receipt is not None else {}),
            protected_resources_changed=True if resource_drift else None if mutation_started else False,
            protected_resources_may_have_changed=mutation_started and not resource_drift,
            filesystem_writes_performed=True,
            env_files_read=True,
            rollback=rollback,
            **({"accepted_release_schema_compatibility": f2d_attestation,
                "f2d_behavioural_probes": f2d_probe_statuses,
                "f2d_generation": f2d_generation, "f2d_generation_rule": generation_rule,
                "f2d_image_contract": f2d_image_contract} if f2d_release else {}),
        )
        try:
            receipt["durable_failure_receipt"] = persist_failure(
                receipt_dir, receipt
            )
        except (OSError, DeploymentError):
            receipt["durable_failure_receipt"] = None
            receipt["failure_receipt_persistence"] = "failed"
        raise OperationFailed(receipt) from original
    finally:
        if docker_config:
            try: runner(["docker", "logout", "ghcr.io"], env=env)
            except DeploymentError: pass
            shutil.rmtree(docker_config, ignore_errors=True)
        if snapshot is not None:
            try:
                size = snapshot.stat().st_size
                with snapshot.open("r+b", buffering=0) as handle:
                    handle.write(b"\0" * size)
                    handle.flush()
                    os.fsync(handle.fileno())
                snapshot.unlink()
            except OSError:
                pass
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    result.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    result.add_argument("--operation", choices=("authority-gate", "preflight", "promote"), default="authority-gate")
    result.add_argument("--mode", choices=("bootstrap", "upgrade"), default="bootstrap")
    result.add_argument("--candidate", type=Path)
    result.add_argument("--candidate-checksum", type=Path)
    result.add_argument("--candidate-run-id")
    result.add_argument("--candidate-attestation", type=Path)
    result.add_argument("--registry-token-file", type=Path)
    result.add_argument("--registry-username")
    result.add_argument("--runtime-directory", type=Path)
    return result


def _main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authority: dict[str, Any] = {}
    try:
        authority = load_json(args.authority, "production target authority")
        blockers = validate_authority(authority)
        if blockers:
            operation = {
                "preflight": "production-preflight",
                "promote": "production-promotion",
                "authority-gate": "production-authority-gate",
            }[args.operation]
            print(json.dumps(stopped_receipt(authority, blockers, operation=operation), sort_keys=True))
            return 78
        if args.operation == "authority-gate":
            receipt = stopped_receipt(
                authority, [], operation="production-authority-gate"
            )
            receipt["status"] = "authority-verified"
            print(json.dumps(receipt, sort_keys=True))
            return 0
        if args.candidate is None or args.candidate_checksum is None:
            raise DeploymentError("candidate manifest and checksum are required")
        receipt = promote(args, authority)
    except OperationFailed as exc:
        print(json.dumps(exc.receipt, sort_keys=True))
        return 78
    except DeploymentError as exc:
        operation = {
            "preflight": "production-preflight",
            "promote": "production-promotion",
            "authority-gate": "production-authority-gate",
        }[args.operation]
        receipt = stopped_receipt(authority, [str(exc)], operation=operation)
        if (
            isinstance(exc, OperationCancelled)
            and args.operation == "promote"
            and _PREMUTATION_FAILURE_RECEIPT_DIR is not None
        ):
            # A cancellation during the read-only pre-mutation gates occurs
            # before promote() creates any ephemeral credentials or services,
            # but it still needs durable host evidence.
            receipt.update(
                status="failed",
                source_sha="unknown",
                release_run_id=args.candidate_run_id or "unknown",
                database_access_performed=None,
                database_access_may_have_been_performed=True,
                service_changes_performed=False,
                service_changes_may_have_been_performed=False,
                filesystem_writes_performed=True,
                rollback={"attempted": False, "status": "not-required"},
            )
            try:
                receipt["durable_failure_receipt"] = persist_failure(
                    _PREMUTATION_FAILURE_RECEIPT_DIR, receipt
                )
            except (OSError, DeploymentError):
                receipt["durable_failure_receipt"] = None
                receipt["failure_receipt_persistence"] = "failed"
        print(json.dumps(receipt, sort_keys=True))
        return 78
    except Exception as exc:
        operation = {
            "preflight": "production-preflight",
            "promote": "production-promotion",
            "authority-gate": "production-authority-gate",
        }[args.operation]
        print(json.dumps(stopped_receipt(
            authority, [f"internal_failure:{type(exc).__name__}"], operation=operation,
        ), sort_keys=True))
        return 78
    print(json.dumps(receipt, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    with controlled_cancellation():
        return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
