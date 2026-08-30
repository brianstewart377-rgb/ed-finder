import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_external_db_config.sh"
APPLIER = ROOT / "scripts" / "apply_migrations.sh"


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
    assert "docker compose up -d --no-deps redis" in deploy
    assert "docker compose exec -T redis redis-cli ping" in deploy
    assert "docker compose ps --status running --services postgres" in deploy
    assert "bundled postgres is running in external database mode" in deploy
    assert 'if [[ "$EXTERNAL_DB_MODE" == "false" ]]; then\n  docker compose ps postgres' in deploy


def _fake_psql(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    psql = fake_bin / "psql"
    psql.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >>\"$FAKE_PSQL_ARGV_LOG\"\n"
        "stat -c '%a' \"$PGSERVICEFILE\" >>\"$FAKE_SERVICE_MODE_LOG\"\n"
        "case \"$EDFINDER_VALIDATING_URL_NAME\" in\n"
        "  DATABASE_APP_URL) printf '%s\\n' \"$FAKE_APP_IDENTITY\";;\n"
        "  DATABASE_READONLY_URL) printf '%s\\n' \"$FAKE_READONLY_IDENTITY\";;\n"
        "  DATABASE_IMPORT_URL) printf '%s\\n' \"$FAKE_IMPORT_IDENTITY\";;\n"
        "  DATABASE_MAINTENANCE_URL) printf '%s\\n' \"$FAKE_MAINTENANCE_IDENTITY\";;\n"
        "  DATABASE_MIGRATION_URL) printf '%s\\n' \"$FAKE_MIGRATION_IDENTITY\";;\n"
        "  *) exit 2;;\n"
        "esac\n",
        encoding="utf-8",
    )
    psql.chmod(psql.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def _preflight_env(tmp_path: Path) -> dict[str, str]:
    env = _env()
    fake_bin = _fake_psql(tmp_path)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_PSQL_ARGV_LOG"] = str(tmp_path / "psql-argv.log")
    env["FAKE_SERVICE_MODE_LOG"] = str(tmp_path / "service-mode.log")
    capabilities = {
        "APP": "t|t|t|t|f|f",
        "READONLY": "t|f|f|f|f|f",
        "IMPORT": "t|t|t|t|f|f",
        "MAINTENANCE": "t|f|f|t|t|f",
        "MIGRATION": "t|t|t|t|t|t",
    }
    for index, (role, flags) in enumerate(capabilities.items(), start=1):
        env[f"FAKE_{role}_IDENTITY"] = f"180002|72623859790382856|edfinder|726f6c65{index:02x}|{flags}"
    return env


def test_external_preflight_connects_every_role_and_accepts_one_pg18_identity(tmp_path):
    env = _preflight_env(tmp_path)
    result = subprocess.run(
        ["bash", str(VALIDATOR)], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "separated external roles have suitable privileges" in result.stdout
    assert "do-not-print-this" not in result.stdout + result.stderr
    argv = Path(env["FAKE_PSQL_ARGV_LOG"]).read_text(encoding="utf-8")
    assert "service=external_preflight" in argv
    assert "postgresql://" not in argv
    assert "do-not-print-this" not in argv
    assert set(Path(env["FAKE_SERVICE_MODE_LOG"]).read_text().splitlines()) == {"600"}


def test_external_preflight_rejects_role_on_a_different_cluster(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_IMPORT_IDENTITY"] = "180002|99999999999999999|edfinder|696d706f7274|t|t|t|t|f|f"
    result = subprocess.run(
        ["bash", str(VALIDATOR)], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_IMPORT_URL does not target the same PostgreSQL cluster and database" in result.stderr
    assert "do-not-print-this" not in result.stdout + result.stderr


def test_external_preflight_rejects_role_on_a_different_database(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_MIGRATION_IDENTITY"] = "180002|72623859790382856|postgres|6d6967726174696f6e|t|t|t|t|t|t"
    result = subprocess.run(
        ["bash", str(VALIDATOR)], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_MIGRATION_URL does not target the same PostgreSQL cluster and database" in result.stderr


def test_external_preflight_checks_pg18_for_every_role(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_MAINTENANCE_IDENTITY"] = "170009|72623859790382856|edfinder|6d61696e74656e616e6365|t|f|f|t|t|f"
    result = subprocess.run(
        ["bash", str(VALIDATOR)], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_MAINTENANCE_URL must target PostgreSQL 18" in result.stderr


def test_external_preflight_rejects_reused_role_credentials(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_READONLY_IDENTITY"] = env["FAKE_APP_IDENTITY"]
    result = subprocess.run(["bash", str(VALIDATOR)], env=env, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "same database role as DATABASE_APP_URL" in result.stderr


def test_external_preflight_rejects_overprivileged_reader(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_READONLY_IDENTITY"] = "180002|72623859790382856|edfinder|726561646572|t|t|f|f|f|f"
    result = subprocess.run(["bash", str(VALIDATOR)], env=env, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "role is not strictly read-only" in result.stderr


def test_external_preflight_requires_migration_ddl_and_maintenance_capability(tmp_path):
    env = _preflight_env(tmp_path)
    env["FAKE_MIGRATION_IDENTITY"] = "180002|72623859790382856|edfinder|6d6967726174696f6e|t|t|t|t|t|f"
    result = subprocess.run(["bash", str(VALIDATOR)], env=env, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "lacks required schema DDL capability" in result.stderr


def test_deploy_preserves_operator_exported_values_after_loading_dotenv():
    deploy = (ROOT / "scripts" / "deploy_main.sh").read_text(encoding="utf-8")
    assert 'done < <(compgen -e)' in deploy
    assert 'source .env' in deploy
    assert 'export "$name=${OPERATOR_EXPORTED_ENV[$name]}"' in deploy
    assert "export EDFINDER_ENV_ALREADY_RESOLVED=1" in deploy


def test_migration_applier_does_not_resource_dotenv_after_deploy_resolution():
    applier = (ROOT / "scripts" / "apply_migrations.sh").read_text(encoding="utf-8")
    assert '"${EDFINDER_ENV_ALREADY_RESOLVED:-0}" != "1"' in applier
    assert 'DATABASE_URL="${DATABASE_MIGRATION_URL:-${DATABASE_URL:-}}"' in applier


def test_migration_applier_runtime_preserves_resolved_operator_url(tmp_path):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    manifest = sql_dir / "migration-manifest.txt"
    manifest.write_text("# intentionally empty\n", encoding="utf-8")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DATABASE_MIGRATION_URL=postgresql://dotenv:wrong@db.invalid/edfinder\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    argv_log = tmp_path / "migration-argv.log"
    psql = fake_bin / "psql"
    psql.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >>\"$FAKE_MIGRATION_ARGV_LOG\"\n",
        encoding="utf-8",
    )
    psql.chmod(psql.stat().st_mode | stat.S_IXUSR)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "ENV_FILE": str(dotenv),
            "SQL_DIR": str(sql_dir),
            "MIGRATION_MANIFEST": str(manifest),
            "DATABASE_MIGRATION_URL": "postgresql://operator:correct@db.invalid/edfinder",
            "EDFINDER_ENV_ALREADY_RESOLVED": "1",
            "FAKE_MIGRATION_ARGV_LOG": str(argv_log),
        }
    )
    result = subprocess.run(
        ["bash", str(APPLIER)], env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    argv = argv_log.read_text(encoding="utf-8")
    assert "postgresql://operator:correct@db.invalid/edfinder" in argv
    assert "dotenv:wrong" not in argv
