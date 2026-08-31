#!/usr/bin/env python3
"""Stream a fail-closed, non-secret V3 source recovery archive to stdout.

This helper is intentionally read-only: Docker is queried only for selected
Compose labels and every selected file is read from the resolved Compose source
root.  The tar stream is written to stdout so the remote host is not mutated.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
from typing import BinaryIO, Iterable


CONTAINER_NAME = "edfinder-v3-phase4c-full-20260827_r5-postgres"
EXPECTED_COMPOSE_PROJECT = "edfinder-v3-phase4c-full-20260827_r5"
MAX_FILES = 2_000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".yml", ".yaml", ".sql", ".sh", ".py", ".md", ".txt", ".json"}
BUILD_FILE_PREFIXES = ("dockerfile", "containerfile")
FORBIDDEN_PARTS = {
    ".env",
    ".git",
    "backup",
    "backups",
    "cert",
    "certs",
    "credential",
    "credentials",
    "data",
    "dump",
    "dumps",
    "id_rsa",
    "id_ed25519",
    "key",
    "keys",
    "log",
    "logs",
    "pgbackrest",
    "private",
    "secret",
    "secrets",
    "ssh",
    "token",
    "tokens",
    "volume",
    "volumes",
}
FORBIDDEN_FRAGMENTS = (
    "password",
    "passwd",
    "credential",
    "secret",
    "token",
    "private_key",
    "apikey",
    "api_key",
    "id_rsa",
    "id_ed25519",
)
FORBIDDEN_STEMS = {"backup", "backups", "data", "dump", "dumps", "log", "logs", "pgbackrest"}
COMPOSE_WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
COMPOSE_CONFIG_FILES_LABEL = "com.docker.compose.project.config_files"
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
SCHEMA = "edfinder-v3-runtime-recovery/v1"


class RecoveryError(RuntimeError):
    """A safety contract failed; no partial archive should be trusted."""


@dataclass(frozen=True)
class CollectedFile:
    relative: str
    data: bytes
    mode: int
    sha256: str


def parse_compose_labels(raw: str) -> tuple[Path, tuple[Path, ...], str]:
    try:
        labels = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecoveryError("Docker Compose labels were not valid JSON") from exc
    if not isinstance(labels, dict):
        raise RecoveryError("Docker labels must be a JSON object")
    working_value = labels.get(COMPOSE_WORKING_DIR_LABEL)
    configs_value = labels.get(COMPOSE_CONFIG_FILES_LABEL)
    project_value = labels.get(COMPOSE_PROJECT_LABEL)
    if not isinstance(working_value, str) or not working_value.startswith("/"):
        raise RecoveryError("Compose working directory label is missing or not absolute")
    if not isinstance(configs_value, str) or not configs_value.strip():
        raise RecoveryError("Compose config-files label is missing")
    if project_value != EXPECTED_COMPOSE_PROJECT:
        raise RecoveryError("Compose project label does not match the retained project")
    root = Path(working_value).resolve(strict=True)
    if not root.is_dir():
        raise RecoveryError("Compose working directory is not a directory")
    configs: list[Path] = []
    for value in configs_value.split(","):
        value = value.strip()
        if not value:
            raise RecoveryError("Compose config-files label contains an empty path")
        candidate = Path(value) if value.startswith("/") else root / value
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RecoveryError("Compose config file escapes the source root") from exc
        configs.append(resolved)
    return root, tuple(configs), project_value


def _safe_name(relative: PurePosixPath) -> bool:
    for part in relative.parts:
        lower = part.lower()
        if lower in FORBIDDEN_PARTS or lower.startswith(".env"):
            return False
        if any(fragment in lower for fragment in FORBIDDEN_FRAGMENTS):
            return False
        if lower.endswith((".pem", ".key", ".crt", ".cer", ".p12", ".pfx", ".jks")):
            return False
    name = relative.name.lower()
    if PurePosixPath(name).stem in FORBIDDEN_STEMS:
        return False
    return relative.suffix.lower() in ALLOWED_SUFFIXES or name.startswith(BUILD_FILE_PREFIXES)


def collect_files(root: Path, required_configs: Iterable[Path]) -> list[CollectedFile]:
    root = root.resolve(strict=True)
    required = {path.resolve(strict=True) for path in required_configs}
    selected: list[CollectedFile] = []
    total = 0
    def walk_error(error: OSError) -> None:
        raise RecoveryError(f"Unable to traverse source tree: {error.filename or 'unknown path'}") from error

    for directory, dirnames, filenames in os.walk(
        root, topdown=True, onerror=walk_error, followlinks=False
    ):
        directory_path = Path(directory)
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            path = directory_path / name
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if path.is_symlink():
                raise RecoveryError(f"Source tree contains a directory symlink: {relative}")
            if all(part.lower() not in FORBIDDEN_PARTS for part in relative.parts):
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            path = directory_path / name
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if not _safe_name(relative):
                continue
            lst = path.lstat()
            if stat.S_ISLNK(lst.st_mode):
                raise RecoveryError(f"Selected path is a symlink: {relative}")
            if not stat.S_ISREG(lst.st_mode):
                raise RecoveryError(f"Selected path is not a regular file: {relative}")
            resolved = path.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise RecoveryError(f"Selected path escapes source root: {relative}") from exc
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags)
            except OSError as exc:
                raise RecoveryError(f"Unable to open selected file safely: {relative}") from exc
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (lst.st_dev, lst.st_ino):
                    raise RecoveryError(f"Selected file identity changed: {relative}")
                if before.st_size > MAX_FILE_BYTES:
                    raise RecoveryError(f"Selected file exceeds per-file limit: {relative}")
                chunks: list[bytes] = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        raise RecoveryError(f"Selected file was truncated while reading: {relative}")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    raise RecoveryError(f"Selected file grew while reading: {relative}")
                after = os.fstat(descriptor)
                if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
                ):
                    raise RecoveryError(f"Selected file changed while reading: {relative}")
            finally:
                os.close(descriptor)
            data = b"".join(chunks)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise RecoveryError("Selected files exceed total-size limit")
            selected.append(
                CollectedFile(relative.as_posix(), data, stat.S_IMODE(before.st_mode), hashlib.sha256(data).hexdigest())
            )
            if len(selected) > MAX_FILES:
                raise RecoveryError("Selected files exceed file-count limit")
    selected_paths = {(root / item.relative).resolve(strict=True) for item in selected}
    if not required.issubset(selected_paths):
        raise RecoveryError("A labeled Compose config file was rejected by the allowlist")
    return selected


def build_manifest(files: Iterable[CollectedFile]) -> dict[str, object]:
    entries = [
        {
            "path": item.relative,
            "size": len(item.data),
            "mode": f"{item.mode:04o}",
            "sha256": item.sha256,
        }
        for item in files
    ]
    return {
        "schema": SCHEMA,
        "file_count": len(entries),
        "total_bytes": sum(int(entry["size"]) for entry in entries),
        "files": entries,
    }


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def stream_archive(
    root: Path,
    project: str,
    files: list[CollectedFile],
    output: BinaryIO,
    *,
    target_host_identity: str = "",
    trusted_commit: str = "",
    trusted_ref: str = "",
    start_utc: str | None = None,
) -> None:
    start_utc = start_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = build_manifest(files)
    receipt = {
        "schema": SCHEMA,
        "operation": "recover-v3-runtime-contract",
        "container": CONTAINER_NAME,
        "source_root": str(root),
        "compose_project": project,
        "start_utc": start_utc,
        "end_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target_host_identity": target_host_identity,
        "exit_status": 0,
        "outcome": "success",
        "trusted_implementation_commit": trusted_commit,
        "trusted_implementation_ref": trusted_ref,
        "docker_metadata_fields": [COMPOSE_PROJECT_LABEL, COMPOSE_WORKING_DIR_LABEL, COMPOSE_CONFIG_FILES_LABEL],
        "docker_inspect_env": False,
        "db_access": False,
        "host_mutation": False,
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "limits": {"max_files": MAX_FILES, "max_total_bytes": MAX_TOTAL_BYTES, "max_file_bytes": MAX_FILE_BYTES},
    }
    with tarfile.open(fileobj=output, mode="w|gz", format=tarfile.PAX_FORMAT) as archive:
        for item in files:
            info = tarfile.TarInfo(f"source/{item.relative}")
            info.size = len(item.data)
            info.mode = item.mode
            info.mtime = 0
            archive.addfile(info, io.BytesIO(item.data))
        _add_bytes(archive, "recovery-manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
        _add_bytes(archive, "recovery-receipt.json", json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")


def docker_compose_labels(container: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "--type", "container", "--format", "{{json .Config.Labels}}", container],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RecoveryError("Unable to read Docker labels for the retained container")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default=CONTAINER_NAME, choices=[CONTAINER_NAME])
    parser.add_argument("--target-host-identity", default="")
    parser.add_argument("--trusted-commit", default="")
    parser.add_argument("--trusted-ref", default="")
    args = parser.parse_args(argv)
    try:
        root, configs, project = parse_compose_labels(docker_compose_labels(args.container))
        files = collect_files(root, configs)
        stream_archive(
            root,
            project,
            files,
            sys.stdout.buffer,
            target_host_identity=args.target_host_identity,
            trusted_commit=args.trusted_commit,
            trusted_ref=args.trusted_ref,
        )
    except (OSError, RecoveryError, subprocess.SubprocessError) as exc:
        print(f"STOP: V3 runtime recovery failed closed: {exc}", file=sys.stderr)
        return 1
    print("V3 runtime recovery stream completed without DB access or host mutation", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
