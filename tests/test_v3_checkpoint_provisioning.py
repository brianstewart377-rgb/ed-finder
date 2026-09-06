"""Contracts for bounded Contabo V3 live-checkpoint infrastructure provisioning."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import importlib.util

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/v3-live-checkpoint-provision.yml"
PROVISIONER = ROOT / "scripts/operator/actions/v3-live-checkpoint-provision.sh"
AUTHORITY = ROOT / "deploy/v3-live-checkpoint/target-authority.json"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(name: str) -> dict:
    return next(
        item
        for item in _workflow()["jobs"]["provision"]["steps"]
        if item.get("name") == name
    )


def _run_dispatch_request(
    tmp_path: Path, **overrides: str
) -> subprocess.CompletedProcess[str]:
    output = tmp_path / "github-output"
    env = {
        **os.environ,
        "EVENT_NAME": "workflow_dispatch",
        "INPUT_OPERATION": "provision-infrastructure",
        "INPUT_BACKEND_IMAGE": "",
        "INPUT_WEB_IMAGE": "",
        "BEFORE_SHA": "",
        "CURRENT_SHA": "",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(output),
        **overrides,
    }
    return subprocess.run(
        ["bash", "-c", _step("Resolve allowlisted provisioning request")["run"]],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_workflow_is_separate_request_triggered_and_environment_gated():
    workflow = _workflow()
    triggers = workflow["on"]
    job = workflow["jobs"]["provision"]

    assert set(triggers) == {"workflow_dispatch", "push"}
    assert triggers["push"]["branches"] == ["v3-live-checkpoint-provision-requests"]
    assert triggers["push"]["paths"] == [
        ".github/v3-live-checkpoint-provision-requests/*.json"
    ]
    assert set(triggers["workflow_dispatch"]["inputs"]) == {
        "operation",
        "backend_image",
        "web_image",
    }
    assert triggers["workflow_dispatch"]["inputs"]["operation"]["options"] == [
        "provision-infrastructure"
    ]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["environment"] == "v3-live-checkpoint"
    assert workflow["concurrency"]["cancel-in-progress"] == "false"


def test_request_allowlist_rejects_partial_wrong_or_unpinned_ghcr_inputs(tmp_path):
    backend = "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "a" * 64
    web = "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "b" * 64
    accepted = _run_dispatch_request(
        tmp_path, INPUT_BACKEND_IMAGE=backend, INPUT_WEB_IMAGE=web
    )
    assert accepted.returncode == 0, accepted.stderr

    cases = (
        {"INPUT_OPERATION": "deploy"},
        {"INPUT_BACKEND_IMAGE": backend},
        {
            "INPUT_BACKEND_IMAGE": "ghcr.io/attacker/image@sha256:" + "a" * 64,
            "INPUT_WEB_IMAGE": web,
        },
        {
            "INPUT_BACKEND_IMAGE": backend.replace("@sha256:", ":latest"),
            "INPUT_WEB_IMAGE": web,
        },
    )
    for index, values in enumerate(cases):
        result = _run_dispatch_request(tmp_path / str(index), **values)
        assert result.returncode == 64


def test_workflow_uses_trusted_main_source_free_bundle_and_sanitized_outputs_only():
    source = WORKFLOW.read_text(encoding="utf-8")
    steps = _workflow()["jobs"]["provision"]["steps"]
    names = [step.get("name") for step in steps]

    assert names.index("Resolve allowlisted provisioning request") < names.index(
        "Checkout trusted provisioning implementation"
    )
    trusted = _step("Checkout trusted provisioning implementation")
    assert trusted["with"] == {
        "ref": "main",
        "path": "trusted-main",
        "persist-credentials": "false",
    }
    bundle = _step("Assemble source-free provisioning bundle")["run"]
    assert "scripts/apply_migrations.sh" in bundle
    assert "scripts/seed_check.sh" in bundle
    assert "sql/*.sql" in bundle
    assert "v3_release_manifest import migration_set" in bundle
    assert "apps/api" not in bundle
    assert "apps/web" not in bundle

    upload = _step("Upload sanitized provisioning evidence")["with"]
    assert upload["path"].splitlines() == [
        "${{ runner.temp }}/v3-live-checkpoint-provisioning-output/provisioning-receipt.json",
        "${{ runner.temp }}/v3-live-checkpoint-provisioning-output/target-authority-candidate.json",
    ]
    assert "deploy/v3-live-checkpoint/target-authority.json" not in bundle
    assert (
        'Path("trusted-main/deploy/v3-live-checkpoint/target-authority.json")' in source
    )
    for forbidden in (
        "ssh-keyscan",
        "ED_NEW_OPERATOR_",
        "git pull",
        "docker compose up",
    ):
        assert forbidden not in source


def test_workflow_uses_only_dedicated_pinned_ssh_secret_boundary():
    source = WORKFLOW.read_text(encoding="utf-8")
    secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", source))
    assert secrets == {
        "V3_LIVE_CHECKPOINT_SSH_KEY",
        "V3_LIVE_CHECKPOINT_HOST",
        "V3_LIVE_CHECKPOINT_PORT",
        "V3_LIVE_CHECKPOINT_USER",
        "V3_LIVE_CHECKPOINT_SSH_KNOWN_HOSTS",
    }
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in source
    assert "ssh-keygen -F" in source


def test_provisioner_guards_exact_target_and_runner_set_before_mutation():
    source = PROVISIONER.read_text(encoding="utf-8")
    mutation = source.index("MUTATION_STARTED=true")

    for guard in (
        '[[ "$(hostname -s 2>/dev/null)" == "$TARGET_HOSTNAME" ]]',
        '[[ "$(hostname -f 2>/dev/null)" == "$TARGET_FQDN" ]]',
        '[[ "$(uname -m)" == "$TARGET_ARCH" ]]',
        "exact_runners_active || stop runner_service_set_mismatch",
    ):
        assert source.index(guard) < mutation
    assert (
        source.count(
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service"
        )
        >= 2
    )
    assert (
        source.count(
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service"
        )
        >= 2
    )
    assert (
        source.count(
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service"
        )
        >= 2
    )
    assert (
        source.index("exact_runners_active || stop runner_service_set_changed")
        > mutation
    )
    for forbidden in (
        "systemctl restart actions.runner",
        "systemctl stop actions.runner",
        "systemctl start actions.runner",
    ):
        assert forbidden not in source


def test_provisioner_owns_only_checkpoint_infrastructure_and_never_deploys_app():
    source = PROVISIONER.read_text(encoding="utf-8")

    assert 'APP_NETWORK="edfinder-v3-checkpoint-app"' in source
    assert 'ORIGIN_PORT="18080"' in source
    assert "postgresql-18 postgresql-client-18" in source
    assert "scripts/seed_check.sh" in source
    assert "apply_migrations.sh --include-manual" in source
    assert "sql/seed_preview.sql" in source
    assert "default_transaction_read_only=on" in source
    assert "server_name $TARGET_FQDN;" in source
    assert "return 404" in source
    assert "production_data_copied:false" in source
    assert "application_deploy_performed:false" in source
    assert "redis_provisioned:false" in source
    assert "valkey_provisioned:false" in source
    assert "nats_provisioned:false" in source
    for forbidden in (
        "docker compose up",
        "docker compose down",
        "git pull",
        "git clone",
        "target-authority.json",
        "nb79a3d.mevnode.com",
    ):
        assert forbidden not in source


def test_ghcr_authority_requires_real_anonymous_digest_pulls_or_blocker():
    source = PROVISIONER.read_text(encoding="utf-8")
    assert "printf '%s\\n' '{}' >\"$probe_config/config.json\"" in source
    assert 'docker --host unix:///var/run/docker.sock pull "$BACKEND_IMAGE"' in source
    assert 'docker --host unix:///var/run/docker.sock pull "$WEB_IMAGE"' in source
    assert 'GHCR_STATUS="anonymous_public_digest_pull_proven"' in source
    assert "explicit_secret_backed_ghcr_pull_authority_required" in source
    assert "docker login" not in source
    assert "GITHUB_TOKEN" not in source


def test_committed_target_authority_remains_the_original_stopped_document():
    import json

    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    assert authority["status"] == "stopped"
    assert authority["external_authority"]["api_env_file"] is None
    assert authority["external_authority"]["database_source_authority"] is None
    assert authority["external_authority"]["ghcr_pull_authority"] is None


def test_success_and_transport_blocker_candidate_shapes_pass_deploy_validator():
    import copy
    import json

    spec = importlib.util.spec_from_file_location(
        "v3_checkpoint_deploy",
        ROOT / "scripts/operator/v3_checkpoint_deploy.py",
    )
    assert spec is not None and spec.loader is not None
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)

    recorded = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    transport = copy.deepcopy(recorded)
    transport["blockers"] = sorted(
        set(transport["blockers"] + ["remote_transport_or_bundle_failed"])
    )
    assert "remote_transport_or_bundle_failed" in deploy.validate_authority(transport)

    candidate = copy.deepcopy(recorded)
    candidate["status"] = "authorized"
    candidate["blockers"] = []
    candidate["observed_runtime"]["container_runtime"] = "29.1.0"
    candidate["observed_runtime"]["compose"] = "5.0.0"
    candidate["observed_runtime"]["docker_networks"] = [
        "bridge",
        "edfinder-v3-checkpoint-app",
        "host",
        "none",
    ]
    candidate["external_authority"] = {
        "api_env_file": "/etc/ed-finder/v3-checkpoint/api.env",
        "api_env_owner_uid": 1000,
        "api_env_mode": "0600",
        "database_source_authority": (
            "contabo-vmi3542235-native-postgresql18-preview-v1"
        ),
        "schema_identity_receipt": (
            "/var/lib/edfinder-v3-checkpoint/schema-identity.json"
        ),
        "schema_identity_receipt_sha256": "a" * 64,
        "origin_bind": "http://127.0.0.1:18080",
        "edge_route_authority": (
            "http-only-provider-fqdn-vmi3542235.contaboserver.net-"
            "to-loopback-18080-no-dns"
        ),
        "receipt_directory": "/var/lib/edfinder-v3-checkpoint/receipts",
        "receipt_owner_uid": 1000,
        "receipt_mode": "0700",
        "ghcr_pull_authority": "anonymous-public-digest-pull:proved",
        "docker_config_directory": ("/var/lib/edfinder-v3-checkpoint/docker-config"),
        "docker_config_owner_uid": 1000,
        "docker_config_mode": "0700",
        "docker_context": "edfinder-v3-checkpoint",
    }
    assert deploy.validate_authority(candidate) == []

    source = PROVISIONER.read_text(encoding="utf-8")
    for key in candidate["external_authority"]:
        assert f"{key}:" in source


def test_provisioner_rejects_non_root_before_target_mutation(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("non-root boundary test requires a non-root test runner")
    result = subprocess.run(
        [
            str(PROVISIONER),
            "--operator-user",
            subprocess.check_output(["id", "-un"], text=True).strip(),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 77
    assert result.stdout == ""
    assert "requires non-interactive root authority" in result.stderr


@pytest.mark.parametrize("shell", ["bash"])
def test_provisioner_has_valid_shell_syntax(shell):
    result = subprocess.run(
        [shell, "-n", str(PROVISIONER)], text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
