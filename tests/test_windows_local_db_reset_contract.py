from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_windows_local_db_reset_script_uses_local_compose_and_ledgered_apply():
    script = _read('scripts', 'dev', 'reset_local_db.ps1')

    assert "[string]$DatabaseName = 'edfinder'" in script
    assert '[switch]$ConfirmReset' in script
    assert "[switch]$SchemaOnly" in script
    assert "Refusing destructive local DB reset without -ConfirmReset." in script
    assert "Join-Path $repoRoot 'docker-compose.local.yml'" in script
    assert "'scripts\\dev\\run-bash.ps1'" in script
    assert "'compose', '-f', $composeLocal, 'up', '-d', 'postgres', 'redis'" in script
    assert "'scripts/apply_migrations.sh'" in script
    assert "'--include-manual'" in script
    assert '/docker-entrypoint-initdb.d/seed_preview.sql' in script
    assert 'REFRESH MATERIALIZED VIEW mv_archetype_rankings;' in script


def test_windows_dev_environment_docs_advertise_local_db_reset_entrypoint():
    doc = _read('docs', 'development', 'windows-dev-environment.md')

    assert 'reset_local_db.ps1' in doc
    assert '-ConfirmReset' in doc
    assert 'docker-compose.local.yml' in doc
