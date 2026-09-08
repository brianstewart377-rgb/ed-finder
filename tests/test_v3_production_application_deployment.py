from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/v3-production/compose.yml"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
DEPLOYER = ROOT / "scripts/operator/v3_production_deploy.py"
INVENTORY = ROOT / "scripts/operator/v3_production_inventory.py"
INVENTORY_ACTION = ROOT / "scripts/operator/actions/v3-production-inventory.sh"
PROMOTE_ACTION = ROOT / "scripts/operator/actions/v3-production-promote.sh"
WORKFLOW = ROOT / ".github/workflows/v3-production-application-deploy.yml"
RUNBOOK = ROOT / "docs/operations/v3-production-application-release.md"


def _load_deployer():
    spec = importlib.util.spec_from_file_location("v3_production_deploy", DEPLOYER)
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
        "production_local_docker_context_authority_missing",
        "production_promotion_cpython314_runtime_unproved",
        "production_edge_loopback_cutover_topology_authority_missing",
    }.issubset(value["blockers"])
    assert value["application_contract"]["compose_project"] == "edfinder-v3-production"
    assert "checkpoint" not in value["application_contract"]["compose_project"]
    assert value["application_contract"]["compose_sha256"] == hashlib.sha256(COMPOSE.read_bytes()).hexdigest()
    assert all(value["external_authority"][key] is None for key in (
        "application_network", "api_env_file", "schema_identity_file",
        "edge_route_authority", "receipt_directory", "docker_context",
    ))


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
    assert "FROM public.schema_migrations" in source
    assert "ORDER BY filename" in source
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
        '"docker_ps_ports"',
        '"58080"',
        '"58081"',
        '"bindings"',
        '"owners"',
    ):
        assert required_inventory_fact in source
    assert '"docker", "context", "inspect", "default"' in source
    assert "command -v python3.14" not in action
    assert "command -v python3" in action
    for forbidden in (
        ".Config.Env", ".docker/config", "docker context export", "docker restart",
        "docker stop", "docker start", "compose up", "INSERT INTO", "UPDATE ",
        "DELETE FROM", "TRUNCATE", "ALTER TABLE", "DROP TABLE",
    ):
        assert forbidden not in source


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


def test_production_schema_identity_preserves_release_manifest_order(tmp_path):
    deployer = _load_deployer()
    release_spec = importlib.util.spec_from_file_location(
        "v3_release_manifest_for_production_test",
        ROOT / "scripts/release/v3_release_manifest.py",
    )
    assert release_spec and release_spec.loader
    release = importlib.util.module_from_spec(release_spec)
    release_spec.loader.exec_module(release)
    migration_set = release.migration_set(ROOT)
    assert migration_set["entries"] != sorted(
        migration_set["entries"], key=lambda item: item["path"]
    )
    schema = {
        "schema_version": deployer.SCHEMA_IDENTITY_SCHEMA,
        "database_identity": {
            "container": deployer.POSTGRES_CONTAINER,
            "database_name": "edfinder",
            "database_user": "edfinder",
            "application_host": deployer.POSTGRES_CONTAINER,
            "server_address": "local",
            "server_port": 5432,
        },
        "migration_set_identity": migration_set["identity"],
        "migration_set_entries": migration_set["entries"],
        "evidence": "reviewed-production-inventory-receipt",
    }
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")

    assert deployer.validate_schema_file(
        path, hashlib.sha256(path.read_bytes()).hexdigest()
    )["migration_set_identity"] == migration_set["identity"]


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


def test_workflow_is_manual_main_only_protected_and_uses_pinned_ssh_trust():
    workflow = _workflow()
    source = WORKFLOW.read_text(encoding="utf-8")

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "github.ref == 'refs/heads/main'" in source
    assert "github.repository == 'brianstewart377-rgb/ed-finder'" in source
    assert workflow["jobs"]["inventory"]["environment"] == "v3-production-readonly"
    assert workflow["jobs"]["production-operation"]["environment"] == "v3-production"
    assert source.count("persist-credentials: false") >= 4
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in source
    assert "ssh-keyscan" not in source
    assert "V3_PRODUCTION_SSH_KEY" in source
    assert "V3_LIVE_CHECKPOINT" not in source
    assert "ED_NEW_OPERATOR" not in source
    assert "target_confirmation" in source
    assert source.count("uses: actions/download-artifact@") == 2
    assert "Stop before credentials or SSH while production authority is blocked" in source
    assert "Candidate is not the exact current main release" in source
    assert "exec bash scripts/operator/actions/v3-production-promote.sh" not in source
    assert "--runtime-directory" in source
    assert "kill -TERM" in source


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
    assert "loopback ports `58080` and `58081`" in source
    assert "fills a blocker" in source
    assert "stale `edfinder-v3-api:phase4c-r5`" in source
    assert "Redis and NATS are not removed or replaced" in source


def test_new_shell_launchers_parse():
    for path in (INVENTORY_ACTION, PROMOTE_ACTION):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_inventory_ledger_parser_rejects_extra_or_malformed_output():
    inventory = _load_inventory()
    good = json.dumps(
        {
            "database_name": "edfinder",
            "server_address": "local",
            "server_port": 5432,
            "transaction_read_only": "on",
            "migrations": [
                {"filename": "001_initial.sql", "checksum_sha256": "a" * 64}
            ],
        }
    )
    completed = subprocess.CompletedProcess(["psql"], 0, good, "")
    assert inventory.parse_ledger(completed)["inspection_succeeded"] is True

    for hostile in (
        good + "\nignored-extra-output",
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
        "docker", "context", "inspect", "default", "--format",
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
        "inspection_succeeded": True,
        "name": "default",
        "docker_endpoint": "tcp://127.0.0.1:2375",
    }

    for unsafe_endpoint in (
        "ssh://user:password@example.invalid/run/docker.sock",
        "tcp://token@example.invalid:2375",
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
                "Ports": "127.0.0.1:58080->80/tcp, 0.0.0.0:58081->81/tcp",
            },
            {
                "Names": "candidate-web",
                "State": "running",
                "Ports": "127.0.0.1:58081->3000/tcp",
            },
            {
                "Names": "stopped-web",
                "State": "exited",
                "Ports": "127.0.0.1:58081->3000/tcp",
            },
        ],
        inspection_succeeded=True,
    )
    assert ownership["inspection_succeeded"] is True
    assert ownership["ports"]["58080"]["owners"] == ["edfinder-v3-proxy"]
    assert ownership["ports"]["58080"]["bindings"] == [
        {"container": "edfinder-v3-proxy", "container_port": 80, "protocol": "tcp"}
    ]
    assert ownership["ports"]["58081"]["owners"] == ["candidate-web"]
    assert ownership["ports"]["58081"]["bindings"] == [
        {"container": "candidate-web", "container_port": 3000, "protocol": "tcp"}
    ]

    incomplete = inventory.loopback_origin_ownership(
        [{"Names": "malformed", "State": "running", "Ports": ["not-a-string"]}],
        inspection_succeeded=False,
    )
    assert incomplete["inspection_succeeded"] is False
    assert incomplete["ports"]["58080"]["owners"] == []
    assert incomplete["ports"]["58081"]["owners"] == []
