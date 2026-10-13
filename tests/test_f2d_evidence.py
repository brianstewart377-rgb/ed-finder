from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator.lib import f2d_evidence as evidence


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_evidence_paths_are_fixed_repository_relative_paths() -> None:
    assert evidence.EVIDENCE_DIR == Path("docs/operations/evidence/f2d")
    assert evidence.COMPLETE_RECEIPT == evidence.EVIDENCE_DIR / "complete-read-receipt.json"
    assert evidence.COEFFICIENT_DECISION == evidence.EVIDENCE_DIR / "coefficient-decision.json"
    assert evidence.FRACTIONS == evidence.EVIDENCE_DIR / "calibration-fractions.json"
    assert evidence.ARCHETYPE_FOOTPRINT == (
        evidence.EVIDENCE_DIR / "archetype-footprint-receipt.json"
    )
    assert evidence.SEARCH_FOOTPRINT == evidence.EVIDENCE_DIR / "search-footprint-receipt.json"
    assert evidence.STEP0_RECEIPT == Path(
        "docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json"
    )


def test_canonical_json_matches_complete_read_contract() -> None:
    value = {"unicode": "é", "nested": {"z": 2, "a": 1}, "compact": [1, 2]}
    assert evidence.canonical_json(value) == (
        '{"compact":[1,2],"nested":{"a":1,"z":2},"unicode":"\\u00e9"}'
    )
    assert evidence.canonical_sha256(value) == evidence.canonical_sha256(
        {"compact": [1, 2], "nested": {"a": 1, "z": 2}, "unicode": "é"}
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_refuses_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        evidence.canonical_json({"value": value})


def test_seal_does_not_mutate_body_and_load_sealed_accepts_it(tmp_path: Path) -> None:
    body = {"schema_version": "test/v1", "rows": 3}
    receipt = evidence.seal(body)
    assert body == {"schema_version": "test/v1", "rows": 3}
    assert receipt["content_sha256"] == evidence.canonical_sha256(body)

    path = tmp_path / "receipt.json"
    _write_json(path, receipt)
    assert evidence.load_sealed(path) == receipt


def test_seal_refuses_an_existing_content_hash() -> None:
    with pytest.raises(ValueError, match="already contains"):
        evidence.seal({"content_sha256": "0" * 64})


def test_load_sealed_refuses_a_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing or not a file"):
        evidence.load_sealed(tmp_path / "missing.json")


def test_load_sealed_refuses_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    _write_json(target, evidence.seal({"value": 1}))
    link = tmp_path / "receipt.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="is a symlink"):
        evidence.load_sealed(link)


@pytest.mark.parametrize("contents", ["not-json", "{", "\udcff"])
def test_load_sealed_refuses_invalid_json(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(contents.encode("utf-8", errors="surrogatepass"))
    with pytest.raises(ValueError, match="unreadable or invalid JSON"):
        evidence.load_sealed(path)


@pytest.mark.parametrize("value", [None, [], "receipt", 1])
def test_load_sealed_refuses_a_non_object(tmp_path: Path, value: object) -> None:
    path = tmp_path / "receipt.json"
    _write_json(path, value)
    with pytest.raises(ValueError, match="not a JSON object"):
        evidence.load_sealed(path)


@pytest.mark.parametrize(
    "content_sha256",
    [None, 123, "", "0" * 63, "g" * 64, "A" * 64],
)
def test_load_sealed_refuses_missing_or_malformed_hash(
    tmp_path: Path,
    content_sha256: object,
) -> None:
    path = tmp_path / "receipt.json"
    value = {"value": 1}
    if content_sha256 is not None:
        value["content_sha256"] = content_sha256
    _write_json(path, value)
    with pytest.raises(ValueError, match="missing or malformed"):
        evidence.load_sealed(path)


def test_load_sealed_refuses_a_non_verifying_hash(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    receipt = evidence.seal({"value": 1})
    receipt["value"] = 2
    _write_json(path, receipt)
    with pytest.raises(ValueError, match="content_sha256 mismatch"):
        evidence.load_sealed(path)
