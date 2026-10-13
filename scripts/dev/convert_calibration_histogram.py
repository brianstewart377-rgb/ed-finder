#!/usr/bin/env python3
"""Convert a sealed complete calibration receipt to footprint fractions.

The eight archetype keys remain at the top level so the output can be passed
directly to ``measure_wide_archetype_footprint.py --fractions-json``.  The
additional top-level fields bind those fractions to their source receipt and
to the converter checkout that produced them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operator.lib.f2d_operator_identity import (  # noqa: E402
    OperatorIdentityError,
    compute_operator_code_sha256,
)

ARCHETYPE_KEYS = (
    "paradise",
    "mining_hub",
    "manufacturing_hub",
    "megacomplex",
    "research_hub",
    "stronghold",
    "population_capital",
    "flexible",
)
TIERS = ("S", "A", "B", "C", "D")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class HistogramConversionError(ValueError):
    """A calibration receipt is not eligible for histogram conversion."""


def canonical_json(value: object) -> str:
    """Return the repository's compact, deterministic JSON representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def receipt_body_sha256(receipt: dict[str, Any]) -> str:
    """Hash a receipt's canonical body (everything except its seal)."""
    body = dict(receipt)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HistogramConversionError(f"{field} must be a lowercase SHA-256 digest")
    return value


def verify_complete_receipt(receipt: object) -> dict[str, Any]:
    """Validate the complete-mode marker and canonical content seal."""
    if not isinstance(receipt, dict):
        raise HistogramConversionError("source receipt must be a JSON object")
    if receipt.get("mode") != "complete":
        raise HistogramConversionError("source receipt mode must be 'complete'")
    sealed = _require_sha256(receipt.get("content_sha256"), "content_sha256")
    calculated = receipt_body_sha256(receipt)
    if calculated != sealed:
        raise HistogramConversionError(
            "source receipt content_sha256 does not match its canonical body"
        )
    return receipt


def _assert_monotonic(key: str, floors: dict[str, float]) -> None:
    if not 1.0 >= floors["60"] >= floors["76"] >= floors["88"] >= 0.0:
        raise HistogramConversionError(
            f"{key} fractions are not monotonic: expected 1 >= f60 >= f76 >= f88 >= 0"
        )


def _tier_histogram(receipt: dict[str, Any], key: str) -> dict[str, int]:
    per_archetype = receipt.get("per_archetype")
    if not isinstance(per_archetype, dict):
        raise HistogramConversionError("source receipt per_archetype must be an object")
    if key not in per_archetype:
        raise HistogramConversionError(f"source receipt is missing archetype key {key!r}")
    entry = per_archetype[key]
    if not isinstance(entry, dict) or not isinstance(entry.get("tier_histogram"), dict):
        raise HistogramConversionError(f"source receipt {key!r} tier_histogram must be an object")
    histogram = entry["tier_histogram"]
    missing = [tier for tier in TIERS if tier not in histogram]
    if missing:
        raise HistogramConversionError(
            f"source receipt {key!r} tier_histogram is missing tiers: {', '.join(missing)}"
        )
    counts: dict[str, int] = {}
    for tier in TIERS:
        count = histogram[tier]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise HistogramConversionError(
                f"source receipt {key!r} tier {tier} count must be a non-negative integer"
            )
        counts[tier] = count
    return counts


def convert_receipt(
    receipt: object,
    *,
    converter_f2d_operator_code_sha256: str,
) -> dict[str, object]:
    """Return footprint fractions and the identities that govern their use."""
    complete = verify_complete_receipt(receipt)
    source_identity = _require_sha256(
        complete.get("f2d_operator_code_sha256"),
        "f2d_operator_code_sha256",
    )
    converter_identity = _require_sha256(
        converter_f2d_operator_code_sha256,
        "converter_f2d_operator_code_sha256",
    )
    system_count = complete.get("system_count")
    if isinstance(system_count, bool) or not isinstance(system_count, int) or system_count <= 0:
        raise HistogramConversionError("source receipt system_count must be a positive integer")

    fractions: dict[str, dict[str, float]] = {}
    for key in ARCHETYPE_KEYS:
        histogram = _tier_histogram(complete, key)
        total = sum(histogram.values())
        if total != system_count:
            raise HistogramConversionError(
                f"source receipt {key!r} tier total {total} does not equal system_count "
                f"{system_count}"
            )
        floors = {
            "60": (histogram["S"] + histogram["A"] + histogram["B"]) / total,
            "76": (histogram["S"] + histogram["A"]) / total,
            "88": histogram["S"] / total,
        }
        _assert_monotonic(key, floors)
        fractions[key] = floors

    fractions_sha256 = hashlib.sha256(
        canonical_json(fractions).encode("utf-8")
    ).hexdigest()
    return {
        **fractions,
        "fractions_sha256": fractions_sha256,
        "source_receipt_content_sha256": complete["content_sha256"],
        "source_f2d_operator_code_sha256": source_identity,
        "converter_f2d_operator_code_sha256": converter_identity,
    }


def convert_file(receipt_path: Path, output_path: Path, *, repo_root: Path = ROOT) -> None:
    """Read, verify, convert and atomically replace the requested output file."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HistogramConversionError(f"could not read source receipt: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HistogramConversionError(f"source receipt is not valid JSON: {exc}") from exc

    identity = compute_operator_code_sha256(repo_root)
    converted = convert_receipt(
        receipt,
        converter_f2d_operator_code_sha256=identity,
    )
    if output_path.is_symlink():
        raise HistogramConversionError("output path must not be a symlink")
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(canonical_json(converted) + "\n", encoding="utf-8")
    temporary.replace(output_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, help="sealed complete-read receipt")
    parser.add_argument("--output", type=Path, required=True, help="fractions JSON to write")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        convert_file(args.receipt, args.output)
    except (HistogramConversionError, OperatorIdentityError, OSError) as exc:
        print(f"calibration histogram conversion refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
