#!/usr/bin/env python3
"""Read-only capacity gate for the two F2d Finder products."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operator.lib import f2d_operator_identity  # noqa: E402


RECEIPT_SCHEMA = "ed-finder/v3-finder-capacity-gate/v1"
BUILD_START_SCHEMA = "ed-finder/v3-build-start-receipt/v1"
DEFAULT_DATABASE_URL_ENV = "V3_FINDER_CAPACITY_GATE_DATABASE_URL"
DEFAULT_IDENTITY_ENV = "F2D_OPERATOR_CODE_SHA256_ATTESTED"
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
FLOORS = ("60", "76", "88")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA_NAME = re.compile(r"v3_gen_[a-z][a-z0-9_]{0,30}\Z")
_FAILURE_CONTEXT: dict[str, Any] | None = None


@dataclass
class GateRefusal(ValueError):
    """A refusal assigned to one ordered gate item."""

    exit_code: int
    item: str
    reason: str
    field: str | None = None
    expected: object = None
    actual: object = None
    context: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.reason


def refuse(
    exit_code: int,
    item: str,
    reason: str,
    *,
    field: str | None = None,
    expected: object = None,
    actual: object = None,
) -> NoReturn:
    raise GateRefusal(
        exit_code,
        item,
        reason,
        field,
        expected,
        actual,
        _FAILURE_CONTEXT,
    )


def _positive_int(value: object, field: str, *, item: str = "e") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        refuse(
            15 if item == "f" else 14,
            item,
            f"{field} must be a positive integer",
            field=field,
            actual=value,
        )
    return value


def ceil_div(numerator: int, denominator: int) -> int:
    """Divide non-negative integers, rounding upward."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("ceil_div requires a non-negative numerator and positive denominator")
    return (numerator + denominator - 1) // denominator


def ceil_fraction(value: Fraction) -> int:
    """Round a non-negative rational upward."""
    if value < 0:
        raise ValueError("capacity values cannot be negative")
    return ceil_div(value.numerator, value.denominator)


def reserve_bytes(projected_new_bytes: int) -> int:
    """Apply the exact 15 percent capacity reserve."""
    if projected_new_bytes < 0:
        raise ValueError("projected bytes cannot be negative")
    return (23 * projected_new_bytes + 19) // 20


def canonical_json(value: object) -> str:
    """Return the canonical representation used for byte-identity checks."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def histogram_fractions(
    per_archetype: object, system_count: int
) -> dict[str, dict[str, Fraction]]:
    """Validate the complete histogram and derive its 24 exact fractions."""
    if system_count <= 0:
        refuse(12, "c", "system_count must be positive", field="system_count")
    if not isinstance(per_archetype, dict) or set(per_archetype) != set(ARCHETYPE_KEYS):
        refuse(
            12,
            "c",
            "complete histogram does not contain exactly the eight archetype keys",
            field="per_archetype",
        )
    result: dict[str, dict[str, Fraction]] = {}
    for key in ARCHETYPE_KEYS:
        entry = per_archetype[key]
        histogram = entry.get("tier_histogram") if isinstance(entry, dict) else None
        if not isinstance(histogram, dict) or set(histogram) != set(TIERS):
            refuse(12, "c", "tier histogram is incomplete", field=f"per_archetype.{key}")
        if any(
            isinstance(count, bool) or not isinstance(count, int) or count < 0
            for count in histogram.values()
        ):
            refuse(12, "c", "tier histogram has an invalid count", field=f"per_archetype.{key}")
        total = sum(histogram.values())
        if total != system_count:
            refuse(
                12,
                "c",
                "tier histogram total differs from system_count",
                field=f"per_archetype.{key}.tier_histogram",
                expected=system_count,
                actual=total,
            )
        result[key] = {
            "60": Fraction(histogram["S"] + histogram["A"] + histogram["B"], total),
            "76": Fraction(histogram["S"] + histogram["A"], total),
            "88": Fraction(histogram["S"], total),
        }
    return result


def sigma_all(fractions: dict[str, dict[str, Fraction]]) -> Fraction:
    """Return the exact sum of all 24 tier fractions."""
    return sum(
        (fractions[key][floor] for key in ARCHETYPE_KEYS for floor in FLOORS),
        start=Fraction(),
    )


def full_archetype_projection(
    *,
    system_count: int,
    sigma: Fraction,
    heap_bytes_per_row: int,
    primary_key_bytes_per_row: int,
    weighted_index_bytes_per_row: int,
    tier_index_bytes_per_row_per_unit_fraction: int,
) -> dict[str, int]:
    """Project a fresh wide-Archetype build using exact integer arithmetic."""
    projected_heap = heap_bytes_per_row * system_count
    projected_fixed_index = (
        primary_key_bytes_per_row + weighted_index_bytes_per_row
    ) * system_count
    projected_tier_index = ceil_fraction(
        tier_index_bytes_per_row_per_unit_fraction * sigma * system_count
    )
    return {
        "projected_heap_bytes": projected_heap,
        "projected_fixed_index_bytes": projected_fixed_index,
        "projected_tier_index_bytes": projected_tier_index,
        "projected_archetype_bytes": (
            projected_heap + projected_fixed_index + projected_tier_index
        ),
    }


def resume_projection(
    *,
    full_projection: int,
    rows_done: int,
    system_count: int,
    bytes_done: int,
    fixed_bytes_per_row: int,
    variable_left: int,
    tier_left: int = 0,
) -> dict[str, Any]:
    """Bound a recognised resume from the unsealed source tail."""
    if not 0 <= rows_done <= system_count:
        raise ValueError("resume rows_done is outside the generation")
    if min(full_projection, bytes_done, fixed_bytes_per_row, variable_left, tier_left) < 0:
        raise ValueError("resume byte terms cannot be negative")
    rows_left = system_count - rows_done
    fixed_left = fixed_bytes_per_row * rows_left
    remaining = fixed_left + variable_left + tier_left
    projection_remainder = max(0, full_projection - bytes_done)
    if remaining >= projection_remainder:
        charged = remaining
        branch = "source_derived_remaining"
    else:
        charged = projection_remainder
        branch = "full_projection_minus_bytes_done"
    return {
        "resume_recognised": True,
        "rows_done": rows_done,
        "rows_left": rows_left,
        "bytes_done": bytes_done,
        "fixed_left": fixed_left,
        "variable_left": variable_left,
        "tier_left": tier_left,
        "remaining": remaining,
        "projection_minus_bytes_done": projection_remainder,
        "term_charged": charged,
        "max_branch": branch,
    }


def fresh_projection(full_projection: int, reason: str) -> dict[str, Any]:
    """Describe the conservative full charge for a non-resume."""
    return {
        "resume_recognised": False,
        "resume_reason": reason,
        "rows_done": 0,
        "rows_left": None,
        "bytes_done": 0,
        "fixed_left": None,
        "variable_left": None,
        "tier_left": None,
        "remaining": full_projection,
        "projection_minus_bytes_done": full_projection,
        "term_charged": full_projection,
        "max_branch": "full_projection",
    }


def capacity_result(
    *,
    archetype: dict[str, Any],
    search: dict[str, Any],
    available_bytes: int,
) -> dict[str, Any]:
    """Combine product charges and apply the reserve."""
    projected_new = int(archetype["term_charged"]) + int(search["term_charged"])
    required = reserve_bytes(projected_new)
    return {
        "projected_new_bytes": projected_new,
        "required_bytes": required,
        "available_bytes": available_bytes,
        "headroom_bytes": available_bytes - required,
        "passes": available_bytes >= required,
    }


def _same(field: str, actual: object, expected: object, code: int, item: str) -> None:
    if actual != expected:
        refuse(
            code,
            item,
            f"{field} mismatch",
            field=field,
            expected=expected,
            actual=actual,
        )


def _same_canonical(
    field: str, actual: object, expected: object, code: int, item: str
) -> None:
    try:
        matches = canonical_json(actual) == canonical_json(expected)
    except (TypeError, ValueError):
        matches = False
    if not matches:
        refuse(
            code,
            item,
            f"{field} canonical JSON mismatch",
            field=field,
            expected=expected,
            actual=actual,
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_seal_for_item(
    value: dict[str, Any],
    *,
    canonical_sha256: Any,
    exit_code: int,
    item: str,
    label: str,
) -> None:
    """Validate an already-read evidence seal at its ordered gate item."""
    content_sha256 = value.get("content_sha256")
    if not isinstance(content_sha256, str) or SHA256_RE.fullmatch(content_sha256) is None:
        refuse(
            exit_code,
            item,
            f"{label} content_sha256 is missing or malformed",
            field=f"{label}.content_sha256",
        )
    body = dict(value)
    del body["content_sha256"]
    if canonical_sha256(body) != content_sha256:
        refuse(
            exit_code,
            item,
            f"{label} content_sha256 mismatch",
            field=f"{label}.content_sha256",
            expected=canonical_sha256(body),
            actual=content_sha256,
        )


def check_coefficient_decision(
    decision: dict[str, Any],
    complete: dict[str, Any],
    coefficients: dict[str, Any],
    *,
    canonical_sha256: Any | None = None,
) -> dict[str, Any]:
    """Check ordered item (a)."""
    if canonical_sha256 is not None:
        validate_seal_for_item(
            decision,
            canonical_sha256=canonical_sha256,
            exit_code=10,
            item="a",
            label="coefficient_decision",
        )
    _same("coefficient_decision", decision.get("coefficient_decision"), "accepted", 10, "a")
    _same_canonical("coefficients", decision.get("coefficients"), coefficients, 10, "a")
    _same(
        "complete_receipt_content_sha256",
        decision.get("complete_receipt_content_sha256"),
        complete.get("content_sha256"),
        10,
        "a",
    )
    return {"item": "a", "status": "passed", "compared": {
        "coefficient_decision": "accepted",
        "coefficients": coefficients,
        "complete_receipt_content_sha256": complete.get("content_sha256"),
    }}


def check_complete_identity(
    complete: dict[str, Any],
    *,
    identity: str,
    code_identity: dict[str, str],
    coefficients: dict[str, Any],
    model_sha256: str,
    model_file_sha256: str,
    generation: Any,
    expected_manifest: dict[str, Any],
    canonical_sha256: Any,
) -> dict[str, Any]:
    """Check ordered item (b)."""
    expected_generation = {
        "generation_key": generation.key,
        "derived_generation_id": generation.identifier,
        "publication_sequence": generation.publication_sequence,
    }
    for field, expected in (
        ("f2d_operator_code_sha256", identity),
        ("code_identity", code_identity),
        ("archetype_model_sha256", model_sha256),
        ("model_file_sha256", model_file_sha256),
    ):
        _same(field, complete.get(field), expected, 11, "b")
    _same_canonical("coefficients", complete.get("coefficients"), coefficients, 11, "b")
    block = complete.get("generation")
    if not isinstance(block, dict):
        refuse(11, "b", "generation block is missing", field="generation")
    for field, expected in expected_generation.items():
        _same(f"generation.{field}", block.get(field), expected, 11, "b")
    _same_canonical(
        "expected_product_manifest",
        complete.get("expected_product_manifest"),
        expected_manifest,
        11,
        "b",
    )
    manifest_digest = canonical_sha256(expected_manifest)
    _same(
        "expected_product_manifest_sha256",
        complete.get("expected_product_manifest_sha256"),
        manifest_digest,
        11,
        "b",
    )
    return {"item": "b", "status": "passed", "compared": {
        "generation": expected_generation,
        "f2d_operator_code_sha256": identity,
        "code_identity": code_identity,
        "coefficients": coefficients,
        "archetype_model_sha256": model_sha256,
        "model_file_sha256": model_file_sha256,
        "expected_product_manifest_sha256": manifest_digest,
    }}


def check_complete_histogram(
    complete: dict[str, Any], *, live_system_count: int, expected_systems: int,
    chunk_system_count: int, live_chunk_plan_sha256: str,
) -> tuple[dict[str, dict[str, Fraction]], dict[str, Any]]:
    """Check ordered item (c)."""
    _same("mode", complete.get("mode"), "complete", 12, "c")
    receipt_count = complete.get("system_count")
    if (
        isinstance(receipt_count, bool)
        or not isinstance(receipt_count, int)
        or receipt_count <= 0
    ):
        refuse(
            12,
            "c",
            "complete system_count must be a positive integer",
            field="complete.system_count",
            actual=receipt_count,
        )
    for field, actual in (
        ("complete.system_count", receipt_count),
        ("derived_generation.expected_systems", expected_systems),
        ("build_chunk.systems", chunk_system_count),
    ):
        _same(field, actual, live_system_count, 12, "c")
    fractions = histogram_fractions(complete.get("per_archetype"), live_system_count)
    plan = complete.get("chunk_plan")
    if not isinstance(plan, dict):
        refuse(12, "c", "chunk_plan is missing", field="chunk_plan")
    _same("chunk_plan.sha256", plan.get("sha256"), live_chunk_plan_sha256, 12, "c")
    result = {"item": "c", "status": "passed", "compared": {
        "system_count": live_system_count,
        "receipt_system_count": receipt_count,
        "expected_systems": expected_systems,
        "chunk_system_count": chunk_system_count,
        "chunk_plan_sha256": live_chunk_plan_sha256,
    }}
    return fractions, result


def check_fractions(
    complete: dict[str, Any],
    fractions_file: dict[str, Any],
    derived: dict[str, dict[str, Fraction]],
    *,
    identity: str,
    canonical_sha256: Any,
) -> tuple[Fraction, dict[str, Any]]:
    """Check ordered item (d)."""
    expected_fields = set(ARCHETYPE_KEYS) | {
        "fractions_sha256",
        "source_receipt_content_sha256",
        "source_f2d_operator_code_sha256",
        "converter_f2d_operator_code_sha256",
    }
    if set(fractions_file) != expected_fields:
        refuse(
            13,
            "d",
            "fractions file shape is not converter output",
            field="fractions",
            expected=sorted(expected_fields),
            actual=sorted(fractions_file),
        )
    sigma = sigma_all(derived)
    receipt_sigma = complete.get("sigma_all")
    if isinstance(receipt_sigma, bool) or not isinstance(receipt_sigma, (int, float)):
        refuse(13, "d", "receipt sigma_all is missing", field="sigma_all")
    if abs(float(sigma) - float(receipt_sigma)) > 1e-9:
        refuse(13, "d", "sigma_all mismatch", field="sigma_all", expected=float(sigma), actual=receipt_sigma)
    if sigma > 4:
        refuse(13, "d", "sigma_all exceeds 4.0", field="sigma_all", expected="<=4.0", actual=float(sigma))
    fraction_object = {key: {floor: float(derived[key][floor]) for floor in FLOORS} for key in ARCHETYPE_KEYS}
    supplied = {key: fractions_file.get(key) for key in ARCHETYPE_KEYS}
    _same_canonical("fractions", supplied, fraction_object, 13, "d")
    digest = canonical_sha256(supplied)
    _same("fractions_sha256", fractions_file.get("fractions_sha256"), digest, 13, "d")
    _same(
        "source_receipt_content_sha256",
        fractions_file.get("source_receipt_content_sha256"),
        complete.get("content_sha256"),
        13,
        "d",
    )
    _same(
        "converter_f2d_operator_code_sha256",
        fractions_file.get("converter_f2d_operator_code_sha256"),
        identity,
        13,
        "d",
    )
    _same(
        "source_f2d_operator_code_sha256",
        fractions_file.get("source_f2d_operator_code_sha256"),
        identity,
        13,
        "d",
    )
    return sigma, {"item": "d", "status": "passed", "compared": {
        "sigma_all": {"numerator": sigma.numerator, "denominator": sigma.denominator, "float": float(sigma)},
        "fractions_sha256": digest,
        "source_receipt_content_sha256": complete.get("content_sha256"),
        "converter_f2d_operator_code_sha256": identity,
    }}


def real_pre010_bytes_per_row(step0: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Derive the real pre-010 Search cost from the step-0 observation."""
    try:
        total = step0["footprint"]["measured_footprint_attribution"]["system_search"]["generations"]["ratings_v4_prod_p4_opt1"]["attributed_bytes"]
        rows = step0["footprint"]["rows_by_generation"]["ratings_v4_prod_p4_opt1"]["search_systems"]
    except (KeyError, TypeError):
        refuse(14, "e", "step 0 Search footprint fields are absent", field="step0.footprint")
    total = _positive_int(total, "step0.attributed_bytes")
    rows = _positive_int(rows, "step0.search_systems")
    return ceil_div(total, rows), {"attributed_bytes": total, "search_systems": rows}


def check_footprints(
    archetype: dict[str, Any],
    search: dict[str, Any],
    fractions_file: dict[str, Any],
    step0: dict[str, Any],
    *,
    identity: str,
    checkout_011_sha256: str,
    checkout_010_sha256: str,
    ledger_011_sha256: str | None,
    ledger_010_sha256: str | None,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Check ordered item (e), after the shared receipt validators ran."""
    for label, value, expected in (
        ("archetype.migration_011_sha256", archetype.get("migration_011_sha256"), checkout_011_sha256),
        ("ledger.011", ledger_011_sha256, checkout_011_sha256),
        ("archetype.fractions_sha256", archetype.get("fractions_sha256"), fractions_file.get("fractions_sha256")),
        ("archetype.f2d_operator_code_sha256", archetype.get("f2d_operator_code_sha256"), identity),
        ("search.migration_010_sha256", search.get("migration_010_sha256"), checkout_010_sha256),
        ("ledger.010", ledger_010_sha256, checkout_010_sha256),
        ("search.f2d_operator_code_sha256", search.get("f2d_operator_code_sha256"), identity),
    ):
        _same(label, value, expected, 14, "e")
    values = {
        field: _positive_int(archetype.get(field), f"archetype.{field}")
        for field in (
            "heap_bytes_per_row",
            "primary_key_bytes_per_row",
            "weighted_index_bytes_per_row",
            "tier_index_bytes_per_row_per_unit_fraction",
            "archetype_fixed_bytes_per_row",
        )
    }
    delta = search.get("measured_010_delta_bytes_per_row")
    if isinstance(delta, bool) or not isinstance(delta, int) or delta < 0:
        refuse(
            14,
            "e",
            "search.measured_010_delta_bytes_per_row must be a non-negative integer",
            field="search.measured_010_delta_bytes_per_row",
            actual=delta,
        )
    values["measured_010_delta_bytes_per_row"] = delta
    values["search_fixed_bytes_per_row"] = _positive_int(
        search.get("search_fixed_bytes_per_row"), "search.search_fixed_bytes_per_row"
    )
    pre010, source = real_pre010_bytes_per_row(step0)
    values["real_pre010_bytes_per_row"] = pre010
    return values, {"item": "e", "status": "passed", "compared": {
        **values,
        "real_pre010_source": source,
        "migration_011_sha256": checkout_011_sha256,
        "migration_010_sha256": checkout_010_sha256,
        "fractions_sha256": fractions_file.get("fractions_sha256"),
        "f2d_operator_code_sha256": identity,
    }}


def validate_footprint_receipts(
    archetype: dict[str, Any],
    search: dict[str, Any],
    *,
    archetype_validator: Any,
    search_validator: Any,
) -> None:
    """Map footprint shape, seal, and eligibility failures to item (e)."""
    for label, receipt, validator in (
        ("archetype", archetype, archetype_validator),
        ("search", search, search_validator),
    ):
        try:
            validator(receipt)
        except ValueError as exc:
            message = str(exc)
            known_fields = (
                "content_sha256",
                "schema_version",
                "capacity_gate_eligible",
                "score_distribution_source",
                "distribution_source",
                "heap_bytes_per_row",
                "primary_key_bytes_per_row",
                "weighted_index_bytes_per_row",
                "tier_index_bytes_per_row_per_unit_fraction",
                "archetype_fixed_bytes_per_row",
                "measured_010_delta_bytes_per_row",
                "search_fixed_bytes_per_row",
                "migration_011_sha256",
                "migration_010_sha256",
                "fractions_sha256",
                "f2d_operator_code_sha256",
            )
            mismatched = next(
                (field for field in known_fields if field in message),
                "receipt",
            )
            refuse(14, "e", message, field=f"{label}.{mismatched}")


def check_volume(
    volume: dict[str, Any], step0: dict[str, Any], required: int, *, now: datetime
) -> dict[str, Any]:
    """Check ordered item (f)."""
    for field in ("filesystem", "filesystem_type", "mount_source", "mount_destination"):
        if not isinstance(volume.get(field), str) or not volume[field]:
            refuse(
                15,
                "f",
                f"volume {field} is missing or invalid",
                field=field,
                actual=volume.get(field),
            )
    size = _positive_int(volume.get("size_bytes"), "volume.size_bytes", item="f")
    used = volume.get("used_bytes")
    if isinstance(used, bool) or not isinstance(used, int) or not 0 <= used <= size:
        refuse(
            15,
            "f",
            "volume used_bytes is invalid",
            field="used_bytes",
            actual=used,
        )
    try:
        observed_disk = step0["footprint"]["host_disk"]
    except (KeyError, TypeError):
        refuse(15, "f", "step 0 host disk fields are absent", field="step0.footprint.host_disk")
    if not isinstance(observed_disk.get("filesystem"), str) or not observed_disk["filesystem"]:
        refuse(15, "f", "step 0 filesystem is absent", field="step0.footprint.host_disk.filesystem")
    if (
        not isinstance(observed_disk.get("mount_destination"), str)
        or not observed_disk["mount_destination"]
    ):
        refuse(
            15,
            "f",
            "step 0 mount destination is absent",
            field="step0.footprint.host_disk.mount_destination",
        )
    _same("volume.filesystem", volume.get("filesystem"), observed_disk.get("filesystem"), 15, "f")
    allowed_destinations = {"/var/lib/postgresql/data", observed_disk.get("mount_destination")}
    if volume.get("mount_destination") not in allowed_destinations:
        refuse(15, "f", "volume mount destination mismatch", field="mount_destination", expected=sorted(str(v) for v in allowed_destinations), actual=volume.get("mount_destination"))
    read_at = volume.get("read_at")
    try:
        parsed = datetime.fromisoformat(read_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        refuse(15, "f", "volume read_at is invalid", field="read_at", actual=read_at)
    age = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    if not 0 <= age <= 900:
        refuse(15, "f", "volume reading is not fresh", field="read_at", expected="within last 15 minutes", actual=read_at)
    available = _positive_int(volume.get("avail_bytes"), "volume.avail_bytes", item="f")
    if available > size:
        refuse(
            15,
            "f",
            "volume avail_bytes exceeds size_bytes",
            field="avail_bytes",
            expected=f"<={size}",
            actual=available,
        )
    if used + available > size:
        refuse(
            15,
            "f",
            "volume used_bytes plus avail_bytes exceeds size_bytes",
            field="volume.size_bytes",
            expected=f">={used + available}",
            actual=size,
        )
    if available < required:
        refuse(15, "f", "available capacity is below required capacity", field="available_bytes", expected=required, actual=available)
    return {"item": "f", "status": "passed", "compared": {
        "available_bytes": available, "required_bytes": required,
        "filesystem": volume.get("filesystem"), "mount_destination": volume.get("mount_destination"),
        "read_at": read_at,
    }}


def _json_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON path is missing or not a regular file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON value is not an object: {path}")
    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _live_generation(connection: Any, generation_key: str) -> dict[str, Any]:
    row = connection.execute(
        """SELECT g.derived_generation_id::text,g.generation_key,g.lifecycle_state,
                  g.expected_systems,g.canonical_generation_id::text,
                  g.canonical_publication_sequence,g.manifest,p.publication_sequence
             FROM v3_meta.derived_generation g
             LEFT JOIN v3_meta.current_derived_generation p
               ON p.singleton AND p.derived_generation_id=g.derived_generation_id
            WHERE g.generation_key=%s""",
        (generation_key,),
    ).fetchone()
    if row is None:
        refuse(12, "c", "pinned generation is absent", field="generation_key")
    return {
        "identifier": row[0], "key": row[1], "state": row[2], "expected_systems": int(row[3]),
        "canonical_generation_id": row[4], "canonical_publication_sequence": int(row[5]),
        "manifest": row[6], "publication_sequence": row[7],
    }


def _chunk_plan(connection: Any, generation_id: str, canonical_sha256: Any) -> tuple[list[list[int]], int, str]:
    rows = connection.execute(
        """SELECT chunk_ordinal,systems FROM v3_derived.build_chunk
            WHERE derived_generation_id=%s ORDER BY chunk_ordinal""",
        (generation_id,),
    ).fetchall()
    plan = [[int(row[0]), int(row[1])] for row in rows]
    return plan, sum(row[1] for row in plan), canonical_sha256(plan)


def _live_system_count(connection: Any, generation_id: str) -> int:
    row = connection.execute(
        """SELECT COALESCE(sum(systems),0) FROM v3_derived.build_chunk
            WHERE derived_generation_id=%s""",
        (generation_id,),
    ).fetchone()
    return int(row[0])


def _ledger_hash(connection: Any, migration_name: str) -> str | None:
    row = connection.execute(
        """SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration
            WHERE migration_name=%s""",
        (migration_name,),
    ).fetchone()
    return None if row is None else row[0]


def _product_rows(connection: Any, generation_id: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """SELECT product_code,lifecycle_state,encode(manifest_sha256,'hex'),validation_receipt
             FROM v3_meta.derived_product WHERE derived_generation_id=%s""",
        (generation_id,),
    ).fetchall()
    products: dict[str, dict[str, Any]] = {}
    for code, state, manifest_sha, validation in rows:
        products[code] = {
            "product_code": code, "lifecycle_state": state,
            "manifest_sha256": manifest_sha, "validation_receipt": validation,
        }
        if state == "READY" and (
            not isinstance(validation, dict) or validation.get("status") != "VERIFIED"
        ):
            refuse(16, "live_state", "READY product lacks a VERIFIED receipt", field=f"{code}.validation_receipt")
    return products


def _sealed_chunks(
    connection: Any,
    generation_id: str,
    product_code: str,
    plan_systems: dict[int, int],
) -> tuple[list[int], int]:
    from psycopg import sql

    tables = {
        "system_search": "search_build_chunk",
        "system_archetype": "archetype_build_chunk",
    }
    table = tables.get(product_code)
    if table is None:
        refuse(
            16,
            "live_state",
            "unsupported product code for sealed chunks",
            field="product_code",
            expected=sorted(tables),
            actual=product_code,
        )
    rows = connection.execute(
        sql.SQL(
            "SELECT chunk_ordinal,systems FROM {} "
            "WHERE derived_generation_id=%s ORDER BY chunk_ordinal"
        ).format(sql.Identifier("v3_derived", table)),
        (generation_id,),
    ).fetchall()
    ordinals = [int(row[0]) for row in rows]
    invalid = sorted(set(ordinals) - set(plan_systems))
    if invalid:
        refuse(16, "live_state", "sealed chunk ordinal is outside the canonical plan", field=f"{product_code}.chunk_ordinal", actual=invalid)
    for ordinal, systems in rows:
        if int(systems) != plan_systems[int(ordinal)]:
            refuse(
                16,
                "live_state",
                "sealed chunk systems differ from the canonical plan",
                field=f"{product_code}.chunk[{int(ordinal)}].systems",
                expected=plan_systems[int(ordinal)],
                actual=int(systems),
            )
    return ordinals, sum(int(row[1]) for row in rows)


def _relation_size(connection: Any, relation: str, generation_id: str) -> int:
    row = connection.execute(
        "SELECT pg_total_relation_size(%s::regclass)", (relation,),
    ).fetchone()
    return int(row[0])


def _start_bytes(
    state_root: Path, product_code: str, generation_id: str, manifest_sha: str, identity: str,
) -> tuple[int | None, str]:
    path = state_root / "build-start-receipt.json"
    if not path.exists():
        return None, "build-start receipt absent"
    try:
        from scripts.operator.lib import f2d_evidence

        receipt = f2d_evidence.load_sealed(path)
    except (OSError, ValueError) as exc:
        refuse(
            16,
            "live_state",
            f"build-start receipt refused: {type(exc).__name__}",
            field=f"{product_code}.build_start_receipt",
        )
    if receipt.get("schema_version") != BUILD_START_SCHEMA:
        refuse(
            16,
            "live_state",
            "build-start receipt schema_version mismatch",
            field=f"{product_code}.build_start_receipt.schema_version",
            expected=BUILD_START_SCHEMA,
            actual=receipt.get("schema_version"),
        )
    if receipt.get("f2d_operator_code_sha256") != identity:
        refuse(
            16,
            "live_state",
            "build-start receipt operator identity mismatch",
            field=f"{product_code}.build_start_receipt.f2d_operator_code_sha256",
            expected=identity,
            actual=receipt.get("f2d_operator_code_sha256"),
        )
    expected_product = {
        "product_code": product_code,
        "derived_generation_id": generation_id,
        "manifest_sha256": manifest_sha,
    }
    if any(receipt.get(field) != value for field, value in expected_product.items()):
        return None, "build-start receipt identity mismatch"
    started_at = receipt.get("started_at")
    try:
        parsed_started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if parsed_started_at.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        refuse(
            16,
            "live_state",
            "build-start receipt started_at invalid",
            field=f"{product_code}.build_start_receipt.started_at",
            actual=started_at,
        )
    start = receipt.get("relation_total_bytes_at_start")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        refuse(
            16,
            "live_state",
            "build-start receipt size invalid",
            field=f"{product_code}.build_start_receipt.relation_total_bytes_at_start",
            actual=start,
        )
    return start, "matched sealed build-start receipt"


def _search_tail_bytes(
    connection: Any, generation_id: str, canonical_schema: str,
) -> int:
    if SCHEMA_NAME.fullmatch(canonical_schema) is None:
        refuse(16, "live_state", "canonical schema is invalid", field="canonical_schema", actual=canonical_schema)
    from psycopg import sql

    query = sql.SQL(
        """SELECT COALESCE(sum(octet_length(s.name)
                    +COALESCE(octet_length(gr.display_name),0)
                    +COALESCE(octet_length(ms.main_star_class),0)),0)
             FROM v3_derived.system_rating_vector r
             JOIN {}.systems s ON s.id64=r.system_id64
        LEFT JOIN v3_vocab.galaxy_region gr ON gr.galaxy_region_id=s.galaxy_region_id
        LEFT JOIN LATERAL (
                   SELECT bm.body_class AS main_star_class
                     FROM v3_derived.body_mechanics bm
                    WHERE bm.derived_generation_id=%s
                      AND bm.system_id64=r.system_id64 AND bm.is_main_star IS TRUE
                 ORDER BY bm.body_pk LIMIT 1
                  ) ms ON true
            WHERE r.derived_generation_id=%s
              AND NOT EXISTS (
                  SELECT 1 FROM v3_derived.search_build_chunk c
                   WHERE c.derived_generation_id=r.derived_generation_id
                     AND c.chunk_ordinal=r.chunk_ordinal)"""
    ).format(sql.Identifier(canonical_schema))
    row = connection.execute(query, (generation_id, generation_id)).fetchone()
    return 2 * int(row[0])


def _archetype_tier_entries_left(
    complete: dict[str, Any], complete_state: Path, sealed_ordinals: set[int], validator: Any,
) -> int:
    try:
        chunks = validator(complete, complete_state / "per-chunk.jsonl")
    except (OSError, ValueError) as exc:
        refuse(
            16,
            "live_state",
            f"complete per-chunk log refused: {type(exc).__name__}",
            field="archetype.per_chunk",
        )
    entries = 0
    unsealed = 0
    for chunk in chunks:
        if int(chunk["chunk_ordinal"]) in sealed_ordinals:
            continue
        unsealed += 1
        for key in ARCHETYPE_KEYS:
            histogram = chunk["per_archetype"][key]["tier_histogram"]
            entries += (histogram["S"] + histogram["A"] + histogram["B"])
            entries += histogram["S"] + histogram["A"]
            entries += histogram["S"]
    if unsealed == 0:
        refuse(16, "live_state", "recognised Archetype resume has no unsealed chunk in the complete log", field="archetype.per_chunk")
    return entries


def _ready_verified_search_product(
    product: dict[str, Any] | None, expected_manifest_sha: str
) -> bool:
    """True when the Search product is already READY/VERIFIED for current code.

    A READY Search product costs no further disk, but only when its registered
    manifest is the one the current code builds. A READY product for another
    manifest cannot complete the intended publication path, so the gate refuses
    it instead of charging zero and letting the irreversible Archetype build
    start on top of it.
    """
    if product is None or product["lifecycle_state"] != "READY":
        return False
    receipt = product["validation_receipt"]
    if not (isinstance(receipt, dict) and receipt.get("status") == "VERIFIED"):
        return False
    if product["manifest_sha256"] != expected_manifest_sha:
        refuse(
            16,
            "live_state",
            "READY Search product manifest differs from the current code's manifest",
            field="system_search.manifest_sha256",
            expected=expected_manifest_sha,
            actual=product["manifest_sha256"],
        )
    return True


def _product_projection(
    *,
    connection: Any,
    product_code: str,
    product: dict[str, Any] | None,
    expected_manifest_sha: str,
    sealed_ordinals: list[int],
    rows_done: int,
    system_count: int,
    full_projection: int,
    fixed_bytes_per_row: int,
    generation_id: str,
    canonical_schema: str,
    state_root: Path,
    identity: str,
    complete: dict[str, Any],
    complete_state: Path,
    tier_unit_cost: int,
    per_chunk_validator: Any,
) -> dict[str, Any]:
    if sealed_ordinals and product is None:
        refuse(16, "live_state", "sealed chunks exist without a product row", field=product_code)
    if not sealed_ordinals:
        return fresh_projection(full_projection, "no sealed chunk receipts")
    if product is None or product["lifecycle_state"] != "BUILDING":
        return fresh_projection(full_projection, "product is not BUILDING")
    if product["manifest_sha256"] != expected_manifest_sha:
        return fresh_projection(full_projection, "product manifest identity differs")
    if rows_done > system_count:
        refuse(16, "live_state", "sealed chunk systems exceed system_count", field=f"{product_code}.rows_done")
    relation = f"v3_derived.{product_code}"
    current_size = _relation_size(connection, relation, generation_id)
    start, start_reason = _start_bytes(
        state_root, product_code, generation_id, expected_manifest_sha, identity
    )
    bytes_done = max(0, current_size - start) if start is not None else 0
    rows_left = system_count - rows_done
    if product_code == "system_search":
        variable_left = _search_tail_bytes(connection, generation_id, canonical_schema)
        tier_left = 0
    else:
        variable_left = 2 * 63 * rows_left
        entries = _archetype_tier_entries_left(
            complete, complete_state, set(sealed_ordinals), per_chunk_validator
        )
        tier_left = tier_unit_cost * entries
    result = resume_projection(
        full_projection=full_projection,
        rows_done=rows_done,
        system_count=system_count,
        bytes_done=bytes_done,
        fixed_bytes_per_row=fixed_bytes_per_row,
        variable_left=variable_left,
        tier_left=tier_left,
    )
    result["build_start_receipt"] = start_reason
    result["relation_total_bytes_now"] = current_size
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-key", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--publication-sequence", required=True, type=int)
    parser.add_argument("--volume-reading", required=True, type=Path)
    parser.add_argument("--complete-state", required=True, type=Path)
    parser.add_argument("--search-state", required=True, type=Path)
    parser.add_argument("--archetype-state", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--image-model-file", type=Path,
        default=Path("/app/shared_contracts/v3_system_archetype_model.py"),
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=1_800_000)
    parser.add_argument("--database-url-env", default=DEFAULT_DATABASE_URL_ENV)
    args = parser.parse_args(argv)
    if args.publication_sequence < 1 or args.statement_timeout_ms < 1:
        parser.error("publication sequence and statement timeout must be positive")
    return args


def _runtime_modules() -> dict[str, Any]:
    from scripts import v3_archetype_calibration_complete as calibration
    from scripts import v3_system_archetype as archetype_builder
    from scripts import v3_system_search as search_builder
    from scripts.dev import measure_search_footprint
    from scripts.dev import measure_wide_archetype_footprint
    from scripts.operator.lib import f2d_evidence
    from shared_contracts import v3_system_archetype_model as model

    return {
        "calibration": calibration, "archetype_builder": archetype_builder,
        "search_builder": search_builder, "archetype_footprint": measure_wide_archetype_footprint,
        "search_footprint": measure_search_footprint, "evidence": f2d_evidence, "model": model,
    }


def run_gate(
    connection: Any, args: argparse.Namespace, *, identity: str,
    modules: dict[str, Any], now: datetime | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run all reads and return ``(exit_code, sealed_receipt)``."""
    global _FAILURE_CONTEXT

    evidence = modules["evidence"]
    calibration = modules["calibration"]
    archetype_builder = modules["archetype_builder"]
    search_builder = modules["search_builder"]
    model = modules["model"]
    results: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {}
    _FAILURE_CONTEXT = {
        "item_results": results,
        "inputs": inputs,
        "intermediates": {},
        "generation": {
            "generation_key": args.generation_key,
            "derived_generation_id": args.generation_id,
            "publication_sequence": args.publication_sequence,
        },
    }

    try:
        complete = _json_file(ROOT / evidence.COMPLETE_RECEIPT)
        decision = _json_file(ROOT / evidence.COEFFICIENT_DECISION)
        fractions_file = _json_file(ROOT / evidence.FRACTIONS)
        archetype_footprint = _json_file(ROOT / evidence.ARCHETYPE_FOOTPRINT)
        search_footprint = _json_file(ROOT / evidence.SEARCH_FOOTPRINT)
        step0 = _json_file(ROOT / evidence.STEP0_RECEIPT)
        volume = _json_file(args.volume_reading)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        refuse(3, "precheck", f"evidence input refused: {type(exc).__name__}")
    for name, value in (
        ("complete_receipt", complete), ("coefficient_decision", decision),
        ("archetype_footprint", archetype_footprint), ("search_footprint", search_footprint),
    ):
        inputs[f"{name}_content_sha256"] = value.get("content_sha256")
    inputs["fractions_sha256"] = fractions_file.get("fractions_sha256")

    results.append(check_coefficient_decision(
        decision,
        complete,
        archetype_builder._coefficients(),
        canonical_sha256=evidence.canonical_sha256,
    ))

    live = _live_generation(connection, args.generation_key)
    if (
        live["identifier"] != args.generation_id
        or live["key"] != args.generation_key
        or live["state"] != "PUBLISHED"
        or live["publication_sequence"] != args.publication_sequence
    ):
        refuse(12, "c", "pinned current PUBLISHED generation identity mismatch", field="generation")
    manifest = live["manifest"]
    schema = manifest.get("canonical_schema") if isinstance(manifest, dict) else None
    if not isinstance(schema, str) or SCHEMA_NAME.fullmatch(schema) is None:
        refuse(12, "c", "generation canonical schema is invalid", field="canonical_schema")
    generation = archetype_builder.Generation(
        identifier=live["identifier"], key=live["key"], state=live["state"],
        canonical_generation_id=live["canonical_generation_id"],
        canonical_publication_sequence=live["canonical_publication_sequence"],
        canonical_schema=schema, expected_systems=live["expected_systems"],
    )
    object.__setattr__(generation, "publication_sequence", live["publication_sequence"])
    validate_seal_for_item(
        complete,
        canonical_sha256=evidence.canonical_sha256,
        exit_code=11,
        item="b",
        label="complete_receipt",
    )
    try:
        checkout_model_sha = _sha256_file(
            ROOT / "shared_contracts/v3_system_archetype_model.py"
        )
        if args.image_model_file.is_symlink() or not args.image_model_file.is_file():
            refuse(
                11,
                "b",
                "API image archetype model file is missing or symlinked",
                field="model_file_sha256",
            )
        image_model_sha = _sha256_file(args.image_model_file)
    except OSError as exc:
        refuse(
            11,
            "b",
            f"model file is unavailable: {type(exc).__name__}",
            field="model_file_sha256",
        )
    _same("image_model_file_sha256", image_model_sha, checkout_model_sha, 11, "b")
    expected_manifest = archetype_builder.product_manifest(generation)
    results.append(check_complete_identity(
        complete, identity=identity, code_identity=archetype_builder.code_identity(),
        coefficients=archetype_builder._coefficients(), model_sha256=model.archetype_model_sha256(),
        model_file_sha256=checkout_model_sha, generation=generation,
        expected_manifest=expected_manifest, canonical_sha256=evidence.canonical_sha256,
    ))

    try:
        calibration.validate_complete_receipt(complete)
    except ValueError as exc:
        refuse(12, "c", str(exc), field="mode")
    plan, planned_systems, plan_sha = _chunk_plan(
        connection, args.generation_id, evidence.canonical_sha256
    )
    if tuple(model.ARCHETYPE_KEYS) != ARCHETYPE_KEYS:
        refuse(
            12,
            "c",
            "capacity-gate archetype keys differ from the shared model",
            field="model.ARCHETYPE_KEYS",
            expected=list(model.ARCHETYPE_KEYS),
            actual=list(ARCHETYPE_KEYS),
        )
    chunk_systems = _live_system_count(connection, args.generation_id)
    if planned_systems != chunk_systems:
        refuse(
            12,
            "c",
            "chunk plan and live system aggregate differ",
            field="build_chunk.systems",
            expected=planned_systems,
            actual=chunk_systems,
        )
    fractions, item_c = check_complete_histogram(
        complete, live_system_count=chunk_systems,
        expected_systems=live["expected_systems"], chunk_system_count=chunk_systems,
        live_chunk_plan_sha256=plan_sha,
    )
    results.append(item_c)
    system_count = chunk_systems
    sigma, item_d = check_fractions(
        complete, fractions_file, fractions, identity=identity,
        canonical_sha256=evidence.canonical_sha256,
    )
    results.append(item_d)
    inputs["fractions_content_sha256"] = evidence.canonical_sha256(fractions_file)

    validate_footprint_receipts(
        archetype_footprint,
        search_footprint,
        archetype_validator=(
            modules["archetype_footprint"].validate_archetype_footprint_receipt
        ),
        search_validator=modules["search_footprint"].validate_search_footprint_receipt,
    )

    checkout_011 = _sha256_file(ROOT / "sql/v3/migrations/011_v3_system_archetype.sql")
    checkout_010 = _sha256_file(ROOT / "sql/v3/migrations/010_v3_system_search_body_type_counts.sql")
    costs, item_e = check_footprints(
        archetype_footprint, search_footprint, fractions_file, step0,
        identity=identity, checkout_011_sha256=checkout_011, checkout_010_sha256=checkout_010,
        ledger_011_sha256=_ledger_hash(connection, "011_v3_system_archetype.sql"),
        ledger_010_sha256=_ledger_hash(connection, "010_v3_system_search_body_type_counts.sql"),
    )
    results.append(item_e)
    inputs.update(
        {
            "step0": item_e["compared"]["real_pre010_source"],
            "step0_host_disk": {
                field: step0["footprint"]["host_disk"].get(field)
                for field in ("filesystem", "mount_destination")
            },
            "volume_reading": volume,
            "costs": costs,
            "sigma_all": {
                "numerator": sigma.numerator,
                "denominator": sigma.denominator,
                "float": float(sigma),
            },
            "system_count": system_count,
            "system_count_sources": {
                "complete_receipt": complete["system_count"],
                "derived_generation": live["expected_systems"],
                "build_chunk": chunk_systems,
            },
        }
    )

    full_arch = full_archetype_projection(
        system_count=system_count, sigma=sigma,
        heap_bytes_per_row=costs["heap_bytes_per_row"],
        primary_key_bytes_per_row=costs["primary_key_bytes_per_row"],
        weighted_index_bytes_per_row=costs["weighted_index_bytes_per_row"],
        tier_index_bytes_per_row_per_unit_fraction=costs["tier_index_bytes_per_row_per_unit_fraction"],
    )
    full_search = (
        costs["real_pre010_bytes_per_row"] + costs["measured_010_delta_bytes_per_row"]
    ) * system_count
    products = _product_rows(connection, args.generation_id)
    plan_systems = {row[0]: row[1] for row in plan}
    search_ordinals, search_done = _sealed_chunks(
        connection, args.generation_id, "system_search", plan_systems
    )
    archetype_ordinals, archetype_done = _sealed_chunks(
        connection, args.generation_id, "system_archetype", plan_systems
    )
    search_manifest_sha = evidence.canonical_sha256(search_builder.product_manifest(
        search_builder.Generation(
            identifier=generation.identifier, key=generation.key, state=generation.state,
            canonical_generation_id=generation.canonical_generation_id,
            canonical_publication_sequence=generation.canonical_publication_sequence,
            canonical_schema=generation.canonical_schema, expected_systems=generation.expected_systems,
        )
    ))
    archetype_manifest_sha = complete["expected_product_manifest_sha256"]

    search_product = products.get("system_search")
    if _ready_verified_search_product(search_product, search_manifest_sha):
        search_projection = fresh_projection(0, "product is READY with VERIFIED receipt")
    else:
        search_projection = _product_projection(
            connection=connection, product_code="system_search", product=search_product,
            expected_manifest_sha=search_manifest_sha, sealed_ordinals=search_ordinals,
            rows_done=search_done, system_count=system_count, full_projection=full_search,
            fixed_bytes_per_row=costs["search_fixed_bytes_per_row"], generation_id=args.generation_id,
            canonical_schema=schema, state_root=args.search_state, identity=identity,
            complete=complete, complete_state=args.complete_state,
            tier_unit_cost=costs["tier_index_bytes_per_row_per_unit_fraction"],
            per_chunk_validator=calibration.validate_per_chunk_log,
        )
    archetype_projection = _product_projection(
        connection=connection, product_code="system_archetype",
        product=products.get("system_archetype"), expected_manifest_sha=archetype_manifest_sha,
        sealed_ordinals=archetype_ordinals, rows_done=archetype_done,
        system_count=system_count, full_projection=full_arch["projected_archetype_bytes"],
        fixed_bytes_per_row=costs["archetype_fixed_bytes_per_row"], generation_id=args.generation_id,
        canonical_schema=schema, state_root=args.archetype_state, identity=identity,
        complete=complete, complete_state=args.complete_state,
        tier_unit_cost=costs["tier_index_bytes_per_row_per_unit_fraction"],
        per_chunk_validator=calibration.validate_per_chunk_log,
    )
    intermediates = {
        **full_arch,
        "full_projected_search_bytes": full_search,
        "system_archetype": archetype_projection,
        "system_search": search_projection,
    }
    projected_archetype = archetype_projection["term_charged"]
    projected_search = search_projection["term_charged"]
    projected_new = projected_archetype + projected_search
    required = reserve_bytes(projected_new)
    _FAILURE_CONTEXT.update(
        {
            "intermediates": intermediates,
            "projected_archetype_bytes": projected_archetype,
            "projected_search_bytes": projected_search,
            "projected_new_bytes": projected_new,
            "required_bytes": required,
        }
    )
    # The database reads above can outlast the 15-minute freshness window; the
    # operator action keeps rewriting the reading while the gate runs, so the
    # comparison uses the freshest one rather than the one taken at launch.
    try:
        volume = _json_file(args.volume_reading)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        refuse(3, "precheck", f"volume reading refused: {type(exc).__name__}")
    inputs["volume_reading"] = volume
    available_bytes = volume.get("avail_bytes")
    if isinstance(available_bytes, bool) or not isinstance(available_bytes, int):
        refuse(
            15,
            "f",
            "volume avail_bytes is missing or invalid",
            field="volume.avail_bytes",
            actual=available_bytes,
        )
    arithmetic = capacity_result(
        archetype=archetype_projection,
        search=search_projection,
        available_bytes=available_bytes,
    )
    _FAILURE_CONTEXT.update(
        {
            **arithmetic,
        }
    )
    results.append(check_volume(volume, step0, arithmetic["required_bytes"], now=now or datetime.now(timezone.utc)))
    body = {
        "schema_version": RECEIPT_SCHEMA, "status": "passed", "exit_code": 0,
        "item_results": results,
        "inputs": inputs,
        "intermediates": intermediates,
        "projected_archetype_bytes": archetype_projection["term_charged"],
        "projected_search_bytes": search_projection["term_charged"],
        **arithmetic, "f2d_operator_code_sha256": identity,
        "generation": {"generation_key": args.generation_key, "derived_generation_id": args.generation_id, "publication_sequence": args.publication_sequence},
        "read_only": True, "db_writes_performed": False,
    }
    return 0, evidence.seal(body)


def _failure_receipt(
    *, identity: str | None, code: int, item: str, reason: str,
    field: str | None = None, expected: object = None, actual: object = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from scripts.operator.lib import f2d_evidence

    failure = {"item": item, "reason": reason}
    if field is not None:
        failure.update({"field": field, "expected": expected, "actual": actual})
    context = context or {}
    prior_results = context.get("item_results")
    item_results = list(prior_results) if isinstance(prior_results, list) else []
    item_results.append({"item": item, "status": "refused", **failure})
    required = context.get("required_bytes")
    available = context.get("available_bytes")
    if required is None and field == "available_bytes" and isinstance(expected, int):
        required = expected
    if available is None and field == "available_bytes" and isinstance(actual, int):
        available = actual
    return f2d_evidence.seal({
        "schema_version": RECEIPT_SCHEMA, "status": "refused", "exit_code": code,
        "item_results": item_results,
        "failures": [failure],
        "inputs": context.get("inputs", {}),
        "intermediates": context.get("intermediates", {}),
        "projected_archetype_bytes": context.get("projected_archetype_bytes"),
        "projected_search_bytes": context.get("projected_search_bytes"),
        "projected_new_bytes": context.get("projected_new_bytes"),
        "required_bytes": required, "available_bytes": available,
        "headroom_bytes": (
            available - required
            if available is not None and required is not None
            else None
        ),
        "f2d_operator_code_sha256": identity,
        "generation": context.get("generation"),
        "read_only": True, "db_writes_performed": False,
    })


def _output_argument(argv: list[str]) -> Path | None:
    """Locate only the failure-receipt destination without parsing arguments."""
    for index, value in enumerate(argv[:-1]):
        if value == "--output":
            return Path(argv[index + 1])
    return None


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    attested = os.environ.get(DEFAULT_IDENTITY_ENV)
    try:
        identity = f2d_operator_identity.require_operator_code_identity(ROOT, attested)
    except f2d_operator_identity.OperatorIdentityError as exc:
        receipt = _failure_receipt(identity=None, code=2, item="identity", reason=str(exc))
        output = _output_argument(raw_argv)
        if output is not None:
            _atomic_json(output, receipt)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 2
    args = parse_args(raw_argv)
    try:
        modules = _runtime_modules()
        modules["calibration"].refuse_unlisted_checkout_modules()
    except (ImportError, ValueError, f2d_operator_identity.OperatorIdentityError) as exc:
        receipt = _failure_receipt(identity=identity, code=3, item="precheck", reason=type(exc).__name__)
        _atomic_json(args.output, receipt)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 3
    dsn = os.environ.get(args.database_url_env)
    if not dsn:
        receipt = _failure_receipt(identity=identity, code=3, item="precheck", reason="database URL environment variable is missing")
        _atomic_json(args.output, receipt)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 3
    try:
        import psycopg

        with psycopg.connect(dsn) as connection:
            connection.read_only = True
            connection.execute("SELECT set_config('default_transaction_read_only','on',false)")
            connection.execute("SELECT set_config('statement_timeout',%s,false)", (f"{args.statement_timeout_ms}ms",))
            connection.execute("SELECT set_config('plan_cache_mode','force_custom_plan',false)")
            code, receipt = run_gate(connection, args, identity=identity, modules=modules)
    except GateRefusal as exc:
        code = exc.exit_code
        receipt = _failure_receipt(
            identity=identity, code=code, item=exc.item, reason=exc.reason,
            field=exc.field, expected=exc.expected, actual=exc.actual,
            context=exc.context,
        )
    except Exception as exc:  # database drivers expose a changing exception hierarchy
        code = 4
        receipt = _failure_receipt(
            identity=identity,
            code=4,
            item="database",
            reason=type(exc).__name__,
            context=_FAILURE_CONTEXT,
        )
    _atomic_json(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
