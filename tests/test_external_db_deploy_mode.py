import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_external_db_config.sh"


def _env(password: str = "do-not-print-this") -> dict[str, str]:
    env = os.environ.copy()
    for name, role in (
        ("DATABASE_APP_URL", "app"),
        ("DATABASE_READONLY_URL", "readonly"),
        ("DATABASE_IMPORT_URL", "import"),
        ("DATABASE_MAINTENANCE_URL", "maintenance"),
        ("DATABASE_MIGRATION_URL", "migration"),
    ):
        env[name] = f"postgresql://{role}:{password}@db.example.invalid/edfinder"
    return env


def test_external_config_fails_closed_when_a_role_url_is_missing():
    env = _env()
    env.pop("DATABASE_MIGRATION_URL")
    result = subprocess.run(
        ["bash", str(VALIDATOR), "--config-only"], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_MIGRATION_URL is required" in result.stderr
    assert "do-not-print-this" not in result.stdout + result.stderr


def test_external_config_rejects_the_bundled_compose_database():
    env = _env()
    env["DATABASE_APP_URL"] = "postgresql://app:do-not-print-this@postgres/edfinder"
    result = subprocess.run(
        ["bash", str(VALIDATOR), "--config-only"], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "bundled Compose postgres" in result.stderr
    assert "do-not-print-this" not in result.stdout + result.stderr


def test_external_config_accepts_complete_role_urls_without_leaking_them():
    result = subprocess.run(
        ["bash", str(VALIDATOR), "--config-only"], env=_env(),
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0
    assert "configuration is complete" in result.stdout
    assert "do-not-print-this" not in result.stdout + result.stderr


def test_deploy_external_mode_never_starts_compose_dependencies():
    deploy = (ROOT / "scripts" / "deploy_main.sh").read_text(encoding="utf-8")
    assert "--external-db" in deploy
    assert "bash scripts/validate_external_db_config.sh" in deploy
    assert "docker compose up -d --build --no-deps api eddn maintenance" in deploy
    assert "docker compose up -d --force-recreate --no-deps nginx" in deploy
    assert 'if [[ "$EXTERNAL_DB_MODE" == "false" ]]; then\n  docker compose ps postgres' in deploy
