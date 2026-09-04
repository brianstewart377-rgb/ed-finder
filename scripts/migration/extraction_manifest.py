#!/usr/bin/env python3
"""Fail-closed validation for reviewed selective-extraction manifests.

This module validates plans only.  It deliberately contains no database or
pg_restore execution path.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.migration.legacy_object_registry import (
        DumpObject,
        classify_object,
        load_registry as load_object_registry,
    )
except ModuleNotFoundError:  # Direct execution: python scripts/migration/...
    from legacy_object_registry import (  # type: ignore[no-redef]
        DumpObject,
        classify_object,
        load_registry as load_object_registry,
    )


SCHEMA_VERSION = "legacy-selective-extraction-manifest/v1"
CANDIDATE_CLASS = "candidate_private_manual_user_history"
DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "config/legacy-migration/object-classification-v1.json"
)
ALLOWED_FILTER_OPERATORS = {"eq", "in", "range"}
ALLOWED_CONFLICT_POLICIES = {"abort", "skip_existing", "update_if_unchanged"}
IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
FORBIDDEN_TEXT = re.compile(
    r"(?i)(select\s+\*|\b(select|insert|update|delete|drop|alter|copy)\b.+\b(from|into|table)\b"
    r"|(?:postgres(?:ql)?|mysql|redis)://|(?:password|passwd|secret|token|api[_-]?key)\s*[=:]"
    r"|(?:^|\s)(?:sudo|bash|sh|curl|wget|nc)\s|[;&|`]|\$\(|\bproduction\b|\bprod(?:uction)?[_-]?(?:db|database)\b)"
)


class ManifestValidationError(ValueError):
    """Raised when a manifest is incomplete or unsafe."""


def _fail(message: str) -> None:
    raise ManifestValidationError(message)


def _object_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    entries = registry.get("objects")
    if not isinstance(entries, list):
        entries = registry.get("classifications")
    if not isinstance(entries, list):
        _fail("classification registry must contain an objects list")
    return entries


def _registry_classes(registry: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in _object_entries(registry):
        if not isinstance(entry, dict):
            _fail("classification registry contains a non-object entry")
        # Only exact names are eligible for extraction. Reviewed families are
        # intentionally insufficient for a data-bearing extraction manifest.
        name = entry.get("name") or entry.get("object_name")
        classification = entry.get("classification") or entry.get("class")
        if isinstance(name, str) and isinstance(classification, str):
            result[name] = classification
    return result


def _table_registry_entry(registry: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Resolve an exact table name using the canonical matcher or test fixture map."""
    if isinstance(registry.get("entries"), list):
        schema, table = name.split(".", 1) if "." in name else ("public", name)
        match = classify_object(registry, DumpObject("TABLE", schema, table))
        return None if match is None else dict(match)
    classification = _registry_classes(registry).get(name)
    return (
        None
        if classification is None
        else {
            "classification": classification,
            "row_content_inspection_permitted": True,
        }
    )


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(f"classification registry is not a regular file: {path}")
    try:
        value = dict(load_object_registry(path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _fail(f"cannot read classification registry: {exc}")
    if not isinstance(value, dict):
        _fail("classification registry root must be an object")
    return value


def _require_keys(value: dict[str, Any], required: set[str], context: str) -> None:
    missing = sorted(required - value.keys())
    if missing:
        _fail(f"{context} is missing required fields: {', '.join(missing)}")


def _exact_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    extras = sorted(value.keys() - allowed)
    if extras:
        _fail(f"{context} contains unsupported fields: {', '.join(extras)}")


def _safe_identifier(value: Any, context: str, *, qualified: bool = False) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{context} must be a non-empty identifier")
    parts = value.split(".") if qualified else [value]
    if any(not IDENTIFIER.fullmatch(part) for part in parts):
        _fail(f"{context} must be an exact lower-case SQL identifier")
    return value


def _scan_unsafe_text(value: Any, path: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(
                r"(?i)(password|passwd|secret|token|credential|api[_-]?key|dsn|uri|url|host)",
                str(key),
            ):
                _fail(
                    f"credential, connection, or host field is forbidden at {path}.{key}"
                )
            _scan_unsafe_text(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_unsafe_text(child, f"{path}[{index}]")
    elif isinstance(value, str) and FORBIDDEN_TEXT.search(value):
        _fail(f"SQL, shell, credential, or production-like text is forbidden at {path}")


def _validate_count_bound(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        _fail(f"{context} must be an object")
    if set(value) not in ({"exact"}, {"minimum", "maximum"}):
        _fail(f"{context} must contain exact or minimum and maximum")
    numbers = list(value.values())
    if any(
        not isinstance(number, int) or isinstance(number, bool) or number < 0
        for number in numbers
    ):
        _fail(f"{context} counts must be non-negative integers")
    if "minimum" in value and value["minimum"] > value["maximum"]:
        _fail(f"{context} minimum exceeds maximum")


def validate_manifest(manifest: dict[str, Any], registry: dict[str, Any]) -> None:
    """Validate *manifest* or raise :class:`ManifestValidationError`."""

    if not isinstance(manifest, dict):
        _fail("manifest root must be an object")
    _scan_unsafe_text(manifest)
    required = {
        "schema_version",
        "manifest_id",
        "dump_sha256",
        "tables",
        "owner_approval",
        "abort_conditions",
        "rollback_conditions",
    }
    _require_keys(manifest, required, "manifest")
    _exact_keys(manifest, required, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        _fail(f"schema_version must be {SCHEMA_VERSION}")
    _safe_identifier(manifest["manifest_id"], "manifest_id")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["dump_sha256"])):
        _fail("dump_sha256 must be a lower-case SHA-256 digest")
    tables = manifest["tables"]
    if not isinstance(tables, list) or not tables:
        _fail("tables must be a non-empty exact allowlist")
    seen: set[str] = set()
    table_required = {
        "source_table",
        "columns",
        "key_filters",
        "maximum_rows",
        "destination_mapping",
        "idempotency_key_columns",
        "conflict_policy",
        "relationship_validations",
        "expected_source_count",
        "expected_target_count",
    }
    for index, table in enumerate(tables):
        context = f"tables[{index}]"
        if not isinstance(table, dict):
            _fail(f"{context} must be an object")
        _require_keys(table, table_required, context)
        _exact_keys(table, table_required, context)
        source = _safe_identifier(
            table["source_table"], f"{context}.source_table", qualified=True
        )
        if source in seen:
            _fail(f"duplicate source table: {source}")
        seen.add(source)
        registry_entry = _table_registry_entry(registry, source)
        if (
            registry_entry is None
            or registry_entry.get("classification") != CANDIDATE_CLASS
        ):
            _fail(f"{source} is not exact-classified as {CANDIDATE_CLASS}")
        if registry_entry.get("row_content_inspection_permitted") is not True:
            _fail(f"{source} does not permit row-content inspection")
        columns = table["columns"]
        if (
            not isinstance(columns, list)
            or not columns
            or len(set(columns)) != len(columns)
        ):
            _fail(f"{context}.columns must be a non-empty unique list")
        for column in columns:
            _safe_identifier(column, f"{context}.columns entry")
        filters = table["key_filters"]
        if not isinstance(filters, list) or not filters:
            _fail(f"{context}.key_filters must be non-empty and bounded")
        for filter_index, key_filter in enumerate(filters):
            if not isinstance(key_filter, dict):
                _fail(f"{context}.key_filters[{filter_index}] must be an object")
            _require_keys(
                key_filter,
                {"column", "operator", "value"},
                f"{context}.key_filters[{filter_index}]",
            )
            _exact_keys(
                key_filter,
                {"column", "operator", "value"},
                f"{context}.key_filters[{filter_index}]",
            )
            _safe_identifier(
                key_filter["column"], f"{context}.key_filters[{filter_index}].column"
            )
            if key_filter["column"] not in columns:
                _fail(f"{context} filter column must be explicitly allowlisted")
            if key_filter["operator"] not in ALLOWED_FILTER_OPERATORS:
                _fail(f"{context} filter operator is not allowed")
            operator = key_filter["operator"]
            value = key_filter["value"]
            scalar = isinstance(value, (str, int)) and not isinstance(value, bool)
            if operator == "eq" and not scalar:
                _fail(f"{context} eq filter requires one string or integer")
            if operator == "in" and (
                not isinstance(value, list)
                or not 1 <= len(value) <= 10_000
                or any(
                    not isinstance(item, (str, int)) or isinstance(item, bool)
                    for item in value
                )
            ):
                _fail(f"{context} in filter requires 1..10000 string or integer values")
            if operator == "range":
                if not isinstance(value, dict) or set(value) != {
                    "minimum",
                    "maximum",
                }:
                    _fail(f"{context} range filter requires exact minimum and maximum")
                limits = list(value.values())
                if any(
                    not isinstance(item, (str, int)) or isinstance(item, bool)
                    for item in limits
                ):
                    _fail(f"{context} range limits must be strings or integers")
                if type(limits[0]) is not type(limits[1]) or limits[0] > limits[1]:
                    _fail(f"{context} range limits are not comparable or ordered")
            values = (
                value
                if isinstance(value, list)
                else list(value.values())
                if isinstance(value, dict)
                else [value]
            )
            if any(
                isinstance(item, str) and any(mark in item for mark in ("*", "?"))
                for item in values
            ):
                _fail(f"{context} wildcard filter values are forbidden")
        maximum_rows = table["maximum_rows"]
        if (
            not isinstance(maximum_rows, int)
            or isinstance(maximum_rows, bool)
            or maximum_rows < 1
        ):
            _fail(f"{context}.maximum_rows must be a positive integer")
        mapping = table["destination_mapping"]
        if not isinstance(mapping, dict):
            _fail(f"{context}.destination_mapping must be an object")
        _require_keys(mapping, {"table", "columns"}, f"{context}.destination_mapping")
        _exact_keys(mapping, {"table", "columns"}, f"{context}.destination_mapping")
        _safe_identifier(
            mapping["table"], f"{context}.destination_mapping.table", qualified=True
        )
        if not isinstance(mapping["columns"], dict) or set(mapping["columns"]) != set(
            columns
        ):
            _fail(
                f"{context}.destination_mapping.columns must map every source column exactly"
            )
        for destination in mapping["columns"].values():
            _safe_identifier(destination, f"{context}.destination column")
        idempotency_keys = table["idempotency_key_columns"]
        if (
            not isinstance(idempotency_keys, list)
            or not idempotency_keys
            or len(set(idempotency_keys)) != len(idempotency_keys)
            or any(key not in columns for key in idempotency_keys)
        ):
            _fail(
                f"{context}.idempotency_key_columns must be a non-empty subset of columns"
            )
        if table["conflict_policy"] not in ALLOWED_CONFLICT_POLICIES:
            _fail(f"{context}.conflict_policy is not allowed")
        relationships = table["relationship_validations"]
        if not isinstance(relationships, list) or not relationships:
            _fail(f"{context}.relationship_validations must be non-empty")
        for relationship in relationships:
            if not isinstance(relationship, dict):
                _fail(f"{context} relationship validation must be an object")
            _require_keys(
                relationship,
                {
                    "source_columns",
                    "referenced_table",
                    "referenced_columns",
                    "required",
                },
                context,
            )
            _exact_keys(
                relationship,
                {
                    "source_columns",
                    "referenced_table",
                    "referenced_columns",
                    "required",
                },
                context,
            )
            if relationship["required"] is not True:
                _fail(f"{context} relationship validation must be required")
            _safe_identifier(
                relationship["referenced_table"],
                f"{context}.referenced_table",
                qualified=True,
            )
            for key in ("source_columns", "referenced_columns"):
                values = relationship[key]
                if not isinstance(values, list) or not values:
                    _fail(f"{context}.{key} must be a non-empty list")
                for value in values:
                    _safe_identifier(value, f"{context}.{key} entry")
            if len(relationship["source_columns"]) != len(
                relationship["referenced_columns"]
            ):
                _fail(f"{context} relationship column cardinality differs")
        _validate_count_bound(
            table["expected_source_count"], f"{context}.expected_source_count"
        )
        _validate_count_bound(
            table["expected_target_count"], f"{context}.expected_target_count"
        )
    approval = manifest["owner_approval"]
    if not isinstance(approval, dict):
        _fail("owner_approval must be an object")
    _require_keys(
        approval, {"owner", "decision", "approved_at", "scope"}, "owner_approval"
    )
    _exact_keys(
        approval, {"owner", "decision", "approved_at", "scope"}, "owner_approval"
    )
    if approval["decision"] != "approved":
        _fail("owner_approval.decision must be approved")
    for field in ("owner", "approved_at", "scope"):
        if not isinstance(approval[field], str) or not approval[field].strip():
            _fail(f"owner_approval.{field} must be non-empty")
    for field in ("abort_conditions", "rollback_conditions"):
        values = manifest[field]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(v, str) or not v.strip() for v in values)
        ):
            _fail(f"{field} must be a non-empty list of explicit conditions")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an offline extraction manifest (no extraction is performed)."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest, load_registry(args.registry))
    except (OSError, json.JSONDecodeError, ManifestValidationError) as exc:
        parser.error(str(exc))
    print("manifest valid; no data was extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
