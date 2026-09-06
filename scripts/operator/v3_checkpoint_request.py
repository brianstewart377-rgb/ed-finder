#!/usr/bin/env python3
"""Validate and serialize the request-only V3 checkpoint dispatch contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


MAX_REQUEST_BYTES = 16 * 1024
MAX_EVIDENCE_BYTES = 512
MAX_REVIEWED_SETS_BYTES = 8 * 1024
MAX_REVIEWED_SETS = 64
REQUEST_PATH = re.compile(
    r"[.]github/v3-checkpoint-requests/[a-z0-9][a-z0-9._-]{0,126}[.]json\Z"
)
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
MIGRATION_SET = re.compile(r"sha256:[0-9a-f]{64}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SENSITIVE_TEXT = re.compile(
    r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)"
)
URI_USERINFO = re.compile(r"[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@", re.I)

RELEASE_OPERATION = "v3-application-immutable-release"
DEPLOY_OPERATION = "v3-application-live-checkpoint-deploy"
WORKFLOWS = {
    RELEASE_OPERATION: "v3-application-release.yml",
    DEPLOY_OPERATION: "v3-application-live-checkpoint-preflight.yml",
}
RELEASE_INPUTS = {
    "source_sha",
    "schema_compatibility",
    "compatibility_evidence",
    "reviewed_compatible_migration_sets",
    "rollback_eligible",
}
DEPLOY_INPUTS = {"deployment_mode", "release_run_id"}
COMPATIBILITY_VALUES = {
    "unknown",
    "exact",
    "backward-compatible",
    "incompatible",
}


class RequestError(ValueError):
    """A sanitized, operator-safe request validation failure."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestError("request JSON contains a duplicate object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise RequestError("request JSON contains a non-standard numeric constant")


def _load_json_bytes(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise RequestError("request must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise RequestError("request must be valid JSON") from exc
    except RecursionError as exc:
        raise RequestError("request JSON nesting is too deep") from exc


def _exact_object(value: object, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RequestError(f"{location} must be a JSON object")
    if set(value) != expected:
        raise RequestError(f"{location} keys do not match the allowlisted contract")
    return value


def _require_string(inputs: dict[str, Any], key: str) -> str:
    value = inputs[key]
    if not isinstance(value, str):
        raise RequestError(f"{key} must be a JSON string")
    return value


def _validate_evidence(value: str, *, proved: bool) -> None:
    if len(value.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise RequestError("compatibility_evidence exceeds its size limit")
    if proved:
        if not value or value != value.strip() or not value.isprintable():
            raise RequestError(
                "proved compatibility requires a bounded single-line evidence identifier"
            )
        if SENSITIVE_TEXT.search(value) or URI_USERINFO.search(value):
            raise RequestError("compatibility_evidence contains secret-like material")
    elif value:
        raise RequestError(
            "unknown or incompatible schema compatibility cannot carry evidence"
        )


def _validate_reviewed_sets(value: str, *, compatibility: str) -> None:
    if len(value.encode("utf-8")) > MAX_REVIEWED_SETS_BYTES:
        raise RequestError("reviewed_compatible_migration_sets exceeds its size limit")
    if compatibility != "backward-compatible":
        if value.strip():
            raise RequestError(
                "reviewed migration sets are allowed only for backward-compatible releases"
            )
        return

    identities: list[str] = []
    for raw_identity in value.splitlines():
        identity = raw_identity.strip()
        if not identity:
            continue
        if not MIGRATION_SET.fullmatch(identity):
            raise RequestError("reviewed migration sets contain an invalid identity")
        identities.append(identity)
    if len(identities) > MAX_REVIEWED_SETS:
        raise RequestError("too many reviewed migration set identities")
    if len(identities) != len(set(identities)):
        raise RequestError("reviewed migration set identities must be unique")


def _validate_release_inputs(value: object) -> dict[str, Any]:
    inputs = _exact_object(value, RELEASE_INPUTS, "release inputs")
    source_sha = _require_string(inputs, "source_sha")
    if not GIT_SHA.fullmatch(source_sha):
        raise RequestError(
            "source_sha must be exactly 40 lowercase hexadecimal characters"
        )

    compatibility = _require_string(inputs, "schema_compatibility")
    if compatibility not in COMPATIBILITY_VALUES:
        raise RequestError("schema_compatibility is not allowlisted")
    evidence = _require_string(inputs, "compatibility_evidence")
    reviewed_sets = _require_string(inputs, "reviewed_compatible_migration_sets")
    rollback_eligible = inputs["rollback_eligible"]
    if type(rollback_eligible) is not bool:
        raise RequestError("rollback_eligible must be a JSON boolean")

    proved = compatibility in {"exact", "backward-compatible"}
    _validate_evidence(evidence, proved=proved)
    _validate_reviewed_sets(reviewed_sets, compatibility=compatibility)
    if rollback_eligible and not proved:
        raise RequestError(
            "rollback eligibility requires proved schema compatibility"
        )
    return inputs


def _validate_deploy_inputs(value: object) -> dict[str, Any]:
    inputs = _exact_object(value, DEPLOY_INPUTS, "deploy inputs")
    deployment_mode = _require_string(inputs, "deployment_mode")
    if deployment_mode not in {"bootstrap", "upgrade"}:
        raise RequestError("deployment_mode is not allowlisted")
    release_run_id = _require_string(inputs, "release_run_id")
    if not RUN_ID.fullmatch(release_run_id):
        raise RequestError("release_run_id must be a bounded positive decimal string")
    return inputs


def validate_request(value: object) -> tuple[str, dict[str, Any]]:
    request = _exact_object(value, {"operation", "inputs"}, "request")
    operation = request["operation"]
    if not isinstance(operation, str) or operation not in WORKFLOWS:
        raise RequestError("operation is not allowlisted")
    if operation == RELEASE_OPERATION:
        inputs = _validate_release_inputs(request["inputs"])
    else:
        inputs = _validate_deploy_inputs(request["inputs"])
    return operation, inputs


def prepare_request(
    *, request_root: Path, request_relative: str, request_sha: str
) -> tuple[str, str, dict[str, Any]]:
    if not REQUEST_PATH.fullmatch(request_relative):
        raise RequestError("request path is outside the dedicated allowlist")
    if not GIT_SHA.fullmatch(request_sha):
        raise RequestError("request commit SHA is invalid")

    request_path = request_root / request_relative
    try:
        metadata = request_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RequestError("request path must be one regular file")
        if metadata.st_size == 0 or metadata.st_size > MAX_REQUEST_BYTES:
            raise RequestError("request file size is outside the allowed range")
        raw = request_path.read_bytes()
    except RequestError:
        raise
    except OSError as exc:
        raise RequestError("request file cannot be read safely") from exc

    operation, inputs = validate_request(_load_json_bytes(raw))
    request_id = (
        f"v3cp-{request_sha[:12]}-{hashlib.sha256(raw).hexdigest()[:12]}"
    )
    payload = {"ref": "main", "inputs": inputs, "return_run_details": True}
    return request_id, WORKFLOWS[operation], payload


def validate_dispatch_response(value: object, repository: str) -> int:
    if not REPOSITORY.fullmatch(repository):
        raise RequestError("repository identity is invalid")
    if not isinstance(value, dict):
        raise RequestError("GitHub dispatch response is invalid")
    run_id = value.get("workflow_run_id")
    if type(run_id) is not int or not RUN_ID.fullmatch(str(run_id)):
        raise RequestError("GitHub dispatch response has no valid workflow run ID")
    expected_api_url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    expected_html_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    if (
        value.get("run_url") != expected_api_url
        or value.get("html_url") != expected_html_url
    ):
        raise RequestError("GitHub dispatch response run URLs are invalid")
    return run_id


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")


def _append_outputs(path: Path, values: dict[str, str | int]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--request-root", type=Path, required=True)
    prepare.add_argument("--request-relative", required=True)
    prepare.add_argument("--request-sha", required=True)
    prepare.add_argument("--payload", type=Path, required=True)
    prepare.add_argument("--github-output", type=Path, required=True)

    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("--response", type=Path, required=True)
    confirm.add_argument("--repository", required=True)
    confirm.add_argument("--github-output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "prepare":
            request_id, workflow_file, payload = prepare_request(
                request_root=args.request_root,
                request_relative=args.request_relative,
                request_sha=args.request_sha,
            )
            _write_payload(args.payload, payload)
            _append_outputs(
                args.github_output,
                {"request_id": request_id, "workflow_file": workflow_file},
            )
        else:
            raw_response = args.response.read_bytes()
            response = _load_json_bytes(raw_response)
            run_id = validate_dispatch_response(response, args.repository)
            _append_outputs(args.github_output, {"target_run_id": run_id})
            print(run_id)
    except (OSError, RequestError) as exc:
        message = str(exc) if isinstance(exc, RequestError) else "control-plane file error"
        print(f"Request dispatch stopped: {message}", file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
