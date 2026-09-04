from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.migration.legacy_object_registry import (
    DEFAULT_REGISTRY,
    DumpObject,
    RegistryError,
    classify_object,
    current_schema_objects,
    load_registry,
    match_object,
    unclassified_objects,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[1]


def test_registry_covers_every_object_declared_by_current_migrations() -> None:
    registry = load_registry()
    sql_paths = sorted((ROOT / "sql").glob("[0-9][0-9][0-9]_*.sql"))

    missing = unclassified_objects(registry, current_schema_objects(sql_paths))

    assert missing == []


@pytest.mark.parametrize(
    ("object_type", "name", "classification"),
    [
        ("TABLE", "systems", "public_reconstructable"),
        ("TABLE", "system_notes", "candidate_private_manual_user_history"),
        (
            "TABLE",
            "station_external_identity",
            "candidate_private_manual_user_history",
        ),
        ("TABLE DATA", "routes", "candidate_private_manual_user_history"),
        ("TABLE", "web_sessions", "never_migrate_credentials_operational_security"),
        ("TABLE", "profile_sync", "never_migrate_credentials_operational_security"),
        ("TABLE", "admin_job_runs", "never_migrate_credentials_operational_security"),
        ("TABLE", "api_cache", "derived_rebuildable"),
        ("MATERIALIZED VIEW", "mv_map_heat_50ly", "derived_rebuildable"),
        ("MATERIALIZED VIEW DATA", "mv_map_heat_50ly", "derived_rebuildable"),
        ("INDEX", "idx_routes_commander_created", "derived_rebuildable"),
        ("DEFAULT ACL", "app_owner", "never_migrate_credentials_operational_security"),
    ],
)
def test_expected_classification(
    object_type: str, name: str, classification: str
) -> None:
    match = classify_object(load_registry(), DumpObject(object_type, "public", name))
    assert match is not None
    assert match["classification"] == classification


def test_unknown_objects_fail_closed() -> None:
    assert (
        classify_object(
            load_registry(), DumpObject("TABLE", "public", "surprise_table")
        )
        is None
    )
    assert (
        classify_object(
            load_registry(), DumpObject("TABLE DATA", "public", "surprise_table")
        )
        is None
    )


def test_match_object_accepts_sanitised_parser_mapping() -> None:
    match = match_object(
        load_registry(),
        {"object_type": "TABLE DATA", "schema": "public", "name": "system_notes"},
    )
    assert match is not None
    assert match["classification"] == "candidate_private_manual_user_history"


def test_registry_source_is_versioned_and_declares_fail_closed_default() -> None:
    raw = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    assert raw["registry_version"] == 1
    assert raw["default_disposition"] == "unclassified_blocker"


def test_registry_rejects_unanchored_families() -> None:
    registry = copy.deepcopy(load_registry())
    registry["entries"][0].pop("name")
    registry["entries"][0]["name_pattern"] = "public"
    with pytest.raises(RegistryError, match="anchored"):
        validate_registry(registry)


def test_registry_rejects_ambiguous_matches() -> None:
    registry = copy.deepcopy(load_registry())
    registry["entries"].append(copy.deepcopy(registry["entries"][1]))
    with pytest.raises(RegistryError, match="ambiguous"):
        classify_object(registry, DumpObject("EXTENSION", "", "pg_trgm"))
