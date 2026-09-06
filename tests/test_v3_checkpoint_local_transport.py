"""Executable regressions for the sealed, worktree-independent host handoff."""
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import types
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/operator/v3_checkpoint_bootstrap.py"
ENTRY = "scripts/operator/actions/v3-live-checkpoint-local.sh"
SHA = "a" * 40


def load_module(path=SOURCE):
    spec = importlib.util.spec_from_file_location("checkpoint_bootstrap_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def envelope(extra=None, source=SHA, operation="provision"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        files = {ENTRY: b"echo verified-operation\n",
                 "operation.json": json.dumps({"source_sha": source, "operation": operation}).encode()}
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if extra is not None:
            archive.addfile(extra, io.BytesIO(b""))
    payload = output.getvalue()
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("operation.tar", payload)
    return zipped.getvalue(), hashlib.sha256(payload).hexdigest()


def test_sealed_bundle_unpacks_without_consulting_worktree(tmp_path):
    module = load_module()
    payload, digest = envelope()
    module.unpack_bundle(payload, digest, tmp_path)
    assert (tmp_path / ENTRY).read_text() == "echo verified-operation\n"
    assert (tmp_path / ENTRY).stat().st_mode & 0o222 == 0o200


def test_wrong_digest_stops_before_any_operation_file_is_written(tmp_path):
    module = load_module()
    payload, _ = envelope()
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.unpack_bundle(payload, "0" * 64, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["parent", "absolute", "symlink", "hardlink", "duplicate"])
def test_authenticated_bundle_still_rejects_unsafe_members(tmp_path, kind):
    module = load_module()
    member = tarfile.TarInfo({"parent": "../outside", "absolute": "/outside",
                              "duplicate": ENTRY}.get(kind, "unsafe"))
    if kind in ("symlink", "hardlink"):
        member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "/etc/passwd"
    payload, digest = envelope(member)
    with pytest.raises(ValueError):
        module.unpack_bundle(payload, digest, tmp_path)
    assert not (tmp_path.parent / "outside").exists()


@pytest.mark.parametrize("drift", ["none", "checksum", "source", "operation"])
def test_bootstrap_executes_only_verified_private_code_not_poisoned_checkout(tmp_path, monkeypatch, drift):
    module = load_module()
    worktree = tmp_path / "coding-worktree"
    (worktree / ENTRY).parent.mkdir(parents=True)
    (worktree / ENTRY).write_text("echo COMPROMISED\n")
    monkeypatch.chdir(worktree)
    payload, digest = envelope(source="b" * 40 if drift == "source" else SHA,
                               operation="deploy" if drift == "operation" else "provision")
    if drift == "checksum":
        digest = "0" * 64
    ignored_script = tmp_path / "mutable-runner-script"
    ignored_script.write_text("raise RuntimeError('MUTABLE SCRIPT EXECUTED')\n")
    monkeypatch.setattr(sys, "argv", [str(SOURCE), "123", digest, SHA, "provision",
                                     str(tmp_path / "receipt.json"), str(ignored_script)])
    monkeypatch.setattr(module.os, "environ", {"GH_TOKEN": "synthetic-token", "PYTHONPATH": str(worktree)})
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "uname", lambda: types.SimpleNamespace(nodename="vmi3542235", machine="x86_64"))
    monkeypatch.setattr(module.socket, "getfqdn", lambda: "vmi3542235.contaboserver.net")
    real_temp = tempfile.TemporaryDirectory
    monkeypatch.setattr(module.tempfile, "TemporaryDirectory",
                        lambda **kw: real_temp(prefix=kw["prefix"], dir=tmp_path))
    executed = []
    def run(command, **kwargs):
        assert module.os.environ == {}
        if command[0] == "/usr/bin/curl":
            assert "--location-trusted" not in command
            assert kwargs["input"] == b"Authorization: Bearer synthetic-token\n"
            assert "synthetic-token" not in " ".join(command)
            return subprocess.CompletedProcess(command, 0, stdout=payload)
        private = kwargs["cwd"]
        assert private != worktree and not private.is_relative_to(worktree)
        assert (private / ENTRY).read_text() == "echo verified-operation\n"
        assert private.stat().st_mode & 0o022 == 0
        assert kwargs["env"] == {"PATH": module.PATH, "HOME": "/root", "LANG": "C", "LC_ALL": "C"}
        executed.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(module.subprocess, "run", run)
    if drift == "none":
        assert module.main() == 0
        assert executed == [["/bin/bash", ENTRY]]
    else:
        with pytest.raises(ValueError):
            module.main()
        assert executed == []
    assert not list(tmp_path.glob("edfinder-v3-*"))


def test_privileged_jobs_have_no_worktree_or_toolcache_execution():
    import runpy
    checker = runpy.run_path(str(ROOT / "tests/test_v3_checkpoint_validator_runtime.py"))
    control = yaml.safe_load((ROOT / ".github/workflows/v3-live-checkpoint-control.yml").read_text())
    deploy = yaml.safe_load((ROOT / ".github/workflows/v3-application-live-checkpoint-preflight.yml").read_text())
    for file, name in checker["PREINSTALL_BOOTSTRAPS"]:
        path = ROOT / ".github/workflows" / file
        job = yaml.safe_load(path.read_text())["jobs"][name]
        assert checker["is_verified_checkpoint_preinstall_job"](path, name, job)
    for job in (control["jobs"]["prepare-provision"], deploy["jobs"]["deploy"]):
        assert job["runs-on"] == "ubuntu-24.04"
        checkout = next(step for step in job["steps"] if "checkout@" in step.get("uses", ""))
        assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}
    assert control["jobs"]["provision"]["concurrency"] == deploy["concurrency"]
    assert deploy["jobs"]["public-smoke"]["runs-on"] == "ubuntu-24.04"
    assert deploy["jobs"]["public-smoke"]["needs"] == ["deploy", "apply-local"]


def test_custom_shell_never_opens_actions_generated_file(tmp_path):
    import runpy
    helper = runpy.run_path(str(ROOT / "tests/test_v3_checkpoint_validator_runtime.py"))
    path = ROOT / ".github/workflows/v3-live-checkpoint-control.yml"
    step = yaml.safe_load(path.read_text())["jobs"]["provision"]["steps"][0]
    words = helper["shell_words"](step["shell"])
    malicious = tmp_path / "mutable.sh"
    marker = tmp_path / "executed"
    malicious.write_text(f"touch '{marker}'\n")
    # Invoke only the OS Python portion. The real bootstrap stops at host identity
    # on CI; changing or removing the generated script cannot change that outcome.
    args = [sys.executable, *words[4:-1], str(malicious)]
    first = subprocess.run(args, text=True, capture_output=True, check=False, timeout=10)
    malicious.unlink()
    second = subprocess.run(args, text=True, capture_output=True, check=False, timeout=10)
    assert first.returncode == second.returncode == 78
    assert first.stderr == second.stderr
    assert not marker.exists()
    assert "Checkpoint bootstrap stopped" in first.stderr


def test_bundle_builder_reads_committed_objects_and_seals_request(tmp_path, monkeypatch):
    path = ROOT / "scripts/operator/v3_checkpoint_bundle.py"
    module = load_module(path)
    payload, _ = envelope()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = tarfile.open(fileobj=io.BytesIO(archive.read("operation.tar")))
        data = members.extractfile(ENTRY).read()
    git_tar = io.BytesIO()
    with tarfile.open(fileobj=git_tar, mode="w") as archive:
        member = tarfile.TarInfo(ENTRY); member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    calls = []
    def archive(command):
        calls.append(command)
        return git_tar.getvalue()
    monkeypatch.setattr(module.subprocess, "check_output", archive)
    output = tmp_path / "operation.tar"
    gh_output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setattr(sys, "argv", [str(path), "provision", "--source", SHA, "--output", str(output)])
    module.main()
    assert calls[0][:3] == ["git", "archive", SHA]
    with tarfile.open(output) as archive:
        assert json.load(archive.extractfile("operation.json")) == {"operation": "provision", "source_sha": SHA}
    assert gh_output.read_text() == "bundle_sha256=" + hashlib.sha256(output.read_bytes()).hexdigest() + "\n"


@pytest.mark.parametrize("login, apply, logout, expected", [
    (0, 0, 0, 0), (1, 0, 0, 1), (0, 78, 0, 78), (0, 0, 1, 78),
])
def test_nonroot_deploy_cleanup_survives_login_apply_and_logout_failure(
    tmp_path, login, apply, logout, expected
):
    import os
    (tmp_path / "operation.json").write_text(json.dumps({
        "operation": "deploy", "mode": "bootstrap", "release_run_id": "42",
    }))
    script = r'''
id() { if [ "$#" = 1 ]; then echo 0; else echo 1234; fi; }
stat() { if [ "$2" = %u ]; then echo 0; else echo 755; fi; }
hostname() { echo vmi3542235; }
uname() { echo x86_64; }
systemctl() {
  for suffix in '' '-2' '-3'; do
    echo "actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker${suffix}.service"
  done
}
python3.14() {
  case "$*" in
    *sys.version_info*) return 0;;
    *) /usr/bin/python3 "$@";;
  esac
}
runuser() {
  printf '%s\n' "$*" >> "$TEST_ROOT/runuser-calls"
  case " $* " in
    *' docker login '*) cat >/dev/null; return "$TEST_LOGIN";;
    *' docker logout '*) return "$TEST_LOGOUT";;
    *) printf '{"status":"accepted"}\n'; return "$TEST_APPLY";;
  esac
}
source "$TEST_DISPATCHER"
'''
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path, env={
        **os.environ, "TEST_ROOT": str(tmp_path), "TEST_LOGIN": str(login),
        "TEST_LOGOUT": str(logout), "TEST_APPLY": str(apply),
        "TEST_DISPATCHER": str(ROOT / ENTRY), "GHCR_TOKEN": "synthetic-secret",
    }, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == expected, result.stderr
    calls = (tmp_path / "runuser-calls").read_text().splitlines()
    assert "docker login ghcr.io" in calls[0]
    assert "docker logout ghcr.io" in calls[-1]
    assert all("-u codex -- env -i" in call for call in calls)
    if login:
        assert len(calls) == 2
    else:
        assert "--mode bootstrap --candidate-run-id 42" in calls[1]
    assert "synthetic-secret" not in "\n".join(calls) + result.stdout + result.stderr
