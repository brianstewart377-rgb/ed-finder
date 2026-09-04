from __future__ import annotations

import copy

import pytest

from scripts.migration.extraction_manifest import (
    DEFAULT_REGISTRY,
    ManifestValidationError,
    load_registry,
    validate_manifest,
)


@pytest.fixture
def registry() -> dict:
    return {
        "objects": [
            {
                "name": "public.user_notes",
                "classification": "candidate_private_manual_user_history",
            },
            {
                "name": "public.systems",
                "classification": "public_reconstructable_source_data",
            },
        ]
    }


@pytest.fixture
def manifest() -> dict:
    return {
        "schema_version": "legacy-selective-extraction-manifest/v1",
        "manifest_id": "reviewed_user_notes_001",
        "dump_sha256": "a" * 64,
        "tables": [
            {
                "source_table": "public.user_notes",
                "columns": ["user_id", "note"],
                "key_filters": [
                    {"column": "user_id", "operator": "in", "value": [10, 11]}
                ],
                "maximum_rows": 2,
                "destination_mapping": {
                    "table": "public.user_notes",
                    "columns": {"user_id": "user_id", "note": "note"},
                },
                "idempotency_key_columns": ["user_id"],
                "conflict_policy": "abort",
                "relationship_validations": [
                    {
                        "source_columns": ["user_id"],
                        "referenced_table": "public.users",
                        "referenced_columns": ["id"],
                        "required": True,
                    }
                ],
                "expected_source_count": {"exact": 2},
                "expected_target_count": {"minimum": 0, "maximum": 2},
            }
        ],
        "owner_approval": {
            "owner": "data-owner",
            "decision": "approved",
            "approved_at": "2026-09-04T12:00:00Z",
            "scope": "two reviewed user note records",
        },
        "abort_conditions": ["count is outside the approved bounds"],
        "rollback_conditions": ["relationship validation fails"],
    }


def test_accepts_complete_bounded_candidate_manifest(
    manifest: dict, registry: dict
) -> None:
    validate_manifest(manifest, registry)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda m: m["tables"][0].update(source_table="public.*"),
            "exact lower-case SQL identifier",
        ),
        (
            lambda m: m["tables"][0].update(columns=["*"]),
            "exact lower-case SQL identifier",
        ),
        (lambda m: m["tables"][0].update(key_filters=[]), "non-empty and bounded"),
        (
            lambda m: m["tables"][0].update(
                key_filters=[{"column": "user_id", "operator": "in", "value": ["*"]}]
            ),
            "wildcard filter values",
        ),
        (
            lambda m: m["tables"][0].update(
                key_filters=[
                    {"column": "user_id", "operator": "range", "value": {"minimum": 9}}
                ]
            ),
            "exact minimum and maximum",
        ),
        (lambda m: m["tables"][0].pop("maximum_rows"), "missing required fields"),
        (lambda m: m["tables"][0].update(maximum_rows=0), "positive integer"),
        (
            lambda m: m["tables"][0].update(idempotency_key_columns=["missing"]),
            "non-empty subset",
        ),
        (lambda m: m["tables"][0].update(conflict_policy="upsert"), "not allowed"),
        (
            lambda m: m["tables"][0].update(relationship_validations=[]),
            "must be non-empty",
        ),
        (lambda m: m["owner_approval"].update(decision="pending"), "must be approved"),
        (lambda m: m.update(sql="SELECT * FROM users"), "forbidden"),
        (lambda m: m["abort_conditions"].append("sh -c whoami"), "forbidden"),
        (
            lambda m: m["owner_approval"].update(scope="postgresql://user:pw@db/x"),
            "forbidden",
        ),
        (lambda m: m["owner_approval"].update(password="hunter2"), "forbidden"),
        (
            lambda m: m["owner_approval"].update(scope="copy to production_db"),
            "forbidden",
        ),
    ],
)
def test_rejects_unsafe_or_incomplete_manifests(
    manifest: dict, registry: dict, mutation, expected: str
) -> None:
    candidate = copy.deepcopy(manifest)
    mutation(candidate)
    with pytest.raises(ManifestValidationError, match=expected):
        validate_manifest(candidate, registry)


def test_rejects_non_candidate_and_unknown_tables(
    manifest: dict, registry: dict
) -> None:
    manifest["tables"][0]["source_table"] = "public.systems"
    with pytest.raises(ManifestValidationError, match="not exact-classified"):
        validate_manifest(manifest, registry)

    manifest["tables"][0]["source_table"] = "public.unknown"
    with pytest.raises(ManifestValidationError, match="not exact-classified"):
        validate_manifest(manifest, registry)


def test_rejects_reviewed_family_without_exact_registry_entry(manifest: dict) -> None:
    registry = {
        "objects": [
            {
                "family": "public.user_*",
                "classification": "candidate_private_manual_user_history",
            }
        ]
    }
    with pytest.raises(ManifestValidationError, match="not exact-classified"):
        validate_manifest(manifest, registry)


def test_current_registry_accepts_exact_candidate_name_from_reviewed_family(
    manifest: dict,
) -> None:
    if not DEFAULT_REGISTRY.exists():
        pytest.skip("classification registry is developed alongside this validator")
    manifest["tables"][0]["source_table"] = "public.system_notes"
    validate_manifest(manifest, load_registry())


def test_current_registry_rejects_candidate_whose_rows_may_not_be_inspected(
    manifest: dict,
) -> None:
    manifest["tables"][0]["source_table"] = "public.app_users"
    with pytest.raises(
        ManifestValidationError, match="does not permit row-content inspection"
    ):
        validate_manifest(manifest, load_registry())
