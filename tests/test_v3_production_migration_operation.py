"""Guards for the reviewed V3 production schema migration operation.

The operation must never guess: the live ledger has to be an exact prefix of the
committed lineage, each migration must own its transaction, and the ledger row
must commit atomically with the migration. These tests drive that logic with
fakes so no production host is required.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "scripts/operator/v3_production_migrate.py"
DEPLOYER = ROOT / "scripts/operator/v3_production_deploy.py"
IDENTITY = ROOT / "scripts/operator/v3_schema_identity.py"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
WORKFLOW = ROOT / ".github/workflows/v3-production-schema-migration.yml"
ACTION = ROOT / "scripts/operator/actions/v3-production-migrate.sh"
PLAN_VERIFIER = ROOT / "scripts/operator/v3_production_migration_plan.py"


def _load():
    spec = importlib.util.spec_from_file_location("v3_production_migrate", MIGRATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_deployer(module, *, sha256=None, secure_path=None):
    return SimpleNamespace(
        POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres",
        DATABASE_USER="edfinder_v3",
        DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5",
        LEDGER_SQL="SELECT 1",
        MAX_JSON=2 * 1024 * 1024,
        secure_path=secure_path or (lambda *_args, **_kwargs: None),
        sha256_file=sha256
        or (lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()),
    )


def test_desired_entries_are_the_committed_lineage_with_verified_hashes():
    module = _load()

    entries = module.desired_entries(ROOT)

    assert [entry["ledger_name"] for entry in entries] == [
         "001_v3_baseline.sql",
         "002_v3_accounts_identity.sql",
         "r1_v3/001_structural_shell.sql",
         "003_ratings_v4_derived.sql",
         "004_v3_search_spatial_clusters.sql",
         "005_v3_journal_intelligence.sql",
         "006_v3_derived_product_lifecycle.sql",
        "008_v3_journal_commander_ownership.sql",
        "009_v3_journal_galaxy_contributions.sql",
    ]
    for entry in entries:
        source = (ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == entry["sha256"]


def test_plan_reports_pending_only_when_the_live_ledger_is_an_exact_prefix():
    module = _load()
    desired = module.desired_entries(ROOT)

    applied, pending = module.plan_migrations(desired, desired[:2])
    assert [entry["ledger_name"] for entry in applied] == [
        "001_v3_baseline.sql",
        "002_v3_accounts_identity.sql",
    ]
    assert [entry["ledger_name"] for entry in pending] == [
        "r1_v3/001_structural_shell.sql",
        "003_ratings_v4_derived.sql",
        "004_v3_search_spatial_clusters.sql",
        "005_v3_journal_intelligence.sql",
        "006_v3_derived_product_lifecycle.sql",
        "008_v3_journal_commander_ownership.sql",
        "009_v3_journal_galaxy_contributions.sql",
    ]

    # Nothing pending is a legitimate state, not an error.
    applied, pending = module.plan_migrations(desired, desired)
    assert len(applied) == len(desired) and pending == []


def test_plan_refuses_a_live_ledger_that_is_ahead_or_divergent():
    module = _load()
    desired = module.desired_entries(ROOT)

    with pytest.raises(module.MigrationError, match="ahead"):
        module.plan_migrations(desired, [*desired, {"ledger_name": "999_x.sql", "sha256": "a" * 64}])

    divergent_name = [
        {"ledger_name": "001_something_else.sql", "sha256": desired[0]["sha256"]}
    ]
    with pytest.raises(module.MigrationError, match="diverges at position 1"):
        module.plan_migrations(desired, divergent_name)

    divergent_hash = [{"ledger_name": desired[0]["ledger_name"], "sha256": "b" * 64}]
    with pytest.raises(module.MigrationError, match="hash mismatch"):
        module.plan_migrations(desired, divergent_hash)


def test_live_ledger_pins_the_local_database_server_and_socket():
    module = _load()
    deployer = _fake_deployer(module)
    observed = {
        "database_name": deployer.DATABASE_NAME,
        "server_address": "local",
        "server_port": 5432,
        "transaction_read_only": "on",
        "migrations": [],
    }
    calls: list[list[str]] = []

    def runner(argv, **_kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=json.dumps(observed))

    assert module.live_ledger(deployer, {}, runner) == []
    assert "--host" in calls[0] and module.POSTGRES_SOCKET in calls[0]
    assert calls[0][calls[0].index("--port") + 1] == "5432"

    for field, value in (
        ("database_name", "elsewhere"),
        ("server_address", "10.0.0.9"),
        ("server_port", 6432),
    ):
        changed = {**observed, field: value}
        with pytest.raises(module.MigrationError, match="unexpected database server"):
            module.live_ledger(
                deployer, {}, lambda *_args, **_kwargs: SimpleNamespace(
                    stdout=json.dumps(changed)
                ),
            )


def test_a_migration_about_to_be_applied_must_own_its_transaction():
    module = _load()

    module.require_self_transactional("BEGIN;\nSELECT 1;\nCOMMIT;\n", "test.sql")
    module.require_self_transactional("-- lead\nBEGIN;\nSELECT 1;\nCOMMIT;", "test.sql")

    for bad in ("SELECT 1;\n", "BEGIN;\nSELECT 1;\n", "SELECT 1;\nCOMMIT;\n", ""):
        with pytest.raises(module.MigrationError, match="does not manage its own transaction"):
            module.require_self_transactional(bad, "test.sql")

    # The next migration in line satisfies the rule; 002 predates it and is
    # already applied, so it is never re-applied.
    derived = (ROOT / "sql/v3/migrations/003_ratings_v4_derived.sql").read_text(encoding="utf-8")
    module.require_self_transactional(derived, "003_ratings_v4_derived.sql")


def test_ledger_row_and_migration_commit_atomically():
    module = _load()
    entry = module.desired_entries(ROOT)[0]
    calls: list[dict] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return SimpleNamespace(stdout="", returncode=0)

    module.apply_migration(_fake_deployer(module), entry, {}, runner, ROOT)

    assert len(calls) == 1
    combined = calls[0]["input_text"]
    assert "BEGIN;\n" in combined and combined.rstrip().endswith("COMMIT;")
    assert combined.count("COMMIT;") == 1
    assert "INSERT INTO v3_meta.schema_migration" in combined
    assert module.POSTGRES_SOCKET in calls[0]["argv"]
    assert combined.index("INSERT INTO v3_meta.schema_migration") < combined.rindex("COMMIT;")
    assert entry["ledger_name"] in combined and entry["sha256"] in combined


def test_ledger_row_splices_before_the_actual_terminal_commit():
    module = _load()
    entry = module.desired_entries(ROOT)[0]
    source = "BEGIN;\nSELECT 1;\n  COMMIT;\n-- retained trailing comment\n"

    combined = module.migration_with_atomic_ledger(entry, source)

    assert combined.count("COMMIT;") == 1
    assert combined.index("INSERT INTO v3_meta.schema_migration") < combined.index(
        "COMMIT;"
    )
    assert combined.endswith("\n-- retained trailing comment\n")


def test_a_failed_combined_transaction_has_no_second_ledger_write():
    module = _load()
    entry = module.desired_entries(ROOT)[0]
    calls: list[dict] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        raise RuntimeError("psql failed")

    with pytest.raises(RuntimeError):
        module.apply_migration(_fake_deployer(module), entry, {}, runner, ROOT)

    assert len(calls) == 1
    assert "INSERT INTO v3_meta.schema_migration" in calls[0]["input_text"]
    assert calls[0]["input_text"].rstrip().endswith("COMMIT;")


def test_pinned_schema_identity_must_match_the_host_file(tmp_path):
    module = _load()
    identity = tmp_path / "schema-identity.json"
    identity.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(identity.read_bytes()).hexdigest()
    external = {
        "schema_identity_file": str(identity),
        "schema_identity_owner_uid": 0,
        "schema_identity_mode": "0600",
        "schema_identity_sha256": digest,
    }
    seen: list[tuple] = []

    def secure_path(path, uid, mode, *, directory):
        seen.append((path, uid, mode, directory))

    deployer = _fake_deployer(module, secure_path=secure_path)
    assert module.verify_schema_identity(deployer, external) == digest
    assert seen == [(identity, 0, "0600", False)]

    external["schema_identity_sha256"] = "f" * 64
    with pytest.raises(module.MigrationError, match="does not match the host file"):
        module.verify_schema_identity(deployer, external)


def _write_identity(path: Path, identity, entries) -> dict:
    document = identity.build(ROOT)
    document["migration_set_entries"] = entries
    document["migration_set_identity"] = identity.migration_set_identity(entries)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return document


def test_transition_binds_live_prefix_target_identity_and_every_rollback_prefix(tmp_path):
    module = _load()
    deployer = _load_path(DEPLOYER, "transition_deployer")
    identity = _load_path(IDENTITY, "transition_identity")
    desired = module.desired_entries(ROOT)
    current_path = tmp_path / "installed-schema.json"
    target_path = tmp_path / "target-schema.json"
    current = _write_identity(current_path, identity, desired[:7])
    target = _write_identity(target_path, identity, desired)
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    authority["external_authority"] = {
        **authority["external_authority"],
        "schema_identity_file": str(current_path),
        "schema_identity_owner_uid": os.geteuid(),
        "schema_identity_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
    }
    authority["schema_transition"] = {
        **authority["schema_transition"],
        "from_schema_identity_sha256": hashlib.sha256(current_path.read_bytes()).hexdigest(),
        "from_migration_set_identity": current["migration_set_identity"],
        "to_migration_set_identity": target["migration_set_identity"],
    }
    authority["accepted_release_schema_compatibility"]["compatible_migration_sets"] = sorted(
        module.prefix_identities(identity, desired)[6:]
    )

    observed, before, install_pending = module.inspect_schema_transition(
        deployer, authority, authority["external_authority"], desired, target_path,
        desired[:7],
    )
    assert observed == target
    assert before == authority["schema_transition"]["from_schema_identity_sha256"]
    assert install_pending is True

    authority["accepted_release_schema_compatibility"]["compatible_migration_sets"].remove(
        identity.migration_set_identity(desired[:8])
    )
    with pytest.raises(module.MigrationError, match="omits a transition prefix"):
        module.inspect_schema_transition(
            deployer, authority, authority["external_authority"], desired, target_path,
            desired[:7],
        )


def test_target_schema_identity_is_installed_atomically_after_migrations(tmp_path):
    module = _load()
    deployer = _load_path(DEPLOYER, "install_deployer")
    current = tmp_path / "schema-identity.json"
    candidate = tmp_path / "candidate.json"
    current.write_text('{"old":true}\n', encoding="utf-8")
    candidate.write_text('{"new":true}\n', encoding="utf-8")
    current.chmod(0o600)
    candidate.chmod(0o600)

    module.install_schema_identity(
        deployer, candidate, current, owner_uid=os.geteuid(), mode="0600"
    )

    assert current.read_bytes() == candidate.read_bytes()
    assert stat.S_IMODE(current.stat().st_mode) == 0o600


def test_governed_migration_workflow_is_manual_protected_and_source_bounded():
    import yaml

    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["operation"]["options"] == ["plan", "apply"]
    assert inputs["plan_run_id"]["required"] == "false"
    job = workflow["jobs"]["production-migration"]
    assert job["environment"] == "v3-production"
    assert workflow["concurrency"]["group"] == "v3-production-application-authority"
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "git fetch --no-tags origin refs/heads/main" in source
    assert "Canonical main moved while production approval was pending" in source
    assert source.count("git fetch --no-tags origin refs/heads/main") == 2
    assert "Canonical main moved immediately before production apply" in source
    assert source.rindex("git fetch --no-tags origin refs/heads/main") < source.index(
        'tar -C "$BUNDLE" -cf - . | ssh'
    )
    assert "ed-finder-prod/nb79a3d.mevnode.com" in source
    assert "V3_PRODUCTION_SSH_KNOWN_HOSTS" in source
    assert "--candidate-schema-identity" in source
    assert "--source-sha '$SOURCE_SHA'" in source
    assert "--workflow-run-id '$WORKFLOW_RUN_ID'" in source
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in source
    assert "v3_production_migration_plan.py" in source
    assert "apply requires a plan run ID" in source
    assert "gh api" not in source
    assert "tar --no-same-permissions --no-same-owner --no-overwrite-dir" in source
    assert "trap cancel HUP INT TERM" in source
    assert "kill -TERM" in source and 'wait \\"\\$child\\"' in source
    assert "v3-production-schema-migration" in source
    for forbidden in ("docker stop", "docker compose", "registry-token", "apply_migrations.sh"):
        assert forbidden not in source


def test_migration_launcher_requires_exact_cpython314_only_for_apply():
    source = ACTION.read_text(encoding="utf-8")
    assert 'if [ "$operation" = apply ]' in source
    assert "python314_required_for_production_migration" in source
    assert "compatible_readonly_python" in source
    assert "v3_production_migrate.py" in source


def test_migration_launcher_runtime_stop_uses_the_full_receipt_contract():
    source_sha = "a" * 40
    result = subprocess.run(
        [
            "bash", str(ACTION), "--operation", "invalid",
            "--source-sha", source_sha, "--workflow-run-id", "123",
        ],
        check=False, capture_output=True, text=True,
    )

    assert result.returncode == 78
    receipt = json.loads(result.stdout)
    assert receipt["schema_version"] == "ed-finder/v3-production-migration-receipt/v1"
    assert receipt["source_sha"] == source_sha
    assert receipt["workflow_run_id"] == "123"
    assert receipt["target"] == {
        "production": True, "hostname": "ed-finder-prod",
        "fqdn": "nb79a3d.mevnode.com",
    }
    assert receipt["database_access_performed"] is False
    assert receipt["database_writes_performed"] is False


def test_receipt_is_written_root_only_with_a_sidecar(tmp_path):
    module = _load()
    authority = {"target": {"hostname": "ed-finder-prod", "fqdn": "nb79a3d.mevnode.com"}}
    desired = module.desired_entries(ROOT)
    payload = module.receipt_payload(
        authority, status="applied", desired=desired, applied=desired[:2],
        pending=desired[2:], applied_now=desired[2:], identity_sha256="a" * 64,
        failures=[], writes=True,
    )

    assert payload["schema_version"] == "ed-finder/v3-production-migration-receipt/v1"
    assert payload["operation"] == "production-migration"
    assert payload["migrations_performed"] is True
    assert payload["service_changes_performed"] is False
    assert payload["desired_ledger_sha256"].startswith("sha256:")

    path = module.write_receipt(tmp_path, "migration-test.json", payload)
    body = path.read_bytes()
    assert json.loads(body)["status"] == "applied"
    sidecar = tmp_path / "migration-test.json.sha256"
    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(body).hexdigest()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".v3-production-migration-*"))


def test_post_mutation_audit_finalization_ignores_later_cancellation():
    module = _load()
    events: list[str] = []
    deployer = SimpleNamespace(
        cancellation_blocked=lambda: nullcontext(),
    )
    controller = SimpleNamespace(
        mark_commit_started=lambda: events.append("marked"),
    )

    module.begin_audit_finalization(deployer, controller)

    assert events == ["marked"]


def test_failed_identity_install_rechecks_the_secured_host_state(tmp_path):
    module = _load()
    installed = tmp_path / "schema-identity.json"
    installed.write_text('{"target":true}\n', encoding="utf-8")
    before = "a" * 64
    target = hashlib.sha256(installed.read_bytes()).hexdigest()
    external = {
        "schema_identity_file": str(installed),
        "schema_identity_owner_uid": os.geteuid(),
        "schema_identity_mode": "0600",
    }
    secured: list[Path] = []
    deployer = _fake_deployer(
        module,
        secure_path=lambda path, *_args, **_kwargs: secured.append(path),
    )

    observed, updated, failures = module.reconcile_schema_identity_after_failure(
        deployer, external, identity_before=before, identity_target=target,
    )
    assert observed == target
    assert updated is True
    assert failures == []
    assert secured == [installed]

    installed.unlink()
    observed, updated, failures = module.reconcile_schema_identity_after_failure(
        deployer, external, identity_before=before, identity_target=target,
    )
    assert observed is None
    assert updated is None
    assert failures == ["post_failure_schema_identity_unverified:FileNotFoundError"]


def test_interrupted_unknown_write_state_is_never_reported_as_false():
    module = _load()
    payload = module.receipt_payload(
        {}, status="stopped", desired=[], applied=[], pending=[], applied_now=[],
        identity_sha256=None, failures=["operation_cancelled:SIGTERM"], writes=None,
        source_sha="a" * 40, workflow_run_id="123", database_access=True,
    )

    assert payload["schema_version"] == module.MIGRATION_RECEIPT_SCHEMA
    assert payload["target"] == {
        "production": True, "hostname": "ed-finder-prod",
        "fqdn": "nb79a3d.mevnode.com",
    }
    assert payload["database_writes_performed"] is None
    assert payload["migrations_performed"] is None


def test_apply_plan_verifier_binds_github_run_receipt_and_exact_lineage():
    migration = _load()
    verifier = _load_path(PLAN_VERIFIER, "migration_plan_verifier")
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    desired = migration.desired_entries(ROOT)
    run_id = "123456789"
    source_sha = "a" * 40
    receipt = migration.receipt_payload(
        authority, status="planned", desired=desired, applied=desired[:7],
        pending=desired[7:], applied_now=[],
        identity_sha256=authority["external_authority"]["schema_identity_sha256"],
        failures=[], writes=False, source_sha=source_sha, workflow_run_id=run_id,
        database_access=True,
        identity_before_sha256=authority["schema_transition"]["from_schema_identity_sha256"],
        identity_after_sha256=authority["schema_transition"]["from_schema_identity_sha256"],
        identity_updated=False, prior_release_compatibility_verified=True,
    )
    run = {
        "id": int(run_id), "path": verifier.WORKFLOW_PATH,
        "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
        "head_branch": "main", "head_sha": source_sha,
        "head_repository": {"full_name": verifier.CANONICAL_REPOSITORY},
    }

    verifier.validate_run(run, run_id=run_id, source_sha=source_sha)
    verifier.validate_receipt(
        receipt, authority, desired, run_id=run_id, source_sha=source_sha
    )

    with pytest.raises(verifier.PlanError, match="canonical_workflow"):
        verifier.validate_run(
            {**run, "path": ".github/workflows/other.yml"},
            run_id=run_id, source_sha=source_sha,
        )
    with pytest.raises(verifier.PlanError, match="exact committed lineage"):
        verifier.validate_receipt(
            {**receipt, "pending": receipt["pending"][:-1]}, authority, desired,
            run_id=run_id, source_sha=source_sha,
        )


def test_operation_uses_the_v3_ledger_and_never_the_v2_applier():
    source = MIGRATE.read_text(encoding="utf-8")

    assert "INSERT INTO v3_meta.schema_migration" in source
    assert "with deployer.controlled_cancellation() as cancellation_controller:" in source
    assert "begin_audit_finalization(deployer, cancellation_controller)" in source
    # It borrows the deployer's read-only probe instead of redefining its own.
    assert "deployer.LEDGER_SQL" in source
    for forbidden in (
        "apply_migrations.sh",
        "sql/migration-manifest.txt",
        "schema_migrations",
        "FROM v3_meta.schema_migration",
    ):
        assert forbidden not in source
    # Schema changes must not arrive through the service-changing deployer.
    assert "'docker', 'stop'" not in source and '"docker", "stop"' not in source
