"""Security contracts for the permanent Contabo privilege interface."""
import hashlib
import importlib.machinery
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/operator/install_v3_checkpoint_host_interface.py"
LAUNCHER_SOURCE = ROOT / "scripts/operator/actions/edfinder-v3-checkpoint-launcher"
BOOTSTRAP_SOURCE = ROOT / "scripts/operator/v3_checkpoint_bootstrap.py"
FIXED_LAUNCHER = "/usr/local/sbin/edfinder-v3-checkpoint-launcher"


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    specification = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(specification)
    loader.exec_module(module)
    return module


def make_install_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    for relative in ("usr", "usr/local", "usr/local/sbin", "usr/local/libexec",
                     "etc", "etc/sudoers.d"):
        path = target / relative
        path.mkdir()
        path.chmod(0o755)
    (target / "etc/sudoers.d").chmod(0o750)
    (target / "etc/sudoers").write_text("Defaults env_reset\n")
    return target


def test_installer_writes_narrow_root_owned_interface_idempotently(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_test")
    target = make_install_root(tmp_path)
    owner = os.getuid()
    validations = []
    checks = []

    def validate(path):
        validations.append(path)
        assert path.exists()

    digest = module.install(ROOT, target, owner, validate, checks.append)
    launcher = target / module.LAUNCHER_TARGET
    bootstrap = target / module.BOOTSTRAP_TARGET
    sudoers = target / module.SUDOERS_TARGET
    identity = {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                for path in (launcher, bootstrap, sudoers)}

    assert digest == hashlib.sha256(BOOTSTRAP_SOURCE.read_bytes()).hexdigest()
    assert checks == [digest]
    assert launcher.read_bytes() == LAUNCHER_SOURCE.read_bytes()
    assert bootstrap.read_bytes() == BOOTSTRAP_SOURCE.read_bytes()
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755
    assert stat.S_IMODE(bootstrap.stat().st_mode) == 0o600
    assert stat.S_IMODE(sudoers.stat().st_mode) == 0o440
    assert all(path.stat().st_uid == owner and path.stat().st_gid == owner
               for path in (launcher, bootstrap, sudoers))

    policy = sudoers.read_text()
    assert policy == module.SUDOERS.decode("ascii")
    assert 'env_keep="GH_TOKEN"' in policy
    assert "NOPASSWD:NOSETENV: " + FIXED_LAUNCHER in policy
    assert "NOPASSWD: ALL" not in policy
    assert "codex ALL=" not in policy
    for forbidden in ("/usr/bin/python", "/bin/bash", "/usr/sbin/runuser", "docker"):
        assert forbidden not in policy

    # Global policy is checked before and after, and the staged rule is checked
    # before replacement. Identical reruns do not replace installed inodes.
    assert validations[0] == target / "etc/sudoers"
    assert validations[-1] == target / "etc/sudoers"
    module.install(ROOT, target, owner, validate, checks.append)
    assert identity == {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                        for path in (launcher, bootstrap, sudoers)}
    assert checks == [digest, digest]
    assert stat.S_IMODE((target / "etc/sudoers.d").stat().st_mode) == 0o750


def test_installer_rejects_symlink_target_without_following_it(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_symlink_test")
    target = make_install_root(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    destination = target / module.BOOTSTRAP_TARGET
    destination.parent.mkdir()
    destination.symlink_to(outside)
    with pytest.raises(RuntimeError, match="unsafe existing target"):
        module.install(ROOT, target, os.getuid(), lambda path: None, lambda digest: None)
    assert outside.read_text() == "unchanged"


def test_installer_rejects_unsafe_parent_and_never_changes_existing_directory_mode(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_parent_test")
    target = make_install_root(tmp_path)
    sudoers_directory = target / "etc/sudoers.d"
    sudoers_directory.chmod(0o777)
    with pytest.raises(RuntimeError, match="unsafe installation directory"):
        module.install(ROOT, target, os.getuid(), lambda path: None, lambda digest: None)
    assert stat.S_IMODE(sudoers_directory.stat().st_mode) == 0o777


def test_sudoers_rule_parses_with_visudo_when_available(tmp_path):
    visudo = Path("/usr/sbin/visudo")
    if not visudo.exists():
        pytest.skip("visudo is unavailable")
    module = load(INSTALLER, "checkpoint_installer_visudo_test")
    rule = tmp_path / "edfinder-v3-checkpoint"
    rule.write_bytes(module.SUDOERS)
    rule.chmod(0o440)
    subprocess.run([str(visudo), "-cf", str(rule)], check=True, capture_output=True, text=True)


def launcher_fixture(tmp_path, monkeypatch):
    module = load(LAUNCHER_SOURCE, "checkpoint_launcher_test")
    helper = tmp_path / "v3_checkpoint_bootstrap.py"
    helper.write_text("print('installed helper')\n")
    monkeypatch.setattr(module, "BOOTSTRAP", helper)
    monkeypatch.setattr(module, "validate_identity", lambda: None)
    monkeypatch.setattr(module.os, "environ", {
        "GH_TOKEN": "synthetic-token", "SUDO_USER": "codex",
        "SUDO_UID": "1234", "SUDO_GID": "1234", "PYTHONPATH": "/poison",
        "BASH_ENV": "/poison",
    })
    return module, hashlib.sha256(helper.read_bytes()).hexdigest()


def test_launcher_clears_environment_and_execs_only_installed_os_python(tmp_path, monkeypatch):
    module, digest = launcher_fixture(tmp_path, monkeypatch)
    receipt = "/tmp/v3-live-checkpoint-deployment-receipt-42-1.json"
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--bootstrap-sha", digest,
                                     "123", "b" * 64, "a" * 40, "deploy", receipt,
                                     "/runner/_work/_temp/generated.sh"])
    executed = []

    def execve(program, arguments, environment):
        executed.append((program, arguments, environment))
        raise RuntimeError("exec captured")

    monkeypatch.setattr(module.os, "execve", execve)
    with pytest.raises(RuntimeError, match="exec captured"):
        module.main()
    program, arguments, environment = executed[0]
    assert program == "/usr/bin/python3"
    assert arguments[:4] == ["/usr/bin/python3", "-I", "-S", str(module.BOOTSTRAP)]
    assert arguments[4:7] == ["--expected-bootstrap-sha", digest, "123"]
    assert environment == {
        "PATH": module.SAFE_PATH, "HOME": "/root", "LANG": "C", "LC_ALL": "C",
        "GH_TOKEN": "synthetic-token",
    }
    assert "PYTHONPATH" not in module.os.environ and "BASH_ENV" not in module.os.environ


def test_launcher_stale_helper_fails_closed_before_exec(tmp_path, monkeypatch, capsys):
    module, _ = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--check", "0" * 64])
    monkeypatch.setattr(module.os, "execve", lambda *args: pytest.fail("must not exec"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 78
    error = capsys.readouterr().err
    assert "installed bootstrap is stale" in error
    assert "reinstall required" in error


@pytest.mark.parametrize("operation,receipt", [
    ("provision", "/tmp/v3-live-checkpoint-deployment-receipt-42-1.json"),
    ("deploy", "/tmp/v3-live-checkpoint-authority-candidate-42-1.json"),
])
def test_launcher_pairs_operation_with_exact_receipt_path(
    tmp_path, monkeypatch, operation, receipt
):
    module, digest = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--bootstrap-sha", digest,
                                     "123", "b" * 64, "a" * 40, operation, receipt,
                                     "/runner/_work/_temp/generated.sh"])
    monkeypatch.setattr(module.os, "execve", lambda *args: pytest.fail("must not exec"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 78


def test_workflow_sudo_targets_only_the_fixed_launcher():
    for name, job_name in (("v3-live-checkpoint-control.yml", "provision"),
                           ("v3-application-live-checkpoint-preflight.yml", "apply-local")):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        shell = workflow["jobs"][job_name]["defaults"]["run"]["shell"]
        assert shell.startswith("/usr/bin/sudo -n --preserve-env=GH_TOKEN " + FIXED_LAUNCHER)
        for forbidden in ("sudo -n /usr/bin/python", "sudo -n /bin/bash",
                          "sudo -n /usr/sbin/runuser", "sudo -n docker"):
            assert forbidden not in shell


def test_current_runbooks_document_single_install_then_release_deploy_smoke():
    infrastructure = (ROOT / "docs/operations/v3-live-checkpoint-infrastructure.md").read_text()
    release = (ROOT / "docs/operations/v3-application-checkpoint-release.md").read_text()
    command = "sudo /usr/bin/python3 -I -S scripts/operator/install_v3_checkpoint_host_interface.py"
    assert command in infrastructure
    assert 'V3-CHECKPOINT {"operation":"provision"}' in infrastructure
    assert "repeatable staging path is issue #623 `release`" in infrastructure
    assert "`deploy` → the canonical workflow's automatic external public smoke" in infrastructure
    assert 'V3-CHECKPOINT {"operation":"release"' in release
    assert 'V3-CHECKPOINT {"operation":"deploy"' in release
    assert "automatic GitHub-hosted public smoke" in release
    assert "Routine deployment never invokes provisioning" in release
