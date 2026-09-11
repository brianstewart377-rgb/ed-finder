"""Guards for the reviewed V3 production schema migration operation.

The operation must never guess: the live ledger has to be an exact prefix of the
committed lineage, each migration must own its transaction, and the ledger row is
recorded only after the migration commits. These tests drive that logic with
fakes so no production host is required.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "scripts/operator/v3_production_migrate.py"


def _load():
    spec = importlib.util.spec_from_file_location("v3_production_migrate", MIGRATE)
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
        "004_v3_search_spatial_clusters.sql",
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
        "004_v3_search_spatial_clusters.sql",
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


def test_ledger_row_is_recorded_only_after_the_migration_commits():
    module = _load()
    entry = module.desired_entries(ROOT)[0]
    calls: list[dict] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return SimpleNamespace(stdout="", returncode=0)

    module.apply_migration(_fake_deployer(module), entry, {}, runner, ROOT)

    assert len(calls) == 2
    assert calls[0]["input_text"] == (ROOT / entry["path"]).read_text(encoding="utf-8")
    assert "INSERT INTO v3_meta.schema_migration" in calls[1]["argv"][-1]
    assert entry["ledger_name"] in calls[1]["argv"][-1]
    assert entry["sha256"] in calls[1]["argv"][-1]


def test_a_failed_migration_never_records_a_ledger_row():
    module = _load()
    entry = module.desired_entries(ROOT)[0]
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(argv)
        raise RuntimeError("psql failed")

    with pytest.raises(RuntimeError):
        module.apply_migration(_fake_deployer(module), entry, {}, runner, ROOT)

    assert len(calls) == 1
    assert not any("INSERT INTO" in " ".join(argv) for argv in calls)


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


def test_operation_uses_the_v3_ledger_and_never_the_v2_applier():
    source = MIGRATE.read_text(encoding="utf-8")

    assert "INSERT INTO v3_meta.schema_migration" in source
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
