"""Load and match the reviewed legacy object classification registry.

This module deliberately has no database or network integration.  A caller must
receive an explicit match before it may propose any disposition for a dump
object; no match (or more than one match) is an unclassified blocker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = (
    ROOT / "config" / "legacy-migration" / "object-classification-v1.json"
)

CLASSES = {
    "public_reconstructable",
    "derived_rebuildable",
    "candidate_private_manual_user_history",
    "never_migrate_credentials_operational_security",
}
OBJECT_TYPES = {
    "SCHEMA",
    "EXTENSION",
    "TABLE",
    "MATERIALIZED VIEW",
    "VIEW",
    "TYPE",
    "FUNCTION",
    "TRIGGER",
    "INDEX",
    "SEQUENCE",
    "CONSTRAINT",
    "DEFAULT",
    "TABLE DATA",
    "MATERIALIZED VIEW DATA",
    "FK CONSTRAINT",
    "CHECK CONSTRAINT",
    "SEQUENCE OWNED BY",
    "SEQUENCE SET",
    "COMMENT",
    "ACL",
    "DEFAULT ACL",
}
REQUIRED_METADATA = {
    "classification",
    "rationale",
    "authoritative_source_or_rebuild",
    "candidate_key_columns",
    "relationship_columns",
    "row_content_inspection_permitted",
    "proposed_disposition",
}


class RegistryError(ValueError):
    """The registry is invalid or cannot classify an object safely."""


@dataclass(frozen=True)
class DumpObject:
    object_type: str
    schema: str
    name: str


def load_registry(path: Path = DEFAULT_REGISTRY) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    expanded = dict(data)
    expanded["entries"] = [
        {**profiles.get(entry.get("profile"), {}), **entry}
        for entry in data.get("entries", [])
    ]
    validate_registry(expanded)
    return expanded


def validate_registry(data: Mapping[str, Any]) -> None:
    if (
        data.get("registry_version") != 1
        or data.get("default_disposition") != "unclassified_blocker"
    ):
        raise RegistryError("registry must be version 1 and fail closed by default")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RegistryError("registry entries must be a non-empty list")
    identities: set[tuple[str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not REQUIRED_METADATA <= entry.keys():
            raise RegistryError("every entry must include all classification metadata")
        object_type = entry.get("object_type")
        schema = entry.get("schema")
        exact = entry.get("name")
        pattern = entry.get("name_pattern")
        if object_type not in OBJECT_TYPES or not isinstance(schema, str):
            raise RegistryError("entry has an unsupported object type or schema")
        if (exact is None) == (pattern is None):
            raise RegistryError(
                "entry must contain exactly one of name or name_pattern"
            )
        if pattern is not None:
            if (
                not isinstance(pattern, str)
                or not pattern.startswith("^")
                or not pattern.endswith("$")
            ):
                raise RegistryError("family patterns must be anchored")
            re.compile(pattern, re.ASCII)
        identity = (object_type, schema, exact or f"pattern:{pattern}")
        if identity in identities:
            raise RegistryError(f"duplicate registry entry: {identity}")
        identities.add(identity)
        if entry["classification"] not in CLASSES:
            raise RegistryError("entry has an unsupported classification")
        if not isinstance(entry["candidate_key_columns"], list) or not isinstance(
            entry["relationship_columns"], list
        ):
            raise RegistryError("key and relationship columns must be lists")
        if not isinstance(entry["row_content_inspection_permitted"], bool):
            raise RegistryError("row inspection permission must be boolean")


def classify_object(
    registry: Mapping[str, Any], obj: DumpObject
) -> Mapping[str, Any] | None:
    # pg_restore lists table definitions and their data as separate TOC items.
    # Data inherits the exact reviewed table decision rather than matching a
    # catch-all TABLE DATA rule that could accidentally weaken classification.
    inherited_type = {
        "TABLE DATA": "TABLE",
        "MATERIALIZED VIEW DATA": "MATERIALIZED VIEW",
    }.get(obj.object_type)
    lookup = DumpObject(inherited_type, obj.schema, obj.name) if inherited_type else obj
    matches = []
    for entry in registry["entries"]:
        if (
            entry["object_type"] != lookup.object_type
            or entry["schema"] != lookup.schema
        ):
            continue
        if entry.get("name") == lookup.name or (
            entry.get("name_pattern") is not None
            and re.fullmatch(entry["name_pattern"], lookup.name, re.ASCII)
        ):
            matches.append(entry)
    if len(matches) > 1:
        raise RegistryError(f"ambiguous registry classification for {obj}")
    return matches[0] if matches else None


def match_object(
    registry: Mapping[str, Any], toc_item: Mapping[str, Any] | object
) -> Mapping[str, Any] | None:
    """Adapter for sanitised TOC parser records used by the inventory CLI."""

    def field(name: str) -> Any:
        if isinstance(toc_item, Mapping):
            return toc_item.get(name)
        return getattr(toc_item, name, None)

    values = (field("object_type"), field("schema"), field("name"))
    if (
        not isinstance(values[0], str)
        or not values[0]
        or not isinstance(values[1], str)
        or not isinstance(values[2], str)
        or not values[2]
    ):
        raise RegistryError(
            "TOC item must provide object_type, schema, and name strings"
        )
    return classify_object(registry, DumpObject(*values))


_CREATE_PATTERNS = {
    "EXTENSION": re.compile(
        r"(?im)^\s*CREATE\s+EXTENSION\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)"
    ),
    "TABLE": re.compile(
        r"(?im)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)"
    ),
    "MATERIALIZED VIEW": re.compile(
        r"(?im)^\s*CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)"
    ),
    "VIEW": re.compile(
        r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:public\.)?([a-z_][a-z0-9_]*)"
    ),
    "TYPE": re.compile(r"(?im)^\s*CREATE\s+TYPE\s+(?:public\.)?([a-z_][a-z0-9_]*)"),
    "FUNCTION": re.compile(
        r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-z_][a-z0-9_]*)"
    ),
    "TRIGGER": re.compile(r"(?im)^\s*CREATE\s+TRIGGER\s+([a-z_][a-z0-9_]*)"),
    "INDEX": re.compile(
        r"(?im)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)"
    ),
}


def current_schema_objects(sql_paths: Iterable[Path]) -> set[DumpObject]:
    """Extract named objects declared by the ordered repository migrations."""
    text = "\n".join(path.read_text(encoding="utf-8") for path in sql_paths)
    objects = {DumpObject("SCHEMA", "", "public")}
    for object_type, pattern in _CREATE_PATTERNS.items():
        schema = "" if object_type == "EXTENSION" else "public"
        objects.update(
            DumpObject(object_type, schema, name) for name in pattern.findall(text)
        )
    return objects


def unclassified_objects(
    registry: Mapping[str, Any], objects: Iterable[DumpObject]
) -> list[DumpObject]:
    return sorted(
        (obj for obj in objects if classify_object(registry, obj) is None),
        key=lambda obj: (obj.object_type, obj.schema, obj.name),
    )
