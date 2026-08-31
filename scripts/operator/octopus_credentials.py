#!/usr/bin/env python3
"""Strict, non-executing Octopus integration credential transfer codec."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

ALLOWLIST = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_APP_CLIENT_ID",
    "GITHUB_APP_CLIENT_SECRET",
    "NEXT_PUBLIC_GITHUB_APP_SLUG",
    "GITHUB_STATE_SECRET",
)
REQUIRED = frozenset(ALLOWLIST[2:])
MAX_VALUE = 64 * 1024
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
PEM = re.compile(
    r"^-----BEGIN (?:RSA |EC )?PRIVATE KEY-----\n"
    r"[A-Za-z0-9+/=\n\r]+\n-----END (?:RSA |EC )?PRIVATE KEY-----\n?$"
)


class Invalid(ValueError):
    pass


def _quoted(lines: list[str], index: int, value: str, quote: str) -> tuple[str, int]:
    chunks: list[str] = []
    current = value[1:]
    while True:
        escaped = False
        for pos, char in enumerate(current):
            if char == quote and (quote == "'" or not escaped):
                if current[pos + 1 :].strip():
                    raise Invalid("unexpected content after quoted value")
                chunks.append(current[:pos])
                raw = "\n".join(chunks)
                if quote == "'":
                    return raw, index
                # Deliberately limited: no shell/variable expansion.
                return re.sub(
                    r"\\([\\\"nrt])",
                    lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m[1], m[1]),
                    raw,
                ), index
            escaped = char == "\\" and not escaped
        chunks.append(current)
        index += 1
        if index >= len(lines):
            raise Invalid("unterminated quoted value")
        current = lines[index]


def parse_dotenv(path: Path) -> dict[str, str]:
    try:
        raw = path.read_bytes()
        if b"\0" in raw:
            raise Invalid("NUL byte is forbidden")
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Invalid("dotenv must be UTF-8") from exc
    lines = text.replace("\r\n", "\n").split("\n")
    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[:1].isspace() or "=" not in line:
            raise Invalid(f"malformed dotenv line {i}")
        key, raw_value = line.split("=", 1)
        if not NAME.fullmatch(key):
            raise Invalid(f"invalid variable name on line {i}")
        allowlisted = key in ALLOWLIST
        if raw_value.startswith(("'", '"')):
            value, end = _quoted(lines, i - 1, raw_value, raw_value[0])
            i = end + 1
        else:
            # Non-allowlisted settings are deliberately ignored rather than
            # interpreted. They may legitimately contain Compose/shell-style
            # template syntax; only copied credential values must be strict
            # non-executing literals.
            if allowlisted and (
                raw_value != raw_value.strip() or any(c in raw_value for c in "`$")
            ):
                raise Invalid(f"unsafe unquoted value for key {key}")
            value = raw_value
        if allowlisted:
            if key in result:
                raise Invalid(f"duplicate allowlisted key: {key}")
            if not value:
                raise Invalid(f"empty required value: {key}")
            if len(value.encode()) > MAX_VALUE:
                raise Invalid(f"oversized value for key: {key}")
            result[key] = value
    return result


def validate(values: dict[str, str]) -> None:
    unknown = set(values) - set(ALLOWLIST)
    if unknown:
        raise Invalid(f"unexpected key: {sorted(unknown)[0]}")
    missing = REQUIRED - set(values)
    if missing:
        raise Invalid(f"missing required key: {sorted(missing)[0]}")
    if not values["GITHUB_APP_ID"].isdigit():
        raise Invalid("invalid type for key: GITHUB_APP_ID")
    pem = values["GITHUB_APP_PRIVATE_KEY"]
    if len(re.findall(r"-----BEGIN ", pem)) != 1 or not PEM.fullmatch(pem):
        raise Invalid("invalid PEM shape for key: GITHUB_APP_PRIVATE_KEY")
    for key, value in values.items():
        if not value or len(value.encode()) > MAX_VALUE or "\0" in value:
            raise Invalid(f"invalid size for key: {key}")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check(source: Path) -> None:
    """Validate the reusable integration credential contract without emitting values."""
    values = parse_dotenv(source)
    validate(values)
    print("integration_credentials_valid: true")
    print(f"provider_openai_present: {'true' if 'OPENAI_API_KEY' in values else 'false'}")
    print(f"provider_anthropic_present: {'true' if 'ANTHROPIC_API_KEY' in values else 'false'}")


def export(source: Path, output: Path, htpasswd: Path | None) -> None:
    values = parse_dotenv(source)
    validate(values)
    document: dict[str, object] = {"schema": 1, "integrations": values}
    if htpasswd and htpasswd.exists():
        data = htpasswd.read_bytes()
        if len(data) > MAX_VALUE or b"\0" in data or not data.endswith(b"\n"):
            raise Invalid("invalid ui.htpasswd")
        document["ui_htpasswd"] = data.decode("utf-8")
    atomic_write(
        output,
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )


def merge(payload: Path, env_path: Path, htpasswd_path: Path) -> None:
    doc = json.loads(payload.read_text(encoding="utf-8"))
    if set(doc) - {"schema", "integrations", "ui_htpasswd"} or doc.get("schema") != 1:
        raise Invalid("invalid transfer schema")
    values = doc.get("integrations")
    if not isinstance(values, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in values.items()
    ):
        raise Invalid("invalid integrations object")
    validate(values)
    parse_dotenv(env_path)
    # Preserve every target value except allowlisted integrations; fresh local secrets never travel.
    rendered = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not ("=" in line and line.split("=", 1)[0] in ALLOWLIST)
    ]
    for key in ALLOWLIST:
        if key in values:
            value = (
                values[key]
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            rendered.append(f'{key}="{value}"')
    atomic_write(env_path, ("\n".join(rendered) + "\n").encode())
    if "ui_htpasswd" in doc:
        value = doc["ui_htpasswd"]
        if (
            not isinstance(value, str)
            or len(value.encode()) > MAX_VALUE
            or "\0" in value
        ):
            raise Invalid("invalid ui.htpasswd")
        atomic_write(htpasswd_path, value.encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("--source", type=Path, required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--source", type=Path, required=True)
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--htpasswd", type=Path)
    mer = sub.add_parser("merge")
    mer.add_argument("--payload", type=Path, required=True)
    mer.add_argument("--env", type=Path, required=True)
    mer.add_argument("--htpasswd", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            check(args.source)
        elif args.command == "export":
            export(args.source, args.output, args.htpasswd)
        else:
            merge(args.payload, args.env, args.htpasswd)
    except (Invalid, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
