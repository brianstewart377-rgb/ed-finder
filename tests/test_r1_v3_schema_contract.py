from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "r1_v3"
MIGRATION = SQL_DIR / "001_structural_shell.sql"
MANIFEST = SQL_DIR / "migration-manifest.txt"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_r1_v3_manifest_is_isolated_and_explicit() -> None:
    assert MANIFEST.read_text(encoding="utf-8").splitlines() == ["001_structural_shell.sql"]
    legacy_manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(encoding="utf-8")
    assert "001_structural_shell.sql" not in legacy_manifest
    assert "r1_v3" not in legacy_manifest


def test_structural_shell_is_additive_only() -> None:
    sql = _sql()
    executable_lines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    forbidden_statement = re.compile(r"^(INSERT|UPDATE|DELETE|TRUNCATE|COPY|DROP)\b", re.IGNORECASE)
    assert not [line for line in executable_lines if forbidden_statement.search(line)]
    assert not re.search(r"\b(ALTER|CREATE)\s+(TABLE|SCHEMA|VIEW)\s+v3_", sql, re.IGNORECASE)
    assert "REFERENCES public." not in sql


def test_structural_shell_creates_only_r1_logical_schemas() -> None:
    sql = _sql()
    for schema in ("r1_meta", "r1_cache", "r1_plan"):
        assert f"CREATE SCHEMA {schema};" in sql
    assert "CREATE SCHEMA v3_" not in sql


def test_catalog_bound_foreign_key_types_are_uuid() -> None:
    sql = _sql()
    assert re.search(r"canonical_generation_id\s+UUID\s+NOT NULL", sql)
    assert re.search(r"created_from_canonical_generation_id\s+UUID", sql)
    assert re.search(r"owner_account_id\s+UUID\s+NOT NULL", sql)
    assert "canonical_generation_id  BIGINT" not in sql
    assert "canonical_generation_id       BIGINT" not in sql
    assert "REFERENCES v3_meta.canonical_generation (generation_id)" in sql
    assert "REFERENCES v3_identity.account (account_id)" in sql


def test_first_slice_contains_expected_structural_tables_only() -> None:
    sql = _sql()
    expected_tables = {
        "r1_meta.mechanics_revision",
        "r1_meta.model_revision",
        "r1_meta.programme_revision",
        "r1_meta.capability_generation",
        "r1_meta.current_capability_generation",
        "r1_plan.saved_plan",
        "r1_plan.plan_revision",
        "r1_plan.plan_node",
        "r1_plan.plan_allocation",
        "r1_plan.plan_assessment",
    }
    created = set(re.findall(r"CREATE TABLE\s+([a-z0-9_.]+)", sql, re.IGNORECASE))
    assert created == expected_tables
    assert "CREATE TABLE v3_vocab.body_subtype" not in sql
    assert "CREATE TABLE r1_plan.assessment_condition" not in sql


def test_capability_current_is_typed_empty_and_context_free() -> None:
    sql = _sql()
    start = sql.index("CREATE VIEW r1_cache.system_capability_current")
    end = sql.index("CREATE TABLE r1_plan.saved_plan")
    view_sql = sql[start:end].lower()
    assert "where false" in view_sql
    for required in (
        "hmc_count",
        "water_world_count",
        "ammonia_world_count",
        "geological_body_count",
        "geological_unknown_count",
        "surface_slot_unknown_body_count",
        "nearest_hmc_distance_ls",
    ):
        assert required in view_sql
    for forbidden in (
        "plan_fit",
        "pair_resilience",
        "suggested_economy",
        "overall_score",
        "development_score",
        "programme_id",
    ):
        assert forbidden not in view_sql


def test_plan_revision_and_assessment_are_immutable_revision_bound() -> None:
    sql = _sql()
    assert "UNIQUE (plan_id, revision_number)" in sql
    assert "UNIQUE (plan_id, candidate_plan_sha256)" in sql
    assert "fk_r1_saved_plan_current_revision" in sql
    assert "fk_r1_plan_assessment_plan_binding" in sql
    assert "candidate_plan_sha256" in sql
    assert "evidence_snapshot_sha256" in sql
    assert "result_sha256" in sql


def test_exclusive_allocation_has_database_double_credit_guard() -> None:
    sql = _sql()
    assert "uq_r1_plan_allocation_exclusive_resource" in sql
    assert "WHERE allocation_mode = 'exclusive'" in sql
    assert "UNIQUE NULLS NOT DISTINCT" in sql


def test_plan_fit_cannot_exist_for_unsupported_states() -> None:
    sql = _sql()
    assert "chk_r1_plan_assessment_plan_fit_range" in sql
    assert "chk_r1_plan_assessment_plan_fit_state" in sql
    fit_check = sql[sql.index("chk_r1_plan_assessment_plan_fit_state") :]
    assert "conditionally_supported" in fit_check
    assert "supported" in fit_check
    assert "not_supported" not in fit_check.split("CONSTRAINT", 1)[0]


def test_no_universal_or_legacy_rating_columns_are_created() -> None:
    sql = _sql().lower()
    for forbidden_identifier in (
        "overall_development_potential",
        "suggested_economy",
        "overall_score",
        "development_score",
        "r1_ratings",
        "r1_economy_scores",
        "r1_system_value",
    ):
        assert forbidden_identifier not in sql
