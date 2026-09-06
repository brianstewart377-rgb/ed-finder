from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISIONER = ROOT / "scripts/operator/actions/v3-live-checkpoint-provision.sh"
CONTROL = ROOT / ".github/workflows/v3-live-checkpoint-control.yml"
DEPLOY = ROOT / ".github/workflows/v3-application-live-checkpoint-preflight.yml"
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


def test_sensitive_checkpoint_temp_files_have_unconditional_cleanup_and_postgres_access():
    script = _read(PROVISIONER)

    assert 'PW_SQL=""' in script
    assert 'LEDGER_FILE=""' in script
    assert "cleanup_sensitive_temps()" in script
    assert "trap cleanup_sensitive_temps EXIT HUP INT TERM" in script
    assert '[ -z "$PW_SQL" ] || rm -f -- "$PW_SQL"' in script
    assert '[ -z "$LEDGER_FILE" ] || rm -f -- "$LEDGER_FILE"' in script
    assert 'chown postgres:postgres "$PW_SQL"' in script
    assert 'chmod 0600 "$PW_SQL"' in script
    assert '[[ "$DB_PASSWORD" =~ ^[0-9a-f]{48}$ ]]' in script


def test_provisioner_requires_exact_runner_topology():
    script = _read(PROVISIONER)

    assert "verify_exact_runners()" in script
    assert "systemctl list-units --type=service --state=active --no-legend --plain 'actions.runner.*.service'" in script
    assert "unexpected active runner service count" in script
    assert "unexpected active runner topology" in script
    assert script.count("verify_exact_runners") >= 3


def test_checkpoint_database_is_created_once_then_verified_without_migrating():
    script = _read(PROVISIONER)
    seed_call = 'runuser -u postgres -- env DATABASE_URL="$ADMIN_DATABASE_URL" bash scripts/seed_check.sh'
    db_branch = script.index('if [ "$DB_EXISTS" != 1 ]; then')
    seed_at = script.index(seed_call)
    existing_branch = script.index("else", seed_at)
    end_branch = script.index("fi", existing_branch)

    assert db_branch < seed_at < existing_branch < end_branch
    assert script.count(seed_call) == 1
    assert "existing checkpoint database lacks trusted schema receipt" in script
    assert "trusted schema receipt mismatch" in script
    assert "checkpoint migration ledger does not match source" in script
    assert "RECEIPT_MODE=verify" in script
    assert '[ "$DB_CREATED" = false ] || RECEIPT_MODE=create' in script
    assert "PREVIEW_COUNTS" in script
    assert '"40|40|129|10|42"' in script


def test_checkpoint_seed_path_uses_repository_preview_data_and_manual_migrations():
    seed = _read(SEED)

    assert 'apply_migrations.sh" --include-manual' in seed
    assert "seed_preview.sql" in seed
    assert 'assert_count "systems"' in seed
    assert 'assert_count "stations"' in seed
    assert "refresh_map_mviews()" in seed


def test_checkpoint_control_plane_uses_trusted_owner_issue_comment_boundary():
    workflow = _read(CONTROL)

    assert "issue_comment:" in workflow
    assert "types:" in workflow and "- created" in workflow
    assert "github.event.issue.number == 623" in workflow
    assert "github.actor == 'brianstewart377-rgb'" in workflow
    assert "github.event.comment.user.login == 'brianstewart377-rgb'" in workflow
    assert "startsWith(github.event.comment.body, 'V3-CHECKPOINT ')" in workflow
    assert 'REQUEST_BODY: ${{ github.event.comment.body }}' in workflow
    assert 'prefix = "V3-CHECKPOINT "' in workflow
    assert "v3-live-checkpoint-requests" not in workflow
    assert "github.event.before" not in workflow
    assert "git diff" not in workflow


def test_checkpoint_control_plane_keeps_canonical_release_and_deploy_boundaries():
    workflow = _read(CONTROL)

    assert "environment: v3-live-checkpoint" in workflow
    assert "V3_LIVE_CHECKPOINT_SSH_KEY" in workflow
    assert "V3_LIVE_CHECKPOINT_SSH_KNOWN_HOSTS" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "sudo -n env CHECKPOINT_OPERATOR_UID=" in workflow
    assert "ref: main" in workflow
    assert "actions/workflows/v3-application-release.yml/dispatches" in workflow
    assert "actions/workflows/v3-application-live-checkpoint-preflight.yml/dispatches" in workflow
    assert '"schema_compatibility": "exact"' in workflow
    assert '"rollback_eligible": True' in workflow
    assert workflow.count("actions: write") == 2
    assert "ED_NEW_OPERATOR_" not in workflow
    assert "nb79a3d.mevnode.com" not in workflow


def test_checkpoint_deploy_uses_ephemeral_ghcr_auth_only_for_the_deploy_window():
    workflow = _read(DEPLOY)

    assert "packages: read" in workflow
    assert "Authenticate ephemeral Contabo GHCR pull authority" in workflow
    assert "Clear ephemeral Contabo GHCR pull authority" in workflow
    assert "GHCR_TOKEN: ${{ github.token }}" in workflow
    assert "docker login ghcr.io -u brianstewart377-rgb --password-stdin" in workflow
    assert "docker logout ghcr.io" in workflow
    assert "DOCKER_CONFIG=/var/lib/edfinder-v3-checkpoint/docker-config" in workflow
    assert "DOCKER_CONTEXT=edfinder-v3-checkpoint-local" in workflow
    assert workflow.index("Authenticate ephemeral Contabo GHCR pull authority") < workflow.index(
        "Run bounded Contabo deployment boundary"
    )
    assert workflow.index("Run bounded Contabo deployment boundary") < workflow.index(
        "Clear ephemeral Contabo GHCR pull authority"
    )
    assert workflow.index("Clear ephemeral Contabo GHCR pull authority") < workflow.index(
        "Upload sanitized deployment receipt"
    )
