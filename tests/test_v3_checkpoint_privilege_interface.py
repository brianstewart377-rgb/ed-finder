"""Security contracts for the permanent Contabo privilege interface."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
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
LAUNCHER_SHA = hashlib.sha256(LAUNCHER_SOURCE.read_bytes()).hexdigest()


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

    def validate(path):
        validations.append(path)
        assert path.exists()

    self_test_calls = []
    bootstrap_sha, launcher_sha = module.install(
        ROOT, target, owner, validate,
        lambda *args: self_test_calls.append(args),
    )
    launcher = target / module.LAUNCHER_TARGET
    bootstrap = target / module.BOOTSTRAP_TARGET
    sudoers = target / module.SUDOERS_TARGET
    identity = {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                for path in (launcher, bootstrap, sudoers)}

    assert bootstrap_sha == hashlib.sha256(BOOTSTRAP_SOURCE.read_bytes()).hexdigest()
    assert launcher_sha == LAUNCHER_SHA
    assert self_test_calls == [(bootstrap_sha, launcher_sha)]
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
    module.install(ROOT, target, owner, validate,
                   lambda *args: self_test_calls.append(args))
    assert identity == {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                        for path in (launcher, bootstrap, sudoers)}
    assert self_test_calls == [(bootstrap_sha, launcher_sha),
                               (bootstrap_sha, launcher_sha)]
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
        module.install(ROOT, target, os.getuid(), lambda path: None, lambda *args: None)
    assert outside.read_text() == "unchanged"


def test_installer_rejects_unsafe_parent_and_never_changes_existing_directory_mode(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_parent_test")
    target = make_install_root(tmp_path)
    sudoers_directory = target / "etc/sudoers.d"
    sudoers_directory.chmod(0o777)
    with pytest.raises(RuntimeError, match="unsafe installation directory"):
        module.install(ROOT, target, os.getuid(), lambda path: None, lambda *args: None)
    assert stat.S_IMODE(sudoers_directory.stat().st_mode) == 0o777


@pytest.mark.parametrize("failure_point", ["self_test", "final_verify"])
def test_installer_failure_restores_all_prior_interface_files_and_metadata(
    tmp_path, failure_point
):
    module = load(INSTALLER, f"checkpoint_installer_rollback_{failure_point}")
    target = make_install_root(tmp_path)
    owner = os.getuid()
    paths = (
        target / module.BOOTSTRAP_TARGET,
        target / module.LAUNCHER_TARGET,
        target / module.SUDOERS_TARGET,
    )
    modes = (0o640, 0o711, 0o400)
    for index, (path, mode) in enumerate(zip(paths, modes, strict=True)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"prior-{index}".encode("ascii"))
        path.chmod(mode)
        os.chown(path, owner, owner)
    before = {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
               path.stat().st_uid, path.stat().st_gid)
        for path in paths
    }

    def self_test(*_args):
        if failure_point == "self_test":
            raise RuntimeError("synthetic self-test failure")

    def final_verify():
        if failure_point == "final_verify":
            raise RuntimeError("synthetic final verification failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        module.install(
            ROOT, target, owner, lambda _path: None, self_test,
            final_verify=final_verify,
        )

    after = {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
               path.stat().st_uid, path.stat().st_gid)
        for path in paths
    }
    assert after == before


def test_installer_failure_removes_all_new_interface_files(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_new_install_rollback")
    target = make_install_root(tmp_path)
    paths = (
        target / module.BOOTSTRAP_TARGET,
        target / module.LAUNCHER_TARGET,
        target / module.SUDOERS_TARGET,
    )
    with pytest.raises(RuntimeError, match="synthetic self-test failure"):
        module.install(
            ROOT, target, os.getuid(), lambda _path: None,
            lambda *args: (_ for _ in ()).throw(
                RuntimeError("synthetic self-test failure")
            ),
        )
    assert all(not path.exists() for path in paths)


def test_installer_keeps_sudo_rule_absent_while_helpers_can_be_mixed(
    tmp_path, monkeypatch
):
    module = load(INSTALLER, "checkpoint_installer_transaction_helpers")
    target = make_install_root(tmp_path)
    owner = os.getuid()
    sudoers_target = target / module.SUDOERS_TARGET
    launcher_target = target / module.LAUNCHER_TARGET
    original_atomic = module.atomic_install
    failed = False
    helper_events = []

    def atomic(path, content, mode, owner_uid, validator=None, owner_gid=None):
        nonlocal failed
        helper_events.append((path, sudoers_target.exists()))
        if path == launcher_target and not failed:
            failed = True
            raise RuntimeError("synthetic helper replacement failure")
        return original_atomic(path, content, mode, owner_uid, validator, owner_gid)

    monkeypatch.setattr(module, "atomic_install", atomic)
    with pytest.raises(RuntimeError, match="synthetic helper replacement failure"):
        module.install(ROOT, target, owner, lambda path: None, lambda *args: None)
    assert helper_events
    assert all(not active for _, active in helper_events)
    assert not sudoers_target.exists()


def test_installer_rollback_restores_sudo_rule_last(tmp_path, monkeypatch):
    module = load(INSTALLER, "checkpoint_installer_transaction_rollback")
    target = make_install_root(tmp_path)
    owner = os.getuid()
    paths = (
        target / module.BOOTSTRAP_TARGET,
        target / module.LAUNCHER_TARGET,
        target / module.SUDOERS_TARGET,
    )
    modes = (0o640, 0o711, 0o400)
    for path, mode in zip(paths, modes, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"prior-{path.name}".encode())
        path.chmod(mode)
        os.chown(path, owner, owner)

    original_atomic = module.atomic_install
    original_restore = module.restore_state
    failed = False
    restore_order = []

    def atomic(path, content, mode, owner_uid, validator=None, owner_gid=None):
        nonlocal failed
        if path == target / module.LAUNCHER_TARGET and not failed:
            failed = True
            raise RuntimeError("synthetic helper replacement failure")
        return original_atomic(path, content, mode, owner_uid, validator, owner_gid)

    def restore(path, previous):
        restore_order.append(path)
        return original_restore(path, previous)

    monkeypatch.setattr(module, "atomic_install", atomic)
    monkeypatch.setattr(module, "restore_state", restore)
    with pytest.raises(RuntimeError, match="synthetic helper replacement failure"):
        module.install(ROOT, target, owner, lambda path: None, lambda *args: None)
    assert restore_order[-1] == target / module.SUDOERS_TARGET
    assert set(restore_order[:-1]) == {
        target / module.BOOTSTRAP_TARGET,
        target / module.LAUNCHER_TARGET,
    }


def test_installer_accepts_only_root_controlled_exact_main_digest_source(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_source_authentication")
    stage = tmp_path / "stage"
    source = stage / "source"
    stage.mkdir(mode=0o700)
    source.mkdir(mode=0o700)
    for relative in (
        module.INSTALLER_SOURCE,
        module.LAUNCHER_SOURCE,
        module.BOOTSTRAP_SOURCE,
        module.MANIFEST_SOURCE,
    ):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
        destination.chmod(0o600)

    reviewed_sha = "a" * 40
    module.require_authenticated_source(
        source, reviewed_sha, resolve_main=lambda: reviewed_sha,
        owner_uid=os.getuid(), staging_parent=tmp_path,
        installer_path=source / module.INSTALLER_SOURCE,
    )

    (source / module.LAUNCHER_SOURCE).write_bytes(b"locally replaced launcher")
    with pytest.raises(RuntimeError, match="reviewed source digest mismatch"):
        module.require_authenticated_source(
            source, reviewed_sha, resolve_main=lambda: reviewed_sha,
            owner_uid=os.getuid(), staging_parent=tmp_path,
            installer_path=source / module.INSTALLER_SOURCE,
        )


def test_installer_rejects_source_that_is_not_current_trusted_main(tmp_path):
    module = load(INSTALLER, "checkpoint_installer_stale_source")
    source = tmp_path / "stage/source"
    source.mkdir(parents=True)
    source.parent.chmod(0o700)
    source.chmod(0o700)
    with pytest.raises(RuntimeError, match="exact current trusted-main head"):
        module.require_authenticated_source(
            source, "a" * 40, resolve_main=lambda: "b" * 40,
            owner_uid=os.getuid(), staging_parent=tmp_path,
            installer_path=source / module.INSTALLER_SOURCE,
        )


def test_resolver_uses_fixed_hardened_curl_endpoint(monkeypatch):
    module = load(INSTALLER, "checkpoint_installer_resolver_curl_test")
    endpoint = "https://api.github.com/repos/brianstewart377-rgb/ed-finder/commits/main"
    payload = json.dumps({"sha": "a" * 40}).encode("ascii")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv[0] == "/usr/bin/curl"
        assert argv[-1] == endpoint
        assert "--disable" in argv
        assert "--noproxy" in argv and "*" in argv
        assert "--proto" in argv and "=https" in argv
        assert "--proto-redir" in argv and "=https" in argv
        assert "--tlsv1.2" in argv
        assert "--fail" in argv
        assert "--silent" in argv
        assert "--show-error" in argv
        assert "--max-time" in argv and "20" in argv
        assert kwargs["env"] == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
        return subprocess.CompletedProcess(argv, 0, stdout=payload)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.resolve_trusted_main_sha() == "a" * 40
    assert len(calls) == 1


def test_resolver_rejects_invalid_json(monkeypatch):
    module = load(INSTALLER, "checkpoint_installer_resolver_json_test")

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=b"not-json")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        module.resolve_trusted_main_sha()


def test_resolver_rejects_invalid_sha(monkeypatch):
    module = load(INSTALLER, "checkpoint_installer_resolver_sha_test")
    payload = json.dumps({"sha": "B" * 40}).encode("ascii")

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=payload)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="invalid commit SHA"):
        module.resolve_trusted_main_sha()


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
    launcher = tmp_path / "installed-launcher"
    launcher.write_text("print('installed launcher')\n")
    monkeypatch.setattr(module, "BOOTSTRAP", helper)
    monkeypatch.setattr(module, "LAUNCHER", launcher)
    monkeypatch.setattr(module, "validate_identity", lambda: None)
    monkeypatch.setattr(module.os, "environ", {
        "GH_TOKEN": "synthetic-token", "SUDO_USER": "codex",
        "SUDO_UID": "1234", "SUDO_GID": "1234", "PYTHONPATH": "/poison",
        "BASH_ENV": "/poison",
    })
    return (module, hashlib.sha256(helper.read_bytes()).hexdigest(),
            hashlib.sha256(launcher.read_bytes()).hexdigest())


def test_launcher_missing_codex_account_fails_closed_without_traceback(monkeypatch, capsys):
    module = load(LAUNCHER_SOURCE, "checkpoint_launcher_missing_account_test")
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)

    def missing_account(_name):
        raise KeyError("getpwnam(): name not found: 'codex'")

    monkeypatch.setattr(module.pwd, "getpwnam", missing_account)

    with pytest.raises(SystemExit) as stopped:
        module.validate_identity()

    assert stopped.value.code == 78
    error = capsys.readouterr().err
    assert error == "checkpoint launcher stopped: codex account required\n"
    assert "Traceback" not in error


def test_launcher_clears_environment_and_execs_only_installed_os_python(tmp_path, monkeypatch):
    module, bootstrap_sha, launcher_sha = launcher_fixture(tmp_path, monkeypatch)
    receipt = "/tmp/v3-live-checkpoint-deployment-receipt-42-1.json"
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--bootstrap-sha", bootstrap_sha,
                                     "--launcher-sha", launcher_sha,
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
    assert arguments[4:9] == ["--expected-bootstrap-sha", bootstrap_sha,
                              "--expected-launcher-sha", launcher_sha, "123"]
    assert environment == {
        "PATH": module.SAFE_PATH, "HOME": "/root", "LANG": "C", "LC_ALL": "C",
        "GH_TOKEN": "synthetic-token",
    }
    assert "PYTHONPATH" not in module.os.environ and "BASH_ENV" not in module.os.environ


def test_launcher_stale_helper_fails_closed_before_exec(tmp_path, monkeypatch, capsys):
    module, _, launcher_sha = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--check",
                                     "--bootstrap-sha", "0" * 64,
                                     "--launcher-sha", launcher_sha])
    monkeypatch.setattr(module.os, "execve", lambda *args: pytest.fail("must not exec"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 78
    error = capsys.readouterr().err
    assert "installed bootstrap is stale" in error
    assert "reinstall required" in error


def test_launcher_stale_installed_launcher_fails_closed_before_exec(
    tmp_path, monkeypatch, capsys
):
    module, bootstrap_sha, _ = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--check",
                                     "--bootstrap-sha", bootstrap_sha,
                                     "--launcher-sha", "0" * 64])
    monkeypatch.setattr(module.os, "execve", lambda *args: pytest.fail("must not exec"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 78
    error = capsys.readouterr().err
    assert "installed launcher is stale" in error
    assert "reinstall required" in error


def test_launcher_rejects_legacy_bootstrap_only_protocol(
    tmp_path, monkeypatch, capsys
):
    module, bootstrap_sha, _ = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--bootstrap-sha", bootstrap_sha,
                                     "123", "b" * 64, "a" * 40, "provision",
                                     "/tmp/receipt.json", "/ignored.sh"])
    monkeypatch.setattr(module.os, "execve", lambda *args: pytest.fail("must not exec"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 78
    assert "invalid arguments" in capsys.readouterr().err


@pytest.mark.parametrize("operation,receipt", [
    ("provision", "/tmp/v3-live-checkpoint-deployment-receipt-42-1.json"),
    ("deploy", "/tmp/v3-live-checkpoint-authority-candidate-42-1.json"),
])
def test_launcher_pairs_operation_with_exact_receipt_path(
    tmp_path, monkeypatch, operation, receipt
):
    module, bootstrap_sha, launcher_sha = launcher_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [FIXED_LAUNCHER, "--bootstrap-sha", bootstrap_sha,
                                     "--launcher-sha", launcher_sha,
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
    assert "/usr/bin/sudo /bin/bash -ceu" in infrastructure
    assert "mktemp -d /run/edfinder-v3-checkpoint-install.XXXXXXXX" in infrastructure
    assert '--disable --noproxy "*" --proto "=https" --proto-redir "=https"' in infrastructure
    assert "api.github.com/repos/brianstewart377-rgb/ed-finder/commits/main" in infrastructure
    assert "raw.githubusercontent.com/brianstewart377-rgb/ed-finder/$sha/$path" in infrastructure
    assert "sha256sum --check scripts/operator/v3_checkpoint_host_interface.sha256" in infrastructure
    assert "sudo /usr/bin/python3 -I -S scripts/operator/install_v3_checkpoint_host_interface.py" not in infrastructure
    assert 'V3-CHECKPOINT {"operation":"provision"}' in infrastructure
    assert "repeatable staging path is issue #623 `release`" in infrastructure
    assert "`deploy` → the canonical workflow's automatic external public smoke" in infrastructure
    assert 'V3-CHECKPOINT {"operation":"release"' in release
    assert 'V3-CHECKPOINT {"operation":"deploy"' in release
    assert "automatic GitHub-hosted public smoke" in release
    assert "Routine deployment never invokes provisioning" in release
