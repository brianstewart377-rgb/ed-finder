import json
import os
import subprocess
from pathlib import Path

import pytest

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


def test_provisioner_matches_canonical_deploy_host_prerequisites():
    script = _read(PROVISIONER)

    assert "software-properties-common" in script
    assert "add-apt-repository -y ppa:deadsnakes/ppa" in script
    assert "apt-get install -y -qq python3.14" in script
    assert "platform.python_implementation()" in script
    assert "sys.version_info[:2]==(3,14)" in script
    assert "socket.getfqdn()" in script
    assert '[ "$ACTUAL_FQDN" = "$EXPECTED_FQDN" ]' in script
    assert 'touch "$RECEIPT_DIR/deploy.lock"' in script
    assert 'exec 9<>"$RECEIPT_DIR/deploy.lock"' in script
    assert 'flock -n 9 || fail "live-checkpoint deployment lock is unavailable"' in script
    assert 'document["captured_at"] = captured_at' in script
    assert 'atomic_checkpoint_file "$SCHEMA_RECEIPT" "$OP_UID" "$OP_GID"' in script
    assert 'receipt.write_text(' not in script
    assert "verify_origin_authority()" in script
    assert "checkpoint origin port is occupied by an unauthorized process" in script
    assert "edfinder-v3-checkpoint-web" in script
    assert 'grep -qx "127.0.0.1:$ORIGIN_PORT"' in script


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


# Execute only the real helper definitions, never the root/host provisioning entrypoint.
# All filesystem writes below stay in pytest temporary directories; services are stubbed.
def _helpers() -> str:
    return _read(PROVISIONER).split('\n[ "$(id -u)" -eq 0 ]', 1)[0]


def _run_helper(tmp_path, command, *, data=None, extra_env=None):
    env = {
        **os.environ,
        "TEST_ROOT": str(tmp_path),
        "TEST_UID": str(os.getuid()),
        "TEST_GID": str(os.getgid()),
        "TEST_DB_EXISTS": "1",
        "PATH": str(tmp_path / "bin") + os.pathsep + os.environ["PATH"],
        **(extra_env or {}),
    }
    setup = '''
API_ENV="$TEST_ROOT/api.env"
SCHEMA_RECEIPT="$TEST_ROOT/schema-identity.json"
PG_HBA="$TEST_ROOT/pg_hba.conf"
NGINX_SITE="$TEST_ROOT/managed.conf"
OP_UID="$TEST_UID"
OP_GID="$TEST_GID"
DB_EXISTS="$TEST_DB_EXISTS"
NETWORK_GATEWAY=172.22.0.1
NETWORK_SUBNET=172.22.0.0/16
'''
    return subprocess.run(
        ["bash", "-c", _helpers() + setup + command],
        input=data, text=True, capture_output=True, env=env, timeout=15, check=False,
    )


def _stub(tmp_path, name, body):
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o700)


def _api_env(tmp_path, content=None):
    path = tmp_path / "api.env"
    if content is None:
        # Synthetic fixture, never a live credential.
        content = "DATABASE_URL=postgresql://edfinder_checkpoint_app:" + "a" * 48
        content += "@172.22.0.1:5432/edfinder_checkpoint\n"
        content += (
            "CORS_ORIGINS=http://vmi3542235.contaboserver.net\n"
            "REDIS_URL=redis://127.0.0.1:1/0\n"
            "ADMIN_OPERATION_STARTUP_REAP_ENABLED=false\n"
            "EDDN_SIMULATION_INGEST_ENABLED=false\n"
            "AUTH_COOKIE_SECURE=false\n"
            "FRONTIER_REDIRECT_URI=http://vmi3542235.contaboserver.net/api/auth/frontier/callback\n"
        )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("dangling", [False, True])
def test_api_env_symlinks_are_never_read_or_overwritten(tmp_path, dangling):
    target = tmp_path / "unrelated-file"
    if not dangling:
        target.write_text("preserve me", encoding="utf-8")
        target.chmod(0o644)
    (tmp_path / "api.env").symlink_to(target)
    read = _run_helper(tmp_path, "read_checkpoint_password")
    write = _run_helper(
        tmp_path, 'atomic_checkpoint_file "$API_ENV" "$OP_UID" "$OP_GID"', data="replacement",
    )
    assert read.returncode != 0
    assert write.returncode != 0
    assert (tmp_path / "api.env").is_symlink()
    if dangling:
        assert not target.exists()
    else:
        assert target.read_text(encoding="utf-8") == "preserve me"
        assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("content", [None, "", "CORS_ORIGINS=http://example.invalid\n", "DATABASE_URL=\n"])
def test_existing_database_rejects_missing_or_incomplete_api_env(tmp_path, content):
    if content is not None:
        _api_env(tmp_path, content)
    # Exercise credential selection from the entrypoint, including its generation guard.
    script = _read(PROVISIONER)
    selection = script.split('DB_PASSWORD="$(read_checkpoint_password)"', 1)[1].split("DB_CREATED=false", 1)[0]
    command = 'DB_PASSWORD="$(read_checkpoint_password)"' + selection
    _stub(tmp_path, "openssl", 'touch "$TEST_ROOT/password-rotated"; exit 90\n')
    result = _run_helper(tmp_path, command)
    assert result.returncode != 0
    assert not (tmp_path / "password-rotated").exists()


def test_password_is_generated_only_for_initial_creation(tmp_path):
    script = _read(PROVISIONER)
    selection = script.split('DB_PASSWORD="$(read_checkpoint_password)"', 1)[1].split("DB_CREATED=false", 1)[0]
    command = 'DB_PASSWORD="$(read_checkpoint_password)"' + selection
    _stub(tmp_path, "openssl", 'touch "$TEST_ROOT/password-created"; printf "%048d\\n" 0\n')
    result = _run_helper(tmp_path, command, extra_env={"TEST_DB_EXISTS": ""})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "password-created").exists()


def test_verification_preserves_existing_credential_and_skips_password_sql(tmp_path):
    path = _api_env(tmp_path)
    before = path.read_bytes(), path.stat().st_ino
    result = _run_helper(tmp_path, "read_checkpoint_password")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "a" * 48
    assert (path.read_bytes(), path.stat().st_ino) == before
    script = _read(PROVISIONER)
    rotation = script.split("# A verification rerun must never rotate", 1)[1]
    rotation = rotation[rotation.index('\nif [ "$DB_CREATED" = true ]; then'):].split("\nfi", 1)[0] + "\nfi\n"
    _stub(tmp_path, "runuser", 'touch "$TEST_ROOT/role-mutated"; exit 90\n')
    result = _run_helper(tmp_path, "DB_CREATED=false\n" + rotation)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "role-mutated").exists()


@pytest.mark.parametrize("replacement", ["edfinder_checkpoint_app:bad", "wrong_role:" + "a" * 48])
def test_existing_database_rejects_invalid_credential_identity(tmp_path, replacement):
    _api_env(tmp_path, f"DATABASE_URL=postgresql://{replacement}@172.22.0.1:5432/edfinder_checkpoint\n")
    result = _run_helper(tmp_path, "read_checkpoint_password")
    assert result.returncode != 0
    assert "DATABASE_URL identity or password is invalid" in result.stderr


@pytest.mark.parametrize("key", [
    "CORS_ORIGINS", "REDIS_URL", "ADMIN_OPERATION_STARTUP_REAP_ENABLED",
    "EDDN_SIMULATION_INGEST_ENABLED", "AUTH_COOKIE_SECURE", "FRONTIER_REDIRECT_URI",
])
@pytest.mark.parametrize("change", ["remove", "replace", "duplicate"])
def test_verification_rejects_noncredential_environment_drift(tmp_path, key, change):
    path = _api_env(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assignment = next(line for line in lines if line.startswith(key + "="))
    if change == "remove":
        lines.remove(assignment)
    elif change == "replace":
        lines[lines.index(assignment)] = key + "=unexpected"
    else:
        lines.append(assignment)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = path.read_bytes(), path.stat().st_ino
    result = _run_helper(tmp_path, "read_checkpoint_password")
    assert result.returncode != 0
    assert "checkpoint API environment" in result.stderr
    assert (path.read_bytes(), path.stat().st_ino) == before
    assert result.stdout == ""


@pytest.mark.parametrize("change", ["database_url_only", "extra", "malformed", "duplicate_database_url"])
def test_verification_requires_the_complete_managed_environment(tmp_path, change):
    path = _api_env(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if change == "database_url_only":
        lines = lines[:1]
    elif change == "extra":
        lines.append("UNMANAGED_SETTING=true")
    elif change == "malformed":
        lines.append("not-an-assignment")
    else:
        lines.append(lines[0])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = path.read_bytes(), path.stat().st_ino
    script = _read(PROVISIONER)
    selection = script.split('DB_PASSWORD="$(read_checkpoint_password)"', 1)[1].split("DB_CREATED=false", 1)[0]
    _stub(tmp_path, "openssl", 'touch "$TEST_ROOT/password-rotated"; exit 90\n')
    result = _run_helper(tmp_path, 'DB_PASSWORD="$(read_checkpoint_password)"' + selection)
    assert result.returncode != 0
    assert not (tmp_path / "password-rotated").exists()
    assert (path.read_bytes(), path.stat().st_ino) == before


def test_created_api_environment_passes_the_same_complete_rerun_validation(tmp_path):
    script = _read(PROVISIONER)
    start = script.index('if [ "$DB_CREATED" = true ]; then\n  atomic_checkpoint_file "$API_ENV"')
    end = script.index("\nfi", start) + len("\nfi")
    command = 'DB_CREATED=true\nDATABASE_URL="postgresql://edfinder_checkpoint_app:' + "a" * 48
    command += '@172.22.0.1:5432/edfinder_checkpoint"\n'
    command += script[start:end] + "\nread_checkpoint_password"
    result = _run_helper(tmp_path, command)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "a" * 48


def test_atomic_receipt_replacement_preserves_complete_document_and_metadata(tmp_path):
    receipt = tmp_path / "schema-identity.json"
    receipt.write_text('{"captured_at":"old"}\n', encoding="utf-8")
    receipt.chmod(0o600)
    old_inode = receipt.stat().st_ino
    result = _run_helper(
        tmp_path, 'atomic_checkpoint_file "$SCHEMA_RECEIPT" "$OP_UID" "$OP_GID"',
        data='{"captured_at":"new"}\n',
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(receipt.read_text(encoding="utf-8")) == {"captured_at": "new"}
    assert receipt.stat().st_ino != old_inode
    assert receipt.stat().st_uid == os.getuid()
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_failed_atomic_receipt_update_keeps_original_and_cleans_stage(tmp_path, failure):
    receipt = tmp_path / "schema-identity.json"
    receipt.write_text('{"captured_at":"trusted"}\n', encoding="utf-8")
    before = receipt.read_bytes(), receipt.stat().st_ino
    fault = tmp_path / "fault"
    fault.mkdir()
    (fault / "sitecustomize.py").write_text(
        "import os\ndef fail(*args, **kwargs):\n    raise OSError('injected write failure')\n"
        + f"os.{failure} = fail\n", encoding="utf-8",
    )
    result = _run_helper(
        tmp_path, 'atomic_checkpoint_file "$SCHEMA_RECEIPT" "$OP_UID" "$OP_GID"',
        data='{"captured_at":"new"}\n', extra_env={"PYTHONPATH": str(fault)},
    )
    assert result.returncode != 0
    assert (receipt.read_bytes(), receipt.stat().st_ino) == before
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("broad", ["host all all 0.0.0.0/0 trust\n", "host all all 172.22.0.0/16 reject\n", "include earlier.conf\n"])
def test_checkpoint_hba_rule_precedes_broad_rules_and_includes(tmp_path, broad):
    path = tmp_path / "pg_hba.conf"
    old = "host edfinder_checkpoint edfinder_checkpoint_app 172.22.0.0/16 scram-sha-256 # edfinder-v3-checkpoint\n"
    path.write_text(broad + old, encoding="utf-8")
    result = _run_helper(tmp_path, "checkpoint_hba_document")
    assert result.returncode == 0, result.stderr
    assert result.stdout == old + broad
    path.write_text(result.stdout, encoding="utf-8")
    rerun = _run_helper(tmp_path, "checkpoint_hba_document")
    assert rerun.stdout == result.stdout
    script = _read(PROVISIONER)
    assert "WHERE rule_number = 1 AND type = 'host'" in script
    assert "AND auth_method = 'scram-sha-256' AND error IS NULL" in script


@pytest.mark.parametrize("outcome", ["reject", "trust", "unavailable"])
def test_negative_authentication_probe_distinguishes_rejection_from_other_failures(tmp_path, outcome):
    bodies = {
        "reject": 'printf \'password authentication failed for user "%s"\\n\' "$PGUSER" >&2; exit 2\n',
        "trust": "exit 0\n",
        "unavailable": 'echo "connection refused" >&2; exit 2\n',
    }
    _stub(tmp_path, "psql", bodies[outcome])
    result = _run_helper(tmp_path, "verify_checkpoint_password_rejection")
    assert (result.returncode == 0) == (outcome == "reject"), result.stderr


def _nginx_dump(tmp_path, text):
    (tmp_path / "nginx-dump").write_text(text, encoding="utf-8")
    _stub(tmp_path, "nginx", 'cat "$TEST_ROOT/nginx-dump"\n')


def test_nginx_accepts_only_the_managed_fqdn_in_enabled_configuration(tmp_path):
    managed = tmp_path / "managed.conf"
    enabled = tmp_path / "enabled.conf"
    managed.touch()
    enabled.symlink_to(managed)
    fqdn = "vmi3542235.contaboserver.net"
    _nginx_dump(tmp_path, f"# configuration file {enabled}:\nserver {{\nserver_name\n\"{fqdn}\";\n}}\n")
    result = _run_helper(tmp_path, "verify_checkpoint_nginx_ownership required")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("declaration", [
    "server_name vmi3542235.contaboserver.net;",
    'server_name\n"VMI3542235.CONTABOSERVER.NET"\nother.invalid;',
    "server_name vmi3542235.contaboserver.net.;",
])
def test_nginx_rejects_competing_included_fqdn_declarations(tmp_path, declaration):
    _nginx_dump(tmp_path, f"# configuration file {tmp_path}/conf.d/other.conf:\nserver {{{declaration}}}\n")
    result = _run_helper(tmp_path, "verify_checkpoint_nginx_ownership")
    assert result.returncode != 0
    assert "competing nginx site" in result.stderr


def test_nginx_rejects_duplicate_name_warning_even_when_config_test_succeeds(tmp_path):
    fqdn = "vmi3542235.contaboserver.net"
    _nginx_dump(tmp_path, f'nginx: [warn] conflicting server name "{fqdn}" on 0.0.0.0:80, ignored\n# configuration file {tmp_path}/managed.conf:\nserver {{server_name {fqdn};}}\n')
    result = _run_helper(tmp_path, "verify_checkpoint_nginx_ownership required")
    assert result.returncode != 0
    assert "conflicting nginx ownership" in result.stderr


def test_nginx_ignores_comments_but_requires_managed_name_after_install(tmp_path):
    _nginx_dump(tmp_path, f"# configuration file {tmp_path}/other.conf:\n# server_name vmi3542235.contaboserver.net;\nserver {{server_name unrelated.invalid;}}\n")
    before = _run_helper(tmp_path, "verify_checkpoint_nginx_ownership")
    after = _run_helper(tmp_path, "verify_checkpoint_nginx_ownership required")
    assert before.returncode == 0, before.stderr
    assert after.returncode != 0
