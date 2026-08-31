#!/usr/bin/env python3
"""Stream a fail-closed, non-secret V3 source recovery archive to stdout.

This helper is intentionally read-only: Docker is queried only for selected
Compose labels and every selected file is read from the resolved Compose source
root.  The tar stream is written to stdout so the remote host is not mutated.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import re
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
REDACTION_SENTINEL = "REDACTED"
SENSITIVE_NAMES = re.compile(
    r"(?i)(?:^|_)(?:password|passwd|secret|token|api_key|private_key|secret_access_key)$"
)
URI_RE = re.compile(
    r"(?i)\b(postgresql|postgres|redis|rediss)://([^\s/@:]*):([^\s/@]+)@"
)
ASSIGNMENT_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:-\s*)?(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|SECRET_ACCESS_KEY)\s*(?:=|:)\s*)(?P<quote>['\"]?)(?P<value>[^\r\n'\"]+)(?P=quote)(?P<tail>\s*(?:#.*)?)$"
)
PEM_PRIVATE_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
)
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


class RecoveryError(RuntimeError):
    """A safety contract failed; no partial archive should be trusted."""


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative: str
    metadata: os.stat_result


@dataclass(frozen=True)
class PreparedFile:
    source: SourceFile
    disposition: str
    reason_codes: tuple[str, ...]
    original_sha256: str
    payload: bytes | None


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
        raise RecoveryError(
            "Compose working directory label is missing or not absolute"
        )
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
    return relative.suffix.lower() in ALLOWED_SUFFIXES or name.startswith(
        BUILD_FILE_PREFIXES
    )


def collect_files(root: Path, required_configs: Iterable[Path]) -> list[SourceFile]:
    root = root.resolve(strict=True)
    required = {path.resolve(strict=True) for path in required_configs}
    selected: list[SourceFile] = []
    total = 0
    for directory, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            path = directory_path / name
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if path.is_symlink():
                raise RecoveryError(
                    f"Source tree contains a directory symlink: {relative}"
                )
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
                raise RecoveryError(
                    f"Selected path escapes source root: {relative}"
                ) from exc
            if lst.st_size > MAX_FILE_BYTES:
                raise RecoveryError(f"Selected file exceeds per-file limit: {relative}")
            total += lst.st_size
            if total > MAX_TOTAL_BYTES:
                raise RecoveryError("Selected files exceed total-size limit")
            selected.append(SourceFile(path, relative.as_posix(), lst))
            if len(selected) > MAX_FILES:
                raise RecoveryError("Selected files exceed file-count limit")
    selected_paths = {item.path.resolve(strict=True) for item in selected}
    if not required.issubset(selected_paths):
        raise RecoveryError(
            "A labeled Compose config file was rejected by the allowlist"
        )
    return selected


def _is_template(value: str) -> bool:
    value = value.strip().strip("'\"")
    return (
        not value
        or value.upper()
        in {"REDACTED", "CHANGEME", "CHANGE_ME", "PLACEHOLDER", "EXAMPLE"}
        or re.fullmatch(r"\$\{[^}\n]+\}|\$[A-Za-z_][A-Za-z0-9_]*", value) is not None
        or re.fullmatch(r"\$\{\{[^\n]+\}\}|\{\{[^\n]+\}\}|<[^<>\n]+>", value)
        is not None
    )


def _excluded_reason(text: str) -> str | None:
    if PEM_PRIVATE_RE.search(text):
        return "private_key_block"
    if any(pattern.search(text) for pattern in TOKEN_PATTERNS):
        return "recognized_token"
    return None


def _redact_uri(match: re.Match[str]) -> str:
    if _is_template(match.group(2)) and _is_template(match.group(3)):
        return match.group(0)
    return f"{match.group(1)}://{REDACTION_SENTINEL}:{REDACTION_SENTINEL}@"


def _sanitize_text(text: str) -> tuple[str, bool]:
    updated = URI_RE.sub(_redact_uri, text)

    def redact_assignment(match: re.Match[str]) -> str:
        if _is_template(match.group("value")):
            return match.group(0)
        return f"{match.group('prefix')}{match.group('quote')}{REDACTION_SENTINEL}{match.group('quote')}{match.group('tail')}"

    updated = ASSIGNMENT_RE.sub(redact_assignment, updated)
    return updated, updated != text


def _sanitize_json(
    value: object, environment: bool = False
) -> tuple[object, bool, bool]:
    changed = False
    found_environment = False
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            child_environment = key.lower() in {"env", "environment"}
            found_environment |= child_environment
            if (
                SENSITIVE_NAMES.search(key)
                and isinstance(child, str)
                and not _is_template(child)
            ):
                result[key], changed = REDACTION_SENTINEL, True
            else:
                result[key], child_changed, child_found = _sanitize_json(
                    child, environment or child_environment
                )
                changed |= child_changed
                found_environment |= child_found
        return result, changed, found_environment
    if isinstance(value, list):
        result_list: list[object] = []
        for child in value:
            if environment and isinstance(child, str) and "=" in child:
                name, raw = child.split("=", 1)
                if SENSITIVE_NAMES.search(name) and not _is_template(raw):
                    result_list.append(f"{name}={REDACTION_SENTINEL}")
                    changed = True
                    continue
            replacement, child_changed, child_found = _sanitize_json(child, environment)
            result_list.append(replacement)
            changed |= child_changed
            found_environment |= child_found
        return result_list, changed, found_environment
    if isinstance(value, str):
        updated, string_changed = _sanitize_text(value)
        return updated, string_changed, False
    return value, False, False


def _json_has_environment(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in {"env", "environment"} or _json_has_environment(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_json_has_environment(child) for child in value)
    return False


def _unsafe(text: str) -> bool:
    if _excluded_reason(text):
        return True
    if any(
        not (_is_template(match.group(2)) and _is_template(match.group(3)))
        for match in URI_RE.finditer(text)
    ):
        return True
    return any(
        not _is_template(match.group("value")) for match in ASSIGNMENT_RE.finditer(text)
    )


def preflight_files(
    files: list[SourceFile], required_configs: Iterable[Path]
) -> list[PreparedFile]:
    required = {path.resolve(strict=True) for path in required_configs}
    prepared: list[PreparedFile] = []
    for source in files:
        try:
            original = source.path.read_bytes()
        except OSError as exc:
            raise RecoveryError(
                f"Unable to read selected file: {source.relative}"
            ) from exc
        after = source.path.lstat()
        before = source.metadata
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise RecoveryError(
                f"Selected file changed during preflight: {source.relative}"
            )
        digest = hashlib.sha256(original).hexdigest()
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecoveryError(
                f"Selected text file is not valid UTF-8: {source.relative}"
            ) from exc
        parsed: object | None = None
        environment_material = False
        if source.path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RecoveryError(
                    f"Selected JSON file is invalid: {source.relative}"
                ) from exc
            environment_material = _json_has_environment(parsed)
        reason = _excluded_reason(text)
        if reason:
            if source.path.resolve(strict=True) in required:
                raise RecoveryError(
                    f"Required Compose config contains non-redactable material: {source.relative}"
                )
            reasons = (
                (reason, "environment_material_present")
                if environment_material
                else (reason,)
            )
            prepared.append(PreparedFile(source, "excluded", reasons, digest, None))
            continue
        if source.path.suffix.lower() == ".json":
            assert parsed is not None
            sanitized, changed, environment_material = _sanitize_json(parsed)
            safe_text = (
                json.dumps(sanitized, indent=2, sort_keys=True) + "\n"
                if changed
                else text
            )
            if changed:
                try:
                    json.loads(safe_text)
                except (
                    json.JSONDecodeError
                ) as exc:  # pragma: no cover - defensive invariant
                    raise RecoveryError(
                        f"Sanitized JSON became invalid: {source.relative}"
                    ) from exc
        else:
            safe_text, changed = _sanitize_text(text)
        if _unsafe(safe_text):
            raise RecoveryError(
                f"Selected file remained unsafe after sanitization: {source.relative}"
            )
        reasons = (["high_confidence_secret_redacted"] if changed else []) + (
            ["environment_material_present"] if environment_material else []
        )
        prepared.append(
            PreparedFile(
                source,
                "redacted" if changed else "verbatim",
                tuple(reasons),
                digest,
                safe_text.encode(),
            )
        )
    return prepared


def build_manifest(files: list[PreparedFile]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for item in files:
        original = {
            "path": item.source.relative,
            "mode": f"{stat.S_IMODE(item.source.metadata.st_mode):04o}",
            "size": item.source.metadata.st_size,
            "sha256": item.original_sha256,
        }
        entry: dict[str, object] = {
            "original": original,
            "disposition": item.disposition,
            "reason_codes": list(item.reason_codes),
        }
        if item.payload is not None:
            entry["archive"] = {
                "path": f"source/{item.source.relative}",
                "mode": original["mode"],
                "size": len(item.payload),
                "sha256": hashlib.sha256(item.payload).hexdigest(),
            }
        entries.append(entry)
    counts = {
        name: sum(item.disposition == name for item in files)
        for name in ("verbatim", "redacted", "excluded")
    }
    return {
        "schema": SCHEMA,
        "selected_file_count": len(entries),
        "original_total_bytes": sum(item.source.metadata.st_size for item in files),
        "archive_file_count": counts["verbatim"] + counts["redacted"],
        "archive_total_bytes": sum(len(item.payload or b"") for item in files),
        "disposition_counts": counts,
        "files": entries,
    }


def _add_bytes(
    archive: tarfile.TarFile, name: str, payload: bytes, mode: int = 0o644
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def stream_archive(
    root: Path,
    project: str,
    files: list[SourceFile],
    output: BinaryIO,
    required_configs: Iterable[Path] = (),
) -> None:
    prepared = preflight_files(files, required_configs)
    manifest = build_manifest(prepared)
    counts = manifest["disposition_counts"]
    receipt = {
        "schema": SCHEMA,
        "operation": "recover-v3-runtime-contract",
        "container": CONTAINER_NAME,
        "source_root": str(root),
        "compose_project": project,
        "live_docker_metadata_fields_queried": [
            COMPOSE_PROJECT_LABEL,
            COMPOSE_WORKING_DIR_LABEL,
            COMPOSE_CONFIG_FILES_LABEL,
        ],
        "live_docker_environment_queried": False,
        "source_files_with_environment_material": sum(
            "environment_material_present" in item.reason_codes for item in prepared
        ),
        "source_environment_files_redacted": sum(
            item.disposition == "redacted"
            and "environment_material_present" in item.reason_codes
            for item in prepared
        ),
        "source_environment_files_excluded": sum(
            item.disposition == "excluded"
            and "environment_material_present" in item.reason_codes
            for item in prepared
        ),
        "db_access": False,
        "host_mutation": False,
        "selected_file_count": manifest["selected_file_count"],
        "archive_file_count": manifest["archive_file_count"],
        "original_total_bytes": manifest["original_total_bytes"],
        "archive_total_bytes": manifest["archive_total_bytes"],
        "disposition_counts": counts,
        "limits": {
            "max_files": MAX_FILES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
        },
    }
    metadata = [
        json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
        for value in (manifest, receipt)
    ]
    for item in prepared:
        if item.payload is not None and _unsafe(item.payload.decode("utf-8")):
            raise RecoveryError(f"Final payload scan failed: {item.source.relative}")
    if any(_unsafe(payload.decode()) for payload in metadata):
        raise RecoveryError("Recovery metadata failed final payload scan")
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive:
            for item in prepared:
                if item.payload is not None:
                    _add_bytes(
                        archive,
                        f"source/{item.source.relative}",
                        item.payload,
                        stat.S_IMODE(item.source.metadata.st_mode),
                    )
            _add_bytes(archive, "recovery-manifest.json", metadata[0])
            _add_bytes(archive, "recovery-receipt.json", metadata[1])


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
        root, configs, project = parse_compose_labels(
            docker_compose_labels(args.container)
        )
        files = collect_files(root, configs)
        stream_archive(root, project, files, sys.stdout.buffer, configs)
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
