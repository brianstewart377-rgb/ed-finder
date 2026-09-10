from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tarfile
import textwrap
import time
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/v3-production/compose.yml"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
DEPLOYER = ROOT / "scripts/operator/v3_production_deploy.py"
INVENTORY = ROOT / "scripts/operator/v3_production_inventory.py"
SCHEMA_IDENTITY = ROOT / "scripts/operator/v3_schema_identity.py"
INVENTORY_ACTION = ROOT / "scripts/operator/actions/v3-production-inventory.sh"
PROMOTE_ACTION = ROOT / "scripts/operator/actions/v3-production-promote.sh"
PUBLIC_EDGE_CONF = ROOT / "deploy/v3-production/public-auth-edge.nginx.conf"
WORKFLOW = ROOT / ".github/workflows/v3-production-application-deploy.yml"
RUNBOOK = ROOT / "docs/operations/v3-production-application-release.md"
V3_MANIFEST = ROOT / "sql/v3/migration-manifest.txt"

# The reviewed live ledger of the retained production database, read under
# BEGIN READ ONLY by the 2026-09-10 inventory receipt.
LIVE_V3_LEDGER = (
    ("001_v3_baseline.sql", "ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e"),
    ("002_v3_accounts_identity.sql", "e7a2f404b7d8194d74ba4e807ae450c7520a1c8a186ca77e41377307e7b12b07"),
    ("r1_v3/001_structural_shell.sql", "1a2d15c2db5cff7714a01a5d0c710a22326ed57d90d9a20e362495714ad97a40"),
)


def _load_deployer():
    spec = importlib.util.spec_from_file_location("v3_production_deploy", DEPLOYER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_schema_identity():
    spec = importlib.util.spec_from_file_location("v3_schema_identity", SCHEMA_IDENTITY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_inventory():
    spec = importlib.util.spec_from_file_location("v3_production_inventory", INVENTORY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_production_authority_is_separate_exact_and_currently_fail_closed():
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    module = _load_deployer()

    assert value["target"] == {
        "provider": "mevspace",
        "classification": "production",
        "production": True,
        "hostname": "ed-finder-prod",
        "fqdn": "nb79a3d.mevnode.com",
        "architecture": "x86_64",
    }
    assert value["status"] == "stopped"
    assert set(module.validate_authority(value)) == set(value["blockers"])
    assert {
        "production_promotion_cpython314_runtime_unproved",
        "production_edge_loopback_cutover_topology_authority_missing",
    }.issubset(value["blockers"])
    assert value["application_contract"]["compose_project"] == "edfinder-v3-production"
    assert "checkpoint" not in value["application_contract"]["compose_project"]
    assert value["application_contract"]["compose_sha256"] == hashlib.sha256(COMPOSE.read_bytes()).hexdigest()
    # Proven by the reviewed 2026-09-10 inventory receipt: the application
    # network exists and carries exactly the running api and web-slot members.
    assert value["external_authority"]["application_network"] == "edfinder-v3-production"
    assert value["external_authority"]["application_network_allowed_containers"] == [
        "edfinder-v3-api",
        "edfinder-v3-production-web-blue",
        "edfinder-v3-phase4c-full-20260827_r5-postgres",
    ]
    # The reviewed unchanged-edge cutover authority is published from that
    # receipt.  The remaining nulls are host facts that are still unprovisioned.
    assert value["external_authority"]["edge_route_authority"] == {
        "strategy": "verified-loopback-blue-green-port-swap",
        "edge_container": "edfinder-v3-public-auth-edge",
        "active_origin_bind": "127.0.0.1:58080",
        "evidence": "reviewed-production-inventory-receipt",
    }
    assert all(value["external_authority"][key] is None for key in (
        "api_env_file", "api_env_owner_uid", "api_env_mode",
        "schema_identity_file", "receipt_directory",
    ))
    assert value["external_authority"]["docker_context"] == "default"


def test_production_compose_owns_only_blue_green_application_slots():
    value = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = value["services"]

    assert value["name"] == "edfinder-v3-production"
    assert set(services) == {"api-blue", "web-blue", "api-green", "web-green"}
    assert set(value["networks"]) == {"app"}
    assert value["networks"]["app"]["external"] is True
    assert "volumes" not in value
    assert all("depends_on" not in service for service in services.values())
    assert services["api-blue"]["environment"]["EDDN_SIMULATION_INGEST_ENABLED"] == "false"
    assert services["api-blue"]["environment"]["ADMIN_OPERATION_STARTUP_REAP_ENABLED"] == "false"
    for service_name in services:
        assert not any(
            token in service_name for token in ("postgres", "redis", "valkey", "nats", "octopus", "edge", "proxy")
        )


def test_read_only_inventory_has_exact_guards_complete_ledger_and_no_secret_reads():
    source = INVENTORY.read_text(encoding="utf-8")
    action = INVENTORY_ACTION.read_text(encoding="utf-8")

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert 'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"' in source
    assert "BEGIN READ ONLY;" in source
    assert "statement_timeout" in source
    assert 'DB_USER = "edfinder_v3"' in source
    assert 'DB_NAME = "edfinder_v3_phase4c_full_20260827_r5"' in source
    assert "FROM v3_meta.schema_migration" in source
    assert "ORDER BY migration_name" in source
    assert '"container_environment_read": False' in source
    assert '"filesystem_writes_performed": False' in source
    for required_inventory_fact in (
        'receipt["host_runtime"]',
        '"inventory_python"',
        '"python3_14"',
        '"command": "python3"',
        '"command": "python3.14"',
        '"executable"',
        '"implementation"',
        '"version"',
        '"version_info"',
        '"is_exact_cpython_3_14"',
        'receipt["docker_context"]',
        '"docker_endpoint"',
        '"loopback_origin_port_ownership"',
        '"docker_network_settings_ports"',
        '"58080"',
        '"58081"',
        '"bindings"',
        '"owners"',
        '"ComposeLabels"',
        "COMPOSE_LABEL_KEYS",
        'receipt["designated_paths"]',
        "DESIGNATED_PATHS",
        "os.lstat(",
        '"matches_designation"',
        '"expected_owner_uid"',
        '"expected_mode"',
    ):
        assert required_inventory_fact in source
    assert 'return ["docker", "--context", DOCKER_CONTEXT, *arguments]' in source
    assert source.count('"docker"') == 1
    assert "command -v python3.14" not in action
    assert "command -v python3" in action
    for forbidden in (
        ".Config.Env", ".docker/config", "docker context export", "docker restart",
        "docker stop", "docker start", "compose up", "INSERT INTO", "UPDATE ",
        "DELETE FROM", "TRUNCATE", "ALTER TABLE", "DROP TABLE",
    ):
        assert forbidden not in source
    # The designated production paths are reviewed with stat-only evidence, so
    # the helper must never read a file, let alone their contents.
    assert "read_text" not in source
    assert "read_bytes" not in source


def test_inventory_designated_paths_report_stat_only_evidence(tmp_path):
    inventory = _load_inventory()

    missing = inventory.inspect_designated_path(
        {
            "name": "receipt_directory",
            "path": str(tmp_path / "absent"),
            "kind": "directory",
            "owner_uid": 0,
            "mode": "0700",
        }
    )
    assert missing["inspection_succeeded"] is True
    assert missing["exists"] is False
    assert missing["owner_uid"] is None
    assert missing["mode"] is None
    assert missing["matches_designation"] is False

    target = tmp_path / "api.env"
    target.write_text("EDFINDER_SECRET=must-not-be-recorded\n", encoding="utf-8")
    details = os.lstat(target)
    spec = {
        "name": "api_env_file",
        "path": str(target),
        "kind": "file",
        "owner_uid": details.st_uid,
        "mode": f"{stat.S_IMODE(details.st_mode):04o}",
    }
    present = inventory.inspect_designated_path(spec)
    assert present["inspection_succeeded"] is True
    assert present["exists"] is True
    assert present["is_file"] is True
    assert present["is_symlink"] is False
    assert present["owner_uid"] == details.st_uid
    assert present["mode"] == spec["mode"]
    assert present["matches_designation"] is True
    assert "must-not-be-recorded" not in json.dumps(present)

    wrong_kind = inventory.inspect_designated_path({**spec, "kind": "directory"})
    assert wrong_kind["matches_designation"] is False
    wrong_owner = inventory.inspect_designated_path({**spec, "owner_uid": details.st_uid + 1})
    assert wrong_owner["matches_designation"] is False
    wrong_mode = inventory.inspect_designated_path({**spec, "mode": "0644"})
    if spec["mode"] != "0644":
        assert wrong_mode["matches_designation"] is False

    link = tmp_path / "api.env.link"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")
    linked = inventory.inspect_designated_path({**spec, "path": str(link)})
    assert linked["is_symlink"] is True
    assert linked["matches_designation"] is False


def test_v3_lineage_manifest_reproduces_the_reviewed_live_ledger():
    entries: dict[str, tuple[str, str]] = {}
    for raw_line in V3_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        checksum, first_separator, remainder = line.partition("  ")
        ledger_name, second_separator, path = remainder.partition("  ")
        assert first_separator and second_separator, f"unsafe manifest entry: {line!r}"
        assert re.fullmatch(r"[0-9a-f]{64}", checksum), line
        assert re.fullmatch(r"(?:[a-z0-9_]+/)?[0-9]{3}_[a-z0-9_]+\.sql", ledger_name), line
        assert re.fullmatch(r"(?:[a-z0-9_]+/)+[0-9]{3}_[a-z0-9_]+\.sql", path), line
        assert ledger_name not in entries, line
        entries[ledger_name] = (path, checksum)

    assert set(entries) == {name for name, _ in LIVE_V3_LEDGER}
    for ledger_name, reviewed_checksum in LIVE_V3_LEDGER:
        path, checksum = entries[ledger_name]
        assert checksum == reviewed_checksum
        # The committed bytes must be the ones PostgreSQL actually applied, so
        # they stay LF-terminated and byte-identical on every platform.
        source = (ROOT / "sql" / path).read_bytes()
        assert hashlib.sha256(source).hexdigest() == reviewed_checksum
        assert b"\r\n" not in source


def test_inventory_container_labels_are_limited_to_compose_identity():
    inventory = _load_inventory()

    labels = inventory.sanitize_compose_labels(
        "com.docker.compose.project=edfinder-v3-production,"
        "com.docker.compose.service=web-blue,"
        "com.docker.compose.project.working_dir=/opt/ed-finder,"
        "com.docker.compose.project.config_files=/opt/ed-finder/compose.yml,"
        "com.example.token=must-not-appear"
    )

    assert labels == {
        "com.docker.compose.project": "edfinder-v3-production",
        "com.docker.compose.service": "web-blue",
        "com.docker.compose.project.working_dir": "/opt/ed-finder",
        "com.docker.compose.project.config_files": "/opt/ed-finder/compose.yml",
    }
    assert "must-not-appear" not in json.dumps(labels)
    assert inventory.sanitize_compose_labels(None) is None
    assert inventory.sanitize_compose_labels("com.example.token=x") is None

    item = inventory.sanitize_container(
        {
            "Names": "edfinder-v3-api",
            "Image": "edfinder-v3-api:release-6a4fe0ef",
            "ID": "abc",
            "State": "running",
            "Status": "Up 1 day",
            "Ports": "",
            "Networks": "edfinder-v3-production",
            "Labels": "com.docker.compose.project=edfinder-v3-production",
            "Config": {"Env": ["SECRET=leak"]},
        }
    )
    assert item["ComposeLabels"] == {
        "com.docker.compose.project": "edfinder-v3-production"
    }
    assert set(item) == {
        "Names", "Image", "ID", "State", "Status", "Ports", "Networks",
        "ComposeLabels",
    }


def test_production_deployer_uses_release_manifest_and_fresh_schema_compatibility():
    source = DEPLOYER.read_text(encoding="utf-8")

    assert 'ROOT / "scripts/release/v3_release_manifest.py"' in source
    assert 'purpose="deploy"' in source
    assert 'purpose="rollback"' in source
    assert "current_migration_set=schema[\"migration_set_identity\"]" in source
    assert "BEGIN READ ONLY;" in source
    assert "production_migration_authority_absent_or_schema_incompatible" in source
    assert "candidate.get(\"rollback\", {}).get(\"application_only_eligible\")" in source
    for forbidden in ("apply_migrations.sh", "baseline_migration_ledger.sh", "git pull", "docker compose down", "--remove-orphans", "docker volume rm"):
        assert forbidden not in source


def test_production_schema_identity_is_derived_from_the_v3_lineage(tmp_path):
    deployer = _load_deployer()
    identity = _load_schema_identity()

    # The derivation and the deployer must agree on the schema and the database
    # identity, or the produced document could never be accepted.
    assert identity.SCHEMA_IDENTITY_SCHEMA == deployer.SCHEMA_IDENTITY_SCHEMA
    assert identity.DATABASE_IDENTITY == {
        "container": deployer.POSTGRES_CONTAINER,
        "database_name": deployer.DATABASE_NAME,
        "database_user": deployer.DATABASE_USER,
        "application_host": deployer.POSTGRES_CONTAINER,
        "server_address": "local",
        "server_port": 5432,
    }

    document = identity.build(ROOT)
    entries = document["migration_set_entries"]
    assert [(item["ledger_name"], item["sha256"]) for item in entries] == list(
        LIVE_V3_LEDGER
    )
    assert document["migration_set_identity"] == identity.migration_set_identity(entries)
    # The reviewed lineage order is not directory order, and the identity must
    # preserve the manifest order rather than re-sorting it.
    assert entries != sorted(entries, key=lambda item: item["path"])

    path = tmp_path / "schema.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        deployer.validate_schema_file(path, digest)["migration_set_identity"]
        == document["migration_set_identity"]
    )

    tampered = {**document, "migration_set_identity": "sha256:" + "a" * 64}
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(deployer.DeploymentError, match="checksum mismatch"):
        deployer.validate_schema_file(path, digest)


def test_mutation_is_explicit_app_only_and_preserves_edge_database_redis_nats():
    source = DEPLOYER.read_text(encoding="utf-8")

    assert 'runner([*base, "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never", *selected]' in source
    assert 'runner(["docker", "stop", LEGACY_ORIGIN]' in source
    assert 'runner(["docker", "stop", LEGACY_API]' in source
    assert 'runner(["docker", "start", LEGACY_API]' in source
    assert 'runner(["docker", "start", LEGACY_ORIGIN]' in source
    assert "verify_snapshot(protected_before" in source
    assert source.count("live_capacity_guard()") >= 3
    assert source.count("validate_network(") >= 4
    assert 'PUBLIC_EDGE = "edfinder-v3-public-auth-edge"' in source
    assert 'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"' in source
    assert '"edfinder-v3-support-redis"' in AUTHORITY.read_text()
    assert '"edfinder-v3-support-nats"' in AUTHORITY.read_text()
    assert '"edge_recreated": False' in source


def test_rollback_comes_only_from_checksum_bound_prior_accepted_release():
    source = DEPLOYER.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'load_current(receipt_dir)' in source
    assert 'sha256_file(receipt_path) != pointer["receipt_sha256"]' in source
    assert 'sha256_file(manifest_path) != pointer["manifest_sha256"]' in source
    assert '"--pull", "never"' in source
    assert '"kind": "prior-accepted-immutable-release"' in source
    assert "rollback_run_id" not in workflow
    assert "rollback-manifest" not in workflow


def _accepted_receipt(deployer, source_sha: str, run_id: str, manifest: bytes) -> dict:
    return {
        "schema_version": deployer.RECEIPT_SCHEMA,
        "operation": "production-promotion",
        "status": "accepted",
        "source_sha": source_sha,
        "release_run_id": run_id,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }


@pytest.mark.parametrize("prior_exists", [True, False])
def test_post_replace_persistence_failure_restores_prior_pointer_or_absence(
    monkeypatch, tmp_path, prior_exists
):
    deployer = _load_deployer()
    prior_manifest = b'{"git_sha":"' + b"a" * 40 + b'"}\n'
    prior_receipt = _accepted_receipt(deployer, "a" * 40, "111", prior_manifest)
    if prior_exists:
        deployer.persist_accepted(tmp_path, prior_receipt, prior_manifest)
        prior_pointer_bytes = (tmp_path / "current.json").read_bytes()
        prior_pointer = json.loads(prior_pointer_bytes)
    else:
        prior_pointer_bytes = None
        prior_pointer = None

    candidate_manifest = b'{"git_sha":"' + b"b" * 40 + b'"}\n'
    candidate_receipt = _accepted_receipt(
        deployer, "b" * 40, "222", candidate_manifest
    )
    candidate_stem = f"{'b' * 40}-222-{hashlib.sha256(candidate_manifest).hexdigest()}"
    original_fsync = deployer.os.fsync
    directory_fsyncs = 0

    def fail_after_pointer_replace(descriptor):
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
            if directory_fsyncs == 2:
                raise OSError("injected post-replace fsync failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(deployer.os, "fsync", fail_after_pointer_replace)
    with pytest.raises(OSError, match="post-replace"):
        deployer.persist_accepted(tmp_path, candidate_receipt, candidate_manifest)

    if prior_exists:
        assert (tmp_path / "current.json").read_bytes() == prior_pointer_bytes
        assert prior_pointer is not None
        for key in ("receipt_file", "manifest_file"):
            path = tmp_path / prior_pointer[key]
            assert path.is_file()
            assert Path(str(path) + ".sha256").is_file()
    else:
        assert not (tmp_path / "current.json").exists()
    for suffix in (".json", ".release.json", ".json.sha256", ".release.json.sha256"):
        assert not (tmp_path / f"{candidate_stem}{suffix}").exists()


def test_pointer_restore_failure_retains_candidate_targets(monkeypatch, tmp_path):
    deployer = _load_deployer()
    prior_manifest = b'{"git_sha":"' + b"a" * 40 + b'"}\n'
    deployer.persist_accepted(
        tmp_path,
        _accepted_receipt(deployer, "a" * 40, "111", prior_manifest),
        prior_manifest,
    )
    candidate_manifest = b'{"git_sha":"' + b"b" * 40 + b'"}\n'
    candidate_receipt = _accepted_receipt(
        deployer, "b" * 40, "222", candidate_manifest
    )
    original_fsync = deployer.os.fsync
    original_replace = deployer.os.replace
    directory_fsyncs = 0
    current_replacements = 0

    def fail_after_pointer_replace(descriptor):
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
            if directory_fsyncs == 2:
                raise OSError("injected post-replace fsync failure")
        return original_fsync(descriptor)

    def fail_pointer_restore(source, destination):
        nonlocal current_replacements
        if Path(destination) == tmp_path / "current.json":
            current_replacements += 1
            if current_replacements == 2:
                raise OSError("injected pointer restore failure")
        return original_replace(source, destination)

    monkeypatch.setattr(deployer.os, "fsync", fail_after_pointer_replace)
    monkeypatch.setattr(deployer.os, "replace", fail_pointer_restore)
    with pytest.raises(deployer.DeploymentError, match="candidate artifacts retained"):
        deployer.persist_accepted(tmp_path, candidate_receipt, candidate_manifest)

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    for key in ("receipt_file", "manifest_file"):
        path = tmp_path / current[key]
        assert path.is_file()
        assert Path(str(path) + ".sha256").is_file()


def test_workflow_is_manual_main_only_protected_and_uses_pinned_ssh_trust():
    workflow = _workflow()
    source = WORKFLOW.read_text(encoding="utf-8")

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "github.ref == 'refs/heads/main'" in source
    assert "github.repository == 'brianstewart377-rgb/ed-finder'" in source
    assert workflow["jobs"]["inventory"]["environment"] == "ed-new-operator"
    assert workflow["jobs"]["production-operation"]["environment"] == "v3-production"
    assert source.count("persist-credentials: false") >= 4
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in source
    assert "ssh-keyscan" not in source
    assert "V3_PRODUCTION_SSH_KEY" in source
    assert "V3_LIVE_CHECKPOINT" not in source
    assert "ED_NEW_OPERATOR_SSH_KEY" in source
    assert "target_confirmation" in source
    assert source.count("uses: actions/download-artifact@") == 2
    assert source.count("scripts/release/v3_release_run.py") == 2
    assert "gh api" not in source
    assert "release-run.json" not in source
    assert "Stop before credentials or SSH while production authority is blocked" in source
    assert "Candidate is not the exact current main release" in source
    assert "exec bash scripts/operator/actions/v3-production-promote.sh" not in source
    assert "--runtime-directory" in source
    assert "kill -TERM" in source
    assert "trap '' HUP INT TERM" in source
    assert source.index("kill -TERM") < source.index('wait \\"\\$child\\"')
    assert "kill -KILL" not in source


def test_receipts_are_machine_readable_and_secret_safe_by_contract():
    source = DEPLOYER.read_text(encoding="utf-8")

    for field in (
        "database_access_performed", "database_writes_performed", "migrations_performed",
        "application_data_writes_performed", "image_pulls_performed",
        "service_changes_performed", "edge_recreated", "protected_resources_changed",
        "env_contents_recorded", "private_keys_read",
    ):
        assert field in source
    assert "production DATABASE_URL does not target retained PostgreSQL" in source
    assert "parsed.password" in source
    assert ".Config.Env" not in source
    assert "password=" not in source.lower()


def test_runbook_states_no_execution_boundary_and_concrete_first_run_blockers():
    source = RUNBOOK.read_text(encoding="utf-8")

    assert "does **not** authorize executing it during" in source
    assert "No command in this runbook was executed\nagainst production" in source
    assert "root `docker-compose.yml`" in source
    assert "Contabo checkpoint" in source
    assert "production_migration_authority_absent_or_schema_incompatible" in source
    assert "production_promotion_cpython314_runtime_unproved" in source
    assert "production_local_docker_context_authority_missing" in source
    assert "default `python3` used to run inventory" in source
    assert "exactly CPython 3.14" in source
    assert "Docker context `default`" in source
    assert "`unix:///var/run/docker.sock`" in source
    assert "ephemeral-operation-bundle-only" in source
    assert "application- and data-read-only" in source
    assert "atomically restore the prior pointer" in source
    assert "loopback ports `58080` and `58081`" in source
    assert "fills a blocker" in source
    assert "stale `edfinder-v3-api:phase4c-r5`" in source
    assert "Redis and NATS are not removed or replaced" in source


def test_public_edge_forwards_the_app_surface_to_the_single_active_origin():
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    source = PUBLIC_EDGE_CONF.read_text(encoding="utf-8")
    external = authority["external_authority"]
    active = external["active_origin_bind"]
    staging = external["staging_origin_bind"]

    # The cutover swaps which slot owns the active bind while the edge is never
    # repointed, so the public application surface must target the active origin
    # and must never target the staging port.
    assert f"proxy_pass http://{active};" in source
    assert f"http://{staging}" not in source
    assert external["edge_route_authority"]["active_origin_bind"] == active


def test_new_shell_launchers_parse():
    for path in (INVENTORY_ACTION, PROMOTE_ACTION):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_inventory_ledger_parser_rejects_extra_or_malformed_output():
    inventory = _load_inventory()
    good = json.dumps(
        {
            "database_name": inventory.DB_NAME,
            "server_address": "local",
            "server_port": 5432,
            "transaction_read_only": "on",
            "migrations": [
                {"filename": "001_v3_baseline.sql", "checksum_sha256": "a" * 64},
                {"filename": "r1_v3/001_structural_shell.sql", "checksum_sha256": "b" * 64},
            ],
        }
    )
    completed = subprocess.CompletedProcess(["psql"], 0, good, "")
    assert inventory.parse_ledger(completed)["inspection_succeeded"] is True

    for hostile in (
        good + "\nignored-extra-output",
        json.dumps({**json.loads(good), 'database_name': 'edfinder'}),
        json.dumps({**json.loads(good), 'server_address': 'elsewhere'}),
        json.dumps({**json.loads(good), 'migrations': [
            {'filename': '../001_escape.sql', 'checksum_sha256': 'a' * 64}]}),
        json.dumps(
            {
                **json.loads(good),
                "migrations": [
                    {"filename": "001_initial.sql", "checksum_sha256": "a" * 64},
                    {"filename": "002_bad\nname.sql", "checksum_sha256": "b" * 64},
                ],
            }
        ),
    ):
        result = inventory.parse_ledger(
            subprocess.CompletedProcess(["psql"], 0, hostile, "")
        )
        assert result["inspection_succeeded"] is False


def test_inventory_runtime_facts_are_bounded_and_exact(monkeypatch):
    inventory = _load_inventory()

    current = inventory.inventory_runtime()
    assert current["command"] == "python3"
    assert current["used_for_inventory"] is True
    assert current["inspection_succeeded"] is True
    assert current["executable"].startswith("/")
    assert len(current["executable"]) <= 256
    assert len(current["implementation"]) <= inventory.MAX_RUNTIME_VERSION
    assert len(current["version"]) <= inventory.MAX_RUNTIME_VERSION
    assert len(current["version_info"]) == 3
    assert isinstance(current["is_exact_cpython_3_14"], bool)

    monkeypatch.setattr(inventory.shutil, "which", lambda *_args, **_kwargs: None)
    unavailable = inventory.inspect_python314_runtime()
    assert unavailable["exists"] is False
    assert unavailable["inspection_succeeded"] is True
    assert unavailable["command"] == "python3.14"
    assert unavailable["executable"] is None
    assert unavailable["is_exact_cpython_3_14"] is False
    assert unavailable["version"] is None

    monkeypatch.setattr(
        inventory.shutil,
        "which",
        lambda *_args, **_kwargs: "/usr/bin/python3.14",
    )
    monkeypatch.setattr(
        inventory,
        "run",
        lambda _argv: subprocess.CompletedProcess(
            _argv,
            0,
            '{"implementation":"CPython","version":"3.14.1",'
            '"version_info":[3,14,1]}\n',
            "",
        ),
    )
    exact = inventory.inspect_python314_runtime()
    assert exact["inspection_succeeded"] is True
    assert exact["exists"] is True
    assert exact["executable"] == "/usr/bin/python3.14"
    assert exact["implementation"] == "CPython"
    assert exact["version"] == "3.14.1"
    assert exact["version_info"] == [3, 14, 1]
    assert exact["is_exact_cpython_3_14"] is True

    monkeypatch.setattr(
        inventory,
        "run",
        lambda _argv: subprocess.CompletedProcess(
            _argv,
            0,
            '{"implementation":"PyPy","version":"3.14.1",'
            '"version_info":[3,14,1]}\n',
            "",
        ),
    )
    wrong_implementation = inventory.inspect_python314_runtime()
    assert wrong_implementation["inspection_succeeded"] is True
    assert wrong_implementation["exists"] is True
    assert wrong_implementation["is_exact_cpython_3_14"] is False

    monkeypatch.setattr(
        inventory,
        "run",
        lambda _argv: subprocess.CompletedProcess(
            _argv,
            0,
            '{"implementation":"CPython","version":"3.13.9",'
            '"version_info":[3,13,9]}\n',
            "",
        ),
    )
    wrong_version = inventory.inspect_python314_runtime()
    assert wrong_version["inspection_succeeded"] is True
    assert wrong_version["exists"] is True
    assert wrong_version["is_exact_cpython_3_14"] is False

    monkeypatch.setattr(
        inventory,
        "run",
        lambda _argv: subprocess.CompletedProcess(_argv, 0, "not-json\n", ""),
    )
    malformed = inventory.inspect_python314_runtime()
    assert malformed["inspection_succeeded"] is False
    assert malformed["exists"] is True
    assert malformed["implementation"] is None
    assert malformed["version"] is None


def test_inventory_reports_only_default_docker_endpoint_and_loopback_owners(monkeypatch):
    inventory = _load_inventory()
    observed_argv: list[str] = []

    def context_run(argv):
        observed_argv.extend(argv)
        return subprocess.CompletedProcess(
            argv, 0, '"default"\t"unix:///var/run/docker.sock"\n', ""
        )

    monkeypatch.setattr(inventory, "run", context_run)
    assert inventory.inspect_default_docker_context() == {
        "inspection_succeeded": True,
        "name": "default",
        "docker_endpoint": "unix:///var/run/docker.sock",
    }
    assert observed_argv == [
        "docker", "--context", "default", "context", "inspect", "default", "--format",
        "{{json .Name}}\t{{json .Endpoints.docker.Host}}",
    ]

    monkeypatch.setattr(
        inventory,
        "run",
        lambda argv: subprocess.CompletedProcess(
            argv, 0, '"default"\t"tcp://127.0.0.1:2375"\n', ""
        ),
    )
    assert inventory.inspect_default_docker_context() == {
        "inspection_succeeded": False,
        "name": None,
        "docker_endpoint": None,
    }

    for unsafe_endpoint in (
        "ssh://user:password@example.invalid/run/docker.sock",
        "tcp://token@example.invalid:2375",
        "unix:///tmp/docker.sock",
    ):
        monkeypatch.setattr(
            inventory,
            "run",
            lambda argv, endpoint=unsafe_endpoint: subprocess.CompletedProcess(
                argv, 0, json.dumps("default") + "\t" + json.dumps(endpoint) + "\n", ""
            ),
        )
        rejected = inventory.inspect_default_docker_context()
        assert rejected == {
            "inspection_succeeded": False,
            "name": None,
            "docker_endpoint": None,
        }

    ownership = inventory.loopback_origin_ownership(
        [
            {
                "Names": "edfinder-v3-proxy",
                "State": "running",
                "PortsDetail": [
                    {
                        "bind_address": "127.0.0.1", "host_port": 58080,
                        "container_port": 80, "protocol": "tcp",
                    },
                    {
                        "bind_address": "0.0.0.0", "host_port": 58081,
                        "container_port": 81, "protocol": "tcp",
                    },
                ],
            },
            {
                "Names": "candidate-web",
                "State": "running",
                "PortsDetail": [
                    {
                        "bind_address": "127.0.0.1", "host_port": 58081,
                        "container_port": 3000, "protocol": "tcp",
                    }
                ],
            },
            {
                "Names": "stopped-web",
                "State": "exited",
                "PortsDetail": None,
            },
        ],
        inspection_succeeded=True,
    )
    assert ownership["inspection_succeeded"] is True
    assert ownership["ports"]["58080"]["owners"] == ["edfinder-v3-proxy"]
    assert ownership["ports"]["58080"]["bindings"] == [
        {
            "container": "edfinder-v3-proxy", "bind_address": "127.0.0.1",
            "container_port": 80, "protocol": "tcp",
        }
    ]
    assert ownership["ports"]["58080"]["exact_loopback_only"] is True
    assert ownership["ports"]["58081"]["owners"] == [
        "candidate-web", "edfinder-v3-proxy"
    ]
    assert ownership["ports"]["58081"]["bindings"] == [
        {
            "container": "candidate-web", "bind_address": "127.0.0.1",
            "container_port": 3000, "protocol": "tcp",
        },
        {
            "container": "edfinder-v3-proxy", "bind_address": "0.0.0.0",
            "container_port": 81, "protocol": "tcp",
        },
    ]
    assert ownership["ports"]["58081"]["exact_loopback_only"] is False
    assert ownership["exact_loopback_only"] is False

    incomplete = inventory.loopback_origin_ownership(
        [{"Names": "malformed", "State": "running", "PortsDetail": "bad"}],
        inspection_succeeded=False,
    )
    assert incomplete["inspection_succeeded"] is False
    assert incomplete["ports"]["58080"]["owners"] == []
    assert incomplete["ports"]["58081"]["owners"] == []


def test_inventory_stops_before_daemon_evidence_when_default_context_is_not_local(
    monkeypatch, capsys
):
    inventory = _load_inventory()
    docker_commands = []

    monkeypatch.setattr(inventory.socket, "gethostname", lambda: inventory.EXPECTED_HOST)
    monkeypatch.setattr(
        inventory, "inventory_runtime", lambda: {"inspection_succeeded": True}
    )
    monkeypatch.setattr(
        inventory, "inspect_python314_runtime", lambda: {"inspection_succeeded": True}
    )
    monkeypatch.setattr(inventory, "host_capacity", lambda: {})

    def context_only(argv, **_kwargs):
        if argv == ["hostname", "-f"]:
            return subprocess.CompletedProcess(
                argv, 0, inventory.EXPECTED_FQDN + "\n", ""
            )
        if argv[:3] == ["docker", "--context", "default"]:
            docker_commands.append(argv)
            if argv[3:6] != ["context", "inspect", "default"]:
                raise AssertionError(f"daemon evidence escaped failed context gate: {argv}")
            return subprocess.CompletedProcess(
                argv, 0, '"default"\t"tcp://127.0.0.1:2375"\n', ""
            )
        raise AssertionError(argv)

    monkeypatch.setattr(inventory, "run", context_only)
    assert inventory.main() == 78
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["failures"] == ["default_docker_context_inventory_failed"]
    assert receipt["direct_db_access_performed"] is False
    assert len(docker_commands) == 1
    assert docker_commands[0][:3] == ["docker", "--context", "default"]


def test_protected_job_refetches_main_before_credentials_and_maps_fallback_receipts():
    workflow = _workflow()
    steps = workflow["jobs"]["production-operation"]["steps"]
    names = [step.get("name", "") for step in steps]
    recheck_index = names.index("Revalidate exact current main after production approval")
    prepare_index = names.index("Prepare sealed source-free operation bundle and pinned SSH trust")
    execute_index = names.index("Execute exact production authority")
    recheck = steps[recheck_index]["run"]
    execute = steps[execute_index]["run"]

    assert recheck_index < prepare_index < execute_index
    assert "git fetch --no-tags origin refs/heads/main" in recheck
    assert 'git rev-parse HEAD' in recheck
    assert 'git rev-parse FETCH_HEAD' in recheck
    assert steps[recheck_index]["env"]["EXPECTED_SOURCE_SHA"] == "${{ needs.guard.outputs.source_sha }}"
    assert "preflight) receipt_operation=production-preflight" in execute
    assert "promote) receipt_operation=production-promotion" in execute
    assert 'os.environ["RECEIPT_OPERATION"]' in execute
    assert '"operation": "production-promotion"' not in execute
    assert 'preflight = operation == "production-preflight"' in execute
    assert '"database_writes_performed": False if preflight else None' in execute
    assert '"service_changes_performed": False if preflight else None' in execute
    assert '"filesystem_writes_performed": None' in execute
    assert '"filesystem_writes_may_have_been_performed": True' in execute
    assert '"env_files_read": None, "env_files_may_have_been_read": True' in execute


def test_bundle_and_remote_runtime_roots_remain_private_after_archive_extraction(tmp_path):
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'install -d -m 700 "$BUNDLE"' in source
    assert 'tar --no-same-permissions --no-overwrite-dir -xf - -C' in source
    extract = source.index("tar --no-same-permissions --no-overwrite-dir -xf - -C")
    assert source.index('chmod 700 \\"\\$work\\"', extract) > extract

    bundle = tmp_path / "bundle"
    bundle.mkdir(mode=0o755)
    (bundle / "payload").write_text("sealed", encoding="utf-8")
    archive = tmp_path / "bundle.tar"
    with tarfile.open(archive, "w") as handle:
        handle.add(bundle, arcname=".")
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    subprocess.run(
        [
            "tar", "--no-same-permissions", "--no-overwrite-dir", "-xf",
            str(archive), "-C", str(runtime),
        ],
        check=True,
    )
    runtime.chmod(0o700)

    deployer = _load_deployer()
    assert deployer.validate_runtime_directory(runtime) == runtime
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o700


def _launcher_environment(fake_bin: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def test_preflight_launcher_prefers_exact_cpython314_and_falls_back_compatibly(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    actual_python = Path(sys.executable).resolve()
    (fake_bin / "python3.14").symlink_to(actual_python)
    marker = tmp_path / "python3-used"
    _write_executable(
        fake_bin / "python3",
        f"#!/bin/sh\nprintf used > {marker}\nexit 1\n",
    )
    preferred = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation", "preflight"],
        text=True,
        capture_output=True,
        env=_launcher_environment(fake_bin),
        timeout=10,
    )
    assert preferred.returncode == 78
    assert json.loads(preferred.stdout)["operation"] == "production-preflight"
    assert not marker.exists()

    (fake_bin / "python3.14").unlink()
    _write_executable(fake_bin / "python3.14", "#!/bin/sh\nexit 1\n")
    (fake_bin / "python3").unlink()
    (fake_bin / "python3").symlink_to("/usr/bin/python3")
    fallback = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation", "authority-gate"],
        text=True,
        capture_output=True,
        env=_launcher_environment(fake_bin),
        timeout=10,
    )
    assert fallback.returncode == 78
    assert json.loads(fallback.stdout)["operation"] == "production-authority-gate"


def test_launcher_runtime_failures_use_only_validated_operation_names(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "python3.14", "#!/bin/sh\nexit 1\n")
    _write_executable(fake_bin / "python3", "#!/bin/sh\nexit 1\n")
    env = _launcher_environment(fake_bin)

    unsupported = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation", "preflight"],
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert unsupported.returncode == 78
    unsupported_receipt = json.loads(unsupported.stdout)
    assert unsupported_receipt["operation"] == "production-preflight"
    assert unsupported_receipt["failures"] == [
        "python3_unsupported_for_production_readonly"
    ]
    assert unsupported_receipt["filesystem_writes_performed"] is True
    assert unsupported_receipt["filesystem_write_scope"] == (
        "ephemeral-operation-bundle-only"
    )
    for field in (
        "database_writes_performed", "migrations_performed",
        "application_data_writes_performed", "image_pulls_performed",
        "service_changes_performed", "edge_recreated",
        "protected_resources_changed",
    ):
        assert unsupported_receipt[field] is False

    mutation = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation", "promote"],
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert mutation.returncode == 78
    mutation_receipt = json.loads(mutation.stdout)
    assert mutation_receipt["operation"] == "production-promotion"
    assert mutation_receipt["failures"] == [
        "python314_required_for_production_mutation"
    ]
    assert mutation_receipt["filesystem_writes_performed"] is True

    hostile = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation", 'promote\"bad'],
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert hostile.returncode == 78
    hostile_receipt = json.loads(hostile.stdout)
    assert hostile_receipt["operation"] == "production-authority-gate"
    assert hostile_receipt["failures"] == ["invalid_requested_operation"]
    assert "bad" not in hostile.stdout

    equals_form = subprocess.run(
        ["bash", str(PROMOTE_ACTION), "--operation=preflight"],
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert equals_form.returncode == 78
    assert json.loads(equals_form.stdout)["operation"] == "production-preflight"


def test_launcher_runtime_probe_is_bounded_and_invalid_314_is_unsupported(tmp_path):
    invalid_only = tmp_path / "invalid-only"
    invalid_only.mkdir()
    (invalid_only / "timeout").symlink_to("/usr/bin/timeout")
    _write_executable(invalid_only / "python3.14", "#!/bin/sh\nexit 1\n")
    invalid = subprocess.run(
        ["/bin/bash", str(PROMOTE_ACTION), "--operation", "preflight"],
        text=True,
        capture_output=True,
        env={"PATH": str(invalid_only), "LANG": "C", "LC_ALL": "C"},
        timeout=5,
    )
    assert invalid.returncode == 78
    assert json.loads(invalid.stdout)["failures"] == [
        "python3_unsupported_for_production_readonly"
    ]

    hanging = tmp_path / "hanging"
    hanging.mkdir()
    _write_executable(hanging / "python3", "#!/bin/sh\nsleep 30\n")
    started = time.monotonic()
    bounded = subprocess.run(
        ["/bin/bash", str(PROMOTE_ACTION), "--operation", "preflight"],
        text=True,
        capture_output=True,
        env=_launcher_environment(hanging),
        timeout=15,
    )
    elapsed = time.monotonic() - started
    assert bounded.returncode == 78
    assert elapsed < 13
    assert json.loads(bounded.stdout)["failures"] == [
        "python3_unsupported_for_production_readonly"
    ]


def _origin_runner(bindings, listener="127.0.0.1:58080"):
    ports = {"8080/tcp": bindings} if bindings else {"8080/tcp": None}

    def runner(argv, **_kwargs):
        if argv[:3] == ["docker", "ps", "--no-trunc"]:
            return subprocess.CompletedProcess(argv, 0, "edfinder-v3-proxy\n", "")
        if argv[:3] == ["docker", "inspect", "--format"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(ports), "")
        if argv[:3] == ["ss", "-H", "-lnt"]:
            stdout = f"LISTEN 0 4096 {listener} 0.0.0.0:*\n" if listener else ""
            return subprocess.CompletedProcess(argv, 0, stdout, "")
        raise AssertionError(argv)

    return runner


@pytest.mark.parametrize(
    "bindings",
    [
        [{"HostIp": "0.0.0.0", "HostPort": "58080"}],
        [{"HostIp": "::", "HostPort": "58080"}],
        [{"HostIp": "[::]", "HostPort": "58080"}],
        [{"HostIp": "192.0.2.10", "HostPort": "58080"}],
        [
            {"HostIp": "127.0.0.1", "HostPort": "58080"},
            {"HostIp": "0.0.0.0", "HostPort": "58080"},
        ],
        [
            {"HostIp": "127.0.0.1", "HostPort": "58080"},
            {"HostIp": "127.0.0.1", "HostPort": "58080"},
        ],
    ],
)
def test_origin_ownership_rejects_wildcard_alternate_and_duplicate_bindings(bindings):
    deployer = _load_deployer()
    with pytest.raises(deployer.DeploymentError, match="ownership drifted"):
        deployer.verify_origin_ownership(
            "bootstrap", None, {}, _origin_runner(bindings)
        )


def test_origin_ownership_requires_exact_loopback_listener_and_no_staging_binding():
    deployer = _load_deployer()
    exact = [{"HostIp": "127.0.0.1", "HostPort": "58080"}]
    deployer.verify_origin_ownership("bootstrap", None, {}, _origin_runner(exact))

    with pytest.raises(deployer.DeploymentError, match="not exact loopback"):
        deployer.verify_origin_ownership(
            "bootstrap", None, {}, _origin_runner(exact, "0.0.0.0:58080")
        )

    mixed = [
        {"HostIp": "127.0.0.1", "HostPort": "58080"},
        {"HostIp": "127.0.0.1", "HostPort": "58081"},
    ]
    with pytest.raises(deployer.DeploymentError, match="staging origin"):
        deployer.verify_origin_ownership(
            "bootstrap", None, {}, _origin_runner(mixed)
        )


def test_origin_bindings_are_rechecked_for_staging_and_active_cutover():
    deployer = _load_deployer()
    owners = {
        deployer.LEGACY_ORIGIN: {
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "58080"}]
        },
        deployer.CONTAINERS["web-blue"]: {
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "58081"}]
        },
    }

    def runner(argv, **_kwargs):
        if argv[:3] == ["docker", "ps", "--no-trunc"]:
            return subprocess.CompletedProcess(
                argv, 0, "\n".join(owners) + "\n", ""
            )
        if argv[:3] == ["docker", "inspect", "--format"]:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps(owners[argv[-1]]), ""
            )
        if argv[:3] == ["ss", "-H", "-lnt"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                "LISTEN 0 4096 127.0.0.1:58080 0.0.0.0:*\n"
                "LISTEN 0 4096 127.0.0.1:58081 0.0.0.0:*\n",
                "",
            )
        raise AssertionError(argv)

    deployer.verify_exact_origin_bindings(
        deployer.LEGACY_ORIGIN, deployer.CONTAINERS["web-blue"], {}, runner
    )
    source = DEPLOYER.read_text(encoding="utf-8")
    assert source.count("verify_exact_origin_bindings(") >= 4

    owners[deployer.CONTAINERS["web-blue"]]["8080/tcp"].append(
        {"HostIp": "::", "HostPort": "58081"}
    )
    with pytest.raises(deployer.DeploymentError, match="staging origin"):
        deployer.verify_exact_origin_bindings(
            deployer.LEGACY_ORIGIN, deployer.CONTAINERS["web-blue"], {}, runner
        )


def test_inventory_preserves_duplicate_and_non_loopback_binding_evidence():
    inventory = _load_inventory()
    ownership = inventory.loopback_origin_ownership(
        [
            {
                "Names": "edfinder-v3-proxy",
                "State": "running",
                "PortsDetail": [
                    {
                        "bind_address": "127.0.0.1", "host_port": 58080,
                        "container_port": 8080, "protocol": "tcp",
                    },
                    {
                        "bind_address": "127.0.0.1", "host_port": 58080,
                        "container_port": 8080, "protocol": "tcp",
                    },
                    {
                        "bind_address": "::", "host_port": 58081,
                        "container_port": 8080, "protocol": "tcp",
                    },
                ],
            }
        ],
        inspection_succeeded=True,
    )
    assert len(ownership["ports"]["58080"]["bindings"]) == 2
    assert ownership["ports"]["58080"]["exact_loopback_only"] is False
    assert ownership["ports"]["58081"]["bindings"][0]["bind_address"] == "::"
    assert ownership["ports"]["58081"]["exact_loopback_only"] is False
    assert ownership["exact_loopback_only"] is False


def _cancellation_promote_setup(monkeypatch, tmp_path, deployer):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(mode=0o700)
    api_env = tmp_path / "api.env"
    api_env.write_text(
        "DATABASE_URL=postgresql://"
        + deployer.DATABASE_USER
        + ":x@"
        + deployer.POSTGRES_CONTAINER
        + ":5432/"
        + deployer.DATABASE_NAME
        + "\n",
        encoding="utf-8",
    )
    api_env.chmod(0o600)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    schema_path.chmod(0o600)
    token = tmp_path / "token"
    token.write_text("ephemeral", encoding="utf-8")
    token.chmod(0o600)
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    candidate_path = tmp_path / "candidate.json"
    checksum_path = tmp_path / "candidate.json.sha256"
    candidate_path.write_text("{}", encoding="utf-8")
    checksum_path.write_text("unused", encoding="utf-8")

    database_identity = {
        "container": deployer.POSTGRES_CONTAINER,
        "database_name": deployer.DATABASE_NAME,
        "database_user": deployer.DATABASE_USER,
        "application_host": deployer.POSTGRES_CONTAINER,
        "server_address": "local",
        "server_port": 5432,
    }
    schema = {
        "database_identity": database_identity,
        "migration_set_identity": "sha256:" + "c" * 64,
    }
    candidate = {
        "git_sha": "a" * 40,
        "images": {
            "backend": "ghcr.io/example/backend@sha256:" + "b" * 64,
            "web": "ghcr.io/example/web@sha256:" + "d" * 64,
        },
    }
    authority = {
        "target": {
            "production": True,
            "hostname": deployer.EXPECTED_HOST,
            "fqdn": deployer.EXPECTED_FQDN,
        },
        "external_authority": {
            "api_env_file": str(api_env),
            "api_env_owner_uid": os.geteuid(),
            "api_env_mode": "0600",
            "receipt_directory": str(receipt_dir),
            "receipt_owner_uid": os.geteuid(),
            "receipt_mode": "0700",
            "schema_identity_file": str(schema_path),
            "schema_identity_owner_uid": os.geteuid(),
            "schema_identity_mode": "0600",
            "schema_identity_sha256": "e" * 64,
            "docker_context": "default",
            "application_network": "production-app",
            "staging_origin_bind": "127.0.0.1:58081",
            "active_origin_bind": "127.0.0.1:58080",
            "public_origin": "https://ed-finder.app",
        },
        "preservation_contract": {"exact_containers": []},
    }
    args = SimpleNamespace(
        operation="promote",
        mode="bootstrap",
        compose=compose,
        candidate=candidate_path,
        candidate_checksum=checksum_path,
        candidate_run_id="12345",
        registry_token_file=token,
        registry_username="operator",
        runtime_directory=runtime,
    )
    snapshot = runtime / ".snapshot"

    monkeypatch.setattr(deployer, "exact_host_guard", lambda _runner: None)
    monkeypatch.setattr(deployer, "secure_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(deployer, "docker_context_guard", lambda *_args: None)
    monkeypatch.setattr(deployer, "validate_compose", lambda *_args: None)
    monkeypatch.setattr(deployer, "validate_schema_file", lambda *_args: schema)
    monkeypatch.setattr(deployer, "validate_network", lambda *_args: None)
    monkeypatch.setattr(deployer, "live_capacity_guard", lambda: {"logical_cpus": 16})
    def database_identity_from_env(_path, *, on_read=None):
        if on_read is not None:
            on_read()
        return database_identity

    monkeypatch.setattr(
        deployer, "database_identity_from_env", database_identity_from_env
    )
    monkeypatch.setattr(
        deployer, "validate_candidate",
        lambda *_args: (candidate, "f" * 64, b'{}'),
    )
    monkeypatch.setattr(deployer, "container_snapshot", lambda *_args: {})
    monkeypatch.setattr(
        deployer, "all_container_snapshot",
        lambda *_args: {
            deployer.LEGACY_API: "1" * 64 + ":running",
            deployer.LEGACY_ORIGIN: "2" * 64 + ":running",
        },
    )
    monkeypatch.setattr(deployer, "verify_origin_ownership", lambda *_args: None)
    monkeypatch.setattr(deployer, "verify_exact_origin_bindings", lambda *_args: None)
    monkeypatch.setattr(deployer, "verify_edge_routes_to_active_origin", lambda: None)
    monkeypatch.setattr(deployer, "verify_unrelated_snapshot", lambda *_args: None)
    monkeypatch.setattr(deployer, "verify_snapshot", lambda *_args: None)
    monkeypatch.setattr(deployer, "verify_env_unchanged", lambda *_args: None)
    monkeypatch.setattr(deployer, "verify_image", lambda *_args: None)
    monkeypatch.setattr(deployer, "wait_ready", lambda *_args: None)
    monkeypatch.setattr(deployer, "smoke", lambda *_args: {})

    def freeze_env(*_args):
        snapshot.write_text("frozen", encoding="utf-8")
        snapshot.chmod(0o600)
        return snapshot, (0, 0, 0, 0, 0, "digest")

    monkeypatch.setattr(deployer, "freeze_env", freeze_env)
    return args, authority, receipt_dir, snapshot


def _assert_durable_failure_receipt(receipt_dir: Path, receipt: dict) -> None:
    basename = receipt["durable_failure_receipt"]
    path = receipt_dir / basename
    sidecar = Path(str(path) + ".sha256")
    assert path.is_file()
    fields = sidecar.read_text(encoding="utf-8").split()
    assert fields == [hashlib.sha256(path.read_bytes()).hexdigest(), basename]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["failures"] == receipt["failures"]
    assert persisted["rollback"] == receipt["rollback"]
    assert persisted["service_changes_performed"] == receipt[
        "service_changes_performed"
    ]


def test_preflight_reports_ephemeral_bundle_writes_without_application_mutation(
    monkeypatch, tmp_path
):
    deployer = _load_deployer()
    args, authority, _receipt_dir, _snapshot = _cancellation_promote_setup(
        monkeypatch, tmp_path, deployer
    )
    args.operation = "preflight"
    monkeypatch.setattr(deployer, "verify_live_schema", lambda *_args: None)

    receipt = deployer.promote(
        args,
        authority,
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )

    assert receipt["status"] == "preflight-passed"
    assert receipt["filesystem_writes_performed"] is True
    assert receipt["filesystem_write_scope"] == "ephemeral-operation-bundle-only"
    assert receipt["env_files_read"] is True
    for field in (
        "database_writes_performed", "migrations_performed",
        "application_data_writes_performed", "image_pulls_performed",
        "service_changes_performed", "edge_recreated",
        "protected_resources_changed",
    ):
        assert receipt[field] is False


@pytest.mark.parametrize(
    ("failure_point", "message"),
    [
        ("validate_candidate", "candidate validation stopped"),
        ("all_container_snapshot", "container validation stopped"),
        ("verify_origin_ownership", "origin validation stopped"),
    ],
)
def test_failures_after_api_env_read_preserve_audit_state(
    monkeypatch, tmp_path, failure_point, message
):
    deployer = _load_deployer()
    args, authority, _receipt_dir, _snapshot = _cancellation_promote_setup(
        monkeypatch, tmp_path, deployer
    )
    args.operation = "preflight"

    def stop(*_args, **_kwargs):
        raise deployer.DeploymentError(message)

    monkeypatch.setattr(deployer, failure_point, stop)
    with pytest.raises(deployer.OperationFailed) as failed:
        deployer.promote(
            args,
            authority,
            lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
        )

    receipt = failed.value.receipt
    assert receipt["failures"] == [message]
    assert receipt["env_files_read"] is True
    assert receipt["env_contents_recorded"] is False
    assert receipt["filesystem_writes_performed"] is True
    assert "postgresql://" not in json.dumps(receipt)


def test_env_audit_marker_changes_only_after_file_read_succeeds(tmp_path):
    deployer = _load_deployer()
    marker = []
    env_file = tmp_path / "api.env"
    env_file.write_text("not-a-database-url\n", encoding="utf-8")

    with pytest.raises(deployer.DeploymentError, match="exactly one DATABASE_URL"):
        deployer.database_identity_from_env(
            env_file, on_read=lambda: marker.append("read")
        )
    assert marker == ["read"]

    marker.clear()
    with pytest.raises(deployer.DeploymentError, match="unable to read"):
        deployer.database_identity_from_env(
            tmp_path / "missing.env", on_read=lambda: marker.append("read")
        )
    assert marker == []


def test_cancellation_before_mutation_writes_durable_failure_without_service_change(monkeypatch, tmp_path):
    deployer = _load_deployer()
    args, authority, receipt_dir, snapshot = _cancellation_promote_setup(
        monkeypatch, tmp_path, deployer
    )
    commands = []

    def runner(argv, **_kwargs):
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def cancel_before_mutation(*_args):
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(deployer, "verify_live_schema", cancel_before_mutation)
    with deployer.controlled_cancellation():
        with pytest.raises(deployer.OperationFailed) as failed:
            deployer.promote(args, authority, runner)

    receipt = failed.value.receipt
    assert receipt["failures"] == ["operation_cancelled:SIGTERM"]
    assert receipt["rollback"] == {"attempted": False, "status": "not-required"}
    assert receipt["service_changes_performed"] is False
    assert not any("up" in command or "stop" in command for command in commands)
    assert not snapshot.exists()
    _assert_durable_failure_receipt(receipt_dir, receipt)


def test_pre_mutation_gate_cancellation_is_persisted_by_main(monkeypatch, tmp_path, capsys):
    deployer = _load_deployer()
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(mode=0o700)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(
        json.dumps(
            {
                "target": {
                    "production": True,
                    "hostname": deployer.EXPECTED_HOST,
                    "fqdn": deployer.EXPECTED_FQDN,
                },
                "external_authority": {
                    "receipt_directory": str(receipt_dir),
                    "receipt_owner_uid": os.geteuid(),
                    "receipt_mode": "0700",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(deployer, "validate_authority", lambda _authority: [])
    def cancel_in_verified_pre_mutation_gate(*_args):
        deployer._PREMUTATION_FAILURE_RECEIPT_DIR = receipt_dir
        raise deployer.OperationCancelled(signal.SIGTERM)

    monkeypatch.setattr(deployer, "promote", cancel_in_verified_pre_mutation_gate)

    status = deployer._main(
        [
            "--authority", str(authority_path),
            "--operation", "promote",
            "--candidate", str(tmp_path / "candidate.json"),
            "--candidate-checksum", str(tmp_path / "candidate.sha256"),
            "--candidate-run-id", "12345",
        ]
    )
    assert status == 78
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["failures"] == ["operation_cancelled:SIGTERM"]
    assert receipt["rollback"] == {"attempted": False, "status": "not-required"}
    _assert_durable_failure_receipt(receipt_dir, receipt)


def test_cancellation_after_cutover_rolls_back_and_writes_durable_failure(monkeypatch, tmp_path):
    deployer = _load_deployer()
    args, authority, receipt_dir, snapshot = _cancellation_promote_setup(
        monkeypatch, tmp_path, deployer
    )
    commands = []
    route_restored = []
    monkeypatch.setattr(deployer, "verify_live_schema", lambda *_args: None)
    monkeypatch.setattr(
        deployer, "wait_for_preserved_edge_route", lambda: route_restored.append(True)
    )

    def runner(argv, **_kwargs):
        commands.append(argv)
        if (
            "up" in argv
            and argv[-1] == "web-blue"
            and argv[-2] == "never"
        ):
            signal.raise_signal(signal.SIGTERM)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with deployer.controlled_cancellation():
        with pytest.raises(deployer.OperationFailed) as failed:
            deployer.promote(args, authority, runner)

    receipt = failed.value.receipt
    assert receipt["failures"] == ["operation_cancelled:SIGTERM"]
    assert receipt["rollback"] == {
        "attempted": True,
        "status": "verified",
        "kind": "first-cutover-abort-to-preserved-origin",
        "accepted_release_rollback": False,
    }
    assert ["docker", "start", deployer.LEGACY_API] in commands
    assert ["docker", "start", deployer.LEGACY_ORIGIN] in commands
    assert any("rm" in command and "web-blue" in command for command in commands)
    assert route_restored == [True]
    assert not snapshot.exists()
    _assert_durable_failure_receipt(receipt_dir, receipt)


def test_controlled_cancellation_terminates_and_reaps_active_bounded_child(tmp_path):
    child_pid_file = tmp_path / "child.pid"
    helper = textwrap.dedent(
        """
        import signal
        import sys
        from scripts.operator import v3_production_deploy as deployer

        deployer.PROCESS_TERMINATION_GRACE = 0.1
        child_code = (
            "import os,signal,sys,time;"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            "open(sys.argv[1], 'w').write(str(os.getpid()));"
            "time.sleep(60)"
        )
        try:
            with deployer.controlled_cancellation():
                deployer.run_command([sys.executable, "-c", child_code, sys.argv[1]])
        except deployer.OperationCancelled:
            raise SystemExit(78)
        """
    )
    process = subprocess.Popen(
        [sys.executable, "-c", helper, str(child_pid_file)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while not child_pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 78, (stdout, stderr)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
