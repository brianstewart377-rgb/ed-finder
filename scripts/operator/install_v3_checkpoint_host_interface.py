"""Install the fixed, least-privilege Contabo checkpoint host interface."""
import hashlib
import os
import pwd
import secrets
import socket
import stat
import subprocess
import sys
from pathlib import Path

EXPECTED_HOST = "vmi3542235"
EXPECTED_FQDN = "vmi3542235.contaboserver.net"
EXPECTED_ARCH = "x86_64"
INTERFACE_VERSION = "1"
LAUNCHER_SOURCE = Path("scripts/operator/actions/edfinder-v3-checkpoint-launcher")
BOOTSTRAP_SOURCE = Path("scripts/operator/v3_checkpoint_bootstrap.py")
LAUNCHER_TARGET = Path("usr/local/sbin/edfinder-v3-checkpoint-launcher")
BOOTSTRAP_TARGET = Path("usr/local/libexec/edfinder-v3-checkpoint/v3_checkpoint_bootstrap.py")
SUDOERS_TARGET = Path("etc/sudoers.d/edfinder-v3-checkpoint")
SUDOERS = (
    'Defaults!/usr/local/sbin/edfinder-v3-checkpoint-launcher env_reset,env_keep="GH_TOKEN"\n'
    'codex vmi3542235=(root) NOPASSWD:NOSETENV: /usr/local/sbin/edfinder-v3-checkpoint-launcher\n'
).encode("ascii")


def stop(message):
    raise RuntimeError(f"checkpoint host-interface installation stopped: {message}")


def read_source(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_mode & 0o022):
                stop(f"unsafe source file: {path}")
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


def existing_bytes(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        stop(f"unsafe existing target: {path}")
    return path.read_bytes()


def atomic_install(path, content, mode, owner_uid, validator=None):
    previous = existing_bytes(path)
    if previous == content:
        metadata = path.lstat()
        if (metadata.st_uid == owner_uid and metadata.st_gid == owner_uid
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
        os.fchown(descriptor, owner_uid, owner_uid)
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


def system_self_test(bootstrap_sha):
    subprocess.run([
        "/usr/sbin/runuser", "-u", "codex", "--", "/usr/bin/env", "-i",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "HOME=/home/codex",
        "GH_TOKEN=checkpoint-installer-self-test", "/usr/bin/sudo", "-n",
        "--preserve-env=GH_TOKEN",
        "/usr/local/sbin/edfinder-v3-checkpoint-launcher", "--check", bootstrap_sha,
    ], check=True, stdin=subprocess.DEVNULL,
       env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/home/codex"})


def install(source_root, destination_root=Path("/"), owner_uid=0,
            validate_sudoers=system_visudo, self_test=system_self_test):
    launcher = read_source(source_root / LAUNCHER_SOURCE)
    bootstrap = read_source(source_root / BOOTSTRAP_SOURCE)
    bootstrap_sha = hashlib.sha256(bootstrap).hexdigest()

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
    atomic_install(bootstrap_target, bootstrap, 0o600, owner_uid)
    atomic_install(launcher_target, launcher, 0o755, owner_uid)

    # The candidate rule is parsed before it can enter sudo's include directory.
    old_sudoers = existing_bytes(sudoers_target)
    changed = atomic_install(sudoers_target, SUDOERS, 0o440, owner_uid, validate_sudoers)
    try:
        validate_sudoers(destination_root / "etc/sudoers")
    except Exception:
        if changed:
            if old_sudoers is None:
                sudoers_target.unlink(missing_ok=True)
            else:
                atomic_install(sudoers_target, old_sudoers, 0o440, owner_uid)
        raise
    self_test(bootstrap_sha)
    return bootstrap_sha


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
    if len(sys.argv) != 1:
        stop("arguments are not accepted")
    require_host_authority()
    source_root = Path(__file__).resolve().parents[2]
    digest = install(source_root)
    print("checkpoint host interface installed and verified "
          f"interface={INTERFACE_VERSION} bootstrap_sha256={digest}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(78) from None
