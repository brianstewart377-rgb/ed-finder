#!/usr/bin/env python3
"""Create and strictly verify V3 application release manifests.

This tool never contacts a registry, host, or database. Image digests come from
the CI build action; schema identity comes only from the reviewed SQL tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA = "ed-finder/v3-application-release/v1"
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REPOSITORIES = {
    "backend": "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend",
    "web": "ghcr.io/brianstewart377-rgb/ed-finder/v3-web",
}
COMPATIBILITY_STATUSES = {
    "unknown",
    "exact",
    "backward-compatible",
    "incompatible",
}
SENSITIVE_TEXT = re.compile(
    r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)"
)
URI_USERINFO = re.compile(r"[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@", re.I)


class ManifestError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def migration_set(root: Path = ROOT) -> dict[str, Any]:
    manifest_path = root / "sql" / "migration-manifest.txt"
    manifest_bytes = manifest_path.read_bytes()
    entries: list[dict[str, str]] = []

    for raw_line in manifest_bytes.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        filename, separator, raw_mode = line.partition("|")
        mode = raw_mode if separator else "auto"
        if not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", filename):
            raise ManifestError(f"unsafe migration manifest entry: {filename!r}")
        if mode not in {"auto", "manual"}:
            raise ManifestError(f"unsupported migration mode for {filename}: {mode!r}")
        migration_path = root / "sql" / filename
        if not migration_path.is_file():
            raise ManifestError(f"migration file is missing: sql/{filename}")
        entries.append(
            {
                "path": f"sql/{filename}",
                "mode": mode,
                "sha256": _sha256(migration_path.read_bytes()),
            }
        )

    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {
        "algorithm": "sha256",
        "identity": f"sha256:{_sha256(canonical)}",
        "manifest_path": "sql/migration-manifest.txt",
        "manifest_sha256": _sha256(manifest_bytes),
        "entries": entries,
    }


def _validate_image(role: str, value: object) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"images.{role} must be a string")
    expected_prefix = f"{IMAGE_REPOSITORIES[role]}@"
    if not value.startswith(expected_prefix) or not SHA256.fullmatch(
        value.removeprefix(expected_prefix)
    ):
        raise ManifestError(
            f"images.{role} must be {expected_prefix}sha256:<64 lowercase hex>"
        )
    return value


def _exact_keys(value: object, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{location} must be an object")
    actual = set(value)
    if actual != expected:
        raise ManifestError(
            f"{location} keys must be exactly {sorted(expected)}; got {sorted(actual)}"
        )
    return value


def validate_manifest(
    value: object,
    *,
    purpose: str = "release",
    current_migration_set: str | None = None,
) -> dict[str, Any]:
    document = _exact_keys(
        value,
        {
            "schema_version",
            "release_id",
            "git_sha",
            "created_at",
            "images",
            "migration_set",
            "schema_compatibility",
            "rollback",
        },
        "manifest",
    )
    if document["schema_version"] != MANIFEST_SCHEMA:
        raise ManifestError("unsupported manifest schema_version")
    git_sha = document["git_sha"]
    if not isinstance(git_sha, str) or not GIT_SHA.fullmatch(git_sha):
        raise ManifestError(
            "git_sha must be exactly 40 lowercase hexadecimal characters"
        )
    if document["release_id"] != f"git-{git_sha}":
        raise ManifestError("release_id must be derived from the exact git_sha")
    created_at = document["created_at"]
    if not isinstance(created_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at
    ):
        raise ManifestError("created_at must be a UTC RFC3339 second timestamp")
    try:
        datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ManifestError("created_at must be a real UTC RFC3339 timestamp") from exc

    images = _exact_keys(document["images"], set(IMAGE_REPOSITORIES), "images")
    for role in sorted(IMAGE_REPOSITORIES):
        _validate_image(role, images[role])

    migrations = _exact_keys(
        document["migration_set"],
        {"algorithm", "identity", "manifest_path", "manifest_sha256", "entries"},
        "migration_set",
    )
    if migrations["algorithm"] != "sha256":
        raise ManifestError("migration_set.algorithm must be sha256")
    if not isinstance(migrations["identity"], str) or not SHA256.fullmatch(
        migrations["identity"]
    ):
        raise ManifestError("migration_set.identity must be a sha256 identity")
    if migrations["manifest_path"] != "sql/migration-manifest.txt":
        raise ManifestError("unexpected migration manifest path")
    if not isinstance(migrations["manifest_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", migrations["manifest_sha256"]
    ):
        raise ManifestError("migration_set.manifest_sha256 must be 64 lowercase hex")
    if not isinstance(migrations["entries"], list) or not migrations["entries"]:
        raise ManifestError("migration_set.entries must be a non-empty list")
    canonical_entries: list[dict[str, str]] = []
    migration_paths: set[str] = set()
    for index, entry in enumerate(migrations["entries"]):
        item = _exact_keys(
            entry, {"path", "mode", "sha256"}, f"migration_set.entries[{index}]"
        )
        if not isinstance(item["path"], str) or not re.fullmatch(
            r"sql/[0-9]{3}_[a-z0-9_]+\.sql", item["path"]
        ):
            raise ManifestError(f"unsafe migration path at index {index}")
        if item["mode"] not in {"auto", "manual"}:
            raise ManifestError(f"invalid migration mode at index {index}")
        if not isinstance(item["sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", item["sha256"]
        ):
            raise ManifestError(f"invalid migration checksum at index {index}")
        if item["path"] in migration_paths:
            raise ManifestError(f"duplicate migration path at index {index}")
        migration_paths.add(item["path"])
        canonical_entries.append(item)
    calculated_identity = "sha256:" + _sha256(
        json.dumps(canonical_entries, sort_keys=True, separators=(",", ":")).encode()
    )
    if migrations["identity"] != calculated_identity:
        raise ManifestError("migration_set.identity does not match its entries")

    compatibility = _exact_keys(
        document["schema_compatibility"],
        {"status", "compatible_migration_sets", "evidence"},
        "schema_compatibility",
    )
    status = compatibility["status"]
    if status not in COMPATIBILITY_STATUSES:
        raise ManifestError("schema compatibility status is unknown")
    compatible_sets = compatibility["compatible_migration_sets"]
    if not isinstance(compatible_sets, list) or any(
        not isinstance(item, str) or not SHA256.fullmatch(item)
        for item in compatible_sets
    ):
        raise ManifestError(
            "compatible_migration_sets must contain only sha256 identities"
        )
    if len(set(compatible_sets)) != len(compatible_sets):
        raise ManifestError("compatible_migration_sets must not contain duplicates")
    if compatible_sets != sorted(compatible_sets):
        raise ManifestError("compatible_migration_sets must be sorted")
    evidence = compatibility["evidence"]
    if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
        raise ManifestError(
            "schema compatibility evidence must be null or non-empty text"
        )
    if isinstance(evidence, str) and (
        SENSITIVE_TEXT.search(evidence) or URI_USERINFO.search(evidence)
    ):
        raise ManifestError(
            "schema compatibility evidence contains secret-like material"
        )

    proved = status in {"exact", "backward-compatible"}
    if proved:
        if not evidence or not compatible_sets:
            raise ManifestError(
                "proved compatibility requires evidence and migration identities"
            )
        if migrations["identity"] not in compatible_sets:
            raise ManifestError(
                "release migration identity must be explicitly compatible"
            )
    elif compatible_sets or evidence is not None:
        raise ManifestError(
            "unknown/incompatible compatibility cannot carry positive evidence"
        )

    rollback = _exact_keys(
        document["rollback"], {"application_only_eligible", "reason"}, "rollback"
    )
    eligible = rollback["application_only_eligible"]
    if not isinstance(eligible, bool):
        raise ManifestError("rollback.application_only_eligible must be boolean")
    if not isinstance(rollback["reason"], str) or not rollback["reason"].strip():
        raise ManifestError("rollback.reason must be non-empty")
    if SENSITIVE_TEXT.search(rollback["reason"]) or URI_USERINFO.search(
        rollback["reason"]
    ):
        raise ManifestError("rollback.reason contains secret-like material")
    if eligible and not proved:
        raise ManifestError(
            "application-only rollback requires proved schema compatibility"
        )

    if current_migration_set is not None:
        if not SHA256.fullmatch(current_migration_set):
            raise ManifestError("current database migration identity is invalid")
        if not proved or current_migration_set not in compatible_sets:
            raise ManifestError(
                "release compatibility with the current database is absent or unknown"
            )
    if purpose in {"deploy-candidate", "deploy"} and not proved:
        raise ManifestError("deployment requires proved schema compatibility")
    if purpose in {"rollback", "rollback-candidate"} and not eligible:
        raise ManifestError("manifest is not eligible for application-only rollback")
    if purpose in {"deploy", "rollback"}:
        if current_migration_set is None:
            raise ManifestError(
                f"{purpose} requires authoritative current database migration identity"
            )
    elif purpose not in {"release", "deploy-candidate", "rollback-candidate"}:
        raise ManifestError(f"unsupported verification purpose: {purpose}")

    return document


def verify_source_migration_set(document: dict[str, Any], root: Path = ROOT) -> None:
    """Require a release manifest to match the exact checked-out SQL source.

    This check is intentionally used only while sealing a new release from its
    exact Git SHA. Older candidate/rollback manifests can legitimately describe
    a different migration tree and must instead be checked against target schema
    compatibility evidence.
    """

    if document["migration_set"] != migration_set(root):
        raise ManifestError(
            "migration_set does not match the exact checked-out SQL source"
        )


def create_manifest(args: argparse.Namespace) -> dict[str, Any]:
    if not GIT_SHA.fullmatch(args.git_sha):
        raise ManifestError(
            "git_sha must be exactly 40 lowercase hexadecimal characters"
        )
    migrations = migration_set()
    proved = args.compatibility in {"exact", "backward-compatible"}
    if not proved and args.compatibility_evidence is not None:
        raise ManifestError(
            "unknown/incompatible compatibility cannot carry positive evidence"
        )
    compatible_sets = sorted(set(args.compatible_migration_set or []))
    if args.compatibility == "exact":
        compatible_sets = [migrations["identity"]]
    elif proved and migrations["identity"] not in compatible_sets:
        compatible_sets.append(migrations["identity"])
        compatible_sets.sort()
    if not proved:
        compatible_sets = []

    document = {
        "schema_version": MANIFEST_SCHEMA,
        "release_id": f"git-{args.git_sha}",
        "git_sha": args.git_sha,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "images": {"backend": args.backend_image, "web": args.web_image},
        "migration_set": migrations,
        "schema_compatibility": {
            "status": args.compatibility,
            "compatible_migration_sets": compatible_sets,
            "evidence": args.compatibility_evidence if proved else None,
        },
        "rollback": {
            "application_only_eligible": args.rollback_eligible,
            "reason": args.rollback_reason,
        },
    }
    return validate_manifest(document)


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(
            f"unable to read release manifest: {type(exc).__name__}"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--git-sha", required=True)
    create.add_argument("--backend-image", required=True)
    create.add_argument("--web-image", required=True)
    create.add_argument(
        "--compatibility", choices=sorted(COMPATIBILITY_STATUSES), default="unknown"
    )
    create.add_argument("--compatibility-evidence")
    create.add_argument("--compatible-migration-set", action="append")
    create.add_argument("--rollback-eligible", action="store_true")
    create.add_argument("--rollback-reason", required=True)
    create.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    verify.add_argument(
        "--purpose",
        choices=(
            "release",
            "deploy-candidate",
            "deploy",
            "rollback-candidate",
            "rollback",
        ),
        default="release",
    )
    verify.add_argument("--current-migration-set")
    verify.add_argument("--expected-git-sha")
    verify.add_argument("--verify-source-migrations", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            document = create_manifest(args)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(
                json.dumps({"status": "created", "release_id": document["release_id"]})
            )
        else:
            document = validate_manifest(
                _load(args.manifest),
                purpose=args.purpose,
                current_migration_set=args.current_migration_set,
            )
            if (
                args.expected_git_sha is not None
                and document["git_sha"] != args.expected_git_sha
            ):
                raise ManifestError(
                    "manifest git_sha does not match the selected release"
                )
            if args.verify_source_migrations:
                if args.purpose != "release":
                    raise ManifestError(
                        "source migration verification is valid only while sealing a release"
                    )
                verify_source_migration_set(document)
            print(
                json.dumps({"status": "verified", "release_id": document["release_id"]})
            )
    except ManifestError as exc:
        print(json.dumps({"status": "stopped", "error": str(exc)}), file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
