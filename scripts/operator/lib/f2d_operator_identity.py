#!/usr/bin/env python3
"""Compute and verify the content identity of the F2d operator surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import NoReturn


MANIFEST_RELATIVE_PATH = "deploy/v3-production/f2d-operator-code.txt"
ATTESTED_ENVIRONMENT_VARIABLE = "F2D_OPERATOR_CODE_SHA256_ATTESTED"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PATH_RE = re.compile(r"[A-Za-z0-9._+/@-]+\Z")
_REQUIREMENT_RE = re.compile(r"requirement:psycopg\[binary\]==[0-9]+\.[0-9]+\.[0-9]+\Z")


class OperatorIdentityError(ValueError):
    """A named, fail-closed F2d operator identity refusal."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        self.reason = reason
        self.detail = detail
        message = reason if detail is None else f"{reason}:{detail}"
        super().__init__(message)


def _refuse(reason: str, detail: str | None = None) -> NoReturn:
    raise OperatorIdentityError(reason, detail)


def _require_regular_readable_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        _refuse("listed_path_missing", label)
    except OSError as exc:
        _refuse("listed_path_unreadable", f"{label}:{exc.strerror or exc}")
    if stat.S_ISLNK(metadata.st_mode):
        _refuse("listed_path_symlink", label)
    if not stat.S_ISREG(metadata.st_mode):
        _refuse("listed_path_not_regular", label)
    if metadata.st_mode & 0o444 == 0:
        _refuse("listed_path_unreadable", label)


def _read_manifest(repo_root: Path) -> list[str]:
    manifest_path = repo_root / MANIFEST_RELATIVE_PATH
    _require_regular_readable_file(manifest_path, MANIFEST_RELATIVE_PATH)
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _refuse("manifest_unreadable", str(exc))

    entries: list[str] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line or line.startswith("#"):
            continue
        if line != line.strip():
            _refuse("manifest_malformed", f"line_{line_number}:surrounding_whitespace")
        if line.startswith("requirement:"):
            if not _REQUIREMENT_RE.fullmatch(line):
                _refuse("manifest_malformed", f"line_{line_number}:invalid_requirement")
        else:
            if not _PATH_RE.fullmatch(line):
                _refuse("manifest_malformed", f"line_{line_number}:invalid_path")
            pure_path = PurePosixPath(line)
            if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
                _refuse("manifest_malformed", f"line_{line_number}:unsafe_path")
        entries.append(line)

    if not entries:
        _refuse("manifest_empty")
    if len(entries) != len(set(entries)):
        _refuse("manifest_duplicate_entry")
    if entries != sorted(entries):
        _refuse("manifest_not_sorted")
    if MANIFEST_RELATIVE_PATH not in entries:
        _refuse("manifest_missing_self_entry")
    return entries


def manifest_entries(repo_root: Path | str) -> tuple[str, ...]:
    """Return the validated, ordered active entries in the F2d manifest."""

    root = Path(repo_root)
    if not root.is_dir():
        _refuse("repository_root_invalid", os.fspath(root))
    return tuple(_read_manifest(root))


def _sha256_file(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        _refuse("listed_path_unreadable", f"{label}:{exc.strerror or exc}")
    return digest.hexdigest()


def compute_operator_code_sha256(repo_root: Path | str) -> str:
    """Return SHA-256 of canonical ``[entry, content SHA-256]`` JSON pairs."""

    root = Path(repo_root)
    entries = manifest_entries(root)
    pairs: list[list[str]] = []
    for entry in entries:
        if entry.startswith("requirement:"):
            entry_sha256 = hashlib.sha256(entry.encode("utf-8")).hexdigest()
        else:
            path = root / entry
            _require_regular_readable_file(path, entry)
            entry_sha256 = _sha256_file(path, entry)
        pairs.append([entry, entry_sha256])
    canonical = json.dumps(pairs, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def require_operator_code_identity(
    repo_root: Path | str,
    attested: str | None = None,
) -> str:
    """Compute the identity and require an exact valid release attestation."""

    expected = attested if attested is not None else os.environ.get(ATTESTED_ENVIRONMENT_VARIABLE)
    if expected is None or expected == "":
        _refuse("attested_identity_missing")
    if _SHA256_RE.fullmatch(expected) is None:
        _refuse("attested_identity_malformed")
    actual = compute_operator_code_sha256(repo_root)
    if actual != expected:
        _refuse("attested_identity_mismatch", f"expected={expected}:actual={actual}")
    return actual


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compute = subparsers.add_parser("compute", help="print the checkout identity")
    compute.add_argument("repo_root", type=Path)
    verify = subparsers.add_parser("verify", help="verify the attested checkout identity")
    verify.add_argument("repo_root", type=Path)
    verify.add_argument("attested", nargs="?", help=f"defaults to {ATTESTED_ENVIRONMENT_VARIABLE}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "compute":
            identity = compute_operator_code_sha256(args.repo_root)
        else:
            identity = require_operator_code_identity(args.repo_root, args.attested)
    except OperatorIdentityError as exc:
        print(f"f2d operator identity refusal: {exc}", file=sys.stderr)
        return 64
    print(identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
