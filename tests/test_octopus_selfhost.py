from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

import pytest
import yaml


ROOT = Path(__file__).parents[1]
COMPOSE = ROOT / "deploy/octopus-selfhost/compose.yaml"
ENV_TEMPLATE = ROOT / "deploy/octopus-selfhost/octopus.env.template"
SCRIPT = ROOT / "scripts/operator/octopus_selfhost.sh"
RUNBOOK = ROOT / "docs/operations/octopus-selfhost.md"


def run_script(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value
    return result


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        digest.update(str(item.relative_to(path)).encode())
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


def test_compose_is_pinned_private_isolated_and_operationally_bounded() -> None:
    data = yaml.safe_load(COMPOSE.read_text())
    assert data["name"] == "octopus-selfhost"
    services = data["services"]
    assert services["web"]["image"] == "ghcr.io/octopusreview/octopus-selfhost:1.0.122"
    assert services["postgres"]["image"] == "postgres:17-alpine"
    assert services["qdrant"]["image"] == "qdrant/qdrant:v1.17.0"
    assert services["web"]["ports"] == ["127.0.0.1:43300:3000"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["qdrant"]
    assert data["networks"]["octopus_backend"] == {
        "name": "octopus-selfhost-backend",
        "internal": True,
    }
    assert data["networks"]["octopus_egress"] == {"name": "octopus-selfhost-egress"}
    assert set(data["volumes"]) == {"octopus_postgres_data", "octopus_qdrant_data"}
    assert services["web"]["networks"] == ["octopus_backend", "octopus_egress"]
    assert services["postgres"]["networks"] == ["octopus_backend"]
    assert services["qdrant"]["networks"] == ["octopus_backend"]
    for service in services.values():
        assert service["restart"] == "unless-stopped"
        assert service["healthcheck"]["test"]
        assert service["logging"] == {
            "driver": "json-file",
            "options": {"max-size": "20m", "max-file": "3"},
        }
        assert service["mem_limit"]
        assert service["cpus"]

    text = COMPOSE.read_text().lower()
    assert ":latest" not in text
    assert "octopus:octopus" not in text
    assert "password: octopus" not in text
    for forbidden in (
        "ed-postgres",
        "ed-finder_default",
        "schema_migrations",
        "v3-postgres",
    ):
        assert forbidden not in text


def test_template_contains_no_usable_secrets_or_provider_app_credentials() -> None:
    text = ENV_TEMPLATE.read_text()
    assert text.count("GENERATED_BY_PREPARE") == 4
    assert "OPERATOR_SUPPLIED" in text
    for absent in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_WEBHOOK_SECRET",
    ):
        assert absent not in text
    password_values = [
        line.split("=", 1)[1] for line in text.splitlines() if "PASSWORD=" in line
    ]
    assert all(value.lower() != "octopus" for value in password_values)


@pytest.mark.operator
def test_prepare_generates_unique_secret_shapes_without_disclosure(
    tmp_path: Path,
) -> None:
    all_fingerprints: set[str] = set()
    for index in range(2):
        root = tmp_path / f"host-{index}"
        result = run_script(
            "prepare",
            "--target-root",
            str(root),
            "--admin-email",
            "admin@example.invalid",
        )
        assert result.returncode == 0, result.stderr
        deployment = root / "opt/octopus"
        env_path = deployment / "octopus.env"
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
        values = parse_env(env_path)
        secret_keys = {
            "OCTOPUS_POSTGRES_PASSWORD": 64,
            "BETTER_AUTH_SECRET": 64,
            "OCTOPUS_DATA_KEY": 64,
            "OCTOPUS_ADMIN_PASSWORD": 48,
        }
        fingerprints: set[str] = set()
        for key, length in secret_keys.items():
            value = values[key]
            assert len(value) == length
            assert re.fullmatch(r"[0-9a-f]+", value)
            assert value not in result.stdout
            assert value not in result.stderr
            fingerprints.add(hashlib.sha256(value.encode()).hexdigest())
        assert len(fingerprints) == 4
        assert fingerprints.isdisjoint(all_fingerprints)
        all_fingerprints.update(fingerprints)
        assert values["OCTOPUS_ADMIN_EMAIL"] == "admin@example.invalid"
        assert "containers_started: false" in result.stdout
        assert "migrations_applied: false" in result.stdout


@pytest.mark.operator
def test_prepare_fails_closed_and_runs_no_docker(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    docker = fake_bin / "docker"
    docker.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {docker_log}\n")
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
    host = tmp_path / "host"
    existing = host / "opt/octopus"
    existing.mkdir(parents=True)
    sentinel = existing / "do-not-touch"
    sentinel.write_text("preserve")
    result = run_script(
        "prepare",
        "--target-root",
        str(host),
        "--admin-email",
        "admin@example.invalid",
        env=env,
    )
    assert result.returncode != 0
    assert sentinel.read_text() == "preserve"
    assert not docker_log.exists()
    source = SCRIPT.read_text()
    assert "production /opt/octopus preparation requires root" in source
    assert "PREPARE FRESH OCTOPUS ON ED-FINDER-PROD" in source
    assert "docker compose up" not in source
    assert "prisma migrate" not in source

    production_without_confirmation = run_script(
        "prepare",
        "--target-root",
        "/",
        "--admin-email",
        "admin@example.invalid",
    )
    assert production_without_confirmation.returncode != 0
    assert (
        "requires root" in production_without_confirmation.stderr
        or "confirmation phrase" in production_without_confirmation.stderr
    )


@pytest.mark.operator
def test_preflight_is_read_only_and_does_not_expose_environment(tmp_path: Path) -> None:
    host = tmp_path / "synthetic-host"
    (host / "opt/octopus").mkdir(parents=True)
    sentinel = host / "sentinel"
    sentinel.write_text("TOP_SECRET_SENTINEL")
    before = tree_digest(host)
    result = run_script(
        "preflight",
        "--host-root",
        str(host),
        "--expected-hostname",
        "ed-finder-prod",
    )
    assert result.returncode == 0, result.stderr
    assert tree_digest(host) == before
    assert "TOP_SECRET_SENTINEL" not in result.stdout
    assert "expected_hostname: ed-finder-prod" in result.stdout
    assert "kernel_architecture:" in result.stdout
    assert "cpu_count:" in result.stdout
    assert "memory:" in result.stdout
    assert "root_disk:" in result.stdout
    assert "/opt/octopus: exists" in result.stdout
    assert "read_only: true" in result.stdout
    for port in (43300, 43332, 43333, 43334, 80, 443):
        assert f"{port}:" in result.stdout
    assert ".Config.Env" not in SCRIPT.read_text()


@pytest.mark.operator
def test_validate_is_static_and_compose_config_only(tmp_path: Path) -> None:
    host = tmp_path / "host"
    prepared = run_script(
        "prepare",
        "--target-root",
        str(host),
        "--admin-email",
        "admin@example.invalid",
    )
    assert prepared.returncode == 0, prepared.stderr
    deployment = host / "opt/octopus"
    result = run_script("validate", "--deployment-dir", str(deployment))
    assert result.returncode == 0, result.stderr
    assert "static_validation: passed" in result.stdout

    broken = tmp_path / "broken"
    shutil.copytree(deployment, broken)
    compose = broken / "compose.yaml"
    compose.write_text(compose.read_text().replace("127.0.0.1:43300", "0.0.0.0:43300"))
    failed = run_script("validate", "--deployment-dir", str(broken))
    assert failed.returncode != 0


def test_runbook_records_install_cutover_backup_and_separation_contracts() -> None:
    text = RUNBOOK.read_text()
    required = (
        "55583ac832472ad8b535f1f678f9c11837f7cfdb",
        "oven/bun:1.3.4",
        "bun install --frozen-lockfile",
        "bunx prisma migrate deploy",
        "/api/health",
        "/api/version",
        "claude-sonnet-4-6",
        "text-embedding-3-large",
        "provider rate limits",
        "Ollama is explicitly deferred",
        "mandatory first password change",
        "never be two simultaneous active webhook paths",
        "exact PR head SHA",
        "at least seven days",
        "Qdrant is intentionally not backed up initially",
        "separate authorised change",
    )
    for phrase in required:
        assert phrase in text
    assert "new GitHub App" in text
    assert "No legacy Octopus PostgreSQL" in text


def test_current_production_compose_and_nginx_are_not_changed() -> None:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "origin/main",
            "--",
            "docker-compose.yml",
            "config/nginx.conf",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
