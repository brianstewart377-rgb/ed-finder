"""Install the fixed, least-privilege Contabo checkpoint host interface."""
import hashlib
import json
import os
import pwd
import re
import secrets
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_HOST = "vmi3542235"
EXPECTED_FQDN = "vmi3542235.contaboserver.net"
EXPECTED_ARCH = "x86_64"
INTERFACE_VERSION = "1"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
STAGING_PARENT = Path("/run")
INSTALLER_SOURCE = Path("scripts/operator/install_v3_checkpoint_host_interface.py")
LAUNCHER_SOURCE = Path("scripts/operator/actions/edfinder-v3-checkpoint-launcher")
BOOTSTRAP_SOURCE = Path("scripts/operator/v3_checkpoint_bootstrap.py")
MANIFEST_SOURCE = Path("scripts/operator/v3_checkpoint_host_interface.sha256")
LAUNCHER_TARGET = Path("usr/local/sbin/edfinder-v3-checkpoint-launcher")
BOOTSTRAP_TARGET = Path("usr/local/libexec/edfinder-v3-checkpoint/v3_checkpoint_bootstrap.py")
SUDOERS_TARGET = Path("etc/sudoers.d/edfinder-v3-checkpoint")
SUDOERS = (
    'Defaults!/usr/local/sbin/edfinder-v3-checkpoint-launcher env_reset,env_keep="GH_TOKEN"\n'
    'codex vmi3542235=(root) NOPASSWD:NOSETENV: /usr/local/sbin/edfinder-v3-checkpoint-launcher\n'
).encode("ascii")


def stop(message):
    raise RuntimeError(f"checkpoint host-interface installation stopped: {message}")


@dataclass(frozen=True)
class FileState:
    content: bytes
    mode: int
    uid: int
    gid: int


def read_source(path, required_owner=None):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_mode & 0o022):
                stop(f"unsafe source file: {path}")
            if (required_owner is not None
                    and (metadata.st_uid != required_owner
                         or metadata.st_gid != required_owner)):
                stop(f"untrusted source file owner: {path}")
            if not 0 < metadata.st_size <= 1024 * 1024:
                stop(f"invalid source file size: {path}")
            chunks = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(descriptor)
    except OSError as exc:
        stop(f"unable to read source file {path}: {type(exc).__name__}")


def require_secure_directory(path, owner_uid):
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != owner_uid
            or metadata.st_gid != owner_uid or metadata.st_mode & 0o022):
        stop(f"unsafe installation directory: {path}")


def ensure_directory(path, owner_uid):
    try:
        path.lstat()
    except FileNotFoundError:
        require_secure_directory(path.parent, owner_uid)
        path.mkdir(mode=0o755)
        os.chown(path, owner_uid, owner_uid)
        os.chmod(path, 0o755)
    require_secure_directory(path, owner_uid)


def existing_state(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        stop(f"unsafe existing target: {path}")
    return FileState(path.read_bytes(), stat.S_IMODE(metadata.st_mode),
                     metadata.st_uid, metadata.st_gid)


def existing_bytes(path):
    state = existing_state(path)
    return None if state is None else state.content


def matches_state(path, content, mode, owner_uid):
    state = existing_state(path)
    return (state is not None and state.content == content
            and state.mode == mode and state.uid == owner_uid
            and state.gid == owner_uid)


def atomic_install(path, content, mode, owner_uid, validator=None, owner_gid=None):
    if owner_gid is None:
        owner_gid = owner_uid
    previous = existing_bytes(path)
    if previous == content:
        metadata = path.lstat()
        if (metadata.st_uid == owner_uid and metadata.st_gid == owner_gid
                and stat.S_IMODE(metadata.st_mode) == mode):
            if validator is not None:
                validator(path)
            return False
    temporary = path.with_name(f".{path.name}.install-{secrets.token_hex(8)}")
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), mode)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, owner_uid, owner_gid)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if validator is not None:
            validator(temporary)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def system_visudo(path):
    subprocess.run(["/usr/sbin/visudo", "-cf", str(path)], check=True,
                   stdin=subprocess.DEVNULL, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"})


def system_self_test(bootstrap_sha, launcher_sha):
    subprocess.run([
        "/usr/sbin/runuser", "-u", "codex", "--", "/usr/bin/env", "-i",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "HOME=/home/codex",
        "GH_TOKEN=checkpoint-installer-self-test", "/usr/bin/sudo", "-n",
        "--preserve-env=GH_TOKEN",
        "/usr/local/sbin/edfinder-v3-checkpoint-launcher", "--check",
        "--bootstrap-sha", bootstrap_sha, "--launcher-sha", launcher_sha,
    ], check=True, stdin=subprocess.DEVNULL,
       env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/home/codex"})


def restore_state(path, previous):
    if previous is None:
        path.unlink(missing_ok=True)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return
    atomic_install(path, previous.content, previous.mode, previous.uid,
                   owner_gid=previous.gid)


def verify_state(path, expected):
    observed = existing_state(path)
    if observed != expected:
        stop(f"transaction rollback did not restore: {path}")


def resolve_trusted_main_sha():
    """Return the exact current trusted-main SHA over a fixed HTTPS-only curl path."""
    endpoint = "https://api.github.com/repos/brianstewart377-rgb/ed-finder/commits/main"
    try:
        response = subprocess.run(
            [
                "/usr/bin/curl", "--disable", "--silent", "--show-error", "--fail",
                "--location", "--proto", "=https", "--proto-redir", "=https",
                "--tlsv1.2", "--noproxy", "*", "--connect-timeout", "10",
                "--max-time", "20", "--max-filesize", str(1024 * 1024),
                "--header", "Accept: application/vnd.github+json",
                "--header", "User-Agent: edfinder-checkpoint-interface-installer",
                endpoint,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        stop(f"GitHub trusted-main lookup failed: {type(exc).__name__}")
    if response.returncode != 0 or not response.stdout:
        stop("GitHub trusted-main lookup failed")
    payload = response.stdout
    if len(payload) > 1024 * 1024:
        stop("GitHub trusted-main response is oversized")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        stop("GitHub trusted-main lookup returned invalid JSON")
    sha = document.get("sha") if isinstance(document, dict) else None
    if not isinstance(sha, str) or SHA_PATTERN.fullmatch(sha) is None:
        stop("GitHub trusted-main lookup returned an invalid commit SHA")
    return sha


def verify_source_manifest(source_root, owner_uid):
    manifest = read_source(source_root / MANIFEST_SOURCE, required_owner=owner_uid)
    try:
        lines = manifest.decode("ascii").splitlines()
    except UnicodeDecodeError:
        stop("reviewed source digest manifest is not ASCII")
    expected_paths = (INSTALLER_SOURCE, LAUNCHER_SOURCE, BOOTSTRAP_SOURCE)
    expected_names = {str(path) for path in expected_paths}
    observed = {}
    for line in lines:
        parts = line.split("  ")
        if (len(parts) != 2
                or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None
                or parts[1] not in expected_names or parts[1] in observed):
            stop("reviewed source digest manifest is invalid")
        observed[parts[1]] = parts[0]
    if set(observed) != expected_names:
        stop("reviewed source digest manifest is incomplete")
    for relative in expected_paths:
        content = read_source(source_root / relative, required_owner=owner_uid)
        if not secrets.compare_digest(hashlib.sha256(content).hexdigest(),
                                      observed[str(relative)]):
            stop(f"reviewed source digest mismatch: {relative}")


def require_authenticated_source(source_root, reviewed_sha,
                                 resolve_main=resolve_trusted_main_sha,
                                 owner_uid=0, staging_parent=STAGING_PARENT,
                                 installer_path=None):
    if (not source_root.is_absolute() or source_root != source_root.resolve()
            or source_root.parent.parent != staging_parent):
        stop("reviewed source must be in a root-controlled /run staging directory")
    require_secure_directory(source_root.parent, owner_uid)
    require_secure_directory(source_root, owner_uid)
    if SHA_PATTERN.fullmatch(reviewed_sha) is None:
        stop("reviewed main SHA is invalid")
    if resolve_main() != reviewed_sha:
        stop("reviewed source is not the exact current trusted-main head")
    expected_installer = (source_root / INSTALLER_SOURCE).resolve()
    running_installer = Path(__file__).resolve() if installer_path is None else installer_path.resolve()
    if running_installer != expected_installer:
        stop("installer is not executing from the authenticated source directory")
    verify_source_manifest(source_root, owner_uid)


def install(source_root, destination_root=Path("/"), owner_uid=0,
            validate_sudoers=system_visudo, self_test=system_self_test,
            source_owner=None, final_verify=None):
    launcher = read_source(source_root / LAUNCHER_SOURCE, source_owner)
    bootstrap = read_source(source_root / BOOTSTRAP_SOURCE, source_owner)
    bootstrap_sha = hashlib.sha256(bootstrap).hexdigest()
    launcher_sha = hashlib.sha256(launcher).hexdigest()

    # Refuse to modify anything while the host's existing sudo policy is invalid.
    validate_sudoers(destination_root / "etc/sudoers")

    local = destination_root / "usr/local"
    local_sbin = destination_root / "usr/local/sbin"
    local_libexec = destination_root / "usr/local/libexec"
    helper_directory = destination_root / BOOTSTRAP_TARGET.parent
    sudoers_directory = destination_root / SUDOERS_TARGET.parent
    for directory in (local, local_sbin, local_libexec, helper_directory, sudoers_directory):
        ensure_directory(directory, owner_uid)

    launcher_target = destination_root / LAUNCHER_TARGET
    bootstrap_target = destination_root / BOOTSTRAP_TARGET
    sudoers_target = destination_root / SUDOERS_TARGET
    helper_targets = (
        (bootstrap_target, bootstrap, 0o600, None),
        (launcher_target, launcher, 0o755, None),
    )
    previous = {
        path: existing_state(path)
        for path in (bootstrap_target, launcher_target, sudoers_target)
    }
    helpers_unchanged = (
        matches_state(bootstrap_target, bootstrap, 0o600, owner_uid)
        and matches_state(launcher_target, launcher, 0o755, owner_uid)
    )
    sudoers_unchanged = matches_state(
        sudoers_target, SUDOERS, 0o440, owner_uid
    )

    def remove_checkpoint_sudo_authority():
        """Keep the active sudo include path clear while helpers can change."""
        if sudoers_target.exists():
            sudoers_target.unlink()
            directory = os.open(sudoers_target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        validate_sudoers(destination_root / "etc/sudoers")

    try:
        validate_sudoers(destination_root / "etc/sudoers")
        if helpers_unchanged:
            if not sudoers_unchanged:
                atomic_install(sudoers_target, SUDOERS, 0o440, validate_sudoers)
        else:
            remove_checkpoint_sudo_authority()
            for path, content, mode, validator in helper_targets:
                atomic_install(path, content, mode, owner_uid, validator)
            # The candidate rule is parsed before it can enter sudo's include directory,
            # and is installed only after both helpers are internally consistent.
            atomic_install(sudoers_target, SUDOERS, 0o440, validate_sudoers)
            validate_sudoers(destination_root / "etc/sudoers")
        self_test(bootstrap_sha, launcher_sha)
        if final_verify is not None:
            final_verify()
    except Exception as installation_error:
        rollback_errors = []
        try:
            remove_checkpoint_sudo_authority()
        except Exception as exc:
            rollback_errors.append(f"revoke checkpoint sudo authority: {exc}")
        for path in (bootstrap_target, launcher_target):
            try:
                restore_state(path, previous[path])
                verify_state(path, previous[path])
            except Exception as exc:  # retain every rollback failure for diagnosis
                rollback_errors.append(f"{path}: {exc}")
        try:
            restore_state(sudoers_target, previous[sudoers_target])
            verify_state(sudoers_target, previous[sudoers_target])
        except Exception as exc:
            rollback_errors.append(f"{sudoers_target}: {exc}")
        try:
            validate_sudoers(destination_root / "etc/sudoers")
        except Exception as exc:
            rollback_errors.append(f"complete sudo policy: {exc}")
        if rollback_errors:
            stop("installation failed and rollback was incomplete: "
                 + "; ".join(rollback_errors))
        raise installation_error
    return bootstrap_sha, launcher_sha


def require_host_authority():
    if os.geteuid() != 0:
        stop("root execution required")
    account = pwd.getpwnam("codex")
    if (os.environ.get("SUDO_USER") != "codex"
            or os.environ.get("SUDO_UID") != str(account.pw_uid)
            or os.environ.get("SUDO_GID") != str(account.pw_gid)):
        stop("run this installer via sudo from the codex account")
    if (os.uname().nodename.split(".")[0] != EXPECTED_HOST
            or os.uname().machine != EXPECTED_ARCH
            or socket.getfqdn() != EXPECTED_FQDN):
        stop("unexpected checkpoint host identity")


def main():
    if (len(sys.argv) != 5 or sys.argv[1] != "--reviewed-main-sha"
            or sys.argv[3] != "--source-root"):
        stop("exact reviewed source arguments are required")
    require_host_authority()
    reviewed_sha = sys.argv[2]
    source_root = Path(sys.argv[4])
    require_authenticated_source(source_root, reviewed_sha)
    bootstrap_sha, launcher_sha = install(
        source_root,
        source_owner=0,
        final_verify=lambda: require_authenticated_source(source_root, reviewed_sha),
    )
    print("checkpoint host interface installed and verified "
          f"interface={INTERFACE_VERSION} bootstrap_sha256={bootstrap_sha} "
          f"launcher_sha256={launcher_sha}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(78) from None
