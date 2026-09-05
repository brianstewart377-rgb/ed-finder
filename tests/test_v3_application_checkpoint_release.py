from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import tomllib
from argparse import Namespace
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_TOOL = ROOT / "scripts" / "release" / "v3_release_manifest.py"
HOST_PREFLIGHT = ROOT / "scripts" / "operator" / "actions" / "v3-app-deploy-preflight.sh"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "v3-application-release.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "v3-application-deploy-preflight.yml"
GIT_SHA = "a" * 40
DIGEST = "b" * 64


class _NoBoolCoercionLoader(yaml.SafeLoader):
    pass


_NoBoolCoercionLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _load_module():
    spec = importlib.util.spec_from_file_location("v3_release_manifest", MANIFEST_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(*, compatibility: str = "exact", rollback_eligible: bool = True):
    module = _load_module()
    evidence = "reviewed-ci-contract:checkpoint-release-v1" if compatibility == "exact" else None
    args = Namespace(
        git_sha=GIT_SHA,
        backend_image=(
            "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + DIGEST
        ),
        web_image="ghcr.io/brianstewart377-rgb/ed-finder/v3-web@sha256:" + "c" * 64,
        compatibility=compatibility,
        compatibility_evidence=evidence,
        compatible_migration_set=None,
        rollback_eligible=rollback_eligible,
        rollback_reason="Eligible only for the explicitly listed migration identity.",
    )
    return module, module.create_manifest(args)


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
        any(pattern.fullmatch(path) or pattern.match(path) for pattern in backend_patterns)
        for path in ("/api", "/api/health", "/openapi.json", "/s/18446744073709551615")
    )
    assert all(
        not any(pattern.fullmatch(path) or pattern.match(path) for pattern in backend_patterns)
        for path in ("/apiary", "/openapi.json/extra", "/s/not-a-number", "/s/1/extra")
    )


def test_release_dockerfiles_use_frozen_off_host_builds_and_exact_provenance():
    backend = (ROOT / "apps" / "api" / "Dockerfile.release").read_text()
    web = (ROOT / "apps" / "web" / "Dockerfile").read_text()
    api_project = (ROOT / "apps" / "api" / "pyproject.toml").read_text()

    assert "FROM python:3.14-slim" in backend
    assert "uv==0.8.22" in backend
    assert "uv sync --frozen" in backend
    assert (ROOT / "apps" / "api" / "uv.lock").is_file()
    assert 'requires-python = ">=3.14,<3.15"' in api_project
    assert "FROM node:24-alpine" in web
    assert "pnpm@11.25.0" in web
    assert "pnpm install --frozen-lockfile" in web
    assert "FROM nginx:1.29-alpine" in web
    assert "/workspace/apps/web/build/" in web
    for dockerfile in (backend, web):
        assert "ARG BUILD_SHA" in dockerfile
        assert 'org.opencontainers.image.revision="$BUILD_SHA"' in dockerfile
        assert 'BUILD_SHA="$BUILD_SHA"' in dockerfile
        assert "SECRET" not in dockerfile
        assert "PASSWORD" not in dockerfile
    assert 'APP_VERSION="3.0.1"' in backend


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
    assert deploy["jobs"]["preflight"]["environment"] == "ed-new-operator"
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
    assert "git pull" not in workflow


def test_deploy_preflight_consumes_manifests_reuses_only_existing_ssh_boundary():
    workflow = DEPLOY_WORKFLOW.read_text()

    assert "--purpose deploy-candidate" in workflow
    assert "--purpose rollback-candidate" in workflow
    assert "Candidate cannot be its own rollback" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    secret_names = set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow))
    assert secret_names <= {
        "ED_NEW_OPERATOR_SSH_KEY",
        "ED_NEW_OPERATOR_HOST",
        "ED_NEW_OPERATOR_PORT",
        "ED_NEW_OPERATOR_USER",
        "ED_NEW_OPERATOR_SSH_KNOWN_HOSTS",
        "ED_NEW_OPERATOR_KNOWN_HOSTS",
    }
    for forbidden in ("ssh-keyscan", "docker compose", "docker pull", "git pull", "psql", "migrate"):
        assert forbidden not in workflow.lower()


def test_host_preflight_is_machine_readable_and_always_stops_before_mutation():
    result = subprocess.run(["bash", str(HOST_PREFLIGHT)], capture_output=True, text=True)

    assert result.returncode == 78
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    assert receipt["authorized_recreate_targets"] == []
    assert receipt["service_changes_performed"] is False
    assert receipt["database_access_performed"] is False
    assert receipt["migrations_performed"] is False
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["required_facts"] == sorted(receipt["required_facts"])
    assert "accepted_prior_digest_release_and_receipt_compatible_with_current_database" in receipt["required_facts"]
    assert "explicit_postgresql18_redis_nats_and_edge_preservation_targets" in receipt["required_facts"]
    assert "unexpected_host_identity" in receipt["failures"]

    source = HOST_PREFLIGHT.read_text()
    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    for forbidden in (
        "docker compose up",
        "docker restart",
        "docker rm",
        "docker pull",
        "git pull",
        "psql",
        "pg_restore",
        "subprocess.run([\"docker\"",
    ):
        assert forbidden not in source
