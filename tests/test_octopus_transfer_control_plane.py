from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess

import pytest
import yaml

ROOT = Path(__file__).parents[1]
CODEC = ROOT / "scripts/operator/octopus_credentials.py"
NEW = ROOT / ".github/workflows/octopus-new-ops.yml"
OLD = ROOT / ".github/workflows/octopus-legacy-handoff.yml"

PEM = "-----BEGIN PRIVATE KEY-----\nQUJDREVGRw==\n-----END PRIVATE KEY-----"
REQUIRED = {
    "GITHUB_APP_ID": "12345",
    "GITHUB_APP_PRIVATE_KEY": PEM,
    "GITHUB_WEBHOOK_SECRET": "webhook",
    "GITHUB_APP_CLIENT_ID": "client",
    "GITHUB_APP_CLIENT_SECRET": "client-secret",
    "NEXT_PUBLIC_GITHUB_APP_SLUG": "octopus",
    "GITHUB_STATE_SECRET": "state",
}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CODEC), *args], text=True, capture_output=True, check=False
    )


def dotenv(values: dict[str, str]) -> str:
    lines = []
    for key, value in values.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'{key}="{escaped}"')
    return "\r\n".join(lines) + "\r\n"


@pytest.mark.operator
def test_strict_allowlist_multiline_pem_and_atomic_merge(tmp_path: Path) -> None:
    source = tmp_path / "old.env"
    source.write_text(
        dotenv(
            {**REQUIRED, "OPENAI_API_KEY": "openai", "STRIPE_SECRET_KEY": "excluded"}
        )
    )
    ht = tmp_path / "ui.htpasswd"
    ht.write_text("admin:$2y$hash\n")
    payload = tmp_path / "payload"
    result = run(
        "export",
        "--source",
        str(source),
        "--output",
        str(payload),
        "--htpasswd",
        str(ht),
    )
    assert result.returncode == 0, result.stderr
    document = json.loads(payload.read_text())
    assert document["integrations"]["GITHUB_APP_PRIVATE_KEY"] == PEM
    assert "STRIPE_SECRET_KEY" not in document["integrations"]
    target = tmp_path / "octopus.env"
    target.write_text("OCTOPUS_POSTGRES_PASSWORD=fresh\nENABLE_REVIEW_WORKERS=false\n")
    result = run(
        "merge",
        "--payload",
        str(payload),
        "--env",
        str(target),
        "--htpasswd",
        str(tmp_path / "new.htpasswd"),
    )
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "OCTOPUS_POSTGRES_PASSWORD=fresh" in target.read_text()
    assert "ENABLE_REVIEW_WORKERS=false" in target.read_text()
    assert "STRIPE" not in target.read_text()


@pytest.mark.parametrize(
    "mutation,needle",
    [
        (
            lambda s: s + 'GITHUB_APP_ID="9"\n',
            "duplicate allowlisted key: GITHUB_APP_ID",
        ),
        (
            lambda s: s.replace('GITHUB_APP_ID="12345"', 'GITHUB_APP_ID="'),
            "quoted value",
        ),
        (
            lambda s: s.replace("QUJDREVGRw==", "A" * 70000),
            "oversized value for key: GITHUB_APP_PRIVATE_KEY",
        ),
        (
            lambda s: s.replace('GITHUB_WEBHOOK_SECRET="webhook"\r\n', ""),
            "missing required key: GITHUB_WEBHOOK_SECRET",
        ),
        (
            lambda s: s.replace(
                "-----END PRIVATE KEY-----",
                "-----END PRIVATE KEY-----\\n-----BEGIN PRIVATE KEY-----\\nQQ==\\n-----END PRIVATE KEY-----",
            ),
            "invalid PEM shape",
        ),
    ],
)
def test_malformed_values_fail_by_key_or_shape_without_values(
    tmp_path: Path, mutation, needle: str
) -> None:
    source = tmp_path / "old.env"
    source.write_text(mutation(dotenv(REQUIRED)))
    result = run(
        "export", "--source", str(source), "--output", str(tmp_path / "payload")
    )
    assert result.returncode != 0
    assert needle in result.stderr
    for secret in ("client-secret", "webhook", "state"):
        assert secret not in result.stderr


def test_rejects_nul_invalid_names_and_unexpected_continuation(tmp_path: Path) -> None:
    for content in (b"GITHUB_APP_ID=1\0\n", b"BAD-NAME=x\n", b" continuation\n"):
        source = tmp_path / "old.env"
        source.write_bytes(content)
        result = run(
            "export", "--source", str(source), "--output", str(tmp_path / "payload")
        )
        assert result.returncode != 0


def test_workflows_are_trusted_main_pinned_ssh_and_ciphertext_only() -> None:
    for path in (NEW, OLD):
        data = yaml.safe_load(path.read_text())
        assert data["jobs"]["operate"]["steps"][0]["with"]["ref"] == "main"
        text = path.read_text()
        assert "ssh-keyscan" not in text
        assert "StrictHostKeyChecking=yes" in text
        assert "request branch" not in text.lower()
        assert "octopus.env" not in [
            p for p in text.splitlines() if "upload-artifact" in p
        ]
    old = OLD.read_text()
    assert "HETZNER_OPERATOR_KNOWN_HOSTS" in old and "ssh-keygen -F" in old
    assert "retention-days: 1" in old and "octopus-transfer.age" in old
    assert "GITHUB_OUTPUT" not in old


def test_runtime_orders_install_and_gates_worker_and_edge() -> None:
    runtime = (ROOT / "scripts/operator/octopus_runtime.sh").read_text()
    assert (
        runtime.index("up -d postgres qdrant")
        < runtime.index("prisma migrate deploy")
        < runtime.index("up -d web")
    )
    for pin in (
        "55583ac832472ad8b535f1f678f9c11837f7cfdb",
        "oven/bun:1.3.4",
        "v1.0.122",
    ):
        assert pin in runtime
    enable = runtime[runtime.index("enable-worker)") : runtime.index("disable-worker)")]
    for proof in ("private-proof", "old-quiesced", "public-edge-proof"):
        assert proof in enable
    edge = (ROOT / "scripts/operator/octopus_edge.sh").read_text()
    assert "private-proof" in edge and "edge config fingerprint mismatch" in edge
    assert "docker compose down" not in runtime
    assert "docker volume rm" not in runtime


def test_age_contract_is_pinned_and_plaintext_never_uploaded() -> None:
    handoff = (ROOT / "scripts/operator/octopus_handoff.sh").read_text()
    assert "AGE_VERSION=1.3.2" in handoff
    assert "AGE_AMD64_SHA256=" in handoff and "sha256sum -c" in handoff
    assert "age-keygen" in handoff and "chmod 0600" in handoff
    assert "one_time_identity_destroyed: true" in handoff
    assert "payload.json" not in OLD.read_text()


def test_non_secret_credential_check_reports_presence_not_values(tmp_path: Path) -> None:
    source = tmp_path / "legacy.env"
    source.write_text(
        dotenv(
            {
                **REQUIRED,
                "OPENAI_API_KEY": "synthetic-openai-value",
                "ANTHROPIC_API_KEY": "synthetic-anthropic-value",
            }
        )
    )
    result = run("check", "--source", str(source))
    assert result.returncode == 0, result.stderr
    assert "integration_credentials_valid: true" in result.stdout
    assert "provider_openai_present: true" in result.stdout
    assert "provider_anthropic_present: true" in result.stdout
    assert "synthetic-openai-value" not in result.stdout + result.stderr
    assert "synthetic-anthropic-value" not in result.stdout + result.stderr


def test_legacy_preflight_discovers_bounded_env_and_rollback_restores_old_worker() -> None:
    old = OLD.read_text()
    runtime = (ROOT / "scripts/operator/octopus_runtime.sh").read_text()

    assert "if: inputs.operation != 'preflight'" not in old
    assert "legacy-preflight" in old
    assert "legacy-status" in old
    assert "legacy-env-path" in old
    assert "restore-old" in old
    assert "/tmp/octopus_handoff.sh export '$RECIPIENT' /opt/octopus/octopus.env" not in old

    assert '"$DIR/octopus.env" "$DIR/.env"' in runtime
    assert "no supported legacy env file found" in runtime
    assert "multiple supported legacy env files found" in runtime
    preflight = runtime[runtime.index("legacy-preflight)") : runtime.index("legacy-status)")]
    assert "octopus_credentials.py\" check --source" in preflight
    assert "legacy_dc config --quiet" in preflight

    restore = runtime[runtime.index("restore-old)") : runtime.index("enable-worker)")]
    assert "set_workers_file \"$env_file\" true" in restore
    assert "legacy_worker_state) == true" in restore
    assert 'rm -f "$DIR/receipts/old-quiesced"' in restore
