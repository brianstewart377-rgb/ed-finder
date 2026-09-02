#!/usr/bin/env python3
"""Stream a fail-closed, non-secret V3 source recovery archive to stdout.

This helper is intentionally read-only: Docker is queried only for selected
Compose labels and every selected file is read from the resolved Compose source
root. The tar stream is written to stdout so the remote host is not mutated.

Every candidate file is content-scanned before any archive bytes are emitted.
Unsafe optional historical files are excluded with provenance-only metadata;
unsafe required Compose files fail the whole recovery. The exact bytes that pass
scanning are also the bytes hashed and archived, so a path cannot change between
validation and export.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
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
    ".env", ".git", "backup", "backups", "cert", "certs", "credential",
    "credentials", "data", "dump", "dumps", "id_rsa", "id_ed25519", "key",
    "keys", "log", "logs", "pgbackrest", "private", "secret", "secrets",
    "ssh", "token", "tokens", "volume", "volumes",
}
FORBIDDEN_FRAGMENTS = (
    "password", "passwd", "credential", "secret", "token", "private_key",
    "apikey", "api_key", "id_rsa", "id_ed25519",
)
COMPOSE_WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
COMPOSE_CONFIG_FILES_LABEL = "com.docker.compose.project.config_files"
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
SCHEMA = "edfinder-v3-runtime-recovery/v2"

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
STRUCTURED_KEY = r"[A-Za-z_][A-Za-z0-9_.-]*"
MAPPING_KEY_PREFIX = r"(?:^\s*|(?<!\$)[{,]\s*)"
QUOTED_ENV_ASSIGNMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{IDENTIFIER})\s*=\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)", re.MULTILINE,
)
BARE_ENV_ASSIGNMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{IDENTIFIER})\s*=\s*"
    r"(?P<value>\$\{[^}\r\n]*\}|[^\s,\"'\]\}]+)", re.MULTILINE,
)
QUOTED_MAPPING_ENV_RE = re.compile(
    rf"(?m)(?={MAPPING_KEY_PREFIX}(?P<keyquote>[\"']?)(?P<name>{STRUCTURED_KEY})"
    r"(?P=keyquote)\s*:\s*(?P<valquote>[\"'])(?P<value>.*?)(?P=valquote))",
)
BARE_MAPPING_ENV_RE = re.compile(
    rf"(?m)(?={MAPPING_KEY_PREFIX}(?P<keyquote>[\"']?)(?P<name>{STRUCTURED_KEY})"
    r"(?P=keyquote)\s*:(?![ \t]*[\"'])[ \t]*"
    r"(?P<value>\$\{[^}\r\n]*\}|[^,\}\]\r\n#]+))",
)
DOCKERFILE_ENV_SPACE_RE = re.compile(
    rf"(?im)^\s*ENV\s+(?P<name>{IDENTIFIER})\s+(?P<value>[^\r\n#]+)"
)
CREDENTIALED_URI_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]*:(?P<password>[^@\s/]+)@"
)
URI_QUERY_CREDENTIAL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"'<>]*[?&;]"
    r"(?:password|passwd|pwd|secret|token|api_?key)="
    r"(?P<password>[^&#;\s\"'<>]+)"
)
DSN_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)(?:^|[\s?&;])(?:password|passwd|pwd|secret|token|api_?key)\s*=\s*"
    r'''(?P<password>"[^"]*"|'[^']*'|[^\s;&\"']+)'''
)
SQL_PASSWORD_RE = re.compile(
    r"(?is)\b(?:ALTER|CREATE)\s+(?:ROLE|USER)\b[^;]*?\bPASSWORD\s*(?:=)?\s*"
    r"(?P<quote>[\"'])(?P<password>.*?)(?P=quote)"
)
SQL_DOLLAR_PASSWORD_RE = re.compile(
    r"(?is)\b(?:ALTER|CREATE)\s+(?:ROLE|USER)\b[^;]*?\bPASSWORD\s*(?:=)?\s*"
    r"(?P<tag>\$\$|\$[A-Za-z_][A-Za-z0-9_]*\$)(?P<password>.*?)(?P=tag)"
)
AUTHORIZATION_RE = re.compile(
    r'''(?im)["']?Authorization["']?\s*[:=]\s*'''
    r'''(?P<quote>["']?)(?P<scheme>Bearer|Basic)\s+'''
    r'''(?P<credential>[^\s"',\]]+)'''
)
STRUCTURED_ENV_NAME_RE = re.compile(
    rf'''^(?P<indent>[ \t]*)-\s*name\s*:\s*'''
    rf'''(?P<quote>["']?)(?P<name>{IDENTIFIER})(?P=quote)\s*(?:#.*)?$''',
    re.IGNORECASE,
)
STRUCTURED_ENV_VALUE_RE = re.compile(
    r'''^(?P<indent>[ \t]*)value\s*:\s*(?P<value>.+?)\s*(?:#.*)?$''',
    re.IGNORECASE,
)
STRUCTURED_ENV_VALUE_FROM_RE = re.compile(
    r'''^(?P<indent>[ \t]*)valueFrom\s*:''', re.IGNORECASE,
)
FLOW_OBJECT_RE = re.compile(r"\{[^{}\r\n]*\}")
FLOW_NAME_FIELD_RE = re.compile(
    rf'''(?i)(?:^|,)\s*["']?name["']?\s*:\s*'''
    rf'''(?P<quote>["']?)(?P<name>{IDENTIFIER})(?P=quote)(?=\s*(?:,|$))'''
)
FLOW_VALUE_FIELD_RE = re.compile(
    r'''(?i)(?:^|,)\s*["']?value["']?\s*:\s*'''
    r'''(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^,}]+))'''
)
COMMAND_OPTION_SPACE_RE = re.compile(
    r'''(?ix)(?<![A-Za-z0-9_-])--(?:password|passwd|pwd|secret|token|api[-_]?key)\b'''
    r'''[ \t]+(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<placeholder>\$\{[^}\r\n]*\})|(?P<bare>[^\s,;\]\}]+))'''
)
COMMAND_OPTION_ARRAY_RE = re.compile(
    r'''(?ix)["']--(?:password|passwd|pwd|secret|token|api[-_]?key)["']\s*,\s*'''
    r'''(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)')'''
)
K8S_SECRET_KIND_RE = re.compile(
    r'''(?mi)^\s*kind\s*:\s*["']?Secret["']?\s*(?:#.*)?$'''
)
K8S_SECRET_PAYLOAD_RE = re.compile(
    r'''(?mi)^\s*(?:data|stringData)\s*:'''
)
TOKEN_PATTERNS = (
    ("private-key-material", re.compile(
        r"-----BEGIN (?:ENCRYPTED |RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        re.IGNORECASE,
    )),
    ("openai-api-token", re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-api-token", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
CONTENT_SCAN_RULES = (
    "private-key-material", "recognized-api-token", "authorization-credential",
    "credentialed-uri-or-dsn", "credential-command-option",
    "non-placeholder-sensitive-assignment", "structured-name-value-environment-entry",
    "python-ast-sensitive-assignment", "kubernetes-secret-payload",
    "sql-password-statement", "exact-scanned-bytes-archived",
    "sensitive-file-digest-omitted",
)
URL_ENV_NAMES = {"DATABASE_URL", "REDIS_URL", "CACHE_URL", "CELERY_BROKER_URL"}
TOKEN_METRIC_WORDS = {
    "BUDGET", "BUDGETS", "CAP", "CAPACITY", "COUNT", "COUNTS", "EXPIRATION",
    "EXPIRY", "LENGTH", "LENGTHS", "LIMIT", "LIMITS", "MAX", "MIN", "RATE",
    "RATES", "SIZE", "SIZES", "TTL", "WINDOW", "WINDOWS",
}
NONSENSITIVE_REFERENCE_NAMES = {
    "SECRETKEYREF", "SECRETREF", "SECRETNAME", "SECRETKEYSELECTOR", "SECRETSOURCE",
}


@dataclass(frozen=True)
class ScannedFile:
    relative: str
    mode: int
    payload: bytes
    sha256: str


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


def _normalized_name(name: str) -> str:
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    punct_split = re.sub(r"[^A-Za-z0-9]+", "_", camel_split)
    return re.sub(r"_+", "_", punct_split).strip("_").upper()


def _name_is_sensitive(name: str) -> bool:
    upper = _normalized_name(name)
    compact = upper.replace("_", "")
    if compact in NONSENSITIVE_REFERENCE_NAMES:
        return False
    if upper in URL_ENV_NAMES or upper in {"OCTOPUS_DATA_KEY", "DATA_ENCRYPTION_KEY"}:
        return True
    if any(marker in upper for marker in (
        "PASSWORD", "PASSWD", "PRIVATE_KEY", "API_KEY", "APIKEY", "SECRET",
    )):
        return True
    if (
        upper == "PASS"
        or upper.endswith(("_PASS", "_PWD"))
        or "_PASS_" in upper
        or "_PWD_" in upper
    ):
        return True
    parts = [part for part in upper.split("_") if part]
    for index, part in enumerate(parts):
        if part != "TOKEN":
            continue
        previous = parts[index - 1] if index else None
        following = parts[index + 1] if index + 1 < len(parts) else None
        if previous in TOKEN_METRIC_WORDS or following in TOKEN_METRIC_WORDS:
            continue
        return True
    return False


def _jinja_reference_expression_is_safe(body: str) -> bool:
    reference = rf"{IDENTIFIER}(?:\.{IDENTIFIER})*"
    pipeline = [part.strip() for part in body.split("|")]
    if not pipeline or not re.fullmatch(reference, pipeline[0]):
        return False
    for filter_expression in pipeline[1:]:
        filter_match = re.fullmatch(
            rf"(?P<name>{IDENTIFIER})(?:\((?P<arguments>.*)\))?", filter_expression,
        )
        if not filter_match:
            return False
        arguments = filter_match.group("arguments")
        if arguments is None or not arguments.strip():
            continue
        argument = arguments.strip()
        if "," in argument:
            return False
        if filter_match.group("name").lower() == "default":
            quoted_default = re.fullmatch(
                r'''(?P<quote>['\"])(?P<literal>.*?)(?P=quote)''', argument,
            )
            if quoted_default:
                if quoted_default.group("literal"):
                    return False
                continue
            if re.fullmatch(reference, argument):
                continue
            return False
        if not re.fullmatch(reference, argument):
            return False
    return True


def _placeholder_value(value: str) -> bool:
    candidate = value.strip().strip("\"'")
    if not candidate:
        return True
    var_name = IDENTIFIER
    if re.fullmatch(rf"\$\{{{var_name}\}}", candidate):
        return True
    if re.fullmatch(rf"\$\{{{var_name}(?::?\?[^}}]*)\}}", candidate):
        return True
    if re.fullmatch(rf"\$\{{{var_name}(?::-|-)\}}", candidate):
        return True
    if re.fullmatch(rf"\${var_name}", candidate):
        return True
    jinja = re.fullmatch(r"\{\{(?P<body>[^{}]+)\}\}", candidate)
    if jinja:
        return _jinja_reference_expression_is_safe(jinja.group("body").strip())
    if re.fullmatch(
        r"<(?:redacted|placeholder|secret|password|token|[^>]*_here)>",
        candidate, re.IGNORECASE,
    ):
        return True
    if candidate.upper() in {
        "REDACTED", "PLACEHOLDER", "NOT_SET", "UNSET", "REPLACE_ME",
        "YOUR_SECRET_HERE", "YOUR_PASSWORD_HERE", "YOUR_TOKEN_HERE",
    }:
        return True
    if re.fullmatch(r"[*xX]{6,}", candidate):
        return True
    return False


def _unquoted_yaml_null(value: str) -> bool:
    candidate = value.strip()
    if not candidate or candidate.startswith(("\"", "'")):
        return False
    return candidate.lower() in {"null", "~"}


def _secret_file_reference(value: str) -> bool:
    candidate = value.strip().strip("\"'")
    return candidate.startswith(("/", "./", "../"))


def _credential_values(text: str) -> list[str]:
    values = [match.group("password") for match in CREDENTIALED_URI_RE.finditer(text)]
    values.extend(match.group("password") for match in URI_QUERY_CREDENTIAL_RE.finditer(text))
    values.extend(match.group("password") for match in DSN_CREDENTIAL_PARAM_RE.finditer(text))
    return values


def _assignment_value_is_safe(name: str, value: str) -> bool:
    if _placeholder_value(value):
        return True
    upper_name = _normalized_name(name)
    if upper_name.endswith("_FILE") and _secret_file_reference(value):
        return True
    if upper_name in URL_ENV_NAMES:
        candidate = value.strip().strip("\"'")
        credential_values = _credential_values(candidate)
        return not credential_values or all(_placeholder_value(item) for item in credential_values)
    return False


def _compose_secret_reference_collection(name: str, value: str) -> bool:
    return _normalized_name(name) == "SECRETS" and value.strip().startswith(("[", "{"))


def _scan_assignment_patterns(text: str, findings: set[str], *, include_equals: bool = True) -> None:
    if include_equals:
        for pattern in (QUOTED_ENV_ASSIGNMENT_RE, BARE_ENV_ASSIGNMENT_RE):
            for match in pattern.finditer(text):
                name = match.group("name")
                if _name_is_sensitive(name) and not _assignment_value_is_safe(name, match.group("value")):
                    findings.add("sensitive-environment-assignment")

    for match in QUOTED_MAPPING_ENV_RE.finditer(text):
        name = match.group("name")
        value = match.group("value")
        if _compose_secret_reference_collection(name, value):
            continue
        if _name_is_sensitive(name) and not _assignment_value_is_safe(name, value):
            findings.add("sensitive-environment-assignment")

    for match in BARE_MAPPING_ENV_RE.finditer(text):
        name = match.group("name")
        value = match.group("value")
        if _compose_secret_reference_collection(name, value):
            continue
        if not _name_is_sensitive(name) or _unquoted_yaml_null(value):
            continue
        if not _assignment_value_is_safe(name, value):
            findings.add("sensitive-environment-assignment")


def _scan_structured_yaml_environment(text: str, findings: set[str]) -> None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        name_match = STRUCTURED_ENV_NAME_RE.match(line)
        if not name_match:
            continue
        name = name_match.group("name")
        if not _name_is_sensitive(name):
            continue
        base_indent = len(name_match.group("indent").expandtabs(4))
        for next_line in lines[index + 1 : index + 8]:
            stripped = next_line.lstrip(" \t")
            next_indent = len(next_line[: len(next_line) - len(stripped)].expandtabs(4))
            if stripped.startswith("-") and next_indent <= base_indent:
                break
            if STRUCTURED_ENV_VALUE_FROM_RE.match(next_line):
                break
            value_match = STRUCTURED_ENV_VALUE_RE.match(next_line)
            if value_match:
                value = value_match.group("value")
                if not _unquoted_yaml_null(value) and not _assignment_value_is_safe(name, value):
                    findings.add("sensitive-environment-assignment")
                break

    for match in FLOW_OBJECT_RE.finditer(text):
        block = match.group(0)[1:-1]
        name_match = FLOW_NAME_FIELD_RE.search(block)
        value_match = FLOW_VALUE_FIELD_RE.search(block)
        if not name_match or not value_match:
            continue
        name = name_match.group("name")
        if not _name_is_sensitive(name):
            continue
        value = value_match.group("double")
        if value is None:
            value = value_match.group("single")
        if value is None:
            value = value_match.group("bare") or ""
            if _unquoted_yaml_null(value):
                continue
        if not _assignment_value_is_safe(name, value):
            findings.add("sensitive-environment-assignment")


def _scan_structured_json_environment(text: str, findings: set[str]) -> None:
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return

    def walk(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            literal = value.get("value")
            if isinstance(name, str) and _name_is_sensitive(name) and literal is not None:
                if isinstance(literal, (str, int, float, bool)) and not _assignment_value_is_safe(name, str(literal)):
                    findings.add("sensitive-environment-assignment")
            for key, nested in value.items():
                if isinstance(key, str) and _name_is_sensitive(key):
                    if _normalized_name(key) == "SECRETS" and isinstance(nested, (list, dict)):
                        pass
                    elif nested is not None and isinstance(nested, (str, int, float, bool)):
                        if not _assignment_value_is_safe(key, str(nested)):
                            findings.add("sensitive-environment-assignment")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(document)


def _python_target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, ast.Subscript):
        key = target.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return [key.value]
        return []
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_python_target_names(item))
        return names
    return []


def _python_retrieval_call_is_safe(name: str, value: ast.Call) -> bool:
    function_name = ""
    if isinstance(value.func, ast.Name):
        function_name = value.func.id
    elif isinstance(value.func, ast.Attribute):
        function_name = value.func.attr
    if function_name.lower() not in {"get", "getenv"}:
        return True
    defaults = list(value.args[1:])
    defaults.extend(keyword.value for keyword in value.keywords if keyword.arg in {"default", "fallback"})
    for default in defaults:
        if isinstance(default, ast.Constant):
            if default.value is None:
                continue
            if isinstance(default.value, (str, int, float, bool)) and not _assignment_value_is_safe(
                name, str(default.value)
            ):
                return False
    return True


def _python_assignment_value_is_safe(name: str, value: ast.expr) -> bool:
    if isinstance(value, ast.Constant):
        if value.value is None:
            return True
        if isinstance(value.value, (str, int, float, bool)):
            return _assignment_value_is_safe(name, str(value.value))
        return True
    if isinstance(value, ast.JoinedStr):
        for item in value.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value:
                if not _placeholder_value(item.value):
                    return False
        return True
    if isinstance(value, ast.Call):
        return _python_retrieval_call_is_safe(name, value)
    return True


def _scan_python_assignments(text: str, findings: set[str]) -> None:
    try:
        document = ast.parse(text)
    except SyntaxError:
        findings.add("python-syntax-unscannable")
        return
    for node in ast.walk(document):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None:
            continue
        names: list[str] = []
        for target in targets:
            names.extend(_python_target_names(target))
        for name in names:
            if _name_is_sensitive(name) and not _python_assignment_value_is_safe(name, value):
                findings.add("sensitive-environment-assignment")


def _command_credential(match: re.Match[str]) -> str:
    groups = match.groupdict()
    return (
        groups.get("double")
        or groups.get("single")
        or groups.get("placeholder")
        or groups.get("bare")
        or ""
    )


def _scan_command_options(text: str, findings: set[str]) -> None:
    for pattern in (COMMAND_OPTION_SPACE_RE, COMMAND_OPTION_ARRAY_RE):
        for match in pattern.finditer(text):
            credential = _command_credential(match)
            if credential and not _placeholder_value(credential):
                findings.add("credential-command-option")


def _scan_text(text: str, relative: str) -> tuple[str, ...]:
    findings: set[str] = set()
    for category, pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            findings.add(category)
    for match in AUTHORIZATION_RE.finditer(text):
        if not _placeholder_value(match.group("credential")):
            findings.add("authorization-credential")
    for pattern in (CREDENTIALED_URI_RE, URI_QUERY_CREDENTIAL_RE):
        for match in pattern.finditer(text):
            if not _placeholder_value(match.group("password")):
                findings.add("credentialed-uri")
    for line in text.splitlines():
        if not (
            re.search(r"(?i)\b(?:host|dbname|user|port|sslmode)\s*=", line)
            or re.search(r"(?i)\b[A-Za-z0-9_]*DSN[A-Za-z0-9_]*\b", line)
        ):
            continue
        for match in DSN_CREDENTIAL_PARAM_RE.finditer(line):
            password = match.group("password").strip("\"'")
            if not _placeholder_value(password):
                findings.add("credentialed-dsn")
    _scan_command_options(text, findings)

    relative_path = PurePosixPath(relative)
    is_python = relative_path.suffix.lower() == ".py"
    _scan_assignment_patterns(text, findings, include_equals=not is_python)

    if relative_path.name.lower().startswith(BUILD_FILE_PREFIXES):
        for match in DOCKERFILE_ENV_SPACE_RE.finditer(text):
            name = match.group("name")
            if _name_is_sensitive(name) and not _assignment_value_is_safe(name, match.group("value")):
                findings.add("sensitive-environment-assignment")

    suffix = relative_path.suffix.lower()
    if suffix in {".yml", ".yaml"}:
        _scan_structured_yaml_environment(text, findings)
        if K8S_SECRET_KIND_RE.search(text) and K8S_SECRET_PAYLOAD_RE.search(text):
            findings.add("kubernetes-secret-payload")
    elif suffix == ".json":
        _scan_structured_json_environment(text, findings)
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            document = None
        if isinstance(document, dict) and str(document.get("kind", "")).lower() == "secret":
            if "data" in document or "stringData" in document:
                findings.add("kubernetes-secret-payload")
    elif suffix == ".py":
        _scan_python_assignments(text, findings)

    if suffix == ".sql":
        for pattern in (SQL_PASSWORD_RE, SQL_DOLLAR_PASSWORD_RE):
            for match in pattern.finditer(text):
                if not _placeholder_value(match.group("password")):
                    findings.add("sql-password-statement")
    return tuple(sorted(findings))


def _read_scannable_bytes(
    path: Path,
    relative: str,
    expected_metadata: os.stat_result,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RecoveryError(f"Unable to open selected file safely: {relative}") from exc
    with os.fdopen(fd, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise RecoveryError(f"Selected path is no longer a regular file: {relative}")
        if (metadata.st_dev, metadata.st_ino) != (expected_metadata.st_dev, expected_metadata.st_ino):
            raise RecoveryError(f"Selected file identity changed during recovery: {relative}")
        payload = handle.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise RecoveryError(f"Selected file exceeds per-file limit during scan: {relative}")
    return payload, metadata


def scan_selected_files(
    files: Iterable[tuple[Path, str, os.stat_result]],
    required_configs: Iterable[Path],
) -> tuple[list[ScannedFile], list[dict[str, object]]]:
    required = {os.path.abspath(path) for path in required_configs}
    included: list[ScannedFile] = []
    excluded: list[dict[str, object]] = []
    scanned_total = 0
    for path, relative, expected_metadata in files:
        payload, metadata = _read_scannable_bytes(path, relative, expected_metadata)
        scanned_total += len(payload)
        if scanned_total > MAX_TOTAL_BYTES:
            raise RecoveryError("Selected files exceed total-size limit during scan")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecoveryError(f"Selected text file is not valid UTF-8: {relative}") from exc
        findings = _scan_text(text, relative)
        mode = stat.S_IMODE(metadata.st_mode)
        if not findings:
            included.append(ScannedFile(
                relative=relative, mode=mode, payload=payload,
                sha256=hashlib.sha256(payload).hexdigest(),
            ))
            continue
        if os.path.abspath(path) in required:
            categories = ", ".join(findings)
            raise RecoveryError(
                f"Required Compose config contains sensitive content: {relative} ({categories})"
            )
        excluded.append({
            "path": relative,
            "size": len(payload),
            "mode": f"{mode:04o}",
            "findings": list(findings),
        })
    return included, excluded


def build_manifest(
    files: Iterable[ScannedFile],
    excluded_sensitive_files: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    file_list = list(files)
    entries = [
        {"path": item.relative, "size": len(item.payload), "mode": f"{item.mode:04o}", "sha256": item.sha256}
        for item in file_list
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


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes, mode: int = 0o644) -> None:
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
    scanned_total = int(manifest["total_bytes"]) + sum(int(entry["size"]) for entry in excluded)
    receipt = {
        "schema": SCHEMA,
        "operation": "recover-v3-runtime-contract",
        "container": CONTAINER_NAME,
        "source_root": str(root),
        "compose_project": project,
        "docker_metadata_fields": [
            COMPOSE_PROJECT_LABEL, COMPOSE_WORKING_DIR_LABEL, COMPOSE_CONFIG_FILES_LABEL,
        ],
        "docker_inspect_env": False,
        "source_content_scan": {
            "performed": True,
            "mode": "fail-closed-before-stream",
            "rules": list(CONTENT_SCAN_RULES),
            "candidate_file_count": len(files),
            "candidate_total_bytes": scanned_total,
            "included_file_count": manifest["file_count"],
            "included_total_bytes": manifest["total_bytes"],
            "excluded_sensitive_file_count": manifest["excluded_sensitive_file_count"],
            "archive_uses_exact_scanned_bytes": True,
            "excluded_sensitive_content_digests": False,
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
        for item in included:
            _add_bytes(archive, f"source/{item.relative}", item.payload, mode=item.mode)
        _add_bytes(
            archive, "recovery-manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
        )
        _add_bytes(
            archive, "recovery-receipt.json",
            json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n",
        )


def docker_compose_labels(container: str) -> str:
    result = subprocess.run(
        [
            "docker", "inspect", "--type", "container", "--format",
            "{{json .Config.Labels}}", container,
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
    print("V3 runtime recovery stream completed without DB access or host mutation", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
