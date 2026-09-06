"""Fail-closed contracts for provisioning the non-production V3 checkpoint."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVISION_WORKFLOW = ROOT / ".github" / "workflows" / "v3-live-checkpoint-provision.yml"
DISPATCH_WORKFLOW = (
    ROOT / ".github" / "workflows" / "v3-application-checkpoint-dispatch.yml"
)
BOOTSTRAP = ROOT / "deploy" / "v3-live-checkpoint" / "host-bootstrap.sh"
RECEIPT_HELPER = ROOT / "deploy" / "v3-live-checkpoint" / "bootstrap_receipt.py"
SYNTHETIC_FIXTURE = (
    ROOT / "deploy" / "v3-live-checkpoint" / "synthetic-checkpoint-fixture.sql"
)


def _workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_step(path: Path, name: str) -> dict[str, str]:
    workflow = _workflow(path)
    steps = next(iter(workflow["jobs"].values()))["steps"]
    return next(step for step in steps if step.get("name") == name)


def _load_checkpoint_module():
    path = ROOT / "scripts" / "operator" / "v3_checkpoint_deploy.py"
    spec = importlib.util.spec_from_file_location("v3_checkpoint_deploy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_dispatch_validation(
    tmp_path: Path, **inputs: str
) -> subprocess.CompletedProcess[str]:
    step = _workflow_step(DISPATCH_WORKFLOW, "Validate and seal exact canonical inputs")
    env = {
        **os.environ,
        "INPUT_OPERATION": "",
        "INPUT_SOURCE_SHA": "",
        "INPUT_SCHEMA_COMPATIBILITY": "unknown",
        "INPUT_COMPATIBILITY_EVIDENCE": "",
        "INPUT_REVIEWED_MIGRATION_SETS": "",
        "INPUT_ROLLBACK_ELIGIBLE": "false",
        "INPUT_DEPLOYMENT_MODE": "bootstrap",
        "INPUT_RELEASE_RUN_ID": "",
        "SEALED_PAYLOAD": str(tmp_path / "sealed.json"),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        **inputs,
    }
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_provision_request(
    tmp_path: Path, operation: str
) -> subprocess.CompletedProcess[str]:
    step = _workflow_step(PROVISION_WORKFLOW, "Resolve allowlisted request")
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=ROOT,
        env={
            **os.environ,
            "EVENT_NAME": "workflow_dispatch",
            "INPUT_OPERATION": operation,
            "BEFORE_SHA": "0" * 40,
            "CURRENT_SHA": "a" * 40,
            "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_provision_operator_is_request_triggered_and_strictly_allowlisted():
    workflow = _workflow(PROVISION_WORKFLOW)
    triggers = workflow["on"]
    dispatch = triggers["workflow_dispatch"]["inputs"]
    operation = dispatch["operation"]

    assert set(triggers) == {"workflow_dispatch", "push"}
    assert set(dispatch) == {"operation"}
    assert operation["type"] == "choice"
    assert operation["required"] == "true"
    assert set(operation["options"]) == {"check", "provision"}

    push = triggers["push"]
    assert push["branches"] == ["main"]
    assert push["paths"] == [".github/v3-live-checkpoint-requests/*.json"]

    source = _source(PROVISION_WORKFLOW)
    assert "Unsupported operation" in source
    assert "v3-live-checkpoint-requests" in source
    assert "operation" in source
    # Request files are data, not a way to inject extra parameters or commands.
    assert re.search(r"(keys|key).*\[?\"?operation", source, re.IGNORECASE)


def test_manual_provision_request_rejects_everything_outside_allowlist(tmp_path):
    for operation in ("check", "provision"):
        operation_dir = tmp_path / operation
        operation_dir.mkdir()
        result = _run_provision_request(operation_dir, operation)
        assert result.returncode == 0, result.stderr
        assert (operation_dir / "github-output").read_text() == (
            f"operation={operation}\n"
        )

    hostile_dir = tmp_path / "hostile"
    hostile_dir.mkdir()
    hostile = _run_provision_request(hostile_dir, "provision; id")
    assert hostile.returncode != 0
    assert not (hostile_dir / "github-output").exists()


def test_provision_operator_uses_a_pinned_nonproduction_ssh_boundary():
    workflow = _workflow(PROVISION_WORKFLOW)
    assert workflow["permissions"] == {"contents": "read"}

    jobs = workflow["jobs"]
    assert len(jobs) == 1
    job = next(iter(jobs.values()))
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["runs-on"] == "ubuntu-latest"
    assert "v3-live-checkpoint" in str(job["environment"])
    assert int(job["timeout-minutes"]) <= 30

    source = _source(PROVISION_WORKFLOW)
    assert "persist-credentials: false" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=" in source
    assert "ssh-keyscan" not in source
    assert "vmi3542235" in source
    assert "vmi3542235.contaboserver.net" in source
    assert "host-bootstrap.sh" in source
    assert "bootstrap_receipt.py" in source
    assert "synthetic-checkpoint-fixture.sql" in source
    assert "apply_migrations.sh" in source
    assert "v3_checkpoint_deploy.py" in source
    assert "--source-sha" in source or "trusted-source-sha" in source
    assert "--ghcr-username-file" in source
    assert "--ghcr-token-file" in source
    assert "git pull" not in source
    assert "docker build" not in source

    remote = _workflow_step(
        PROVISION_WORKFLOW, "Run bounded source-free prerequisite operator"
    )["run"]
    # Bootstrap's sanitized stdout must not prefix/corrupt the following tar stream.
    assert re.search(r"host-bootstrap[.]sh.*?>\s*/dev/null.*?tar -C", remote)


def test_remote_wrapper_returns_a_clean_tar_stream_after_bootstrap_stdout(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "deploy/v3-live-checkpoint").mkdir(parents=True)
    (bundle / "deploy/v3-live-checkpoint/host-bootstrap.sh").write_text("stub\n")
    (bundle / "request-operation").write_text("check\n")
    (bundle / "trusted-source-sha").write_text("a" * 40 + "\n")
    (bundle / "postgres-image").write_text("postgres:18\n")
    (bundle / "ghcr-proof-image").write_text("")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        "#!/usr/bin/env bash\n"
        'for last_arg in "$@"; do :; done\n'
        'PATH="$FAKE_REMOTE_BIN:$PATH" bash -c "$last_arg"\n'
    )
    fake_ssh.chmod(0o700)
    fake_sudo = fake_bin / "sudo"
    fake_sudo.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == -n && "$2" == tar ]]; then shift; exec "$@"; fi\n'
        "output_dir=''\n"
        "while (($#)); do\n"
        '  if [[ "$1" == --output-dir ]]; then output_dir="$2"; shift 2; else shift; fi\n'
        "done\n"
        '[[ -n "$output_dir" ]] || exit 64\n'
        'printf \'%s\\n\' \'{"status":"accepted"}\' >"$output_dir/provisioning-receipt.json"\n'
        "printf '%s\\n' '{}' >\"$output_dir/target-authority-candidate.json\"\n"
        "printf '%s\\n' '{}' >\"$output_dir/schema-identity-receipt.json\"\n"
        "printf '%064d  schema-identity-receipt.json\\n' 0 >\"$output_dir/schema-identity-receipt.json.sha256\"\n"
        "printf '%s\\n' 'bootstrap stdout must not prefix the tar stream'\n"
    )
    fake_sudo.chmod(0o700)

    result_archive = tmp_path / "result.tar"
    result_dir = tmp_path / "result"
    step = _workflow_step(
        PROVISION_WORKFLOW, "Run bounded source-free prerequisite operator"
    )
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_REMOTE_BIN": str(fake_bin),
            "SSH_HOST": "checkpoint.invalid",
            "SSH_PORT": "22",
            "SSH_USER": "operator",
            "BUNDLE": str(bundle),
            "RESULT_ARCHIVE": str(result_archive),
            "RESULT_DIR": str(result_dir),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    archive_check = subprocess.run(
        ["tar", "-tf", str(result_archive)], check=False, capture_output=True, text=True
    )
    assert archive_check.returncode == 0, archive_check.stderr
    assert (result_dir / "provisioning-receipt.json").is_file()
    assert (result_dir / "target-authority-candidate.json").is_file()
    assert (result_dir / "schema-identity-receipt.json").is_file()
    assert (result_dir / "schema-identity-receipt.json.sha256").is_file()


def test_checkpoint_fixture_is_explicitly_synthetic_and_cannot_import_a_dump():
    source = _source(SYNTHETIC_FIXTURE)
    lowered = source.lower()

    assert "synthetic_non_production" in source
    assert "repository_owned" in source
    assert "checkpoint-synthetic-v1" in source
    assert "Checkpoint Synthetic" in source
    assert "Finder" in source
    assert "Inspect" in source
    for forbidden in (
        "copy ",
        "\\copy",
        "pg_restore",
        "pg_dump",
        "dblink",
        "postgres_fdw",
        "nb79a3d.mevnode.com",
        "edfinder_20260823T021001Z.dump",
    ):
        assert forbidden not in lowered


def test_host_bootstrap_is_syntactically_valid_bounded_and_preserves_three_runners():
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    source = _source(BOOTSTRAP)
    assert re.search(r"set -[Ee]*eu[Ee]*o pipefail", source)
    assert "umask 077" in source
    assert "vmi3542235" in source
    assert "vmi3542235.contaboserver.net" in source
    assert source.count("actions.runner.brianstewart377-rgb-ed-finder.") == 3
    # The same exact-set guard brackets host mutation and receipt generation.
    assert source.count("assert_runners") >= 4
    assert "timeout" in source
    assert "flock" in source
    for forbidden in (
        "git pull",
        "docker build",
        "docker compose build",
        "edfinder_20260823T021001Z.dump",
        "20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1",
        "nb79a3d.mevnode.com",
    ):
        assert forbidden not in source


def test_bootstrap_installs_and_verifies_only_the_checkpoint_dependencies():
    source = _source(BOOTSTRAP)
    lowered = source.lower()

    assert "docker-ce" in source or "docker.io" in source
    assert "docker-compose-plugin" in source or "docker-compose-v2" in source
    assert "postgresql-client-18" in source
    assert "CPython" in source and "(3, 14)" in source
    assert "docker version" in source
    assert "docker compose version" in source
    assert re.search(r"psql\s+--version|psql\s+-V", source)

    assert "postgres:18" in source
    assert "$POSTGRES_VOLUME:/var/lib/postgresql" in source
    assert '.Destination "/var/lib/postgresql"' in source
    assert "/var/lib/postgresql/data" not in source
    assert "PostgreSQL port publication is not exact" in source
    assert "PostgreSQL resource/restart policy is not exact" in source
    assert "edfinder-v3-checkpoint-app" in source
    assert "docker network" in source
    assert "com.edfinder.checkpoint" in source
    assert "docker context" in source
    assert "DOCKER_CONFIG" in source
    assert not re.search(
        r"(?:image|pull)\s*[:=]?\s*(?:redis|valkey|nats)(?::|\s)", lowered
    )


def test_bootstrap_keeps_generated_credentials_target_local_and_out_of_receipts():
    source = _source(BOOTSTRAP)
    lowered = source.lower()

    assert re.search(r"openssl\s+rand|/dev/urandom", source)
    assert re.search(r"(?:chmod|install\s+-m)\s+(?:0?600|0?640)", source)
    assert re.search(r"(?:chmod|install\s+-m)\s+0?700", source)
    assert "api.env" in lowered
    # The unprivileged SSH wrapper must be able to archive sanitized 0600 outputs.
    assert re.search(
        r'chown\s+"?\$OPERATOR_UID:\$OPERATOR_GID"?[^\n]*\$OUTPUT_DIR', source
    )
    assert "set -x" not in source
    assert "postgresql://$DATABASE_OWNER:$owner_password" not in source
    assert "::debug::" not in source
    assert "::notice::" not in source
    assert re.search(r"secret|password|credential", lowered)
    # Receipts may record secret *paths* and auth modes, never values.
    assert re.search(r"saniti[sz]", lowered)
    assert re.search(r"receipt", lowered)


def test_bootstrap_creates_fresh_schema_fixture_and_schema_identity_receipts():
    source = _source(BOOTSTRAP) + _source(RECEIPT_HELPER)
    lowered = source.lower()

    assert "migration-manifest.txt" in source
    assert "apply_migrations.sh" in source
    assert "psql" in source
    assert re.search(r"fixture", lowered)
    assert re.search(r"synthetic", lowered)
    assert "migration_set" in source
    assert "sha256" in lowered
    assert re.search(r"schema[^\n]*(identity|receipt)", lowered)
    assert re.search(r"target.authority|target-authority", lowered)
    assert re.search(r"candidate", lowered)
    assert re.search(r"finder", lowered)
    assert re.search(r"inspect", lowered)


def test_bootstrap_has_bounded_edge_and_ghcr_authority_without_production_routing():
    source = _source(BOOTSTRAP)
    lowered = source.lower()

    assert "127.0.0.1" in source
    assert "vmi3542235.contaboserver.net" in source
    assert re.search(r"edge|reverse.proxy|proxy_pass", lowered)
    assert "cmp --silent" in source
    assert re.search(r"ghcr\.io", lowered)
    assert re.search(r"manifest inspect|docker pull", lowered)
    assert re.search(r"anonymous|docker config|registry auth|ghcr.*credential", lowered)
    assert "ed-finder.app" not in source
    assert "nb79a3d.mevnode.com" not in source


def test_workflow_and_bootstrap_agree_on_complete_bundle_and_receipt_contract():
    workflow = _source(PROVISION_WORKFLOW)
    bootstrap = _source(BOOTSTRAP)
    helper = _source(RECEIPT_HELPER)

    for bundled_path in (
        "deploy/v3-live-checkpoint/bootstrap_receipt.py",
        "deploy/v3-live-checkpoint/synthetic-checkpoint-fixture.sql",
        "scripts/apply_migrations.sh",
        "scripts/operator/v3_checkpoint_deploy.py",
        "scripts/release/v3_release_manifest.py",
        "sql/migration-manifest.txt",
    ):
        assert bundled_path in workflow
        assert bundled_path in bootstrap

    assert "postgres_image_digest" in bootstrap
    assert '"postgres_image_digest"' in helper

    candidate_names = {
        "target-authority.candidate.json",
        "target-authority-candidate.json",
    }
    schema_names = {"schema-identity.json", "schema-identity-receipt.json"}
    assert any(name in workflow and name in helper for name in candidate_names)
    assert any(name in workflow and name in helper for name in schema_names)
    assert any(
        f"{name}.sha256" in workflow and f"{name}.sha256" in helper
        for name in schema_names
    )


def test_receipt_builder_accepts_only_sanitized_observed_checkpoint_facts(tmp_path):
    facts = {
        "mode": "provision",
        "hostname": "vmi3542235",
        "fqdn": "vmi3542235.contaboserver.net",
        "architecture": "x86_64",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "docker_version": "28.0.0",
        "compose_version": "2.39.0",
        "psql_version": "psql (PostgreSQL) 18.0",
        "postgres_version": "18.0",
        "postgres_image": "postgres:18",
        "postgres_image_digest": "docker.io/library/postgres@sha256:" + "d" * 64,
        "postgres_image_id": "sha256:" + "e" * 64,
        "ghcr_proof_image": (
            "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "f" * 64
        ),
        "ghcr_proof_mode": "anonymous",
        "runner_services": [
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service",
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service",
            "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service",
        ],
        "alternative_container_clis_present": [],
        "docker_networks": [
            "bridge",
            "edfinder-v3-checkpoint-app",
            "edfinder-v3-checkpoint-data",
            "host",
            "none",
        ],
        "docker_volumes": ["edfinder_v3_checkpoint_postgres_data"],
        "container_names": ["edfinder-v3-checkpoint-postgres"],
        "api_env_file": "/var/lib/edfinder-v3-checkpoint/api.env",
        "owner_uid": 1001,
        "receipt_directory": "/var/lib/edfinder-v3-checkpoint/deployment-receipts",
        "docker_config_directory": "/var/lib/edfinder-v3-checkpoint/docker-config",
        "docker_context": "v3-live-checkpoint-local",
        "origin_bind": "http://127.0.0.1:18080",
        "edge_route_authority": (
            "non-production HTTP vhost vmi3542235.contaboserver.net proxies only "
            "to http://127.0.0.1:18080"
        ),
        "tcp_listeners": ["0.0.0.0:80", "127.0.0.1:22"],
        "observed_capacity": {
            "logical_cpus": 8,
            "cpu_model": "Synthetic test CPU",
            "memory_total_kib": 24 * 1024 * 1024,
            "memory_available_kib": 20 * 1024 * 1024,
            "swap_total_kib": 0,
            "root_bytes": 300_000_000_000,
            "root_available_bytes": 250_000_000_000,
            "root_filesystem": "ext4",
        },
    }
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    output_dir = tmp_path / "output"
    schema_path = tmp_path / "durable" / "schema-identity-receipt.json"

    result = subprocess.run(
        [
            sys.executable,
            str(RECEIPT_HELPER),
            "--bundle-root",
            str(ROOT),
            "--facts",
            str(facts_path),
            "--output-dir",
            str(output_dir),
            "--source-sha",
            "a" * 40,
            "--schema-path",
            str(schema_path),
            "--refresh-schema",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    receipt = json.loads((output_dir / "provisioning-receipt.json").read_text())
    candidate = json.loads((output_dir / "target-authority-candidate.json").read_text())
    assert receipt["status"] == "accepted"
    assert receipt["target"]["production"] is False
    assert receipt["database"]["production_data_used"] is False
    assert receipt["secret_values_emitted"] is False
    assert candidate["status"] == "authorized"
    assert candidate["blockers"] == []
    checkpoint = _load_checkpoint_module()
    assert checkpoint.validate_authority(candidate) == []
    assert (output_dir / "schema-identity-receipt.json.sha256").is_file()
    serialized = json.dumps([receipt, candidate])
    assert "password=" not in serialized.lower()
    assert "database_url" not in serialized.lower()


def test_dispatcher_only_delegates_exact_inputs_to_the_canonical_workflows():
    workflow = _workflow(DISPATCH_WORKFLOW)
    triggers = workflow["on"]
    inputs = triggers["workflow_dispatch"]["inputs"]

    assert set(triggers) == {"workflow_dispatch"}
    assert set(inputs) == {
        "operation",
        "source_sha",
        "schema_compatibility",
        "compatibility_evidence",
        "reviewed_compatible_migration_sets",
        "rollback_eligible",
        "deployment_mode",
        "release_run_id",
    }
    assert inputs["operation"]["type"] == "choice"
    assert set(inputs["operation"]["options"]) == {"release", "deploy"}
    assert workflow["permissions"] == {"actions": "write", "contents": "read"}
    job = next(iter(workflow["jobs"].values()))
    assert job["if"] == "github.ref == 'refs/heads/main'"

    source = _source(DISPATCH_WORKFLOW)
    assert "Unsupported operation" in source
    assert "v3-application-release.yml" in source
    assert "v3-application-live-checkpoint-preflight.yml" in source
    assert re.search(r"ref[\"']?\s*[:=]\s*[\"']?main", source)
    for canonical_input in (
        "source_sha",
        "schema_compatibility",
        "compatibility_evidence",
        "reviewed_compatible_migration_sets",
        "rollback_eligible",
        "deployment_mode",
        "release_run_id",
    ):
        assert canonical_input in source

    # This is a dispatcher, not a third release or deploy execution boundary.
    assert "docker build" not in source
    assert "build-push-action" not in source
    assert not re.search(r"\bssh\b", source)


def test_dispatcher_seals_only_exact_release_and_deploy_payloads(tmp_path):
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    release = _run_dispatch_validation(
        release_dir,
        INPUT_OPERATION="release",
        INPUT_SOURCE_SHA="a" * 40,
        INPUT_SCHEMA_COMPATIBILITY="exact",
        INPUT_COMPATIBILITY_EVIDENCE="reviewed-ci-contract:checkpoint-release-v1",
        INPUT_ROLLBACK_ELIGIBLE="true",
        INPUT_DEPLOYMENT_MODE="upgrade",
        INPUT_RELEASE_RUN_ID="999",
    )
    assert release.returncode == 0, release.stderr
    assert json.loads((release_dir / "sealed.json").read_text()) == {
        "ref": "main",
        "inputs": {
            "source_sha": "a" * 40,
            "schema_compatibility": "exact",
            "compatibility_evidence": "reviewed-ci-contract:checkpoint-release-v1",
            "reviewed_compatible_migration_sets": "",
            "rollback_eligible": True,
        },
    }

    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    deploy = _run_dispatch_validation(
        deploy_dir,
        INPUT_OPERATION="deploy",
        INPUT_SOURCE_SHA="b" * 40,
        INPUT_DEPLOYMENT_MODE="bootstrap",
        INPUT_RELEASE_RUN_ID="123456789",
    )
    assert deploy.returncode == 0, deploy.stderr
    assert json.loads((deploy_dir / "sealed.json").read_text()) == {
        "ref": "main",
        "inputs": {"deployment_mode": "bootstrap", "release_run_id": "123456789"},
    }


def test_dispatcher_rejects_unknown_operations_and_secret_like_evidence(tmp_path):
    unknown_dir = tmp_path / "unknown"
    unknown_dir.mkdir()
    unknown = _run_dispatch_validation(unknown_dir, INPUT_OPERATION="shell")
    assert unknown.returncode != 0
    assert not (unknown_dir / "sealed.json").exists()

    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    secret = _run_dispatch_validation(
        secret_dir,
        INPUT_OPERATION="release",
        INPUT_SOURCE_SHA="a" * 40,
        INPUT_SCHEMA_COMPATIBILITY="exact",
        INPUT_COMPATIBILITY_EVIDENCE="password=must-not-cross-dispatch",
    )
    assert secret.returncode != 0
    assert not (secret_dir / "sealed.json").exists()
