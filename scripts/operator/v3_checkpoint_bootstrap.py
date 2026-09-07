"""Installed root-owned bootstrap for sealed Contabo checkpoint operations.

The fixed checkpoint launcher starts this file with root-owned OS Python in
isolated/no-site mode. SHA-256 handshakes bind the committed launcher and
bootstrap sources, both installed helpers and the sealed request before any
artifact is downloaded.
Application and canonical deployment runtimes remain exact CPython 3.14.
"""
import hashlib
import io
import json
import os
import pwd
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

LIMIT = 64 * 1024 * 1024
INTERFACE_VERSION = "1"
REPOSITORY = "brianstewart377-rgb/ed-finder"
ENTRY = "scripts/operator/actions/v3-live-checkpoint-local.sh"
LAUNCHER = Path("/usr/local/sbin/edfinder-v3-checkpoint-launcher")
PATH = "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
API = f"https://api.github.com/repos/{REPOSITORY}"
MAX_METADATA = 1024 * 1024
TRUSTED_OPERATIONS = {
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
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bootstrap_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def verify_bootstrap_identity(expected):
    require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
            "invalid expected bootstrap digest")
    require(bootstrap_sha256() == expected,
            "installed checkpoint bootstrap digest mismatch")


def verify_launcher_identity(expected):
    require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
            "invalid expected launcher digest")
    require(hashlib.sha256(LAUNCHER.read_bytes()).hexdigest() == expected,
            "installed checkpoint launcher digest mismatch")


def github_response(token, resource, limit):
    """Read one fixed-origin GitHub API resource without exposing the token."""
    response = subprocess.run([
        "/usr/bin/curl", "--disable", "--silent", "--show-error", "--fail",
        "--location", "--proto", "=https", "--proto-redir", "=https",
        "--tlsv1.2", "--noproxy", "*", "--connect-timeout", "10",
        "--max-time", "120", "--max-filesize", str(limit), "--header", "@-",
        API + resource,
    ], input=("Accept: application/vnd.github+json\n"
              f"Authorization: Bearer {token}\n"
              "X-GitHub-Api-Version: 2022-11-28\n").encode(),
       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"PATH": PATH},
       timeout=130, check=True)
    require(len(response.stdout) <= limit, "oversized GitHub response")
    return response.stdout


def github_json(token, resource):
    try:
        value = json.loads(github_response(token, resource, MAX_METADATA))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid GitHub metadata response") from exc
    require(isinstance(value, dict), "invalid GitHub metadata response")
    return value


def positive_identifier(value):
    return (isinstance(value, int) and not isinstance(value, bool)
            and re.fullmatch(r"[1-9][0-9]{0,19}", str(value)) is not None)


def verify_artifact_provenance(artifact_metadata, run, artifact, source, operation):
    """Bind an operation artifact to its immutable trusted-main workflow run."""
    artifact_name, workflow_path, event = TRUSTED_OPERATIONS[operation]
    association = artifact_metadata.get("workflow_run")
    require(isinstance(association, dict), "artifact has no workflow run provenance")
    run_id = association.get("id")
    repository_id = association.get("repository_id")
    head_repository_id = association.get("head_repository_id")
    repository = run.get("repository")
    head_repository = run.get("head_repository")
    checks = {
        "artifact_id": positive_identifier(artifact_metadata.get("id"))
        and str(artifact_metadata.get("id")) == artifact,
        "artifact_name": artifact_metadata.get("name") == artifact_name,
        "artifact_current": artifact_metadata.get("expired") is False,
        "artifact_run": positive_identifier(run_id)
        and positive_identifier(run.get("id")) and run.get("id") == run_id,
        "artifact_repository": positive_identifier(repository_id)
        and repository_id == head_repository_id,
        "artifact_main_head": association.get("head_branch") == "main"
        and association.get("head_sha") == source,
        "canonical_repository": isinstance(repository, dict)
        and isinstance(head_repository, dict)
        and repository.get("id") == repository_id
        and head_repository.get("id") == repository_id
        and str(repository.get("full_name", "")).casefold() == REPOSITORY.casefold()
        and str(head_repository.get("full_name", "")).casefold() == REPOSITORY.casefold(),
        "canonical_workflow": run.get("path") == workflow_path,
        "trusted_event": run.get("event") == event,
        "trusted_main_head": run.get("head_branch") == "main"
        and run.get("head_sha") == source,
        # The artifact is consumed by a later job in this same canonical run.
        # A completed artifact from an old run is not a fresh operation grant.
        "active_run": run.get("status") == "in_progress"
        and run.get("conclusion") is None,
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    require(not failures, "operation artifact provenance failed: " + ",".join(failures))
    return str(run_id)


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
            with target.open("xb") as output:
                output.write(archive.extractfile(member).read())
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    require(ENTRY in seen and "operation.json" in seen, "incomplete operation bundle")


def save_receipt(document, path):
    """Write only sanitized output, with the runner's privileges, never root's."""
    require(len(document) <= LIMIT, "oversized operation output")
    json.loads(document)
    account = pwd.getpwnam("codex")
    require(account.pw_uid > 0, "non-root receipt account required")
    # This fixed child neither loads user-site Python nor evaluates the filename.
    # Exclusive creation also prevents a rerun from uploading an old receipt.
    writer = (
        "import os,sys; "
        "fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); "
        "f=os.fdopen(fd,'wb'); f.write(sys.stdin.buffer.read()); f.close()"
    )
    subprocess.run([
        "/usr/sbin/runuser", "-u", "codex", "--", "/usr/bin/python3", "-I", "-S",
        "-c", writer, path,
    ], input=document, env={"PATH": PATH, "HOME": account.pw_dir},
       timeout=15, check=True)
    # Root-produced log evidence can be checked against the uploaded copy.
    print("checkpoint receipt sha256=" + hashlib.sha256(document).hexdigest(), file=sys.stderr)
    sys.stdout.buffer.write(document)
    sys.stdout.buffer.flush()


def main():
    if sys.argv[1:2] == ["--check"]:
        require(len(sys.argv) == 6 and sys.argv[2] == "--bootstrap-sha"
                and sys.argv[4] == "--launcher-sha",
                "invalid self-test arguments")
        expected_bootstrap = sys.argv[3]
        expected_launcher = sys.argv[5]
        os.environ.clear()
        require(os.geteuid() == 0, "root bootstrap required")
        require(os.uname().nodename.split(".")[0] == "vmi3542235"
                and os.uname().machine == "x86_64"
                and socket.getfqdn() == "vmi3542235.contaboserver.net",
                "unexpected checkpoint host")
        verify_bootstrap_identity(expected_bootstrap)
        verify_launcher_identity(expected_launcher)
        print("checkpoint launcher self-test ok "
              f"interface={INTERFACE_VERSION} "
              f"bootstrap_sha256={expected_bootstrap} "
              f"launcher_sha256={expected_launcher}")
        return 0
    # {0} is required by Actions' custom-shell contract but is not trusted input.
    # Do not stat, open, source, import, or execute that generated file.
    require(len(sys.argv) == 11 and sys.argv[1] == "--expected-bootstrap-sha"
            and sys.argv[3] == "--expected-launcher-sha",
            "invalid bootstrap arguments")
    expected_bootstrap = sys.argv[2]
    expected_launcher = sys.argv[4]
    artifact, digest, source, operation, receipt, _ignored_script = sys.argv[5:]
    token = os.environ.pop("GH_TOKEN", "")
    os.environ.clear()
    require(os.geteuid() == 0, "root bootstrap required")
    verify_bootstrap_identity(expected_bootstrap)
    verify_launcher_identity(expected_launcher)
    require(re.fullmatch(r"[1-9][0-9]{0,19}", artifact), "invalid artifact id")
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "invalid bundle digest")
    require(re.fullmatch(r"[0-9a-f]{40}", source), "invalid source identity")
    require(operation in ("provision", "deploy"), "invalid operation")
    require(Path(receipt).is_absolute(), "absolute receipt path required")
    require(os.uname().nodename.split(".")[0] == "vmi3542235"
            and os.uname().machine == "x86_64"
            and socket.getfqdn() == "vmi3542235.contaboserver.net", "unexpected checkpoint host")
    os.umask(0o022)
    require(0 < len(token) <= 8192 and not any(c.isspace() for c in token),
            "invalid artifact token")
    artifact_metadata = github_json(token, f"/actions/artifacts/{artifact}")
    association = artifact_metadata.get("workflow_run")
    require(isinstance(association, dict)
            and positive_identifier(association.get("id")),
            "artifact has no workflow run provenance")
    run_id = str(association["id"])
    run = github_json(token, f"/actions/runs/{run_id}")
    verify_artifact_provenance(artifact_metadata, run, artifact, source, operation)
    envelope = github_response(token, f"/actions/artifacts/{artifact}/zip", LIMIT)
    with tempfile.TemporaryDirectory(prefix="edfinder-v3-", dir="/run") as temporary:
        directory = Path(temporary)
        unpack_bundle(envelope, digest, directory)
        request = json.loads((directory / "operation.json").read_text())
        require(request.get("source_sha") == source
                and request.get("operation") == operation
                and request.get("bootstrap_sha256") == expected_bootstrap
                and request.get("launcher_sha256") == expected_launcher,
                "operation bundle identity mismatch")
        directory.chmod(0o755)
        environment = {"PATH": PATH, "HOME": "/root", "LANG": "C", "LC_ALL": "C"}
        if operation == "deploy":
            environment["GHCR_TOKEN"] = token
        outcome = subprocess.run(["/bin/bash", ENTRY], cwd=directory,
                                 env=environment, stdout=subprocess.PIPE, check=False)
        if outcome.stdout:
            save_receipt(outcome.stdout, receipt)
        return outcome.returncode


if __name__ == "__main__":
    try:
        result = main()
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.SubprocessError):
        print("Checkpoint bootstrap stopped; inspect the operation log for its last completed step", file=sys.stderr)
        result = 78
    raise SystemExit(result)
