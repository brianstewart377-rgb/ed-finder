from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
CODEC = ROOT / "scripts/operator/octopus_credentials.py"


def test_unrelated_legacy_template_expressions_do_not_block_allowlisted_check(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.env"
    source.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://octopus:${POSTGRES_PASSWORD}@postgres:5432/octopus",
                "UNRELATED_COMMAND_STYLE=$(not-executed)",
                'GITHUB_APP_ID="12345"',
                'GITHUB_APP_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\\nQUJDREVGRw==\\n-----END PRIVATE KEY-----"',
                'GITHUB_WEBHOOK_SECRET="synthetic-webhook"',
                'GITHUB_APP_CLIENT_ID="synthetic-client"',
                'GITHUB_APP_CLIENT_SECRET="synthetic-client-secret"',
                'NEXT_PUBLIC_GITHUB_APP_SLUG="synthetic-octopus"',
                'GITHUB_STATE_SECRET="synthetic-state"',
                'OPENAI_API_KEY="synthetic-openai"',
                'ANTHROPIC_API_KEY="synthetic-anthropic"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["python3", str(CODEC), "check", "--source", str(source)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "integration_credentials_valid: true" in result.stdout
    assert "provider_openai_present: true" in result.stdout
    assert "provider_anthropic_present: true" in result.stdout
    combined = result.stdout + result.stderr
    for secret in (
        "synthetic-webhook",
        "synthetic-client-secret",
        "synthetic-openai",
        "synthetic-anthropic",
    ):
        assert secret not in combined
