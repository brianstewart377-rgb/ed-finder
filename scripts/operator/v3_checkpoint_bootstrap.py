"""Workflow-embedded bootstrap: no code is loaded from a runner worktree.

Uses the root-owned OS Python solely to authenticate/unpack the operation bundle.
The provisioner installs, and the canonical deployer requires, CPython 3.14.
"""
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

LIMIT = 64 * 1024 * 1024
REPOSITORY = "brianstewart377-rgb/ed-finder"
ENTRY = "scripts/operator/actions/v3-live-checkpoint-local.sh"
PATH = "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unpack_bundle(envelope, digest, directory):
    require(len(envelope) <= LIMIT, "oversized artifact")
    with zipfile.ZipFile(io.BytesIO(envelope)) as archive:
        require(archive.namelist() == ["operation.tar"], "unexpected artifact members")
        require(archive.getinfo("operation.tar").file_size <= LIMIT, "oversized bundle")
        payload = archive.read("operation.tar")
    require(hashlib.sha256(payload).hexdigest() == digest, "bundle checksum mismatch")
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and ".." not in name.parts,
                    "unsafe bundle path")
            require(str(name) not in seen, "duplicate bundle member")
            seen.add(str(name))
            require(member.isdir() or member.isfile(), "non-regular bundle member")
            target = directory.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o755)
                continue
            total += member.size
            require(0 <= member.size <= LIMIT and total <= LIMIT, "oversized bundle contents")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            # Parent is root-created and cannot be written by any coding worker.
            with target.open("xb") as output:
                output.write(archive.extractfile(member).read())
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    require(ENTRY in seen and "operation.json" in seen, "incomplete operation bundle")


def main():
    artifact, digest, source, operation = sys.argv[1:]
    require(os.geteuid() == 0, "root bootstrap required")
    require(re.fullmatch(r"[1-9][0-9]{0,19}", artifact), "invalid artifact id")
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "invalid bundle digest")
    require(re.fullmatch(r"[0-9a-f]{40}", source), "invalid source identity")
    require(operation in ("provision", "deploy"), "invalid operation")
    require(os.uname().nodename.split(".")[0] == "vmi3542235"
            and os.uname().machine == "x86_64"
            and socket.getfqdn() == "vmi3542235.contaboserver.net", "unexpected checkpoint host")
    os.umask(0o022)
    token = sys.stdin.read(8193)
    require(0 < len(token) <= 8192 and not any(c.isspace() for c in token),
            "invalid artifact token")
    # No inherited proxy, curl configuration, CA override, PATH or Python imports.
    # curl strips Authorization on a cross-host redirect; never use location-trusted.
    response = subprocess.run([
        "/usr/bin/curl", "--disable", "--silent", "--show-error", "--fail",
        "--location", "--proto", "=https", "--proto-redir", "=https",
        "--noproxy", "*", "--connect-timeout", "10", "--max-time", "120",
        "--max-filesize", str(LIMIT), "--header", "@-",
        f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact}/zip",
    ], input=f"Authorization: Bearer {token}\n".encode(), stdout=subprocess.PIPE,
       stderr=subprocess.DEVNULL, env={"PATH": PATH}, timeout=130, check=True)
    # /run is root-owned; the private parent stays non-writable by the runner.
    with tempfile.TemporaryDirectory(prefix="edfinder-v3-", dir="/run") as temporary:
        directory = Path(temporary)
        unpack_bundle(response.stdout, digest, directory)
        request = json.loads((directory / "operation.json").read_text())
        require(request.get("source_sha") == source and request.get("operation") == operation,
                "operation bundle identity mismatch")
        # Code and public manifests may be read, never modified, by the non-root
        # canonical deployer and the postgres seed process.
        directory.chmod(0o755)
        environment = {"PATH": PATH, "HOME": "/root", "LANG": "C", "LC_ALL": "C"}
        if operation == "deploy":
            environment["GHCR_TOKEN"] = token
        return subprocess.run(["/bin/bash", ENTRY], cwd=directory,
                              env=environment, check=False).returncode


if __name__ == "__main__":
    try:
        result = main()
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.SubprocessError):
        print("Checkpoint immutable bootstrap stopped; no unverified bundle executed", file=sys.stderr)
        result = 78
    raise SystemExit(result)
