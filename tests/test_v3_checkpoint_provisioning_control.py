from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISIONER = ROOT / "scripts/operator/actions/v3-live-checkpoint-provision.sh"
CONTROL = ROOT / ".github/workflows/v3-live-checkpoint-control.yml"
SEED = ROOT / "scripts/seed_check.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contabo_checkpoint_provisioner_is_persistent_nonproduction_and_read_only():
    script = _read(PROVISIONER)

    assert 'EXPECTED_HOST="vmi3542235"' in script
    assert 'EXPECTED_FQDN="vmi3542235.contaboserver.net"' in script
    assert 'APP_NETWORK="edfinder-v3-checkpoint-app"' in script
    assert 'DB_NAME="edfinder_checkpoint"' in script
    assert 'DB_APP_ROLE="edfinder_checkpoint_app"' in script
    assert 'postgresql-18 postgresql-client-18' in script
    assert 'runuser -u postgres -- env DATABASE_URL="$ADMIN_DATABASE_URL" bash scripts/seed_check.sh' in script
    assert 'ALTER ROLE $DB_APP_ROLE SET default_transaction_read_only = on;' in script
    assert 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO $DB_APP_ROLE;' in script
    assert 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER' in script
    assert "update systems set name=name where false" in script
    assert '"schema_version": "ed-finder/v3-live-checkpoint-schema-identity/v2"' in script
    assert 'REDIS_URL=redis://127.0.0.1:1/0' in script
    assert 'EDDN_SIMULATION_INGEST_ENABLED=false' in script
    assert 'origin_bind": "http://127.0.0.1:18080"' in script
    assert 'per-deploy-github-actions-packages-read-token' in script
    assert "nb79a3d.mevnode.com" not in script
    assert "redis-server" not in script
    assert "valkey" not in script.lower()
    assert "nats-server" not in script


def test_checkpoint_seed_path_uses_repository_preview_data_and_manual_migrations():
    seed = _read(SEED)

    assert 'apply_migrations.sh" --include-manual' in seed
    assert 'seed_preview.sql' in seed
    assert 'assert_count "systems"' in seed
    assert 'assert_count "stations"' in seed
    assert 'refresh_map_mviews()' in seed


def test_checkpoint_control_plane_is_request_triggered_and_keeps_canonical_boundaries():
    workflow = _read(CONTROL)

    assert "v3-live-checkpoint-requests" in workflow
    assert ".github/v3-live-checkpoint-requests/*.json" in workflow
    assert 'environment: v3-live-checkpoint' in workflow
    assert 'V3_LIVE_CHECKPOINT_SSH_KEY' in workflow
    assert 'V3_LIVE_CHECKPOINT_SSH_KNOWN_HOSTS' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'sudo -n env CHECKPOINT_OPERATOR_UID=' in workflow
    assert 'ref: main' in workflow
    assert 'actions/workflows/v3-application-release.yml/dispatches' in workflow
    assert 'actions/workflows/v3-application-live-checkpoint-preflight.yml/dispatches' in workflow
    assert '"schema_compatibility": "exact"' in workflow
    assert '"rollback_eligible": True' in workflow
    assert workflow.count("actions: write") == 2
    assert "ED_NEW_OPERATOR_" not in workflow
    assert "nb79a3d.mevnode.com" not in workflow
