from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / 'scripts' / 'operator' / 'actions' / 'v3-derived-data-status.sh'
WORKFLOW = ROOT / '.github' / 'workflows' / 'v3-derived-data-status.yml'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_v3_derived_data_status_is_one_purpose_pinned_operator_path():
    workflow = _read(WORKFLOW)

    assert "20260905-v3-derived-data-status.json" in workflow
    assert '{"operation": "v3-derived-data-status"}' in workflow
    assert 'ref: main' in workflow
    assert 'trusted-main/scripts/operator/actions/v3-derived-data-status.sh' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'UserKnownHostsFile=~/.ssh/known_hosts' in workflow
    assert 'environment: ed-new-operator' in workflow


def test_v3_derived_data_status_is_host_locked_and_read_only():
    source = _read(ACTION)

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert 'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"' in source
    assert 'BEGIN READ ONLY;' in source
    assert 'statement_timeout' in source
    assert '"read_only": True' in source
    assert '"db_writes_performed": False' in source
    assert '"env_files_read": False' in source
    assert '"private_keys_read": False' in source
    assert '"service_changes_performed": False' in source
    assert '"filesystem_writes_performed": False' in source

    for forbidden in (
        '.env',
        'docker restart',
        'docker compose up',
        'docker compose down',
        'pg_dump',
        'pg_restore',
        'INSERT INTO',
        'UPDATE systems',
        'DELETE FROM',
        'TRUNCATE',
        'ALTER TABLE',
        'CREATE TABLE',
        'DROP TABLE',
        'VACUUM',
        'REINDEX',
        'REFRESH MATERIALIZED VIEW',
    ):
        assert forbidden not in source


def test_v3_derived_data_status_uses_bounded_estimates_and_samples():
    source = _read(ACTION)

    assert 'pg_class' in source
    assert 'reltuples' in source
    assert 'TABLESAMPLE SYSTEM (0.01)' in source
    assert 'TABLESAMPLE SYSTEM (0.05)' in source
    assert 'TABLESAMPLE SYSTEM (0.1)' in source
    assert 'COUNT(*) FROM systems' not in source
    assert 'COUNT(*) FROM ratings' not in source
    for relation in (
        'systems',
        'ratings',
        'cluster_summary',
        'system_slot_topology',
        'system_archetype_scores',
        'system_regional_analysis',
        'mv_archetype_rankings',
    ):
        assert relation in source


def test_v3_derived_data_status_shell_syntax_is_valid():
    result = subprocess.run(['bash', '-n', str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
