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


def test_destructive_v2_storage_recovery_runbook_is_tombstoned():
    runbook = _read('docs', 'operations', 'storage-recovery-runbook-2026-07-12.md')
    normalized = ' '.join(runbook.replace('**', '').split())

    assert 'RETIRED — V1/V2 production storage recovery runbook' in runbook
    assert '**Do not execute this file.**' in runbook
    assert 'It is not a PostgreSQL 18/V3 production runbook' in normalized
    assert 'Issue #573' in runbook
    assert 'DROP INDEX CONCURRENTLY' not in runbook
    assert 'pg_repack ratings' not in runbook


def test_frontier_oauth_doc_fails_closed_away_from_v2_provisioning():
    oauth = _read('docs', 'operations', 'frontier-oauth.md')

    assert 'V3 production configuration boundary' in oauth
    assert 'does **not** authorize placing production secrets' in oauth
    assert 'does not currently contain a reviewed V3 production' in oauth
    assert 'https://ed-finder.app/api/auth/frontier/callback' in oauth
    assert 'v3-app-status' in oauth
    assert 'normal deployment wrapper applies' not in oauth
    assert 'Set these values in the production `.env`' not in oauth


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


def test_legacy_compose_and_maintenance_are_not_v3_pg18_authority():
    compose = _read('docker-compose.yml')
    maintenance = _read('apps', 'maintenance', 'Dockerfile')

    assert 'LEGACY SELF-HOST / LOCAL-CI COMPOSE — NEVER V3 PRODUCTION OR BACKUP AUTHORITY' in compose
    assert 'PostgreSQL 16 — legacy/local Compose compatibility' in compose
    assert 'PostgreSQL 18' in compose
    assert 'LEGACY SELF-HOST / LOCAL-CI IMAGE — NEVER V3 PRODUCTION OR BACKUP AUTHORITY' in maintenance
    assert 'PostgreSQL 16 matches the retained root Compose environment only' in maintenance
    assert 'Current V3' in maintenance and 'PostgreSQL 18' in maintenance


def test_stale_operational_design_docs_fail_closed():
    ledger = _read('docs', 'operations', 'migration-ledger-implementation-plan.md')
    control_plane = _read('docs', 'development', 'chatgpt-ops-control-plane.md')

    assert 'SUPERSEDED DESIGN-ONLY PLAN. DO NOT EXECUTE.' in ledger
    assert 'neither a current V3 migration procedure nor authority' in ledger
    assert 'DESIGN/HISTORICAL DOCUMENT — NOT AN OPERATOR RUNBOOK.' in control_plane
    assert 'operations proposed below were never implemented' in control_plane
    assert 'chatgpt-ed-new-ops.yml' in control_plane


def test_application_hard_cut_is_current_authority():
    roadmap = _read('docs', 'ROADMAP.md')
    stack = _read('docs', 'development', 'v3-application-stack-decision.md')
    agent_contract = _read('CLAUDE.md')
    readme = _read('README.md')

    for authority in (roadmap, stack, agent_contract, readme):
        assert 'apps/web/' in authority
        assert 'sole' in authority
        assert 'Cypress' in authority
    assert 'hard-cut branch remains unmerged until' in roadmap
    assert 'replacement parity is complete' in roadmap
    assert 'not a runnable parallel lane' in stack
    assert 'temporary source evidence only' in agent_contract
    assert 'no Playwright dependency or invocation is current tooling' in readme


def test_live_api_and_layout_importer_copy_is_provider_neutral():
    layout_provider = _read('apps', 'api', 'src', 'colony_planner', 'layout_import_provider.py')
    admin_router = _read('apps', 'api', 'src', 'routers', 'admin.py')
    simulation_router = _read('apps', 'api', 'src', 'routers', 'simulation.py')
    main = _read('apps', 'api', 'src', 'main.py')
    config = _read('apps', 'api', 'src', 'config.py')

    assert 'Live layout-source import is not wired yet' in layout_provider
    assert 'Live Spansh layout import is not wired yet' not in layout_provider
    assert 'external data providers' in admin_router
    assert 'external-source imported' in simulation_router
    assert 'Spansh-imported' not in simulation_router
    assert 'Hetzner' not in main
    assert 'hetzner' not in config.lower()


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
