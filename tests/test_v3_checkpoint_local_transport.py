"""Executable regressions for the sealed, worktree-independent host handoff."""
import hashlib
import importlib.machinery
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
LAUNCHER_SOURCE = ROOT / "scripts/operator/actions/edfinder-v3-checkpoint-launcher"
ENTRY = "scripts/operator/actions/v3-live-checkpoint-local.sh"
SHA = "a" * 40
BOOTSTRAP_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LAUNCHER_SHA = hashlib.sha256(LAUNCHER_SOURCE.read_bytes()).hexdigest()
RUN_ID = 456
REPOSITORY_ID = 987


def provenance(operation="provision"):
    artifact_name, workflow_path, event = {
        "provision": (
            "checkpoint-provision-operation",
            ".github/workflows/v3-live-checkpoint-control.yml",
            "issue_comment",
        ),
        "deploy": (
            "checkpoint-deploy-operation",
            ".github/workflows/v3-application-live-checkpoint-preflight.yml",
            "workflow_dispatch",
        ),
    }[operation]
    artifact = {
        "id": 123,
        "name": artifact_name,
        "expired": False,
        "workflow_run": {
            "id": RUN_ID,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_branch": "main",
            "head_sha": SHA,
        },
    }
    repository = {"id": REPOSITORY_ID, "full_name": "brianstewart377-rgb/ed-finder"}
    run = {
        "id": RUN_ID,
        "repository": repository.copy(),
        "head_repository": repository.copy(),
        "path": workflow_path,
        "event": event,
        "head_branch": "main",
        "head_sha": SHA,
        "status": "in_progress",
        "conclusion": None,
    }
    return artifact, run


def load_module(path=SOURCE):
    spec = importlib.util.spec_from_file_location("checkpoint_bootstrap_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_launcher_module(module, tmp_path):
    installed = tmp_path / "installed-launcher"
    installed.write_bytes(LAUNCHER_SOURCE.read_bytes())
    module.LAUNCHER = installed


def envelope(extra=None, source=SHA, operation="provision", bootstrap_sha=BOOTSTRAP_SHA,
             launcher_sha=LAUNCHER_SHA):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        files = {ENTRY: b"echo verified-operation\n",
                 "operation.json": json.dumps({
                     "source_sha": source, "operation": operation,
                     "bootstrap_sha256": bootstrap_sha,
                     "launcher_sha256": launcher_sha,
                 }).encode()}
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


def test_stale_installed_bootstrap_stops_before_artifact_download(monkeypatch, tmp_path):
    module = load_module()
    install_launcher_module(module, tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SOURCE), "--expected-bootstrap-sha", "0" * 64,
                                     "--expected-launcher-sha", LAUNCHER_SHA,
                                     "123", "b" * 64, SHA, "provision",
                                     str(tmp_path / "receipt.json"), "/ignored.sh"])
    monkeypatch.setattr(module.os, "environ", {"GH_TOKEN": "synthetic-token"})
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("stale helper must stop before download"))
    with pytest.raises(ValueError, match="bootstrap digest mismatch"):
        module.main()


def test_launcher_check_argv_is_accepted_by_bootstrap_self_test(
    tmp_path, monkeypatch, capsys
):
    launcher_source = ROOT / "scripts/operator/actions/edfinder-v3-checkpoint-launcher"
    loader = importlib.machinery.SourceFileLoader(
        "checkpoint_launcher_protocol_test", str(launcher_source)
    )
    spec = importlib.util.spec_from_loader("checkpoint_launcher_protocol_test", loader)
    launcher = importlib.util.module_from_spec(spec)
    loader.exec_module(launcher)

    installed_launcher = tmp_path / "installed-launcher"
    installed_launcher.write_bytes(launcher_source.read_bytes())
    installed_bootstrap = tmp_path / "installed-bootstrap.py"
    installed_bootstrap.write_bytes(SOURCE.read_bytes())

    monkeypatch.setattr(launcher, "LAUNCHER", installed_launcher)
    monkeypatch.setattr(launcher, "BOOTSTRAP", installed_bootstrap)
    monkeypatch.setattr(launcher, "validate_identity", lambda: None)
    monkeypatch.setattr(launcher.os, "environ", {
        "GH_TOKEN": "synthetic-token", "SUDO_USER": "codex",
        "SUDO_UID": "1", "SUDO_GID": "1",
    })

    emitted = []

    def execve(program, arguments, environment):
        emitted.append((program, arguments, environment))
        raise RuntimeError("captured launcher exec")

    monkeypatch.setattr(launcher.os, "execve", execve)
    expected_bootstrap = hashlib.sha256(installed_bootstrap.read_bytes()).hexdigest()
    expected_launcher = hashlib.sha256(installed_launcher.read_bytes()).hexdigest()
    monkeypatch.setattr(sys, "argv", [
        str(launcher_source), "--check",
        "--bootstrap-sha", expected_bootstrap,
        "--launcher-sha", expected_launcher,
    ])
    with pytest.raises(RuntimeError, match="captured launcher exec"):
        launcher.main()

    program, arguments, _ = emitted[0]
    assert program == "/usr/bin/python3"
    assert arguments[:4] == ["/usr/bin/python3", "-I", "-S", str(installed_bootstrap)]
    bootstrap_argv = arguments[4:]

    bootstrap = load_module()
    monkeypatch.setattr(bootstrap, "LAUNCHER", installed_launcher)
    monkeypatch.setattr(sys, "argv", [str(SOURCE), *bootstrap_argv])
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap.os, "uname", lambda: types.SimpleNamespace(
        nodename="vmi3542235", machine="x86_64",
    ))
    monkeypatch.setattr(bootstrap.socket, "getfqdn", lambda: "vmi3542235.contaboserver.net")

    assert bootstrap.main() == 0
    output = capsys.readouterr().out
    assert expected_bootstrap in output
    assert expected_launcher in output
    assert "bootstrap_sha256=" in output
    assert "launcher_sha256=" in output


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


@pytest.mark.parametrize("drift", ["none", "checksum", "source", "operation", "bootstrap", "launcher"])
def test_bootstrap_executes_only_verified_private_code_not_poisoned_checkout(tmp_path, monkeypatch, drift):
    module = load_module()
    install_launcher_module(module, tmp_path)
    worktree = tmp_path / "coding-worktree"
    (worktree / ENTRY).parent.mkdir(parents=True)
    (worktree / ENTRY).write_text("echo COMPROMISED\n")
    monkeypatch.chdir(worktree)
    payload, digest = envelope(source="b" * 40 if drift == "source" else SHA,
                               operation="deploy" if drift == "operation" else "provision",
                               bootstrap_sha="0" * 64 if drift == "bootstrap" else BOOTSTRAP_SHA,
                               launcher_sha="0" * 64 if drift == "launcher" else LAUNCHER_SHA)
    if drift == "checksum":
        digest = "0" * 64
    ignored_script = tmp_path / "mutable-runner-script"
    ignored_script.write_text("raise RuntimeError('MUTABLE SCRIPT EXECUTED')\n")
    monkeypatch.setattr(sys, "argv", [str(SOURCE), "--expected-bootstrap-sha", BOOTSTRAP_SHA,
                                     "--expected-launcher-sha", LAUNCHER_SHA,
                                     "123", digest, SHA, "provision",
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
            assert b"Authorization: Bearer synthetic-token\n" in kwargs["input"]
            assert "synthetic-token" not in " ".join(command)
            if command[-1].endswith("/actions/artifacts/123"):
                metadata, _ = provenance()
                response = json.dumps(metadata).encode()
            elif command[-1].endswith(f"/actions/runs/{RUN_ID}"):
                _, metadata = provenance()
                response = json.dumps(metadata).encode()
            else:
                assert command[-1].endswith("/actions/artifacts/123/zip")
                response = payload
            return subprocess.CompletedProcess(command, 0, stdout=response)
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


@pytest.mark.parametrize("operation", ["provision", "deploy"])
def test_operation_artifact_accepts_only_its_canonical_active_main_workflow(operation):
    module = load_module()
    artifact, run = provenance(operation)
    assert module.verify_artifact_provenance(
        artifact, run, "123", SHA, operation,
    ) == str(RUN_ID)


@pytest.mark.parametrize("drift", [
    "artifact-id", "artifact-name", "expired", "association", "association-repository",
    "association-branch", "association-sha", "run-id", "repository", "head-repository",
    "workflow", "event", "branch", "sha", "completed",
])
def test_untrusted_operation_artifact_provenance_stops_before_download(
    tmp_path, monkeypatch, drift
):
    module = load_module()
    install_launcher_module(module, tmp_path)
    artifact, run = provenance()
    if drift == "artifact-id":
        artifact["id"] = 124
    elif drift == "artifact-name":
        artifact["name"] = "attacker-operation"
    elif drift == "expired":
        artifact["expired"] = True
    elif drift == "association":
        artifact["workflow_run"] = None
    elif drift == "association-repository":
        artifact["workflow_run"]["head_repository_id"] = 654
    elif drift == "association-branch":
        artifact["workflow_run"]["head_branch"] = "codex/attacker"
    elif drift == "association-sha":
        artifact["workflow_run"]["head_sha"] = "b" * 40
    elif drift == "run-id":
        run["id"] = RUN_ID + 1
    elif drift == "repository":
        run["repository"]["full_name"] = "attacker/ed-finder"
    elif drift == "head-repository":
        run["head_repository"]["id"] = 654
    elif drift == "workflow":
        run["path"] = ".github/workflows/attacker.yml"
    elif drift == "event":
        run["event"] = "pull_request"
    elif drift == "branch":
        run["head_branch"] = "codex/attacker"
    elif drift == "sha":
        run["head_sha"] = "b" * 40
    else:
        run.update(status="completed", conclusion="success")

    monkeypatch.setattr(sys, "argv", [str(SOURCE), "--expected-bootstrap-sha", BOOTSTRAP_SHA,
                                     "--expected-launcher-sha", LAUNCHER_SHA,
                                     "123", "b" * 64, SHA, "provision",
                                     str(tmp_path / "receipt.json"), "/ignored.sh"])
    monkeypatch.setattr(module.os, "environ", {"GH_TOKEN": "synthetic-token"})
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "uname", lambda: types.SimpleNamespace(
        nodename="vmi3542235", machine="x86_64",
    ))
    monkeypatch.setattr(module.socket, "getfqdn", lambda: "vmi3542235.contaboserver.net")
    calls = []

    def fetch(command, **_kwargs):
        calls.append(command[-1])
        if command[-1].endswith("/actions/artifacts/123"):
            response = artifact
        elif command[-1].endswith(f"/actions/runs/{RUN_ID}"):
            response = run
        else:
            pytest.fail("untrusted provenance must stop before artifact download")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response).encode())

    monkeypatch.setattr(module.subprocess, "run", fetch)
    with pytest.raises(ValueError, match="provenance"):
        module.main()
    assert all(not call.endswith("/zip") for call in calls)


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
    job = yaml.safe_load(path.read_text())["jobs"]["provision"]
    words = helper["shell_words"](job["defaults"]["run"]["shell"])
    malicious = tmp_path / "mutable.sh"
    marker = tmp_path / "executed"
    malicious.write_text(f"touch '{marker}'\n")
    launcher = ROOT / "scripts/operator/actions/edfinder-v3-checkpoint-launcher"
    # Directly exercise the reviewed launcher source. It stops on CI host identity;
    # changing or removing the ignored generated script cannot affect that result.
    args = [sys.executable, str(launcher), *words[4:-1], str(malicious)]
    first = subprocess.run(args, text=True, capture_output=True, check=False, timeout=10)
    malicious.unlink()
    second = subprocess.run(args, text=True, capture_output=True, check=False, timeout=10)
    assert first.returncode == second.returncode == 78
    assert first.stderr == second.stderr
    assert not marker.exists()
    assert "checkpoint launcher stopped" in first.stderr


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
        if command[:2] == ["git", "show"]:
            if command[2].endswith("v3_checkpoint_bootstrap.py"):
                return SOURCE.read_bytes()
            return LAUNCHER_SOURCE.read_bytes()
        return git_tar.getvalue()
    monkeypatch.setattr(module.subprocess, "check_output", archive)
    output = tmp_path / "operation.tar"
    gh_output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setattr(sys, "argv", [str(path), "provision", "--source", SHA, "--output", str(output)])
    module.main()
    assert calls[0] == ["git", "show", f"{SHA}:scripts/operator/v3_checkpoint_bootstrap.py"]
    assert calls[1] == ["git", "show", f"{SHA}:scripts/operator/actions/edfinder-v3-checkpoint-launcher"]
    assert calls[2][:3] == ["git", "archive", SHA]
    with tarfile.open(output) as archive:
        assert json.load(archive.extractfile("operation.json")) == {
            "bootstrap_sha256": BOOTSTRAP_SHA, "launcher_sha256": LAUNCHER_SHA,
            "operation": "provision", "source_sha": SHA,
        }
    assert gh_output.read_text() == (
        "bundle_sha256=" + hashlib.sha256(output.read_bytes()).hexdigest() + "\n"
        "bootstrap_sha256=" + BOOTSTRAP_SHA + "\n"
        "launcher_sha256=" + LAUNCHER_SHA + "\n"
    )


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
