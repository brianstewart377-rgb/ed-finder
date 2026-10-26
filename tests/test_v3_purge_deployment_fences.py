"""Admission-fence behavior at each production application mutation surface."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
KINDS = (
    "BATCH_STARTED", "REWRITE_STARTED", "SERVICES_QUIESCED",
    "WRITER_FENCE_ENABLED", "AUTOVACUUM_DISABLED", "FAILED_STOP",
    "HOST_LEASE_HELD", "LEDGER_ABSENT", "QUERY_FAILED",
    # Copy-and-drop (019): backups skipping, a staged/swapped relation, or an
    # absent copy ledger each refuse every mutator exactly like the 016 kinds.
    "COPY_BACKUP_SKIP", "COPY_RELATION_STAGED", "COPY_RELATION_SWAPPED", "COPY_LEDGER_ABSENT",
)


def load_deployer():
    spec = importlib.util.spec_from_file_location(
        "purge_deployment_test", ROOT / "scripts/operator/v3_production_deploy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("kind", KINDS)
def test_deployer_refuses_before_any_mutation_or_secret_access(monkeypatch, kind):
    deployer = load_deployer()
    reads = []
    monkeypatch.setattr(deployer, "exact_host_guard", lambda _: reads.append("host"))
    monkeypatch.setattr(deployer, "docker_context_guard", lambda *_: reads.append("context"))

    tool = deployer.purge_state_tool()
    monkeypatch.setattr(tool, "lease_state", lambda: "held" if kind == "HOST_LEASE_HELD" else "free")
    monkeypatch.setattr(deployer, "purge_state_tool", lambda: tool)
    guard = deployer.require_purge_clear

    def guarded(*args):
        reads.append("purge")
        return guard(*args)

    def query(command, **_kwargs):
        sql = command[-1]
        assert sql in (tool.PRESENCE_SQL, tool.STATE_SQL, tool.LEGACY_STATE_SQL)
        if kind == "QUERY_FAILED":
            raise subprocess.CalledProcessError(1, "fixed query")
        value = {"database": tool.DATABASE_NAME, "read_only": "on"}
        if sql == tool.PRESENCE_SQL:
            value["ledger_present"] = kind != "LEDGER_ABSENT"
            value["copy_ledger_present"] = kind not in ("LEDGER_ABSENT", "COPY_LEDGER_ABSENT")
        else:
            # The legacy (pre-019) state read is reached only when the copy
            # ledger is absent; every other path must use the copy-aware read.
            assert sql == (tool.LEGACY_STATE_SQL if kind == "COPY_LEDGER_ABSENT" else tool.STATE_SQL)
            value["unresolved"] = ([{"event_kind": kind, "event_sequence": 1,
                                     "purge_id": "49a0c00d-e722-4209-afd8-9d62b877e30a"}]
                                   if kind in tool.KINDS else [])
            value["copy_backup_skip"] = kind in ("COPY_BACKUP_SKIP", "COPY_RELATION_STAGED", "COPY_RELATION_SWAPPED")
            value["copy_relations"] = ([{"relation_code": "system_search", "phase": "CHUNK_COPIED",
                                         "copy_position": kind.removeprefix("COPY_RELATION_").lower()}]
                                       if kind.startswith("COPY_RELATION_") else [])
        return SimpleNamespace(stdout=json.dumps(value))

    failure = {"HOST_LEASE_HELD": "purge_host_lease_held", "LEDGER_ABSENT": "purge_ledger_absent",
               "QUERY_FAILED": "purge_state_query_failed", "COPY_LEDGER_ABSENT": "purge_copy_ledger_absent",
               "COPY_BACKUP_SKIP": "purge_copy_backup_skip"}.get(kind, "purge_unresolved_" + kind)
    expected_failures = [failure]
    if kind.startswith("COPY_RELATION_"):
        # The deployer joins the fence's failures into one receipt code.
        expected_failures = ["purge_copy_backup_skip,purge_copy_relation_" + kind.removeprefix("COPY_RELATION_").lower()]

    def forbidden(*_, **__):
        pytest.fail("admission failure reached secret access, a lock or mutation")

    monkeypatch.setattr(deployer, "require_purge_clear", guarded)
    for name in ("secure_path", "acquire_lock", "freeze_env", "persist_failure"):
        monkeypatch.setattr(deployer, name, forbidden)
    with pytest.raises(deployer.OperationFailed) as stopped:
        deployer.promote(
            SimpleNamespace(operation="promote"),
            {"external_authority": {"docker_context": "default"}},
            query,
        )
    receipt = stopped.value.receipt
    assert reads == ["host", "context", "purge"]
    assert receipt["status"] == "stopped"
    assert receipt["failures"] == expected_failures
    assert receipt["database_access_performed"] is True
    for field in ("filesystem_writes_performed", "database_writes_performed",
                  "image_pulls_performed", "service_changes_performed", "env_files_read"):
        assert receipt[field] is False


def test_deployer_shared_check_uses_only_pinned_readonly_connection(monkeypatch):
    deployer = load_deployer()
    commands = []
    sql = "BEGIN READ ONLY; SELECT 1; COMMIT;"

    def check(executor):
        assert executor(sql) == "fixed query result"
        return {"status": "clear"}

    monkeypatch.setattr(deployer, "purge_state_tool", lambda: SimpleNamespace(check=check))

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(stdout="fixed query result")

    assert deployer.require_purge_clear({"DOCKER_CONTEXT": "default"}, runner) == {"status": "clear"}
    command, kwargs = commands[0]
    assert command[:7] == ["docker", "exec", deployer.POSTGRES_CONTAINER, "psql", "-X", "--no-psqlrc", "--no-password"]
    assert command[command.index("--username") + 1] == "edfinder_v3"
    assert command[command.index("--dbname") + 1] == "edfinder_v3_phase4c_full_20260827_r5"
    assert command[-2:] == ["--command", sql]
    assert kwargs["env"] == {"DOCKER_CONTEXT": "default"}


@pytest.mark.parametrize("module_name", ("v3_production_deploy", "v3_production_migrate"))
@pytest.mark.parametrize("bytecode_disabled", (False, True))
@pytest.mark.parametrize("load_fails", (False, True))
def test_loading_admission_helper_does_not_write_bytecode(
    monkeypatch, tmp_path, module_name, bytecode_disabled, load_fails,
):
    spec = importlib.util.spec_from_file_location(
        "purge_loader_test", ROOT / f"scripts/operator/{module_name}.py"
    )
    assert spec and spec.loader
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    helper = tmp_path / "scripts/operator/lib/v3_purge_state.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("raise RuntimeError('helper failed')\n" if load_fails else "loaded = True\n")
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "dont_write_bytecode", bytecode_disabled)

    def load_helper():
        if module_name == "v3_production_deploy":
            return operator.purge_state_tool()
        return operator._load("v3_purge_state", helper)

    if load_fails:
        with pytest.raises(RuntimeError, match="helper failed"):
            load_helper()
    else:
        assert load_helper().loaded is True
    assert sys.dont_write_bytecode is bytecode_disabled
    assert sorted(path.name for path in helper.parent.iterdir()) == [helper.name]


def shell_stage(tmp_path, kind):
    stage = tmp_path / "stage"
    actions = stage / "scripts/operator/actions"
    lib = stage / "scripts/operator/lib"
    actions.mkdir(parents=True)
    lib.mkdir()
    failure = "purge_state_" + kind
    report = json.dumps({"status": "refused", "failures": [failure]})
    (lib / "v3-purge-state.sh").write_text(
        "v3_purge_state_check() { printf '%s\\n' " + shlex.quote(report) + "; return 78; }\n"
    )
    return stage, actions, lib, failure


@pytest.mark.parametrize("kind", KINDS)
def test_promote_launcher_refuses_before_deployer_execution(tmp_path, kind):
    stage, actions, _, failure = shell_stage(tmp_path, kind)
    shutil.copyfile(ROOT / "scripts/operator/actions/v3-production-promote.sh", actions / "promote.sh")
    marker = tmp_path / "deployer-executed"
    (stage / "scripts/operator/v3_production_deploy.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hostname = fake_bin / "hostname"
    hostname.write_text("#!/bin/sh\nif [ \"${1:-}\" = -f ]; then echo nb79a3d.mevnode.com; else echo ed-finder-prod; fi\n")
    hostname.chmod(0o700)
    # Exact interpreter remains real; only the local host identity is mocked.
    (fake_bin / "python3.14").symlink_to(sys.executable)
    completed = subprocess.run(
        ["bash", str(actions / "promote.sh"), "--operation", "promote"],
        env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
        text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 78, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["schema_version"] == "ed-finder/v3-production-deployment-receipt/v1"
    assert receipt["failures"] == [failure]
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["database_writes_performed"] is False
    assert receipt["service_changes_performed"] is False
    assert not marker.exists()


@pytest.mark.parametrize("kind", KINDS)
def test_publisher_refuses_with_normal_receipt_before_run_directory_or_lock(tmp_path, kind):
    stage, actions, lib, failure = shell_stage(tmp_path, kind)
    (lib / "f2d_operator_identity.sh").write_text(
        "require_f2d_operator_code_identity() { printf '%064d\\n' 0; }\n"
    )
    shutil.copyfile(ROOT / "scripts/operator/lib/f2d_evidence.py", lib / "f2d_evidence.py")
    script = (ROOT / "scripts/operator/actions/v3-publish-derived-products.sh").read_text()
    # Replace only the final dispatch and read-only target/stage validators.
    # The real run_operation, fence call and receipt implementation run intact.
    script = script[:script.rindex('\ncase "$ACTION" in')]
    mutation = tmp_path / "mutation-reached"
    state = tmp_path / "state"
    script += "\nrequire_target() { PYTHON_BIN=" + shlex.quote(sys.executable) + "; }\n"
    script += "require_stage() { :; }\n"
    script += "require_generation() { touch " + shlex.quote(str(mutation)) + "; }\n"
    script += "acquire_deployment_lock() { touch " + shlex.quote(str(mutation)) + "; }\n"
    script += "STATE_ROOT=" + shlex.quote(str(state)) + "\nrun_operation\n"
    action = actions / "publisher.sh"
    action.write_text(script)
    completed = subprocess.run(
        ["bash", str(action), "run", str(stage), "a" * 40, "test"],
        text=True, capture_output=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 79, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["schema_version"] == "ed-finder/operator-operation-result/v1"
    assert receipt["operation"] == "v3-publish-derived-products"
    assert receipt["status"] == "refused"
    assert receipt["failures"] == [failure]
    assert receipt["db_writes_performed"] is False
    assert receipt["publication_performed"] is False
    assert receipt["receipt"]["schema_version"] == "ed-finder/v3-publish-derived-products/v1"
    assert not state.exists()
    assert not mutation.exists()
    assert not (stage / "action-receipt.json").exists()


def test_deploy_bundle_contains_both_shared_fence_helpers():
    workflow = (ROOT / ".github/workflows/v3-production-application-deploy.yml").read_text()
    assert 'install -m 600 scripts/operator/lib/v3_purge_state.py scripts/operator/lib/v3-purge-state.sh "$BUNDLE/scripts/operator/lib/"' in workflow
