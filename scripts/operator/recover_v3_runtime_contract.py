#!/usr/bin/env python3
"""Stream a fail-closed, non-secret V3 source recovery archive to stdout.

This helper is intentionally read-only: Docker is queried only for selected
Compose labels and every selected file is read from the resolved Compose source
root. The tar stream is written to stdout so the remote host is not mutated.

Every candidate file is content-scanned before any archive bytes are emitted.
Unsafe optional historical files are excluded with provenance-only metadata;
unsafe required Compose files fail the whole recovery.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
from typing import BinaryIO, Iterable


CONTAINER_NAME = "edfinder-v3-phase4c-full-20260827_r5-postgres"
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
COMPOSE_WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
COMPOSE_CONFIG_FILES_LABEL = "com.docker.compose.project.config_files"
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
SCHEMA = "edfinder-v3-runtime-recovery/v2"

SENSITIVE_ENV_NAME = (
    r"(?:"
    r"[A-Z][A-Z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|PRIVATE_KEY|API_KEY|APIKEY)"
    r"[A-Z0-9_]*"
    r"|DATABASE_URL|REDIS_URL|CACHE_URL|CELERY_BROKER_URL"
    r"|OCTOPUS_DATA_KEY|DATA_ENCRYPTION_KEY"
    r")"
)
QUOTED_ENV_ASSIGNMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{SENSITIVE_ENV_NAME})\s*=\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
)
BARE_ENV_ASSIGNMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{SENSITIVE_ENV_NAME})\s*=\s*"
    r"(?P<value>[^\s,\"'\]\}]+)",
)
JSON_MAPPING_ENV_RE = re.compile(
    rf'["\'](?P<name>{SENSITIVE_ENV_NAME})["\']\s*:\s*'
    r'(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
)
YAML_MAPPING_ENV_RE = re.compile(
    rf"(?m)^\s*(?P<name>{SENSITIVE_ENV_NAME})\s*:\s*(?P<value>[^\r\n#]+)",
)
CREDENTIALED_URI_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|redis|rediss|mongodb(?:\+srv)?|"
    r"amqp|amqps)://[^/\s:@]*:(?P<password>[^@\s/]+)@",
)
URI_QUERY_CREDENTIAL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|redis|rediss|mongodb(?:\+srv)?|"
    r"amqp|amqps)://[^\s\"'<>]*[?&;]"
    r"(?:password|passwd|pwd|secret|token|api_?key)=(?P<password>[^&#;\s\"'<>]+)",
)
DSN_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)(?:^|[\s?&;])(?:password|passwd|pwd|secret|token|api_?key)\s*=\s*"
    r"(?P<password>[^\s;&]+)",
)
TOKEN_PATTERNS = (
    (
        "private-key-material",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            re.IGNORECASE,
        ),
    ),
    ("openai-api-token", re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-api-token", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
CONTENT_SCAN_RULES = (
    "private-key-material",
    "recognized-api-token",
    "credentialed-database-or-cache-uri",
    "non-placeholder-sensitive-environment-assignment",
)


class RecoveryError(RuntimeError):
    """A safety contract failed; no partial archive should be trusted."""


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
    if not isinstance(project_value, str) or not project_value.strip():
        raise RecoveryError("Compose project label is missing")
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
    return relative.suffix.lower() in ALLOWED_SUFFIXES or name.startswith(BUILD_FILE_PREFIXES)


def collect_files(
    root: Path,
    required_configs: Iterable[Path],
) -> list[tuple[Path, str, os.stat_result]]:
    root = root.resolve(strict=True)
    required = {path.resolve(strict=True) for path in required_configs}
    selected: list[tuple[Path, str, os.stat_result]] = []
    total = 0
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
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
            if lst.st_size > MAX_FILE_BYTES:
                raise RecoveryError(f"Selected file exceeds per-file limit: {relative}")
            total += lst.st_size
            if total > MAX_TOTAL_BYTES:
                raise RecoveryError("Selected files exceed total-size limit")
            selected.append((path, relative.as_posix(), lst))
            if len(selected) > MAX_FILES:
                raise RecoveryError("Selected files exceed file-count limit")
    selected_paths = {path.resolve(strict=True) for path, _, _ in selected}
    if not required.issubset(selected_paths):
        raise RecoveryError("A labeled Compose config file was rejected by the allowlist")
    return selected


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _placeholder_value(value: str) -> bool:
    candidate = value.strip().strip("\"'")
    if not candidate:
        return True
    if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::\?[^}]*)?\}", candidate):
        return True
    if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", candidate):
        return True
    if re.fullmatch(r"\{\{[^{}]+\}\}", candidate):
        return True
    if re.fullmatch(r"<(?:redacted|placeholder|secret|password|token|[^>]*_here)>", candidate, re.I):
        return True
    if candidate.upper() in {
        "REDACTED",
        "PLACEHOLDER",
        "NOT_SET",
        "UNSET",
        "REPLACE_ME",
        "YOUR_SECRET_HERE",
        "YOUR_PASSWORD_HERE",
        "YOUR_TOKEN_HERE",
    }:
        return True
    if re.fullmatch(r"[*xX]{6,}", candidate):
        return True
    return False


URL_ENV_NAMES = {"DATABASE_URL", "REDIS_URL", "CACHE_URL", "CELERY_BROKER_URL"}


def _assignment_value_is_safe(name: str, value: str) -> bool:
    if _placeholder_value(value):
        return True
    if name.upper() in URL_ENV_NAMES:
        candidate = value.strip().strip("\"'")
        credential_values = [
            match.group("password") for match in CREDENTIALED_URI_RE.finditer(candidate)
        ]
        credential_values.extend(
            match.group("password") for match in DSN_CREDENTIAL_PARAM_RE.finditer(candidate)
        )
        return not credential_values or all(_placeholder_value(item) for item in credential_values)
    return False


def _scan_text(text: str, relative: str) -> tuple[str, ...]:
    findings: set[str] = set()

    for category, pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            findings.add(category)

    for pattern in (CREDENTIALED_URI_RE, URI_QUERY_CREDENTIAL_RE):
        for match in pattern.finditer(text):
            if not _placeholder_value(match.group("password")):
                findings.add("credentialed-uri")

    relative_path = PurePosixPath(relative)
    assignment_scan = (
        relative_path.suffix.lower() in {".sh", ".yml", ".yaml", ".json", ".txt"}
        or relative_path.name.lower().startswith(BUILD_FILE_PREFIXES)
    )
    if assignment_scan:
        for pattern in (QUOTED_ENV_ASSIGNMENT_RE, BARE_ENV_ASSIGNMENT_RE):
            for match in pattern.finditer(text):
                if not _assignment_value_is_safe(
                    match.group("name"), match.group("value")
                ):
                    findings.add("sensitive-environment-assignment")
        if relative_path.suffix.lower() in {".yml", ".yaml", ".json"}:
            mapping_patterns = [JSON_MAPPING_ENV_RE]
            if relative_path.suffix.lower() in {".yml", ".yaml"}:
                mapping_patterns.append(YAML_MAPPING_ENV_RE)
            for pattern in mapping_patterns:
                for match in pattern.finditer(text):
                    if not _assignment_value_is_safe(
                        match.group("name"), match.group("value")
                    ):
                        findings.add("sensitive-environment-assignment")

    return tuple(sorted(findings))


def scan_selected_files(
    files: Iterable[tuple[Path, str, os.stat_result]],
    required_configs: Iterable[Path],
) -> tuple[
    list[tuple[Path, str, os.stat_result]],
    list[dict[str, object]],
]:
    required = {path.resolve(strict=True) for path in required_configs}
    included: list[tuple[Path, str, os.stat_result]] = []
    excluded: list[dict[str, object]] = []

    for path, relative, metadata in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RecoveryError(f"Selected text file is not valid UTF-8: {relative}") from exc

        findings = _scan_text(text, relative)
        if not findings:
            included.append((path, relative, metadata))
            continue

        if path.resolve(strict=True) in required:
            categories = ", ".join(findings)
            raise RecoveryError(
                f"Required Compose config contains sensitive content: {relative} ({categories})"
            )

        excluded.append(
            {
                "path": relative,
                "size": metadata.st_size,
                "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "sha256": _sha256_file(path),
                "findings": list(findings),
            }
        )

    return included, excluded


def build_manifest(
    files: Iterable[tuple[Path, str, os.stat_result]],
    excluded_sensitive_files: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    entries = [
        {
            "path": relative,
            "size": metadata.st_size,
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
            "sha256": _sha256_file(path),
        }
        for path, relative, metadata in files
    ]
    exclusions = list(excluded_sensitive_files)
    return {
        "schema": SCHEMA,
        "file_count": len(entries),
        "total_bytes": sum(int(entry["size"]) for entry in entries),
        "files": entries,
        "excluded_sensitive_file_count": len(exclusions),
        "excluded_sensitive_files": exclusions,
    }


def _add_bytes(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
    mode: int = 0o644,
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def stream_archive(
    root: Path,
    project: str,
    files: list[tuple[Path, str, os.stat_result]],
    output: BinaryIO,
    required_configs: Iterable[Path] = (),
) -> None:
    included, excluded = scan_selected_files(files, required_configs)
    manifest = build_manifest(included, excluded)
    receipt = {
        "schema": SCHEMA,
        "operation": "recover-v3-runtime-contract",
        "container": CONTAINER_NAME,
        "source_root": str(root),
        "compose_project": project,
        "docker_metadata_fields": [
            COMPOSE_PROJECT_LABEL,
            COMPOSE_WORKING_DIR_LABEL,
            COMPOSE_CONFIG_FILES_LABEL,
        ],
        "docker_inspect_env": False,
        "source_content_scan": {
            "performed": True,
            "mode": "fail-closed-before-stream",
            "rules": list(CONTENT_SCAN_RULES),
            "candidate_file_count": len(files),
            "candidate_total_bytes": sum(metadata.st_size for _, _, metadata in files),
            "included_file_count": manifest["file_count"],
            "included_total_bytes": manifest["total_bytes"],
            "excluded_sensitive_file_count": manifest["excluded_sensitive_file_count"],
        },
        "db_access": False,
        "host_mutation": False,
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "limits": {
            "max_files": MAX_FILES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
        },
    }

    with tarfile.open(fileobj=output, mode="w|gz", format=tarfile.PAX_FORMAT) as archive:
        for path, relative, metadata in included:
            info = tarfile.TarInfo(f"source/{relative}")
            info.size = metadata.st_size
            info.mode = stat.S_IMODE(metadata.st_mode)
            info.mtime = 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)
        _add_bytes(
            archive,
            "recovery-manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
        )
        _add_bytes(
            archive,
            "recovery-receipt.json",
            json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n",
        )


def docker_compose_labels(container: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
            "{{json .Config.Labels}}",
            container,
        ],
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
    args = parser.parse_args(argv)
    try:
        root, configs, project = parse_compose_labels(docker_compose_labels(args.container))
        files = collect_files(root, configs)
        stream_archive(root, project, files, sys.stdout.buffer, required_configs=configs)
    except (OSError, RecoveryError, subprocess.SubprocessError) as exc:
        print(f"STOP: V3 runtime recovery failed closed: {exc}", file=sys.stderr)
        return 1
    print(
        "V3 runtime recovery stream completed without DB access or host mutation",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
