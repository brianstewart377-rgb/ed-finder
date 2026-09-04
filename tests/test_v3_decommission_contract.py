import json
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


def test_legacy_data_inventory_is_fail_closed_and_identifies_retained_dump():
    inventory_doc = _read('docs', 'operations', 'legacy-data-inventory.md')
    manifest = json.loads(
        _read('docs', 'operations', 'legacy-data-inventory-manifest.json')
    )

    assert 'Inventory only — not a V3 production recovery or migration runbook' in inventory_doc
    assert 'explicitly confirmed disposable/offline restore, never production' in inventory_doc
    assert 'Unknown, estimated, or blank counts do not pass the gate' in inventory_doc
    assert 'makes no claim' in inventory_doc

    assert manifest['authority'] == 'inventory_only_not_a_recovery_or_migration_runbook'
    assert manifest['production_database_access_authorized'] is False
    assert manifest['migration_complete'] is False
    assert manifest['completeness_evidence'] is None
    assert manifest['retained_dump'] == {
        'filename': 'edfinder_20260823T021001Z.dump',
        'format': 'postgresql_custom',
        'size_bytes': 75931356521,
        'sha256': '20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1',
        'offsite_sync_recorded_at': '2026-08-23T05:32:41Z',
        'identity_reverified_at': None,
    }


def test_legacy_data_manifest_requires_counts_validation_and_dispositions():
    manifest = json.loads(
        _read('docs', 'operations', 'legacy-data-inventory-manifest.json')
    )
    required = set(manifest['required_evidence_fields'])

    assert {
        'source_table_count', 'source_record_count', 'selection_record_count',
        'target_record_count_before', 'target_record_count_after',
        'primary_key_validation', 'referential_integrity_validation',
        'domain_validation', 'privacy_and_ownership_review',
        'reconciliation_result', 'reviewer', 'evidence_references',
    } <= required
    assert manifest['inspection_boundary']['production_forbidden'] is True
    assert manifest['inspection_boundary']['dump_catalogue_inspected'] is False

    groups = {item['classification']: item for item in manifest['inventory']}
    assert set(groups) == {
        'public_reconstructable', 'irreplaceable_private_manual_history',
        'transient_or_operational', 'unresolved_requires_evidence',
    }
    assert 'systems' in groups['public_reconstructable']['tables']
    assert 'app_users' in groups['irreplaceable_private_manual_history']['tables']
    assert 'web_sessions' in groups['transient_or_operational']['tables']
    assert 'ratings' in groups['unresolved_requires_evidence']['tables']
    assert all(group['evidence'] is None for group in groups.values())
    template = manifest['selective_extraction_record_template']
    assert required <= set(template)
    assert template['source_record_count'] is None
    assert template['domain_validation'] == 'not_run'
    assert template['evidence_references'] == []
    assert manifest['selective_extraction_records'] == []


def test_live_runtime_identity_is_host_neutral():
    config = _read('apps', 'api', 'src', 'config.py')
    main = _read('apps', 'api', 'src', 'main.py')
    importer = _read('apps', 'importer', 'src', 'import_spansh.py')

    assert "app_version:        str  = '3.1.0'" in config
    assert 'ED Finder — API Backend' in main
    assert 'ED Finder API backend v{settings.app_version} starting' in main
    assert 'Hetzner' not in config
    assert 'Hetzner' not in main
    assert 'Hetzner' not in importer
    assert 'Server:' not in importer


def test_local_restore_helpers_are_explicitly_never_v3_production():
    for script_name in ('restore_postgres_backup.sh', 'rehearse_postgres_restore.sh'):
        script = _read('scripts', script_name)
        assert 'LOCAL-DEV/CI REHEARSAL ONLY — NEVER V3 PRODUCTION.' in script
        assert 'V3 database recovery remains fail-closed' in script
        assert 'docs/operations/infrastructure-status.md' in script


def test_root_compose_and_maintenance_are_legacy_local_not_v3_authority():
    compose = _read('docker-compose.yml')
    maintenance_files = (
        _read('apps', 'maintenance', 'Dockerfile'),
        *(
            _read('apps', 'maintenance', 'scripts', name)
            for name in (
                'backup_rehearsal.sh',
                'crontab',
                'pg_repack.sh',
                'run_backup.sh',
                'run_disk_watchdog.sh',
                'run_ingest_watchdog.sh',
                'run_maintenance.sh',
            )
        ),
    )

    assert compose.startswith('# LEGACY / SELF-HOST / LOCAL APPLICATION STACK — NOT V3 PRODUCTION.')
    assert 'PostgreSQL 16 services exist' in compose
    assert 'current V3 production uses PostgreSQL 18' in compose
    assert 'apps/maintenance is a legacy/local sidecar, not the V3 backup/PITR design' in compose
    for source in maintenance_files:
        assert 'LEGACY/SELF-HOST/LOCAL' in source
        assert 'V3' in source
