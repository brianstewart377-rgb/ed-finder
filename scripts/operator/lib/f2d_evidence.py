"""Fixed paths and canonical sealing helpers for F2d rollout evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


EVIDENCE_DIR = Path("docs/operations/evidence/f2d")
COMPLETE_RECEIPT = EVIDENCE_DIR / "complete-read-receipt.json"
COEFFICIENT_DECISION = EVIDENCE_DIR / "coefficient-decision.json"
FRACTIONS = EVIDENCE_DIR / "calibration-fractions.json"
ARCHETYPE_FOOTPRINT = EVIDENCE_DIR / "archetype-footprint-receipt.json"
SEARCH_FOOTPRINT = EVIDENCE_DIR / "search-footprint-receipt.json"
STEP0_RECEIPT = Path(
    "docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json"
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def canonical_json(value: object) -> str:
    """Return the canonical JSON representation used by F2d receipts."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_sha256(value: object) -> str:
    """Hash an object's UTF-8 encoded canonical JSON representation."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *body* with its canonical content SHA-256 seal."""
    if not isinstance(body, dict):
        raise ValueError("sealed evidence body must be a JSON object")
    if "content_sha256" in body:
        raise ValueError("sealed evidence body already contains content_sha256")
    return {**body, "content_sha256": canonical_sha256(body)}


def load_sealed(path: str | Path) -> dict[str, Any]:
    """Load a regular JSON file and verify its canonical content seal."""
    evidence_path = Path(path)
    if evidence_path.is_symlink():
        raise ValueError(f"sealed evidence path is a symlink: {evidence_path}")
    if not evidence_path.is_file():
        raise ValueError(f"sealed evidence path is missing or not a file: {evidence_path}")
    try:
        value = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"sealed evidence is unreadable or invalid JSON: {evidence_path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"sealed evidence is not a JSON object: {evidence_path}")

    content_sha256 = value.get("content_sha256")
    if not isinstance(content_sha256, str) or _SHA256_PATTERN.fullmatch(content_sha256) is None:
        raise ValueError(
            f"sealed evidence content_sha256 is missing or malformed: {evidence_path}"
        )
    body = dict(value)
    del body["content_sha256"]
    if canonical_sha256(body) != content_sha256:
        raise ValueError(f"sealed evidence content_sha256 mismatch: {evidence_path}")
    return value
