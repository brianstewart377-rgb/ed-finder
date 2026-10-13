"""Tests for the sealed complete-read histogram converter."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "convert_calibration_histogram.py"
IDENTITY = "a" * 64


def _load():
    spec = importlib.util.spec_from_file_location("convert_calibration_histogram", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _receipt(module, *, system_count=10, histogram=None):
    histogram = histogram or {"S": 1, "A": 2, "B": 3, "C": 2, "D": 2}
    receipt = {
        "mode": "complete",
        "system_count": system_count,
        "f2d_operator_code_sha256": "b" * 64,
        "per_archetype": {
            key: {"tier_histogram": dict(histogram)} for key in module.ARCHETYPE_KEYS
        },
    }
    receipt["content_sha256"] = module.receipt_body_sha256(receipt)
    return receipt


def test_hand_built_receipt_converts_tiers_to_floor_fractions():
    module = _load()
    receipt = _receipt(module)
    converted = module.convert_receipt(
        receipt,
        converter_f2d_operator_code_sha256=IDENTITY,
    )

    for key in module.ARCHETYPE_KEYS:
        assert converted[key] == {"60": 0.6, "76": 0.3, "88": 0.1}
    assert converted["source_receipt_content_sha256"] == receipt["content_sha256"]
    assert converted["source_f2d_operator_code_sha256"] == "b" * 64
    assert converted["converter_f2d_operator_code_sha256"] == IDENTITY


def test_monotonic_fraction_assertion_refuses_inverted_floors():
    module = _load()
    with pytest.raises(module.HistogramConversionError, match="not monotonic"):
        module._assert_monotonic("paradise", {"60": 0.5, "76": 0.2, "88": 0.3})


def test_missing_archetype_key_is_refused():
    module = _load()
    receipt = _receipt(module)
    del receipt["per_archetype"]["flexible"]
    receipt["content_sha256"] = module.receipt_body_sha256(receipt)
    with pytest.raises(module.HistogramConversionError, match="missing archetype key 'flexible'"):
        module.convert_receipt(receipt, converter_f2d_operator_code_sha256=IDENTITY)


def test_per_key_total_must_equal_recorded_system_count():
    module = _load()
    receipt = _receipt(module)
    receipt["per_archetype"]["research_hub"]["tier_histogram"]["D"] -= 1
    receipt["content_sha256"] = module.receipt_body_sha256(receipt)
    with pytest.raises(module.HistogramConversionError, match="does not equal system_count 10"):
        module.convert_receipt(receipt, converter_f2d_operator_code_sha256=IDENTITY)


def test_non_complete_receipt_is_refused():
    module = _load()
    receipt = _receipt(module)
    receipt["mode"] = "sampled"
    receipt["content_sha256"] = module.receipt_body_sha256(receipt)
    with pytest.raises(module.HistogramConversionError, match="mode must be 'complete'"):
        module.convert_receipt(receipt, converter_f2d_operator_code_sha256=IDENTITY)


def test_bad_receipt_seal_is_refused():
    module = _load()
    receipt = _receipt(module)
    receipt["system_count"] = 11
    with pytest.raises(module.HistogramConversionError, match="does not match its canonical body"):
        module.convert_receipt(receipt, converter_f2d_operator_code_sha256=IDENTITY)


def test_fractions_digest_is_stable_and_covers_only_the_fraction_object():
    module = _load()
    forward = _receipt(module)
    reverse = {
        **forward,
        "per_archetype": dict(reversed(list(forward["per_archetype"].items()))),
    }
    reverse["content_sha256"] = module.receipt_body_sha256(reverse)
    first = module.convert_receipt(forward, converter_f2d_operator_code_sha256=IDENTITY)
    second = module.convert_receipt(reverse, converter_f2d_operator_code_sha256=IDENTITY)
    assert first["fractions_sha256"] == second["fractions_sha256"]
    fractions = {key: first[key] for key in module.ARCHETYPE_KEYS}
    expected = hashlib.sha256(module.canonical_json(fractions).encode("utf-8")).hexdigest()
    assert first["fractions_sha256"] == expected


def test_convert_file_writes_directly_consumable_fraction_keys_and_identities(
    tmp_path, monkeypatch
):
    module = _load()
    receipt_path = tmp_path / "complete.json"
    output_path = tmp_path / "fractions.json"
    receipt_path.write_text(json.dumps(_receipt(module)), encoding="utf-8")
    monkeypatch.setattr(module, "compute_operator_code_sha256", lambda _root: IDENTITY)

    module.convert_file(receipt_path, output_path, repo_root=tmp_path)

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert all(key in written for key in module.ARCHETYPE_KEYS)
    assert written["converter_f2d_operator_code_sha256"] == IDENTITY
