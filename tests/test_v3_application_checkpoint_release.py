from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tomllib
from argparse import Namespace
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_TOOL = ROOT / "scripts" / "release" / "v3_release_manifest.py"
RELEASE_RUN_TOOL = ROOT / "scripts" / "release" / "v3_release_run.py"
HOST_PREFLIGHT = (
    ROOT / "scripts" / "operator" / "actions" / "v3-app-live-checkpoint-preflight.sh"
)
CHECKPOINT_TOOL = ROOT / "scripts" / "operator" / "v3_checkpoint_deploy.py"
CHECKPOINT_COMPOSE = ROOT / "deploy" / "v3-live-checkpoint" / "compose.yml"
CHECKPOINT_AUTHORITY = ROOT / "deploy" / "v3-live-checkpoint" / "target-authority.json"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "v3-application-release.yml"
DEPLOY_WORKFLOW = (
    ROOT / ".github" / "workflows" / "v3-application-live-checkpoint-preflight.yml"
)
GIT_SHA = "a" * 40
DIGEST = "b" * 64


class _NoBoolCoercionLoader(yaml.SafeLoader):
    pass


_NoBoolCoercionLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _load_module():
    spec = importlib.util.spec_from_file_location("v3_release_manifest", MANIFEST_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_release_run_module():
    spec = importlib.util.spec_from_file_location("v3_release_run", RELEASE_RUN_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_checkpoint_module():
    spec = importlib.util.spec_from_file_location(
        "v3_checkpoint_deploy", CHECKPOINT_TOOL
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _network_inspection(module, services=()):
    network_id = "1" * 64
    containers = {}
    attachments = {}
    for index, service in enumerate(services, start=2):
        container_id = str(index) * 64
        endpoint_id = str(index + 2) * 64
        container = module.CONTAINERS[service]
        containers[container_id] = {
            "Name": container,
            "EndpointID": endpoint_id,
        }
        attachments[container] = [
            {
                "Id": container_id,
                "NetworkSettings": {
                    "Networks": {
                        module.APP_NETWORK: {
                            "Aliases": [container, service],
                            "NetworkID": network_id,
                            "EndpointID": endpoint_id,
                        }
                    }
                },
            }
        ]
    return {
        "Id": network_id,
        "Name": module.APP_NETWORK,
        "Driver": "bridge",
        "Scope": "local",
        "Ingress": False,
        "Containers": containers,
    }, attachments


def _manifest(
    *,
    compatibility: str = "exact",
    rollback_eligible: bool = True,
    compatible_migration_sets: list[str] | None = None,
):
    module = _load_module()
    evidence = (
        "reviewed-ci-contract:checkpoint-release-v1"
        if compatibility in {"exact", "backward-compatible"}
        else None
    )
    args = Namespace(
        git_sha=GIT_SHA,
        backend_image=(
            "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + DIGEST
        ),
        web_image="ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "c" * 64,
        compatibility=compatibility,
        compatibility_evidence=evidence,
        compatible_migration_set=compatible_migration_sets,
        rollback_eligible=rollback_eligible,
        rollback_reason="Eligible only for the explicitly listed migration identity.",
    )
    return module, module.create_manifest(args)


def _run_release_compatibility_normalizer(
    tmp_path: Path, *, compatibility: str, reviewed_sets: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    workflow = yaml.load(RELEASE_WORKFLOW.read_text(), Loader=_NoBoolCoercionLoader)
    step = next(
        step
        for step in workflow["jobs"]["validate-source"]["steps"]
        if step.get("id") == "compatibility"
    )
    output = tmp_path / "github-output"
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "COMPATIBILITY": compatibility,
            "REVIEWED_COMPATIBLE_MIGRATION_SETS": reviewed_sets,
            "GITHUB_OUTPUT": str(output),
            "RUNNER_TEMP": str(tmp_path),
        },
    )
    return result, output.read_text() if output.exists() else ""


def test_manifest_records_exact_source_images_and_migration_checksums():
    module, manifest = _manifest()

    assert manifest["git_sha"] == GIT_SHA
    assert manifest["release_id"] == f"git-{GIT_SHA}"
    assert set(manifest["images"]) == {"backend", "web"}
    assert all("@sha256:" in image for image in manifest["images"].values())
    assert manifest["migration_set"]["identity"].startswith("sha256:")
    assert len(manifest["migration_set"]["entries"]) > 40
    assert all(entry["sha256"] for entry in manifest["migration_set"]["entries"])
    assert module.validate_manifest(manifest) == manifest


def test_manifest_exact_mode_uses_only_source_identity_and_backward_mode_adds_reviewed_sets():
    reviewed_identity = "sha256:" + "0" * 64
    module, exact = _manifest(
        compatibility="exact", compatible_migration_sets=[reviewed_identity]
    )
    source_identity = module.migration_set()["identity"]
    assert exact["schema_compatibility"]["compatible_migration_sets"] == [
        source_identity
    ]

    _, backward = _manifest(
        compatibility="backward-compatible",
        compatible_migration_sets=[reviewed_identity],
    )
    assert backward["schema_compatibility"]["compatible_migration_sets"] == sorted(
        [reviewed_identity, source_identity]
    )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("git_sha", "a" * 39),
        ("git_sha", "A" * 40),
        ("backend", "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend:latest"),
        (
            "backend",
            "ghcr.io/untrusted/example/v3-backend@sha256:" + DIGEST,
        ),
        (
            "web",
            "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:short",
        ),
    ],
)
def test_manifest_rejects_nonexact_sha_mutable_or_untrusted_images(field, bad_value):
    module, manifest = _manifest()
    if field == "git_sha":
        manifest["git_sha"] = bad_value
    else:
        manifest["images"][field] = bad_value

    with pytest.raises(module.ManifestError):
        module.validate_manifest(manifest)


def test_manifest_rejects_missing_extra_and_secret_like_metadata():
    module, manifest = _manifest()
    missing = copy.deepcopy(manifest)
    del missing["migration_set"]
    extra = copy.deepcopy(manifest)
    extra["environment"] = {"DATABASE_URL": "not-allowed"}
    secret_evidence = copy.deepcopy(manifest)
    secret_evidence["schema_compatibility"]["evidence"] = "password=do-not-record"

    for candidate in (missing, extra, secret_evidence):
        with pytest.raises(module.ManifestError):
            module.validate_manifest(candidate)


def test_unknown_compatibility_and_missing_current_schema_fail_rollback_closed():
    module, unknown = _manifest(compatibility="unknown", rollback_eligible=False)
    assert module.validate_manifest(unknown) == unknown
    with pytest.raises(module.ManifestError, match="proved schema compatibility"):
        module.validate_manifest(unknown, purpose="deploy-candidate")
    with pytest.raises(module.ManifestError, match="not eligible"):
        module.validate_manifest(unknown, purpose="rollback-candidate")

    module, eligible = _manifest()
    with pytest.raises(module.ManifestError, match="authoritative current database"):
        module.validate_manifest(eligible, purpose="rollback")
    with pytest.raises(module.ManifestError, match="absent or unknown"):
        module.validate_manifest(
            eligible, purpose="rollback", current_migration_set="sha256:" + "d" * 64
        )
    assert module.validate_manifest(
        eligible,
        purpose="rollback",
        current_migration_set=eligible["migration_set"]["identity"],
    )


def test_manifest_migration_identity_detects_checksum_tampering():
    module, manifest = _manifest()
    manifest["migration_set"]["entries"][0]["sha256"] = "0" * 64
    with pytest.raises(module.ManifestError, match="does not match"):
        module.validate_manifest(manifest)


def test_manifest_rejects_impossible_timestamp_and_duplicate_migration_paths():
    module, manifest = _manifest()
    invalid_time = copy.deepcopy(manifest)
    invalid_time["created_at"] = "2026-99-99T99:99:99Z"
    duplicate_path = copy.deepcopy(manifest)
    duplicate_path["migration_set"]["entries"].append(
        copy.deepcopy(duplicate_path["migration_set"]["entries"][0])
    )
    duplicate_path["migration_set"]["identity"] = "sha256:" + module._sha256(
        json.dumps(
            duplicate_path["migration_set"]["entries"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )

    with pytest.raises(module.ManifestError, match="real UTC"):
        module.validate_manifest(invalid_time)
    with pytest.raises(module.ManifestError, match="duplicate migration path"):
        module.validate_manifest(duplicate_path)


def test_source_migration_verification_rejects_self_consistent_foreign_tree():
    module, manifest = _manifest()
    manifest["migration_set"]["manifest_sha256"] = "0" * 64

    # Shape/identity validation supports old release and rollback manifests.
    assert module.validate_manifest(manifest) == manifest
    with pytest.raises(module.ManifestError, match="exact checked-out SQL source"):
        module.verify_source_migration_set(manifest)


def test_web_nginx_keeps_only_locked_backend_routes():
    config = (ROOT / "apps" / "web" / "nginx" / "default.conf.template").read_text()

    assert "location = /api" in config
    assert "location ^~ /api/" in config
    assert "location = /openapi.json" in config
    assert "location ~ ^/s/[0-9]+$" in config
    assert "try_files $uri $uri/ /200.html" in config
    assert "location /s/" not in config
    assert "location /openapi.json" not in config
    assert "proxy_pass http://${EDFINDER_API_UPSTREAM}" in config

    backend_patterns = (
        re.compile(r"^/api(?:$|/)"),
        re.compile(r"^/openapi\.json$"),
        re.compile(r"^/s/[0-9]+$"),
    )
    assert all(
        any(
            pattern.fullmatch(path) or pattern.match(path)
            for pattern in backend_patterns
        )
        for path in ("/api", "/api/health", "/openapi.json", "/s/18446744073709551615")
    )
    assert all(
        not any(
            pattern.fullmatch(path) or pattern.match(path)
            for pattern in backend_patterns
        )
        for path in ("/apiary", "/openapi.json/extra", "/s/not-a-number", "/s/1/extra")
    )


def test_release_dockerfiles_use_frozen_off_host_builds_and_exact_provenance():
    backend = (ROOT / "apps" / "api" / "Dockerfile.release").read_text()
    web = (ROOT / "apps" / "web" / "Dockerfile").read_text()
    svelte_config = (ROOT / "apps" / "web" / "svelte.config.js").read_text()
    api_project = (ROOT / "apps" / "api" / "pyproject.toml").read_text()

    assert "FROM python:3.14-slim" in backend
    assert "uv==0.11.33" in backend
    assert "uv sync --frozen" in backend
    assert backend.count("platform.python_implementation() == 'CPython'") == 2
    assert backend.count("sys.version_info[:2] == (3, 14)") == 2
    assert (ROOT / "apps" / "api" / "uv.lock").is_file()
    assert 'requires-python = ">=3.14,<3.15"' in api_project
    assert 'required-version = "==0.11.33"' in api_project
    assert 'exclude-newer = "1 week"' in api_project
    assert "FROM node:24-alpine" in web
    assert "pnpm@11.25.0" in web
    assert "pnpm install --frozen-lockfile" in web
    assert "CYPRESS_INSTALL_BINARY=0" in web
    assert "FROM nginx:1.29-alpine" in web
    assert 'NGINX_ENVSUBST_FILTER="^EDFINDER_API_UPSTREAM$"' in web
    assert "/workspace/apps/web/build/" in web
    assert "process.env.VITE_BUILD_SHA" in svelte_config
    assert "version: { name: buildSha ?? 'development' }" in svelte_config
    for dockerfile in (backend, web):
        assert "ARG BUILD_SHA" in dockerfile
        assert 'org.opencontainers.image.revision="$BUILD_SHA"' in dockerfile
        assert 'BUILD_SHA="$BUILD_SHA"' in dockerfile
        assert "SECRET" not in dockerfile
        assert "PASSWORD" not in dockerfile
    assert 'APP_VERSION="3.0.1"' in backend


def test_release_runbook_requires_python314_across_application_and_tooling():
    runbook = (
        ROOT / "docs" / "operations" / "v3-application-checkpoint-release.md"
    ).read_text()

    assert "every-PR container parity lane" in runbook
    assert "Normal V3 backend unit" in runbook
    assert "Review Lab backend" in runbook
    assert "real FastAPI lifespan" in runbook
    assert "Codex worker bootstrap also validate on" in runbook
    assert "exact CPython 3.14" in runbook
    assert "API continues to own asyncpg" in runbook
    assert "synchronous tooling" in runbook
    assert "uses pinned Psycopg 3" in runbook


def test_release_api_lock_inputs_match_the_existing_pinned_runtime_versions():
    project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text())
    project_dependencies = {
        re.sub(r"\[.*?\]", "", value.split("==", 1)[0]).lower(): value.split("==", 1)[1]
        for value in project["project"]["dependencies"]
    }
    requirement_dependencies = {}
    for line in (ROOT / "apps" / "api" / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        requirement_dependencies[re.sub(r"\[.*?\]", "", name).lower()] = version

    assert project_dependencies == requirement_dependencies


def test_root_docker_context_excludes_common_private_material():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    for pattern in (".git", ".env", ".env.*", "*.key", "*.pem", ".secrets"):
        assert pattern in ignored


def test_release_and_deploy_workflows_are_manual_only_and_separate():
    release = yaml.load(RELEASE_WORKFLOW.read_text(), Loader=_NoBoolCoercionLoader)
    deploy = yaml.load(DEPLOY_WORKFLOW.read_text(), Loader=_NoBoolCoercionLoader)

    assert set(release["on"]) == {"workflow_dispatch"}
    assert set(deploy["on"]) == {"workflow_dispatch"}
    assert "environment" not in release["jobs"]["manifest"]
    assert deploy["jobs"]["deploy"]["environment"] == "v3-live-checkpoint"
    for document in (release, deploy):
        assert "pull_request" not in document["on"]
        assert "push" not in document["on"]
        assert "workflow_run" not in document["on"]


def test_release_workflow_builds_both_images_from_one_exact_main_sha_and_digests():
    workflow = RELEASE_WORKFLOW.read_text()

    assert "Selected SHA is not the checked-out main head" in workflow
    assert workflow.count("needs.validate-source.outputs.git_sha") >= 8
    assert "file: apps/api/Dockerfile.release" in workflow
    assert "file: apps/web/Dockerfile" in workflow
    assert workflow.count("push: true") == 2
    assert "needs.build-backend.outputs.digest" in workflow
    assert "needs.build-web.outputs.digest" in workflow
    assert "v3_release_manifest.py verify" in workflow
    assert "--verify-source-migrations" in workflow
    assert "(cd release && sha256sum v3-application-release.json" in workflow
    assert "git pull" not in workflow


def test_release_workflow_normalizes_and_passes_reviewed_backward_compatibility_sets(
    tmp_path,
):
    first = "sha256:" + "1" * 64
    second = "sha256:" + "2" * 64
    result, output = _run_release_compatibility_normalizer(
        tmp_path,
        compatibility="backward-compatible",
        reviewed_sets=f"  {second}\r\n\n{first}  ",
    )

    assert result.returncode == 0, result.stderr
    assert output == f"compatible_migration_sets={first} {second}\n"

    empty_result, empty_output = _run_release_compatibility_normalizer(
        tmp_path / "empty",
        compatibility="backward-compatible",
        reviewed_sets=" \n\t",
    )
    assert empty_result.returncode == 0, empty_result.stderr
    assert empty_output == "compatible_migration_sets=\n"

    workflow = yaml.load(RELEASE_WORKFLOW.read_text(), Loader=_NoBoolCoercionLoader)
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["reviewed_compatible_migration_sets"]["required"] == "false"
    assert "one per line" in inputs["reviewed_compatible_migration_sets"]["description"]
    workflow_text = RELEASE_WORKFLOW.read_text()
    assert workflow_text.count('args+=(--compatible-migration-set "$identity")') == 2
    assert (
        workflow_text.count('if [ "$COMPATIBILITY" = "backward-compatible" ]; then')
        == 2
    )


@pytest.mark.parametrize(
    ("compatibility", "reviewed_sets", "error"),
    [
        (
            "exact",
            "sha256:" + "1" * 64,
            "accepted only for backward-compatible releases",
        ),
        ("backward-compatible", "sha256:ABC", "64 lowercase hex"),
        (
            "backward-compatible",
            "password=not-an-identity",
            "secret-like material",
        ),
        (
            "backward-compatible",
            "sha256:" + "1" * 64 + "\nsha256:" + "1" * 64,
            "must not contain duplicates",
        ),
    ],
)
def test_release_workflow_rejects_unreviewed_malformed_or_secret_like_sets(
    tmp_path, compatibility, reviewed_sets, error
):
    result, _ = _run_release_compatibility_normalizer(
        tmp_path,
        compatibility=compatibility,
        reviewed_sets=reviewed_sets,
    )

    assert result.returncode == 64
    assert error in result.stderr


def test_deploy_workflow_supports_bootstrap_and_receipt_backed_upgrade():
    workflow = DEPLOY_WORKFLOW.read_text()

    assert "--purpose deploy-candidate" in workflow
    assert "Authenticate release workflow run provenance" in workflow
    assert "scripts/release/v3_release_run.py" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    assert "Contabo live-checkpoint" in workflow
    assert "distinct from production credentials" in workflow
    secret_names = set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow))
    assert secret_names == {
        "V3_LIVE_CHECKPOINT_SSH_KEY",
        "V3_LIVE_CHECKPOINT_HOST",
        "V3_LIVE_CHECKPOINT_PORT",
        "V3_LIVE_CHECKPOINT_USER",
        "V3_LIVE_CHECKPOINT_SSH_KNOWN_HOSTS",
    }
    assert "ED_NEW_OPERATOR_" not in workflow
    assert "v3_checkpoint_deploy.py" in workflow
    assert "Upload sanitized deployment receipt" in workflow
    assert "if: always()" in workflow
    assert workflow.index(
        "Stop locally when target authority is incomplete"
    ) < workflow.index("Download candidate release manifest")
    assert workflow.index("--authority-gate") < workflow.index("ssh -i")
    assert 'remote_receipt="$RECEIPT.remote"' in workflow
    assert "remote_transport_or_bundle_failed" in workflow
    assert "rollback_run_id" not in workflow
    assert "artifacts/rollback" not in workflow
    for forbidden in ("ssh-keyscan", "git pull", "pnpm install", "uv sync", "psql"):
        assert forbidden not in workflow.lower()


def test_release_run_provenance_requires_canonical_successful_main_workflow():
    module = _load_release_run_module()
    manifest = {"git_sha": GIT_SHA}
    canonical = {
        "head_repository": {"full_name": "brianstewart377-rgb/ed-finder"},
        "path": ".github/workflows/v3-application-release.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": GIT_SHA,
    }
    module.validate_run_metadata(
        canonical, manifest, "brianstewart377-rgb/ed-finder", "candidate"
    )

    for field, value in (
        ("path", ".github/workflows/other.yml"),
        ("event", "push"),
        ("conclusion", "failure"),
        ("head_branch", "worker-branch"),
        ("head_sha", "d" * 40),
        ("head_repository", {"full_name": "someone/fork"}),
    ):
        changed = copy.deepcopy(canonical)
        changed[field] = value
        with pytest.raises(module.ReleaseRunError, match="provenance failed"):
            module.validate_run_metadata(
                changed, manifest, "brianstewart377-rgb/ed-finder", "candidate"
            )


def test_release_run_cli_allows_candidate_only_bootstrap_and_pairs_upgrade_args():
    module = _load_release_run_module()
    bootstrap = module._parser().parse_args(
        [
            "--repository",
            "brianstewart377-rgb/ed-finder",
            "--candidate-run-id",
            "123",
            "--candidate-manifest",
            "candidate.json",
        ]
    )
    assert bootstrap.rollback_run_id is None
    assert bootstrap.rollback_manifest is None

    upgrade = module._parser().parse_args(
        [
            "--repository",
            "brianstewart377-rgb/ed-finder",
            "--candidate-run-id",
            "123",
            "--candidate-manifest",
            "candidate.json",
            "--rollback-run-id",
            "122",
            "--rollback-manifest",
            "rollback.json",
        ]
    )
    assert upgrade.rollback_run_id == "122"
    assert upgrade.rollback_manifest == Path("rollback.json")


def test_release_run_fetch_uses_one_fixed_https_authority_and_keeps_token_off_argv(
    monkeypatch,
):
    module = _load_release_run_module()
    token = "secret-token-not-for-argv"
    payload = json.dumps({"id": 42}).encode()
    observed = {}

    def fake_run(command, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.fetch_run("brianstewart377-rgb/ed-finder", "123456789", token)

    assert result == {"id": 42}
    command = observed["command"]
    assert command[0] == "/usr/bin/curl"
    assert command[-1] == (
        "https://api.github.com/repos/brianstewart377-rgb/ed-finder/"
        "actions/runs/123456789"
    )
    assert command.count("--proto") == 1
    assert command[command.index("--proto") + 1] == "=https"
    assert "--location" not in command
    assert token not in " ".join(command)
    assert f"Authorization: Bearer {token}" in observed["kwargs"]["input"].decode()
    assert observed["kwargs"]["stderr"] is subprocess.DEVNULL
    assert observed["kwargs"]["timeout"] == 20


@pytest.mark.parametrize(
    ("repository", "run_id"),
    [
        ("attacker/ed-finder", "123"),
        ("brianstewart377-rgb/ed-finder.evil", "123"),
        ("https://api.github.com/attacker", "123"),
        ("brianstewart377-rgb/ed-finder", "0"),
        ("brianstewart377-rgb/ed-finder", "1/../../secrets"),
        ("brianstewart377-rgb/ed-finder", "1" * 21),
    ],
)
def test_release_run_fetch_rejects_hostile_repository_and_run_inputs(
    monkeypatch, repository, run_id
):
    module = _load_release_run_module()
    network_called = False

    def unexpected_network(*_args, **_kwargs):
        nonlocal network_called
        network_called = True
        raise AssertionError("hostile input reached the network boundary")

    monkeypatch.setattr(module.subprocess, "run", unexpected_network)

    with pytest.raises(module.ReleaseRunError):
        module.fetch_run(repository, run_id, "token")
    assert network_called is False


def test_release_run_fetch_fails_closed_without_leaking_token(monkeypatch):
    module = _load_release_run_module()
    token = "never-report-this-token"

    def fail_run(*_args, **_kwargs):
        raise OSError(token)

    monkeypatch.setattr(module.subprocess, "run", fail_run)
    with pytest.raises(module.ReleaseRunError) as failure:
        module.fetch_run("brianstewart377-rgb/ed-finder", "123", token)
    assert token not in str(failure.value)


def test_release_run_fetch_rejects_header_injection_before_network(monkeypatch):
    module = _load_release_run_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("invalid token reached curl"),
    )

    with pytest.raises(module.ReleaseRunError, match="header characters"):
        module.fetch_run("brianstewart377-rgb/ed-finder", "123", "token\r\nX-Evil: yes")


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (22, b"", "curl exit 22"),
        (63, b"", "exceeds the size limit"),
        (0, b"not-json", "not valid JSON"),
        (0, b"[]", "must be an object"),
    ],
)
def test_release_run_fetch_rejects_transport_and_payload_failures(
    monkeypatch, returncode, stdout, message
):
    module = _load_release_run_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, returncode, stdout=stdout, stderr=b""
        ),
    )

    with pytest.raises(module.ReleaseRunError, match=message):
        module.fetch_run("brianstewart377-rgb/ed-finder", "123", "token")


def test_release_run_fetch_enforces_a_post_transport_response_bound(monkeypatch):
    module = _load_release_run_module()
    oversized = b"x" * (module.MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout=oversized, stderr=b""
        ),
    )

    with pytest.raises(module.ReleaseRunError, match="exceeds the size limit"):
        module.fetch_run("brianstewart377-rgb/ed-finder", "123", "token")


def test_checkpoint_compose_owns_only_bounded_application_resources():
    compose = yaml.safe_load(CHECKPOINT_COMPOSE.read_text())

    assert compose["name"] == "edfinder-v3-checkpoint"
    assert set(compose["services"]) == {"api", "web"}
    assert compose.get("volumes") is None
    assert compose["networks"] == {
        "app": {"name": "edfinder-v3-checkpoint-app", "external": True}
    }
    assert compose["services"]["api"]["container_name"] == "edfinder-v3-checkpoint-api"
    assert compose["services"]["web"]["container_name"] == "edfinder-v3-checkpoint-web"
    assert compose["services"]["api"]["cpus"] == "1.50"
    assert compose["services"]["api"]["mem_limit"] == "1536m"
    assert compose["services"]["web"]["cpus"] == "0.50"
    assert compose["services"]["web"]["mem_limit"] == "512m"
    assert (
        compose["services"]["api"]["environment"]["EDDN_SIMULATION_INGEST_ENABLED"]
        == "false"
    )
    assert (
        compose["services"]["api"]["environment"][
            "ADMIN_OPERATION_STARTUP_REAP_ENABLED"
        ]
        == "false"
    )
    for service in compose["services"].values():
        assert "build" not in service
        assert "depends_on" not in service
    assert all(
        name not in compose["services"]
        for name in ("postgres", "redis", "valkey", "nats", "edge", "runner")
    )


def test_bootstrap_and_upgrade_mutation_plans_are_literal_app_only_allowlists():
    module = _load_checkpoint_module()
    env = {
        "V3_CHECKPOINT_API_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:"
        + "b" * 64,
        "V3_CHECKPOINT_WEB_IMAGE": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:"
        + "c" * 64,
        "V3_CHECKPOINT_SOURCE_SHA": GIT_SHA,
    }
    plan = module.command_plan(CHECKPOINT_COMPOSE, env)

    assert plan[0] == ["docker", "pull", env["V3_CHECKPOINT_API_IMAGE"]]
    assert plan[1] == ["docker", "pull", env["V3_CHECKPOINT_WEB_IMAGE"]]
    assert plan[2][-2:] == ["api", "web"]
    assert "--no-deps" in plan[2]
    assert "--force-recreate" in plan[2]
    assert plan[2][plan[2].index("--pull") + 1] == "never"

    bootstrap_rollback, _ = module.rollback_plan(
        CHECKPOINT_COMPOSE, "bootstrap", env, {"kind": "predeploy_absence"}
    )
    assert all(command[-2:] == ["api", "web"] for command in bootstrap_rollback)
    rollback = {
        "kind": "accepted_release",
        "source_sha": "d" * 40,
        "images": {
            "backend": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:"
            + "e" * 64,
            "web": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "f" * 64,
        },
    }
    upgrade_rollback, rollback_env = module.rollback_plan(
        CHECKPOINT_COMPOSE, "upgrade", env, rollback
    )
    assert len(upgrade_rollback) == 1
    assert upgrade_rollback[0][-2:] == ["api", "web"]
    assert "--no-deps" in upgrade_rollback[0]
    assert "--force-recreate" in upgrade_rollback[0]
    assert upgrade_rollback[0][upgrade_rollback[0].index("--pull") + 1] == "never"
    assert not any(command[:2] == ["docker", "pull"] for command in upgrade_rollback)
    assert rollback_env["V3_CHECKPOINT_API_IMAGE"] == rollback["images"]["backend"]
    assert rollback_env["V3_CHECKPOINT_WEB_IMAGE"] == rollback["images"]["web"]
    assert rollback_env["V3_CHECKPOINT_SOURCE_SHA"] == rollback["source_sha"]
    flattened = " ".join(
        " ".join(command) for command in plan + bootstrap_rollback + upgrade_rollback
    )
    for forbidden in (
        " down ",
        "--remove-orphans",
        "--volumes",
        "postgres",
        "redis",
        "valkey",
        "nats",
    ):
        assert forbidden not in f" {flattened.lower()} "


def test_rendered_compose_allowlist_is_checked_before_any_pull():
    module = _load_checkpoint_module()
    env = {
        "DOCKER_CONTEXT": "checkpoint-test",
        "V3_CHECKPOINT_API_IMAGE": "ghcr.io/example/api@sha256:" + "b" * 64,
        "V3_CHECKPOINT_WEB_IMAGE": "ghcr.io/example/web@sha256:" + "c" * 64,
    }
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        if command[1:3] == ["context", "inspect"]:
            stdout = json.dumps(module.LOCAL_DOCKER_ENDPOINT)
        else:
            stdout = "api web unexpected\n" if command[-1] == "--services" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.DeploymentError, match="service allowlist"):
        module.validate_host_runtime(CHECKPOINT_COMPOSE, env, runner)

    assert not any(command[:2] == ["docker", "pull"] for command in commands)


def test_checkpoint_runtime_accepts_only_authorized_local_docker_context():
    module = _load_checkpoint_module()
    env = {
        "DOCKER_CONTEXT": "checkpoint-test",
        "V3_CHECKPOINT_API_IMAGE": "ghcr.io/example/api@sha256:" + "b" * 64,
        "V3_CHECKPOINT_WEB_IMAGE": "ghcr.io/example/web@sha256:" + "c" * 64,
    }
    commands = []
    network, _attachments = _network_inspection(module)

    def runner(command, **_kwargs):
        commands.append(command)
        if command[1:3] == ["context", "inspect"]:
            stdout = json.dumps(module.LOCAL_DOCKER_ENDPOINT)
        elif command[-1] == "--services":
            stdout = "api web\n"
        elif command[-1] == "--images":
            stdout = (
                f"{env['V3_CHECKPOINT_API_IMAGE']}\n{env['V3_CHECKPOINT_WEB_IMAGE']}\n"
            )
        elif command[:3] == ["docker", "network", "inspect"]:
            stdout = json.dumps([network])
        elif command[:3] == ["systemctl", "list-units", "--type=service"]:
            stdout = "".join(
                f"{service} loaded active running\n"
                for service in module.RUNNER_SERVICES
            )
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    module.validate_host_runtime(CHECKPOINT_COMPOSE, env, runner)

    docker_commands = [command for command in commands if command[0] == "docker"]
    assert docker_commands[0] == [
        "docker",
        "context",
        "inspect",
        "checkpoint-test",
        "--format",
        "{{json .Endpoints.docker.Host}}",
    ]


def test_checkpoint_network_accepts_empty_bootstrap_and_exact_upgrade_topology():
    module = _load_checkpoint_module()
    bootstrap_network, _ = _network_inspection(module)
    module.validate_network_topology(
        "bootstrap", json.dumps([bootstrap_network]), {}, lambda *_args, **_kwargs: None
    )

    upgrade_network, attachments = _network_inspection(module, ("api", "web"))

    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(attachments[command[-1]]), stderr=""
        )

    module.validate_network_topology(
        "upgrade", json.dumps([upgrade_network]), {}, runner
    )

    partial_network, partial_attachments = _network_inspection(module, ("api",))

    def partial_runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(partial_attachments[command[-1]]),
            stderr="",
        )

    module.validate_network_topology(
        "bootstrap-rollback", json.dumps([partial_network]), {}, partial_runner
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("Driver", "overlay"), ("Scope", "swarm"), ("Ingress", True)],
)
def test_checkpoint_network_rejects_wrong_local_bridge_topology(field, value):
    module = _load_checkpoint_module()
    network, _ = _network_inspection(module)
    network[field] = value

    with pytest.raises(module.DeploymentError, match="topology is unauthorized"):
        module.validate_network_topology(
            "bootstrap", json.dumps([network]), {}, lambda *_args, **_kwargs: None
        )


@pytest.mark.parametrize("inspection_output", ["", "{}", "[]", "[{}, {}]"])
def test_checkpoint_network_rejects_malformed_or_unverifiable_output(
    inspection_output,
):
    module = _load_checkpoint_module()

    with pytest.raises(module.DeploymentError, match="network inspection|topology"):
        module.validate_network_topology(
            "bootstrap", inspection_output, {}, lambda *_args, **_kwargs: None
        )


def test_upgrade_network_rejects_unexpected_peer_before_any_pull():
    module = _load_checkpoint_module()
    network, attachments = _network_inspection(module, ("api", "web"))
    network["Containers"]["6" * 64] = {
        "Name": "untrusted-api-peer",
        "EndpointID": "7" * 64,
    }
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(attachments.get(command[-1], [])), stderr=""
        )

    with pytest.raises(module.DeploymentError, match="unexpected peer"):
        module.validate_network_topology("upgrade", json.dumps([network]), {}, runner)
    assert not any(command[:2] == ["docker", "pull"] for command in commands)


def test_upgrade_network_rejects_unexpected_api_alias_on_web_peer():
    module = _load_checkpoint_module()
    network, attachments = _network_inspection(module, ("api", "web"))
    web = module.CONTAINERS["web"]
    attachments[web][0]["NetworkSettings"]["Networks"][module.APP_NETWORK][
        "Aliases"
    ].append("api")

    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(attachments[command[-1]]), stderr=""
        )

    with pytest.raises(module.DeploymentError, match="network aliases"):
        module.validate_network_topology("upgrade", json.dumps([network]), {}, runner)


@pytest.mark.parametrize(
    "inspection_output",
    [
        '"ssh://checkpoint.example"',
        '"tcp://127.0.0.1:2375"',
        '"unix:///run/user/1000/docker.sock"',
        '"unix:///var/run/docker.sock" trailing-output',
        "null",
        "",
    ],
)
def test_checkpoint_runtime_rejects_untrusted_or_unverifiable_docker_context(
    inspection_output,
):
    module = _load_checkpoint_module()
    env = {
        "DOCKER_CONTEXT": "checkpoint-test",
        "V3_CHECKPOINT_API_IMAGE": "ghcr.io/example/api@sha256:" + "b" * 64,
        "V3_CHECKPOINT_WEB_IMAGE": "ghcr.io/example/web@sha256:" + "c" * 64,
    }
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        stdout = inspection_output if command[1:3] == ["context", "inspect"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.DeploymentError, match="Docker context"):
        module.validate_host_runtime(CHECKPOINT_COMPOSE, env, runner)

    assert not any(
        command[:3] == ["docker", "compose", "version"] for command in commands
    )
    assert not any(command[:2] == ["docker", "pull"] for command in commands)


def _write_json_with_checksum(
    directory: Path, name: str, value: dict
) -> tuple[Path, Path]:
    document = directory / name
    document.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    checksum = directory / f"{name}.sha256"
    checksum.write_text(
        f"{hashlib.sha256(document.read_bytes()).hexdigest()}  {name}\n",
        encoding="utf-8",
    )
    return document, checksum


def _schema_receipt(module, manifest, **overrides):
    value = {
        "schema_version": module.SCHEMA_RECEIPT_SCHEMA,
        "database_source_authority": "approved-test-db",
        "database_identity": {
            "database_name": "checkpoint",
            "server_address": "192.0.2.10",
            "server_port": 5432,
        },
        "migration_set_identity": manifest["migration_set"]["identity"],
        "migration_set_entries": manifest["migration_set"]["entries"],
        "captured_at": module.datetime.now(module.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    value.update(overrides)
    return value


def _authorized_checkpoint_authority(tmp_path: Path, schema_path: Path) -> dict:
    api_env = tmp_path / "api.env"
    api_env.write_text(
        "DATABASE_URL=postgresql://checkpoint:test@192.0.2.10/checkpoint\n",
        encoding="utf-8",
    )
    api_env.chmod(0o600)
    authority = json.loads(CHECKPOINT_AUTHORITY.read_text())
    authority["status"] = "authorized"
    authority["blockers"] = []
    authority["observed_runtime"]["container_runtime"] = "Docker test authority"
    authority["observed_runtime"]["compose"] = "Docker Compose test authority"
    authority["observed_runtime"]["docker_networks"] = ["edfinder-v3-checkpoint-app"]
    authority["external_authority"] = {
        "api_env_file": str(api_env),
        "api_env_owner_uid": os.getuid(),
        "api_env_mode": "0600",
        "database_source_authority": "approved-test-db",
        "schema_identity_receipt": str(schema_path),
        "schema_identity_receipt_sha256": hashlib.sha256(
            schema_path.read_bytes()
        ).hexdigest(),
        "origin_bind": "http://127.0.0.1:12345",
        "edge_route_authority": "approved-test-edge-route",
        "receipt_directory": str(tmp_path),
        "receipt_owner_uid": os.getuid(),
        "receipt_mode": "0700",
        "ghcr_pull_authority": "approved-test-ghcr-principal",
        "docker_config_directory": str(tmp_path / "docker-config"),
        "docker_config_owner_uid": os.getuid(),
        "docker_config_mode": "0700",
        "docker_context": "checkpoint-test",
    }
    return authority


def test_bootstrap_needs_no_prior_release_but_upgrade_requires_receipt(tmp_path):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_schema_receipt(module, candidate)), encoding="utf-8")

    validated = module.validate_release_inputs(
        mode="bootstrap",
        candidate_path=candidate_path,
        candidate_checksum=candidate_checksum,
        current_schema_path=schema,
        database_source_authority="approved-test-db",
        rollback_path=None,
        rollback_checksum=None,
        prior_receipt_path=None,
    )
    assert validated["rollback"] == {"kind": "predeploy_absence"}

    with pytest.raises(module.DeploymentError, match="upgrade requires"):
        module.validate_release_inputs(
            mode="upgrade",
            candidate_path=candidate_path,
            candidate_checksum=candidate_checksum,
            current_schema_path=schema,
            database_source_authority="approved-test-db",
            rollback_path=None,
            rollback_checksum=None,
            prior_receipt_path=None,
        )


def test_upgrade_requires_receipt_matching_prior_digest_release(tmp_path):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    rollback = copy.deepcopy(candidate)
    rollback["git_sha"] = "d" * 40
    rollback["release_id"] = "git-" + "d" * 40
    rollback["images"]["backend"] = (
        "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "e" * 64
    )
    rollback["images"]["web"] = (
        "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "f" * 64
    )
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    rollback_path, rollback_checksum = _write_json_with_checksum(
        tmp_path, "rollback.json", rollback
    )
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_schema_receipt(module, candidate)), encoding="utf-8")
    rollback_sum = hashlib.sha256(rollback_path.read_bytes()).hexdigest()
    prior_receipt = tmp_path / "prior.json"
    prior_receipt.write_text(
        json.dumps(
            {
                "schema_version": module.RECEIPT_SCHEMA,
                "status": "accepted",
                "mode": "bootstrap",
                "source_sha": rollback["git_sha"],
                "release_run_id": "122",
                "images": rollback["images"],
                "manifest_sha256": rollback_sum,
                "target": {
                    "provider": "contabo",
                    "classification": "live-checkpoint",
                    "production": False,
                    "hostname": "vmi3542235",
                },
                "compose_project": module.PROJECT,
                "migration_set_identity": candidate["migration_set"]["identity"],
                "changed_resources": list(module.CONTAINERS.values()),
                "smoke": {
                    path: {"status": 200}
                    for path in (
                        "/",
                        "/api/health",
                        "/openapi.json",
                        "/api/v1/auth/session",
                    )
                },
                "database_mutation_performed": False,
                "infrastructure_changes_performed": False,
            }
        ),
        encoding="utf-8",
    )

    validated = module.validate_release_inputs(
        mode="upgrade",
        candidate_path=candidate_path,
        candidate_checksum=candidate_checksum,
        current_schema_path=schema,
        database_source_authority="approved-test-db",
        rollback_path=rollback_path,
        rollback_checksum=rollback_checksum,
        prior_receipt_path=prior_receipt,
    )
    assert validated["rollback"]["source_sha"] == rollback["git_sha"]
    assert validated["rollback"]["release_run_id"] == "122"

    prior_document = json.loads(prior_receipt.read_text())
    module.persist_receipt(tmp_path, prior_document, rollback_path)
    durable_receipt, durable_manifest, durable_checksum = module.load_current_release(
        tmp_path
    )
    durable_validated = module.validate_release_inputs(
        mode="upgrade",
        candidate_path=candidate_path,
        candidate_checksum=candidate_checksum,
        current_schema_path=schema,
        database_source_authority="approved-test-db",
        rollback_path=durable_manifest,
        rollback_checksum=durable_checksum,
        prior_receipt_path=durable_receipt,
    )
    assert durable_validated["rollback"] == validated["rollback"]

    bad_receipt = json.loads(prior_receipt.read_text())
    bad_receipt["images"]["web"] = candidate["images"]["web"]
    prior_receipt.write_text(json.dumps(bad_receipt), encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="does not authenticate"):
        module.validate_release_inputs(
            mode="upgrade",
            candidate_path=candidate_path,
            candidate_checksum=candidate_checksum,
            current_schema_path=schema,
            database_source_authority="approved-test-db",
            rollback_path=rollback_path,
            rollback_checksum=rollback_checksum,
            prior_receipt_path=prior_receipt,
        )


def test_manifest_checksum_rejects_path_bearing_or_tampered_artifacts(tmp_path):
    module = _load_checkpoint_module()
    document = tmp_path / "manifest.json"
    document.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    checksum = tmp_path / "manifest.json.sha256"

    checksum.write_text(f"{digest}  release/manifest.json\n", encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="adjacent manifest basename"):
        module.verify_checksum(document, checksum)
    checksum.write_text(f"{'0' * 64}  manifest.json\n", encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="mismatch"):
        module.verify_checksum(document, checksum)


def test_origin_smoke_checks_exact_required_routes_and_build_identity(monkeypatch):
    module = _load_checkpoint_module()
    responses = {
        "/": (200, b"<!doctype html><html><body>ED-Finder</body></html>", "text/html"),
        "/api/health": (
            200,
            json.dumps(
                {"status": "ok", "database": "connected", "build_sha": GIT_SHA}
            ).encode(),
            "application/json",
        ),
        "/openapi.json": (
            200,
            json.dumps(
                {"paths": {"/api/health": {}, "/api/v1/auth/session": {}}}
            ).encode(),
            "application/json",
        ),
        "/api/v1/auth/session": (
            200,
            json.dumps({"authenticated": False}).encode(),
            "application/json",
        ),
    }
    observed = []

    def fake_get(origin, path):
        observed.append((origin, path))
        return responses[path]

    monkeypatch.setattr(module, "get_origin", fake_get)
    outcomes = module.smoke_origin("http://127.0.0.1:12345", GIT_SHA)

    assert [path for _, path in observed] == [
        "/",
        "/api/health",
        "/openapi.json",
        "/api/v1/auth/session",
    ]
    assert all(value["status"] == 200 for value in outcomes.values())

    responses["/api/health"] = (
        200,
        json.dumps(
            {"status": "ok", "database": "connected", "build_sha": "d" * 40}
        ).encode(),
        "application/json",
    )
    with pytest.raises(module.DeploymentError, match="build/database identity"):
        module.smoke_origin("http://127.0.0.1:12345", GIT_SHA)


def test_readiness_poll_tolerates_startup_latency_and_has_bounded_timeout(monkeypatch):
    module = _load_checkpoint_module()
    elapsed = [0.0]
    attempts = [0]

    def clock():
        return elapsed[0]

    def sleeper(seconds):
        elapsed[0] += seconds

    def eventually_ready(_origin, _path, **_kwargs):
        attempts[0] += 1
        if attempts[0] < 3:
            raise module.DeploymentError("still starting")
        return (
            200,
            json.dumps(
                {"status": "ok", "database": "connected", "build_sha": GIT_SHA}
            ).encode(),
            "application/json",
        )

    monkeypatch.setattr(module, "get_origin", eventually_ready)
    assert (
        module.wait_for_origin_ready(
            "http://127.0.0.1:12345",
            GIT_SHA,
            timeout_seconds=10,
            interval_seconds=2,
            clock=clock,
            sleeper=sleeper,
        )
        == 3
    )
    assert elapsed[0] == 4

    monkeypatch.setattr(
        module,
        "get_origin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            module.DeploymentError("not ready")
        ),
    )
    elapsed[0] = 0
    with pytest.raises(module.DeploymentError, match="readiness timed out"):
        module.wait_for_origin_ready(
            "http://127.0.0.1:12345",
            GIT_SHA,
            timeout_seconds=4,
            interval_seconds=2,
            clock=clock,
            sleeper=sleeper,
        )
    assert elapsed[0] == 4


def test_database_schema_probe_binds_env_target_and_ledger_without_leaking_url(
    tmp_path,
):
    module = _load_checkpoint_module()
    _, manifest = _manifest()
    schema_receipt = _schema_receipt(module, manifest)
    secret_url = "postgresql://checkpoint:do-not-log@db.example:5432/checkpoint"
    api_env = tmp_path / "api.env"
    api_env.write_text(f"DATABASE_URL={secret_url}\n", encoding="utf-8")
    expected_migrations = [
        {
            "filename": entry["path"].removeprefix("sql/"),
            "checksum_sha256": entry["sha256"],
        }
        for entry in manifest["migration_set"]["entries"]
    ]
    observed = {
        **schema_receipt["database_identity"],
        "transaction_read_only": "on",
        "migrations": sorted(expected_migrations, key=lambda item: item["filename"]),
    }
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(observed), stderr=""
        )

    module.verify_database_schema(api_env, schema_receipt, runner)
    command, env = calls[0]
    assert command[0] == "psql"
    assert secret_url not in " ".join(command)
    assert env["PGDATABASE"] == secret_url
    assert "default_transaction_read_only=on" in env["PGOPTIONS"]

    mismatched = copy.deepcopy(observed)
    mismatched["server_address"] = "192.0.2.11"
    completed = []
    with pytest.raises(module.DeploymentError, match="identity does not match"):
        module.verify_database_schema(
            api_env,
            schema_receipt,
            lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(mismatched), stderr=""
            ),
            on_query_completed=lambda: completed.append(True),
        )
    assert completed == [True]

    drifted = copy.deepcopy(observed)
    drifted["migrations"][0]["checksum_sha256"] = "0" * 64
    with pytest.raises(module.DeploymentError, match="ledger has drifted"):
        module.verify_database_schema(
            api_env,
            schema_receipt,
            lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(drifted), stderr=""
            ),
        )


def test_schema_receipt_fails_closed_when_stale(tmp_path):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            _schema_receipt(module, candidate, captured_at="2020-01-01T00:00:00Z")
        ),
        encoding="utf-8",
    )
    with pytest.raises(module.DeploymentError, match="receipt is stale"):
        module.validate_release_inputs(
            mode="bootstrap",
            candidate_path=candidate_path,
            candidate_checksum=candidate_checksum,
            current_schema_path=schema,
            database_source_authority="approved-test-db",
            rollback_path=None,
            rollback_checksum=None,
            prior_receipt_path=None,
        )


def test_sanitized_receipt_is_atomic_current_upgrade_authority(tmp_path):
    module = _load_checkpoint_module()
    accepted_manifest = tmp_path / "accepted-input.json"
    accepted_manifest.write_text("{}", encoding="utf-8")
    accepted_manifest_sha = hashlib.sha256(accepted_manifest.read_bytes()).hexdigest()
    receipt = {
        "schema_version": module.RECEIPT_SCHEMA,
        "status": "accepted",
        "source_sha": GIT_SHA,
        "release_run_id": "12345",
        "images": {
            "backend": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:"
            + "b" * 64,
            "web": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "c" * 64,
        },
        "manifest_sha256": accepted_manifest_sha,
        "target": {"provider": "contabo", "production": False},
        "changed_resources": list(module.CONTAINERS.values()),
        "smoke": {
            path: {"status": 200}
            for path in (
                "/",
                "/api/health",
                "/openapi.json",
                "/api/v1/auth/session",
            )
        },
        "rollback": {"kind": "predeploy_absence"},
    }
    path = module.persist_receipt(tmp_path, receipt, accepted_manifest)

    assert json.loads(path.read_text()) == receipt
    pointer = json.loads((tmp_path / "current.json").read_text())
    assert pointer == {
        "schema_version": module.CURRENT_RECEIPT_SCHEMA,
        "receipt_file": path.name,
        "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "manifest_file": path.name.removesuffix(".json") + ".release.json",
        "manifest_sha256": accepted_manifest_sha,
    }
    assert module.load_current_receipt(tmp_path) == path
    _, durable_manifest, durable_checksum = module.load_current_release(tmp_path)
    assert durable_manifest.read_bytes() == accepted_manifest.read_bytes()
    assert durable_checksum.is_file()
    checksum = (tmp_path / f"{path.name}.sha256").read_text().split()
    assert checksum == [hashlib.sha256(path.read_bytes()).hexdigest(), path.name]
    serialized = path.read_text().lower()
    for forbidden in ("database_url", "password", "private_key", "access_token"):
        assert forbidden not in serialized

    with pytest.raises(OSError, match="immutable deployment receipt"):
        module.persist_receipt(tmp_path, receipt, accepted_manifest)

    original_manifest = durable_manifest.read_bytes()
    durable_manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="manifest checksum mismatch"):
        module.load_current_release(tmp_path)
    durable_manifest.write_bytes(original_manifest)
    durable_manifest.unlink()
    with pytest.raises(module.DeploymentError, match="manifest is missing"):
        module.load_current_release(tmp_path)
    durable_manifest.write_bytes(original_manifest)

    path.write_text("{}", encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="checksum mismatch"):
        module.load_current_receipt(tmp_path)


def test_receipt_pointer_failure_removes_uncommitted_accepted_artifacts(
    tmp_path, monkeypatch
):
    module = _load_checkpoint_module()
    receipt = {
        "source_sha": GIT_SHA,
        "release_run_id": "12345",
        "manifest_sha256": "d" * 64,
        "status": "accepted",
    }
    accepted_manifest = tmp_path / "accepted-input.json"
    accepted_manifest.write_text("{}", encoding="utf-8")
    receipt["manifest_sha256"] = hashlib.sha256(
        accepted_manifest.read_bytes()
    ).hexdigest()
    real_replace = module.os.replace

    def fail_current_pointer(source, destination):
        if Path(destination).name == "current.json":
            raise OSError("simulated current pointer failure")
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_current_pointer)
    with pytest.raises(OSError, match="current pointer"):
        module.persist_receipt(tmp_path, receipt, accepted_manifest)

    assert not (tmp_path / "current.json").exists()
    assert not list(tmp_path.glob(f"{GIT_SHA}-*.json"))
    assert not list(tmp_path.glob(f"{GIT_SHA}-*.json.sha256"))


def test_unsafe_host_identity_stops_before_any_runtime_or_mutation_command(
    tmp_path, monkeypatch
):
    module = _load_checkpoint_module()
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    authority = _authorized_checkpoint_authority(tmp_path, schema)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    calls = []

    monkeypatch.setattr(module.socket, "gethostname", lambda: "wrong-host")

    def forbidden_runner(command, **_kwargs):
        calls.append(command)
        raise AssertionError("unsafe target facts reached the command boundary")

    args = Namespace(
        authority=authority_path,
        compose=CHECKPOINT_COMPOSE,
        mode="bootstrap",
        candidate=tmp_path / "candidate.json",
        candidate_checksum=tmp_path / "candidate.json.sha256",
        candidate_run_id="12345",
        rollback=None,
        rollback_checksum=None,
        rollback_run_id=None,
    )
    with pytest.raises(module.DeploymentError, match="host short identity"):
        module.execute(args, runner=forbidden_runner)
    assert calls == []
    assert not (tmp_path / "deploy.lock").exists()


def test_bootstrap_rejects_dangling_current_pointer_before_any_command(
    tmp_path, monkeypatch
):
    module = _load_checkpoint_module()
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    authority = _authorized_checkpoint_authority(tmp_path, schema)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    current = tmp_path / "current.json"
    current.symlink_to(tmp_path / "missing-prior-receipt.json")
    commands = []

    monkeypatch.setattr(module, "validate_host_files", lambda *_args: None)
    monkeypatch.setattr(module, "acquire_deployment_lock", lambda *_args: object())
    monkeypatch.setattr(module, "release_deployment_lock", lambda *_args: None)

    args = Namespace(
        authority=authority_path,
        compose=CHECKPOINT_COMPOSE,
        mode="bootstrap",
        candidate=tmp_path / "candidate.json",
        candidate_checksum=tmp_path / "candidate.json.sha256",
        candidate_run_id="12345",
    )
    with pytest.raises(module.OperationFailed) as failure:
        module.execute(
            args,
            runner=lambda command, **_kwargs: commands.append(command),
        )

    assert current.is_symlink()
    assert commands == []
    assert failure.value.receipt["service_changes_performed"] is False
    assert failure.value.receipt["image_pulls_performed"] is False


@pytest.mark.parametrize("drift", ["edit", "replacement", "symlink"])
def test_verified_env_source_drift_stops_before_pull_and_cleans_snapshot(
    tmp_path, monkeypatch, drift
):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_schema_receipt(module, candidate)), encoding="utf-8")
    authority = _authorized_checkpoint_authority(tmp_path, schema)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    source = Path(authority["external_authority"]["api_env_file"])
    commands = []
    schema_probe_paths = []

    monkeypatch.setattr(module, "validate_host_files", lambda *_args: None)
    monkeypatch.setattr(module, "acquire_deployment_lock", lambda *_args: object())
    monkeypatch.setattr(module, "release_deployment_lock", lambda *_args: None)

    def verified_database(path, _receipt, _runner, **callbacks):
        schema_probe_paths.append(path)
        assert path != source
        assert path.read_bytes() == source.read_bytes()
        callbacks["on_query_completed"]()
        if drift == "edit":
            source.write_text(
                "DATABASE_URL=postgresql://changed:test@192.0.2.11/other\n",
                encoding="utf-8",
            )
        else:
            source.unlink()
            if drift == "replacement":
                source.write_text(
                    "DATABASE_URL=postgresql://changed:test@192.0.2.11/other\n",
                    encoding="utf-8",
                )
                source.chmod(0o600)
            else:
                source.symlink_to(tmp_path / "missing-api.env")

    monkeypatch.setattr(module, "verify_database_schema", verified_database)
    args = Namespace(
        authority=authority_path,
        compose=CHECKPOINT_COMPOSE,
        mode="bootstrap",
        candidate=candidate_path,
        candidate_checksum=candidate_checksum,
        candidate_run_id="12345",
    )
    with pytest.raises(module.OperationFailed) as failure:
        module.execute(
            args,
            runner=lambda command, **_kwargs: commands.append(command),
        )

    assert schema_probe_paths
    assert commands == []
    assert failure.value.receipt["service_mutation_attempted"] is False
    assert failure.value.receipt["image_pulls_performed"] is False
    assert not list(tmp_path.glob(".v3-verified-api-env-*"))


def test_failed_bootstrap_reports_pulls_mutation_and_verified_absence_rollback(
    tmp_path, monkeypatch
):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_schema_receipt(module, candidate)), encoding="utf-8")
    authority = _authorized_checkpoint_authority(tmp_path, schema)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    commands = []

    monkeypatch.setattr(module, "validate_host_files", lambda *_args: None)
    monkeypatch.setattr(module, "validate_host_runtime", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "verify_bootstrap_absence", lambda *_args: None)
    monkeypatch.setattr(module, "verify_pulled_image", lambda *_args: None)
    monkeypatch.setattr(module, "inspect_network_topology", lambda *_args: None)
    monkeypatch.setattr(module, "acquire_deployment_lock", lambda *_args: object())
    monkeypatch.setattr(module, "release_deployment_lock", lambda *_args: None)

    def verified_database(_path, _receipt, _runner, **callbacks):
        callbacks["on_query_completed"]()

    monkeypatch.setattr(module, "verify_database_schema", verified_database)

    def runner(command, **_kwargs):
        commands.append(command)
        if "up" in command:
            raise module.DeploymentError("simulated app recreation failure")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    args = Namespace(
        authority=authority_path,
        compose=CHECKPOINT_COMPOSE,
        mode="bootstrap",
        candidate=candidate_path,
        candidate_checksum=candidate_checksum,
        candidate_run_id="12345",
        rollback=None,
        rollback_checksum=None,
        rollback_run_id=None,
    )
    with pytest.raises(module.OperationFailed) as failure:
        module.execute(args, runner=runner)

    receipt = failure.value.receipt
    assert receipt["status"] == "failed"
    assert receipt["pulled_images_verified"] == list(candidate["images"].values())
    assert receipt["service_mutation_attempted"] is True
    assert receipt["env_file_consumed_by_compose"] is False
    assert receipt["env_file_may_have_been_consumed_by_compose"] is True
    assert receipt["database_access_performed"] is True
    assert receipt["env_files_read"] is True
    assert receipt["changed_resources"] == list(module.CONTAINERS.values())
    assert receipt["rollback"] == {
        "identity": {"kind": "predeploy_absence"},
        "attempted": True,
        "status": "verified",
    }
    assert (tmp_path / receipt["durable_failure_receipt"]).is_file()
    mutation_commands = [command for command in commands if "up" in command]
    rollback_commands = [
        command for command in commands if "stop" in command or "rm" in command
    ]
    assert mutation_commands[0][-2:] == ["api", "web"]
    assert all(command[-2:] == ["api", "web"] for command in rollback_commands)
    assert not list(tmp_path.glob(".v3-verified-api-env-*"))


@pytest.mark.parametrize(
    "failure_stage",
    [
        "candidate-container",
        "candidate-readiness",
        "candidate-smoke",
        "candidate-receipt",
        "candidate-pull",
    ],
)
def test_failed_upgrade_uses_durable_rollback_and_tracks_database_access(
    tmp_path, monkeypatch, failure_stage
):
    module = _load_checkpoint_module()
    _, candidate = _manifest()
    rollback = copy.deepcopy(candidate)
    rollback["git_sha"] = "d" * 40
    rollback["release_id"] = "git-" + "d" * 40
    rollback["images"] = {
        "backend": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:"
        + "e" * 64,
        "web": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "f" * 64,
    }
    candidate_path, candidate_checksum = _write_json_with_checksum(
        tmp_path, "candidate.json", candidate
    )
    rollback_path, _rollback_checksum = _write_json_with_checksum(
        tmp_path, "prior-input.json", rollback
    )
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_schema_receipt(module, candidate)), encoding="utf-8")
    prior_receipt = {
        "schema_version": module.RECEIPT_SCHEMA,
        "status": "accepted",
        "mode": "bootstrap",
        "source_sha": rollback["git_sha"],
        "release_run_id": "122",
        "images": rollback["images"],
        "manifest_sha256": hashlib.sha256(rollback_path.read_bytes()).hexdigest(),
        "target": {
            "provider": "contabo",
            "classification": "live-checkpoint",
            "production": False,
            "hostname": module.TARGET_HOSTNAME,
        },
        "compose_project": module.PROJECT,
        "migration_set_identity": candidate["migration_set"]["identity"],
        "changed_resources": list(module.CONTAINERS.values()),
        "smoke": {
            path: {"status": 200}
            for path in (
                "/",
                "/api/health",
                "/openapi.json",
                "/api/v1/auth/session",
            )
        },
        "database_mutation_performed": False,
        "infrastructure_changes_performed": False,
    }
    module.persist_receipt(tmp_path, prior_receipt, rollback_path)
    authority = _authorized_checkpoint_authority(tmp_path, schema)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    readiness_shas = []
    commands = []

    monkeypatch.setattr(module, "validate_host_files", lambda *_args: None)
    monkeypatch.setattr(module, "validate_host_runtime", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "verify_origin_state", lambda *_args: None)
    monkeypatch.setattr(module, "verify_pulled_image", lambda *_args: None)
    monkeypatch.setattr(module, "inspect_network_topology", lambda *_args: None)
    monkeypatch.setattr(module, "acquire_deployment_lock", lambda *_args: object())
    monkeypatch.setattr(module, "release_deployment_lock", lambda *_args: None)

    def wait_for_origin_ready(_origin, source_sha):
        readiness_shas.append(source_sha)
        if (
            failure_stage == "candidate-readiness"
            and source_sha == candidate["git_sha"]
        ):
            raise module.DeploymentError("candidate readiness failed")

    monkeypatch.setattr(module, "wait_for_origin_ready", wait_for_origin_ready)

    def smoke_origin(_origin, source_sha):
        if failure_stage == "candidate-smoke" and source_sha == candidate["git_sha"]:
            raise module.DeploymentError("candidate smoke failed")
        return {
            path: {"status": 200}
            for path in (
                "/",
                "/api/health",
                "/openapi.json",
                "/api/v1/auth/session",
            )
        }

    monkeypatch.setattr(module, "smoke_origin", smoke_origin)
    real_persist_receipt = module.persist_receipt

    def persist_receipt(directory, receipt, manifest):
        if failure_stage == "candidate-receipt":
            raise OSError("candidate receipt persistence failed")
        return real_persist_receipt(directory, receipt, manifest)

    monkeypatch.setattr(module, "persist_receipt", persist_receipt)

    def verified_database(_path, _receipt, _runner, **callbacks):
        callbacks["on_query_completed"]()

    monkeypatch.setattr(module, "verify_database_schema", verified_database)

    def verify_containers(_env, source_sha, _images):
        if (
            failure_stage == "candidate-container"
            and source_sha == candidate["git_sha"]
        ):
            raise module.DeploymentError("candidate container verification failed")

    monkeypatch.setattr(module, "verify_app_containers", verify_containers)

    def runner(command, **_kwargs):
        commands.append((command, _kwargs["env"]))
        if (
            failure_stage == "candidate-pull"
            and command[:2] == ["docker", "pull"]
            and command[-1] == candidate["images"]["backend"]
        ):
            raise module.DeploymentError("candidate pull failed")
        if (
            failure_stage != "candidate-pull"
            and "up" in command
            and len([item for item, _env in commands if "up" in item]) == 1
        ):
            Path(authority["external_authority"]["api_env_file"]).write_text(
                "DATABASE_URL=postgresql://changed:test@192.0.2.11/other\n",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    args = Namespace(
        authority=authority_path,
        compose=CHECKPOINT_COMPOSE,
        mode="upgrade",
        candidate=candidate_path,
        candidate_checksum=candidate_checksum,
        candidate_run_id="123",
    )
    with pytest.raises(module.OperationFailed) as failure:
        module.execute(args, runner=runner)

    receipt = failure.value.receipt
    if failure_stage != "candidate-pull":
        assert readiness_shas == [candidate["git_sha"], rollback["git_sha"]]
        assert receipt["rollback"]["status"] == "verified"
        compose_up_calls = [call for call in commands if "up" in call[0]]
        assert len(compose_up_calls) == 2
        rollback_command, rollback_env = compose_up_calls[1]
        assert rollback_command[rollback_command.index("--pull") + 1] == "never"
        assert rollback_command[-2:] == ["api", "web"]
        assert rollback_env["V3_CHECKPOINT_API_IMAGE"] == rollback["images"]["backend"]
        assert rollback_env["V3_CHECKPOINT_WEB_IMAGE"] == rollback["images"]["web"]
        assert rollback_env["V3_CHECKPOINT_SOURCE_SHA"] == rollback["git_sha"]
        candidate_env = compose_up_calls[0][1]
        assert (
            candidate_env["V3_CHECKPOINT_API_ENV_FILE"]
            == rollback_env["V3_CHECKPOINT_API_ENV_FILE"]
        )
        assert (
            candidate_env["V3_CHECKPOINT_API_ENV_FILE"]
            != authority["external_authority"]["api_env_file"]
        )
        assert receipt["env_file_consumed_by_compose"] is True
        assert receipt["env_file_may_have_been_consumed_by_compose"] is False
        rollback_index = commands.index(compose_up_calls[1])
        assert not any(
            command[:2] == ["docker", "pull"]
            for command, _command_env in commands[rollback_index:]
        )
    else:
        assert readiness_shas == []
        assert receipt["rollback"]["status"] == "not-required"
        assert receipt["service_mutation_attempted"] is False
        assert receipt["env_file_consumed_by_compose"] is False
        assert receipt["env_file_may_have_been_consumed_by_compose"] is False
    assert receipt["database_access_performed"] is True
    assert not list(tmp_path.glob(".v3-verified-api-env-*"))


def test_current_target_authority_records_proven_facts_and_exact_blockers():
    authority = json.loads(CHECKPOINT_AUTHORITY.read_text())
    module = _load_checkpoint_module()

    assert module.validate_authority(authority) == sorted(authority["blockers"])
    assert authority["status"] == "stopped"
    assert authority["target"] == {
        "provider": "contabo",
        "classification": "live-checkpoint",
        "production": False,
        "hostname": "vmi3542235",
        "fqdn": "vmi3542235.contaboserver.net",
        "architecture": "x86_64",
    }
    assert authority["observed_capacity"]["logical_cpus"] == 8
    assert len(authority["observed_runtime"]["runner_services"]) == 3
    assert authority["observed_runtime"]["container_runtime"] is None
    assert authority["external_authority"]["database_source_authority"] is None
    assert "authorized_checkpoint_database_source_missing" in authority["blockers"]
    assert "container_runtime_and_compose_unavailable" in authority["blockers"]
    assert (
        hashlib.sha256(CHECKPOINT_COMPOSE.read_bytes()).hexdigest()
        == authority["application_contract"]["compose_sha256"]
    )


def test_host_preflight_is_machine_readable_and_stops_before_mutation():
    result = subprocess.run(
        ["bash", str(HOST_PREFLIGHT)], capture_output=True, text=True
    )

    assert result.returncode == 78
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    assert receipt["target"]["provider"] == "contabo"
    assert receipt["target"]["classification"] == "live-checkpoint"
    assert receipt["target"]["production"] is False
    assert receipt["authorized_recreate_targets"] == ["api", "web"]
    assert receipt["changed_resources"] == []
    assert receipt["service_changes_performed"] is False
    assert receipt["database_access_performed"] is False
    assert receipt["migrations_performed"] is False
    assert "authorized_checkpoint_database_source_missing" in receipt["failures"]
    assert "container_runtime_and_compose_unavailable" in receipt["failures"]

    source = HOST_PREFLIGHT.read_text()
    assert "Contabo is a live-checkpoint environment, not production" in source
    assert "ed-finder-prod" not in source
    assert "nb79a3d.mevnode.com" not in source
    for forbidden in ("git pull", "psql", "pg_restore"):
        assert forbidden not in source


def test_operator_runbook_keeps_contabo_outside_the_production_boundary():
    runbook = (
        ROOT / "docs" / "operations" / "v3-application-checkpoint-release.md"
    ).read_text()

    assert "**Contabo is not production.**" in runbook
    assert "exact `main` SHA" in runbook
    assert "never runs `git pull`" in runbook
    assert "Evidence from Contabo must not be presented as production" in runbook
    assert "Bootstrap checkpoint #1 intentionally has no prior V3 release" in runbook
    assert "persistent infrastructure" in runbook
    assert "NATS is not a V3 checkpoint baseline dependency" in runbook
