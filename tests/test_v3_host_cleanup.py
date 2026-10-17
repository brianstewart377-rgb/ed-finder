"""Disposable filesystem and routing contracts for the fixed host cleanup action."""
from __future__ import annotations

import ast
import base64
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
import yaml


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-host-cleanup.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
EXPECTED_PATHS = (
    "/data/v3/source-artifacts/spansh/2026-08-24T205426Z",
    "/root/edfinder-v3-benchmark",
    "/root/.bun",
    "/root/.codex",
)


def _body():
    return ACTION.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


def _module():
    module = ModuleType("host_cleanup_test")
    exec(compile(_body(), str(ACTION), "exec"), module.__dict__)
    # Keep monkeypatching isolated from pytest's own filesystem operations.
    module.os = SimpleNamespace(**vars(os))
    module.os.path = SimpleNamespace(**vars(os.path))
    return module


def _workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _step(name):
    return next(step for step in _workflow()["jobs"]["execute"]["steps"] if step.get("name") == name)


@pytest.fixture
def sandbox(tmp_path):
    module = _module()
    target = tmp_path / "cleanup"
    target.mkdir()
    (target / "payload").write_bytes(b"unused leftovers" * 256)
    real_lstat = module.os.lstat

    def root_owned(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if str(path) == str(target):
            values = list(result)
            values[4] = 0
            return os.stat_result(values)
        return result

    module.os.lstat = root_owned
    return module, target


def _cleanup(module, target, *, protected_paths=(), spansh=False):
    return module.cleanup_path(str(target), protected_paths=protected_paths, spansh=spansh)


def _assert_refused(module, target, monkeypatch, **kwargs):
    removals = []
    monkeypatch.setattr(module, "remove_tree", lambda path: removals.append(path))
    result = _cleanup(module, target, **kwargs)
    assert result["outcome"] == "refused", result
    assert result["reason"]
    assert result["bytes_freed"] == 0
    assert result["filesystem_writes_performed"] is False
    assert not removals
    assert os.path.lexists(target)
    return result


def test_allowlist_is_exact_literal_tuple_and_is_not_loaded_from_external_inputs(monkeypatch):
    for name in ("ROOT", "ALLOWLIST", "CLEANUP_PATH", "CLEANUP_PATHS", "V3_HOST_CLEANUP_PATHS"):
        monkeypatch.setenv(name, "/etc")
    module = _module()
    assert module.ALLOWLIST == EXPECTED_PATHS
    tree = ast.parse(_body())
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "ALLOWLIST" for target in node.targets)]
    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value) == EXPECTED_PATHS
    source = ACTION.read_text()
    assert "-I -B" in source
    assert "--one-file-system" in source
    assert not any(token in source for token in ("argparse", "os.getenv", "os.environ.get(\"ROOT\"", "glob("))


def test_action_shell_syntax():
    result = subprocess.run(["bash", "-n", str(ACTION)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_absent_path_is_already_absent_without_deletion(sandbox, monkeypatch):
    module, target = sandbox
    absent = target / "never-created"
    monkeypatch.setattr(module, "remove_tree", lambda path: pytest.fail("absent path reached removal"))
    result = _cleanup(module, absent)
    assert result["outcome"] == "already_absent"
    assert result["bytes_before"] == 0
    assert result["bytes_freed"] == 0
    assert result["filesystem_writes_performed"] is False


def test_real_temp_directory_is_removed_and_absence_verified(sandbox):
    module, target = sandbox
    before = subprocess.run(["du", "-sx", "-B1", "--", str(target)], capture_output=True, text=True, check=True)
    expected_bytes = int(before.stdout.split()[0])
    result = _cleanup(module, target)
    assert result["outcome"] == "removed", result
    assert result["bytes_before"] == expected_bytes
    assert result["bytes_freed"] == expected_bytes
    assert result["filesystem_writes_performed"] is True
    assert not os.path.lexists(target)
    assert target.parent.is_dir()


def test_symlinked_target_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    real = target.with_name("real")
    target.rename(real)
    target.symlink_to(real, target_is_directory=True)
    _assert_refused(module, target, monkeypatch)
    assert (real / "payload").is_file()


def test_symlinked_parent_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    link = target.parent / "linked-parent"
    link.symlink_to(target.parent, target_is_directory=True)
    _assert_refused(module, link / target.name, monkeypatch)
    assert (target / "payload").is_file()


def test_mount_point_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    original = module.os.path.ismount
    monkeypatch.setattr(module.os.path, "ismount", lambda path: str(path) == str(target) or original(path))
    _assert_refused(module, target, monkeypatch)


def test_different_root_device_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    original = module.os.lstat

    def other_device(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if str(path) == str(target):
            values = list(result)
            values[2] = os.stat("/").st_dev + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(module.os, "lstat", other_device)
    _assert_refused(module, target, monkeypatch)


def test_pg_version_at_arbitrary_depth_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    pgdata = target / "old" / "postgres" / "18" / "data"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("18\n")
    _assert_refused(module, target, monkeypatch)
    assert (pgdata / "PG_VERSION").read_text() == "18\n"


@pytest.mark.parametrize("relation", ["self", "inside", "ancestor"])
def test_docker_volume_overlap_is_refused(sandbox, monkeypatch, relation):
    module, target = sandbox
    protected = {"self": target, "inside": target / "volume" / "_data", "ancestor": target.parent}[relation]
    _assert_refused(module, target, monkeypatch, protected_paths=(str(protected),))


def test_non_root_owner_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    original = module.os.lstat

    def non_root(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if str(path) == str(target):
            values = list(result)
            values[4] = 1234
            return os.stat_result(values)
        return result

    monkeypatch.setattr(module.os, "lstat", non_root)
    _assert_refused(module, target, monkeypatch)


def test_open_file_under_spansh_directory_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    original = module.os.scandir
    monkeypatch.setattr(module.os, "scandir", lambda path: nullcontext([
        SimpleNamespace(name=str(os.getpid()), path=f"/proc/{os.getpid()}")
    ]) if path == "/proc" else original(path))
    with (target / "payload").open("rb") as opened:
        assert opened.read(1)
        result = _assert_refused(module, target, monkeypatch, spansh=True)
        assert result["reason"] == "open_file_under_path"


def test_failed_post_delete_verification_is_refused(sandbox, monkeypatch):
    module, target = sandbox
    monkeypatch.setattr(module, "remove_tree", lambda path: False)
    result = _cleanup(module, target)
    assert result["outcome"] == "refused"
    assert result["bytes_freed"] == 0
    assert target.exists()


def test_cleanup_is_in_closed_workflow_choice_and_case_allowlists():
    workflow = _workflow()
    options = workflow["on"]["workflow_dispatch"]["inputs"]["operation"]["options"]
    assert options.count("v3-host-cleanup") == 1
    source = WORKFLOW.read_text()
    assert "v3-host-cleanup)" in source
    resolver = _step("Resolve request")["run"]
    assert '"$EVENT_NAME" = "workflow_dispatch"' in resolver
    assert '"$CURRENT_REF" = refs/heads/main' in resolver
    assert workflow["concurrency"] == {"group": "v3-production-application-authority", "cancel-in-progress": "false"}
    assert workflow["jobs"]["execute"]["concurrency"] == {"group": "chatgpt-ed-new-ops", "cancel-in-progress": "false"}
    assert workflow["permissions"] == {"contents": "read"}


def test_cleanup_only_uses_trusted_main_pinned_ssh_and_fixed_action():
    step = _step("Clean up fixed V3 host leftovers")
    assert "v3-host-cleanup" in step["if"]
    source = step["run"]
    assert "trusted-main/scripts/operator/actions/v3-host-cleanup.sh" in source
    assert "trusted-main/deploy/v3-production/target-authority.json" in source
    for option in ("BatchMode=yes", "IdentitiesOnly=yes", "StrictHostKeyChecking=yes", "UserKnownHostsFile=~/.ssh/known_hosts"):
        assert option in source
    assert "sudo -n" in source
    assert "nohup" not in source
    assert "ssh-keyscan" not in WORKFLOW.read_text()
    assert "${{" not in source


def test_cleanup_receipt_is_always_uploaded_and_noticed():
    artifact = _step("Upload V3 host clean-up receipt")
    assert artifact["if"].startswith("always() && ")
    assert artifact["with"] == {
        "name": "v3-host-cleanup-receipt",
        "path": "${{ runner.temp }}/v3-host-cleanup-receipt.json",
        "if-no-files-found": "error",
        "retention-days": "180",
    }
    notice = _step("Annotate V3 host clean-up receipt")
    assert notice["if"].startswith("always() && ")
    assert "::notice title=Host clean-up::" in notice["run"]


def _summary_notice():
    source = _step("Annotate V3 host clean-up receipt")["run"].split("<<'PYTHON'\n", 1)[1].rsplit("\nPYTHON", 1)[0]
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "summary_notice")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(WORKFLOW), "exec"), namespace)
    return namespace["summary_notice"]


def test_summary_notice_escapes_percent_carriage_return_and_line_feed():
    notice = _summary_notice()({
        "status": "stopped", "total_bytes_freed": 42,
        "paths": [{"path": "/root/.bun", "outcome": "refused", "reason": "100%\r\n::error::injected", "bytes_freed": 42}],
    })
    assert notice.startswith("::notice title=Host clean-up::")
    assert "100%25%0D%0A::error::injected" in notice
    assert "\n" not in notice and "\r" not in notice
    assert "/root/.bun: refused" in notice
    assert "bytes_freed=42" in notice and "total_bytes_freed=42" in notice
    assert len(notice) < 4000


def test_summary_notice_is_bounded_after_escape_expansion():
    notice = _summary_notice()({"paths": [{"reason": "%\r\n" * 4000}]})
    assert len(notice) < 4000
    assert "\n" not in notice and "\r" not in notice


@pytest.mark.parametrize(("event", "ref", "accepted"), [
    ("workflow_dispatch", "refs/heads/main", True),
    ("workflow_dispatch", "refs/heads/unreviewed", False),
    ("push", "refs/heads/chatgpt-ed-new-ops-requests", False),
])
def test_cleanup_resolver_only_admits_manual_main_dispatch(tmp_path, event, ref, accepted):
    binary = tmp_path / "bin"
    binary.mkdir()
    git = binary / "git"
    git.write_text("#!/bin/sh\nprintf '%s\\n' '.github/ed-new-ops-requests/cleanup.json'\n")
    git.chmod(0o755)
    (binary / "python").symlink_to(sys.executable)
    request = tmp_path / ".github/ed-new-ops-requests/cleanup.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({"operation": "v3-host-cleanup"}))
    output = tmp_path / "outputs"
    result = subprocess.run(["bash", "-c", _step("Resolve request")["run"]], cwd=tmp_path, capture_output=True, text=True, check=False, env={
        **os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
        "EVENT_NAME": event, "CURRENT_REF": ref, "INPUT_OPERATION": "v3-host-cleanup",
        "BEFORE_SHA": "a" * 40, "CURRENT_SHA": "b" * 40, "GITHUB_OUTPUT": str(output),
    })
    assert result.returncode == (0 if accepted else 64), result.stderr
    assert output.exists() == accepted
    if accepted:
        assert output.read_text() == "operation=v3-host-cleanup\n"


@pytest.mark.parametrize("unsafe_mount", ["self", "nested"])
def test_same_device_bind_mount_from_mountinfo_is_refused(sandbox, monkeypatch, unsafe_mount):
    module, target = sandbox
    mount = target if unsafe_mount == "self" else target / "nested"
    if unsafe_mount == "nested":
        mount.mkdir()
    monkeypatch.setattr(module, "mount_points", lambda: (str(mount),))
    monkeypatch.setattr(module.os.path, "ismount", lambda path: False)
    _assert_refused(module, target, monkeypatch)


def test_internal_symlink_is_not_followed_during_scan_or_removal(sandbox):
    module, target = sandbox
    outside = target.parent / "retained-postgres"
    outside.mkdir()
    (outside / "PG_VERSION").write_text("18")
    (target / "external").symlink_to(outside, target_is_directory=True)
    result = _cleanup(module, target)
    assert result["outcome"] == "removed", result
    assert (outside / "PG_VERSION").read_text() == "18"


def _prepare_receipt(module, monkeypatch):
    module.sys = SimpleNamespace(**vars(sys))
    module.sys.argv = ["-", "committed-authority"]
    monkeypatch.setattr(module, "verify_authority", lambda encoded: None)
    monkeypatch.setattr(module, "root_df", lambda: {"size_bytes": 100, "used_bytes": 50, "available_bytes": 50})
    monkeypatch.setattr(module, "protected_docker_paths", lambda: ())
    real_lstat = module.os.lstat
    monkeypatch.setattr(module.os, "lstat", lambda path, *args, **kwargs: real_lstat("/") if path in EXPECTED_PATHS else real_lstat(path, *args, **kwargs))


@pytest.mark.parametrize("extra_args", [["/etc"], ["--root", "/tmp"], ["--paths=/root"]])
def test_extra_path_arguments_stop_before_any_cleanup(monkeypatch, extra_args):
    module = _module()
    _prepare_receipt(module, monkeypatch)
    module.sys.argv += extra_args
    monkeypatch.setattr(module, "cleanup_path", lambda *args, **kwargs: pytest.fail("invalid args reached cleanup"))
    receipt = module.run_cleanup()
    assert receipt["status"] == "stopped"
    assert receipt["failures"]
    assert receipt["filesystem_writes_performed"] is False


def test_authority_failure_prevents_any_cleanup(monkeypatch):
    module = _module()
    _prepare_receipt(module, monkeypatch)

    def refuse(_encoded):
        raise RuntimeError("unexpected_host_identity_or_authority")

    monkeypatch.setattr(module, "verify_authority", refuse)
    monkeypatch.setattr(module, "cleanup_path", lambda *args, **kwargs: pytest.fail("unverified authority reached cleanup"))
    receipt = module.run_cleanup()
    assert receipt["status"] == "stopped"
    assert receipt["failures"] == ["unexpected_host_identity_or_authority"]
    assert [item["path"] for item in receipt["paths"]] == list(EXPECTED_PATHS)
    assert all(item["outcome"] == "refused" for item in receipt["paths"])


@pytest.mark.parametrize("refused_index", [None, 1])
def test_receipt_uses_only_fixed_paths_in_order_and_stops_on_any_refusal(monkeypatch, refused_index):
    module = _module()
    _prepare_receipt(module, monkeypatch)
    for name in ("ROOT", "ALLOWLIST", "CLEANUP_PATHS", "V3_HOST_CLEANUP_PATHS"):
        monkeypatch.setenv(name, "/etc")
    calls = []

    def cleanup(path, *, protected_paths, spansh):
        index = len(calls)
        calls.append((path, spansh))
        refused = index == refused_index
        return {"path": path, "outcome": "refused" if refused else "removed",
                "reason": "unsafe" if refused else None, "bytes_before": 10,
                "bytes_freed": 0 if refused else 10,
                "filesystem_writes_performed": not refused}

    monkeypatch.setattr(module, "cleanup_path", cleanup)
    receipt = module.run_cleanup()
    assert calls == [(path, index == 0) for index, path in enumerate(EXPECTED_PATHS)]
    assert receipt["status"] == ("success" if refused_index is None else "stopped")
    assert receipt["total_bytes_freed"] == (40 if refused_index is None else 30)
    assert receipt["filesystem_writes_performed"] is True
    assert receipt["db_writes_performed"] is False
    assert receipt["service_changes_performed"] is False
    assert receipt["root_df_before"] is not None and receipt["root_df_after"] is not None


def test_docker_discovery_failure_refuses_every_path_without_removal(monkeypatch):
    module = _module()
    _prepare_receipt(module, monkeypatch)

    def docker_failure():
        raise RuntimeError("docker_inventory_failed")

    monkeypatch.setattr(module, "protected_docker_paths", docker_failure)
    monkeypatch.setattr(module, "cleanup_path", lambda *args, **kwargs: pytest.fail("failed Docker inventory reached cleanup"))
    receipt = module.run_cleanup()
    assert receipt["status"] == "stopped"
    assert all(item["outcome"] == "refused" for item in receipt["paths"])
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["total_bytes_freed"] == 0


def test_absent_fixed_paths_do_not_require_docker_inventory(monkeypatch):
    module = _module()
    _prepare_receipt(module, monkeypatch)

    def absent(_path):
        raise FileNotFoundError

    monkeypatch.setattr(module.os, "lstat", absent)
    monkeypatch.setattr(module, "protected_docker_paths", lambda: pytest.fail("absent path queried Docker"))
    monkeypatch.setattr(module, "cleanup_path", lambda *args, **kwargs: pytest.fail("absent path reached cleanup"))
    receipt = module.run_cleanup()
    assert receipt["status"] == "success"
    assert all(item["outcome"] == "already_absent" for item in receipt["paths"])
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["total_bytes_freed"] == 0


def test_docker_inventory_is_local_and_includes_unused_volumes_and_stopped_container_mounts(monkeypatch):
    module = _module()
    commands = []

    def run(argv):
        commands.append(argv)
        assert argv[:3] == ["docker", "--host", "unix:///var/run/docker.sock"]
        command = argv[3:]
        if command[0] == "info":
            return json.dumps("/custom-docker-root")
        if command[:2] == ["volume", "ls"]:
            return "unused-volume"
        if command[:2] == ["volume", "inspect"]:
            return json.dumps("/unused-volume/_data")
        if command[0] == "ps":
            assert "-aq" in command
            return "stopped-container"
        if command[0] == "inspect":
            return json.dumps([{"Source": "/bind-mount-for-stopped-container"}])
        pytest.fail(f"unexpected command: {command}")

    monkeypatch.setattr(module, "run", run)
    assert set(module.protected_docker_paths()) == {
        "/var/lib/docker", "/custom-docker-root", "/unused-volume/_data", "/bind-mount-for-stopped-container",
    }
    assert len(commands) == 5


@pytest.mark.parametrize("contents", ["", "not a mount table\n", "1 0 8:1 / /somewhere rw - ext4 /dev/root rw\n"])
def test_incomplete_mount_table_fails_closed(monkeypatch, contents):
    module = _module()
    monkeypatch.setattr(module, "open", lambda *args, **kwargs: io.StringIO(contents), raising=False)
    with pytest.raises(RuntimeError, match="mount_.*unverified"):
        module.mount_points()


def test_mount_table_octal_escapes_cannot_hide_bind_mount(monkeypatch):
    module = _module()
    contents = "1 0 8:1 / / rw - ext4 /dev/root rw\n2 1 8:1 /other /root/leftover\\040directory rw - ext4 /dev/root rw\n"
    monkeypatch.setattr(module, "open", lambda *args, **kwargs: io.StringIO(contents), raising=False)
    assert module.mount_points() == ("/", "/root/leftover directory")


@pytest.mark.parametrize("failure", [None, "hostname", "fqdn", "authority", "root"])
def test_committed_authority_and_observed_host_identity_are_required(monkeypatch, failure):
    module = _module()
    authority = json.loads((ROOT / "deploy/v3-production/target-authority.json").read_text())
    if failure == "authority":
        authority["status"] = "stopped"
    encoded = base64.b64encode(json.dumps(authority).encode()).decode()

    def run(argv):
        assert argv in (["hostname", "-s"], ["hostname", "-f"])
        key = "hostname" if argv[-1] == "-s" else "fqdn"
        return "unreviewed-host" if failure == key else authority["target"][key]

    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(module.os, "geteuid", lambda: 1234 if failure == "root" else 0)
    if failure is None:
        module.verify_authority(encoded)
    else:
        with pytest.raises(RuntimeError, match="unexpected_host_identity_or_authority|root_required"):
            module.verify_authority(encoded)


@pytest.mark.parametrize("writes", [False, True])
def test_failed_removal_reports_actual_partial_writes_without_claiming_freed_bytes(sandbox, monkeypatch, writes):
    module, target = sandbox

    def remove(_path):
        raise module.RemovalError("rm_failed", writes)

    monkeypatch.setattr(module, "remove_tree", remove)
    result = _cleanup(module, target)
    assert result["outcome"] == "refused"
    assert result["filesystem_writes_performed"] is writes
    assert result["bytes_freed"] == 0
    assert target.exists()
