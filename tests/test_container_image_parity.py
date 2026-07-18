from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
_CONTAINER_PARITY_ENV = 'EDFINDER_RUN_CONTAINER_PARITY'


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_required_parity_check_runs_for_every_pull_request():
    workflow = _read('.github', 'workflows', 'container-image-parity.yml')
    pull_request_block = workflow.split('  pull_request:', 1)[1].split('  push:', 1)[0]
    push_block = workflow.split('  push:', 1)[1].split('  schedule:', 1)[0]

    assert 'paths:' not in pull_request_block
    assert 'paths:' in push_block


def _docker_binary() -> str:
    docker = shutil.which('docker.exe') or shutil.which('docker')
    if docker is None:
        pytest.skip('docker is required for container parity tests')
    probe = subprocess.run(
        [docker, 'info'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip('docker daemon is unavailable for container parity tests')
    return docker


def _run_docker_compose(docker: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        'POSTGRES_PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'container-parity-test'),
    }
    return subprocess.run(
        [docker, 'compose', *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        check=False,
    )


def test_env_and_compose_expose_optional_readonly_database_dsn():
    env_example = _read('env.example')
    compose = _read('docker-compose.yml')
    review_compose = _read('docker-compose.review.yml')
    api_dockerfile = _read('apps', 'api', 'Dockerfile')
    eddn_dockerfile = _read('apps', 'eddn', 'Dockerfile')
    importer_dockerfile = _read('apps', 'importer', 'Dockerfile')
    maintenance_dockerfile = _read('apps', 'maintenance', 'Dockerfile')
    workflow = _read('.github', 'workflows', 'container-image-parity.yml')

    assert 'DATABASE_READONLY_URL=' in env_example
    assert 'BACKUP_OFFSITE_REMOTE=' in env_example
    assert 'DATABASE_APP_URL=' in env_example
    assert 'DATABASE_IMPORT_URL=' in env_example
    assert 'DATABASE_MAINTENANCE_URL=' in env_example
    assert 'DATABASE_MIGRATION_URL=' in env_example
    assert 'DATABASE_READONLY_URL:' in compose
    assert '${DATABASE_READONLY_URL:-}' in compose
    assert 'DATABASE_APP_URL:-postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder' in compose
    assert 'DATABASE_IMPORT_URL:-postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder' in compose
    assert 'DATABASE_MAINTENANCE_URL:-postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder' in compose
    assert 'DATA_INVARIANTS_DATABASE_URL:' in compose
    assert 'BACKUP_OFFSITE_REMOTE:' in compose
    assert 'context: .' in compose
    assert 'dockerfile: apps/api/Dockerfile' in compose
    assert 'dockerfile: apps/eddn/Dockerfile' in compose
    assert 'dockerfile: apps/importer/Dockerfile' in compose
    assert 'dockerfile: apps/maintenance/Dockerfile' in compose
    assert 'dockerfile: apps/api/Dockerfile' in review_compose
    assert 'COPY shared_contracts/ ./shared_contracts/' in api_dockerfile
    assert 'COPY shared_contracts/ ./shared_contracts/' in eddn_dockerfile
    assert 'COPY shared_contracts/ ./shared_contracts/' in importer_dockerfile
    assert 'python3 py3-psycopg2 rclone' in maintenance_dockerfile
    assert 'COPY scripts/checks/data_invariants.py' in maintenance_dockerfile
    assert 'COPY shared_contracts/data_invariant_contracts.py' in maintenance_dockerfile
    assert "EDFINDER_RUN_CONTAINER_PARITY: 'yes'" in workflow
    assert 'cp env.example .env' in workflow
    assert "'apps/api/requirements.txt'" in workflow
    assert "'apps/eddn/requirements.txt'" in workflow
    assert "'apps/importer/requirements.txt'" in workflow
    assert 'tests/test_container_image_parity.py -q' in workflow
    assert '-k built_api_eddn_and_importer_images_pass_runtime_import_parity' in workflow


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.slow
def test_built_api_eddn_and_importer_images_pass_runtime_import_parity():
    if os.environ.get(_CONTAINER_PARITY_ENV) != 'yes':
        pytest.skip(f'set {_CONTAINER_PARITY_ENV}=yes to run built-image parity smoke')

    docker = _docker_binary()
    build = _run_docker_compose(docker, 'build', 'api', 'eddn', 'importer')
    assert build.returncode == 0, build.stderr or build.stdout

    api_probe = textwrap.dedent(
        """
        import asyncio
        from routers import admin as admin_router

        class FakeConn:
            async def execute(self, query, *args):
                return 'SELECT 1'

            async def fetchval(self, query, *args):
                return 0

            async def fetchrow(self, query, *args):
                if 'FROM journal_import_staging' in query:
                    return {
                        'total_rows': 0,
                        'older_than_7d': 0,
                        'older_than_30d': 0,
                        'older_than_90d': 0,
                        'distinct_systems': 0,
                        'latest_created_at': None,
                        'oldest_created_at': None,
                    }
                if "FROM source_runs" in query and "source_name = 'frontier_journal'" in query:
                    return {
                        'total_runs': 0,
                        'rows_read': 0,
                        'rows_staged': 0,
                        'older_than_30d': 0,
                        'older_than_90d': 0,
                        'latest_finished_at': None,
                        'oldest_started_at': None,
                    }
                if 'FROM observed_facts' in query:
                    return {
                        'total_rows': 0,
                        'older_than_7d': 0,
                        'older_than_30d': 0,
                        'older_than_90d': 0,
                        'distinct_systems': 0,
                        'latest_collected_at': None,
                        'oldest_collected_at': None,
                    }
                if 'FROM evidence_records' in query:
                    return {
                        'total_rows': 0,
                        'active_rows': 0,
                        'superseded_rows': 0,
                        'quarantined_rows': 0,
                        'latest_collected_at': None,
                        'oldest_collected_at': None,
                    }
                return {
                    'tracked_total': 0,
                    'age_0_3d': 0,
                    'age_3_7d': 0,
                    'age_7_14d': 0,
                    'age_over_14d': 0,
                }

        async def main():
            conn = FakeConn()
            ok_snapshot, _ = await admin_router._run_telemetry_hot_log_snapshot_operation(conn)
            ok_invariants, output = await admin_router._run_data_invariants_operation(conn)
            assert ok_snapshot is True
            assert ok_invariants is True
            assert 'ED-Finder data invariants' in output
            print('api-parity-ok')

        asyncio.run(main())
        """
    ).strip()
    api = _run_docker_compose(
        docker,
        'run',
        '--rm',
        '--no-deps',
        'api',
        'python',
        '-c',
        api_probe,
    )
    assert api.returncode == 0, api.stderr or api.stdout
    assert 'api-parity-ok' in api.stdout

    eddn_probe = (
        "import eddn_listener; import canonical_evidence; from shared_contracts import evidence_identity; "
        "assert callable(evidence_identity.content_addressed_evidence_key); "
        "assert eddn_listener.promote_canonical_evidence_for_systems.__module__ == 'canonical_evidence'; "
        "print('eddn-parity-ok')"
    )
    eddn = _run_docker_compose(
        docker,
        'run',
        '--rm',
        '--no-deps',
        'eddn',
        'python',
        '-c',
        eddn_probe,
    )
    assert eddn.returncode == 0, eddn.stderr or eddn.stdout
    assert 'eddn-parity-ok' in eddn.stdout

    importer_probe = (
        'import canonical_evidence_promotion; '
        'from shared_contracts import enrichment_artifact_contracts; '
        "assert callable(canonical_evidence_promotion._content_addressed_evidence_key); "
        "assert hasattr(enrichment_artifact_contracts, 'validate_warehouse_status_artifact'); "
        "print('importer-parity-ok')"
    )
    importer = _run_docker_compose(
        docker,
        'run',
        '--rm',
        '--no-deps',
        'importer',
        '-c',
        importer_probe,
    )
    assert importer.returncode == 0, importer.stderr or importer.stdout
    assert 'importer-parity-ok' in importer.stdout
