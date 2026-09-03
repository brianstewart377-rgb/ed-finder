from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_roadmap_has_explicit_v3_cutover_boundary_and_keeps_v2_historical():
    roadmap = _read('docs', 'ROADMAP.md')

    assert 'V3 infrastructure cutover boundary — 2026-09-02' in roadmap
    assert 'Hetzner/V2 is decommissioned.' in roadmap
    assert 'historical V2 evidence' in roadmap
    assert 'PostgreSQL 18' in roadmap
    assert 'artifact-backed Windows release wrapper' not in roadmap
    assert 'retired Windows/V2 release wrappers' in roadmap


def test_current_infrastructure_fails_closed_without_pg18_recovery_runbook():
    status = _read('docs', 'operations', 'infrastructure-status.md')

    assert 'V3 database recovery boundary' in status
    assert 'does not currently contain an executable PostgreSQL 18 backup/restore/PITR recovery runbook' in status
    assert 'repository-driven production database backup restoration, PITR execution, or disaster-recovery commands are **not authorized**' in status


def test_v2_deploy_and_setup_entrypoints_cannot_return():
    deploy = _read('scripts', 'deploy_main.sh')

    assert not (ROOT / 'setup.sh').exists()
    assert not (ROOT / 'scripts' / 'release-main-to-prod.ps1').exists()
    assert not (ROOT / 'scripts' / 'deploy-hetzner-over-ssh.ps1').exists()
    assert 'RETIRED — V2 single-host deployment entrypoint' in deploy
    assert 'exit 64' in deploy
    for action in ('git pull --ff-only', 'docker compose up', 'bash scripts/apply_migrations.sh'):
        assert action not in deploy


def test_hosted_review_is_absent_from_active_runtime_configs():
    active = '\n'.join(
        (
            _read('docker-compose.yml'),
            _read('config', 'nginx.conf'),
            _read('config', 'nginx-ci.conf'),
        )
    )

    for retired in (
        'review.ed-finder.app',
        '/opt/ed-finder-review',
        'edfinder-review-edge',
        'review-api:8000',
    ):
        assert retired not in active


def test_active_env_example_does_not_publish_v2_storagebox_credentials():
    env_example = _read('env.example')

    assert 'NOT the V3 production secret/configuration authority' in env_example
    assert 'sudo bash setup.sh' not in env_example
    assert 'storagebox:ed-finder/backups/postgres' not in env_example
    assert 'RCLONE_CONFIG_STORAGEBOX_' not in env_example


def test_protected_integration_lane_exercises_postgresql_18():
    workflow = _read('.github', 'workflows', 'ci.yml')
    integration = workflow[workflow.index('  integration:'):workflow.index('  canonical-safety:')]

    assert 'image: postgres:18-alpine' in integration
    assert 'image: postgres:16-alpine' not in integration
    assert 'bash scripts/seed_check.sh' in integration
    assert 'Run data invariants against seeded integration DB' in integration
    assert 'Run integration test suite' in integration


def test_backend_coverage_lane_exercises_postgresql_18():
    workflow = _read('.github', 'workflows', 'coverage.yml')
    backend = workflow[workflow.index('  backend-coverage:'):workflow.index('  frontend-coverage:')]

    assert 'image: postgres:18-alpine' in backend
    assert 'image: postgres:16-alpine' not in backend
    assert 'bash scripts/seed_check.sh' in backend
    assert 'Validate seeded coverage database' in backend
    assert 'Append integration coverage' in backend
