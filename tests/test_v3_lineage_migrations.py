"""Structural guards for the committed V3 lineage migrations.

Rules that every migration must satisfy for the reviewed production migration
operation to apply it safely, plus the objects each migration promises.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sql/v3/migration-manifest.txt"

# 002 predates the self-transaction rule and is already applied, so it is never
# re-applied. Nothing else may join this set.
APPLIED_BEFORE_THE_RULE = {"002_v3_accounts_identity.sql"}


def _entries() -> list[tuple[str, str]]:
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        checksum, _, remainder = line.partition("  ")
        ledger_name, _, path = remainder.partition("  ")
        rows.append((ledger_name, f"sql/{path}"))
        assert re.fullmatch(r"[0-9a-f]{64}", checksum), line
    return rows


def test_every_manifest_migration_exists_and_hashes_as_recorded():
    from hashlib import sha256

    for ledger_name, path in _entries():
        source = (ROOT / path).read_bytes()
        recorded = next(
            line.split("  ")[0]
            for line in MANIFEST.read_text(encoding="utf-8").splitlines()
            if line.strip().endswith(path.removeprefix("sql/"))
        )
        assert sha256(source).hexdigest() == recorded, ledger_name
        assert b"\r\n" not in source, f"{path} must stay LF-terminated"


def test_every_migration_about_to_be_applied_owns_its_transaction():
    module = importlib.util.spec_from_file_location(
        "v3_production_migrate", ROOT / "scripts/operator/v3_production_migrate.py"
    )
    assert module and module.loader
    migrate = importlib.util.module_from_spec(module)
    module.loader.exec_module(migrate)

    for ledger_name, path in _entries():
        text = (ROOT / path).read_text(encoding="utf-8")
        if ledger_name in APPLIED_BEFORE_THE_RULE:
            continue
        migrate.require_self_transactional(text, ledger_name)


def test_004_creates_the_search_spatial_and_cluster_objects():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    for relation in (
        "v3_derived.system_search",
        "v3_spatial.cell_level",
        "v3_spatial.cell_summary",
        "v3_spatial.cluster_run",
        "v3_spatial.cluster",
        "v3_spatial.cluster_member",
    ):
        assert f"CREATE TABLE {relation}" in source
    assert "CREATE SCHEMA v3_spatial" in source
    assert "CREATE VIEW v3_app.system_search" in source
    assert "CREATE VIEW v3_app.cluster_member" in source


def test_004_uses_cube_with_gist_and_not_postgis():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE EXTENSION IF NOT EXISTS cube" in source
    assert "position_ly cube NOT NULL" in source
    assert "USING gist(position_ly)" in source
    # Verified against the retained production database: postgis is unavailable,
    # so nothing may depend on it. The comment naming it is fine; using it is not.
    assert "CREATE EXTENSION IF NOT EXISTS postgis" not in source.lower()
    assert "USING gist(geometry" not in source
    assert "geometry" not in source.lower()


def test_004_applies_the_shared_immutability_guard_to_every_new_relation():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    assert "v3_derived.guard_generation_write()" in source
    for relation in (
        "v3_derived.system_search",
        "v3_spatial.cell_summary",
        "v3_spatial.cluster_run",
        "v3_spatial.cluster",
        "v3_spatial.cluster_member",
    ):
        assert f"'{relation}'" in source, relation
    # Five trigger forms per relation, as 003 established.
    assert "immutable_insert" in source
    assert "immutable_update_old" in source
    assert "immutable_update_new" in source
    assert "immutable_delete" in source
    assert "immutable_truncate" in source


def test_004_never_touches_canonical_truth():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    # TRUNCATE is deliberately absent from this list: the migration adds a
    # BEFORE TRUNCATE guard that forbids it, so the word appears by design.
    for forbidden in (
        "v3_gen_",
        "v3_identity.",
        "v3_vocab.",
        "v3_source.",
        "DROP TABLE",
        "DROP SCHEMA",
    ):
        assert forbidden not in source, forbidden
    # Derived data is generated, never hand-written into canonical relations.
    assert "INSERT INTO v3_gen" not in source


def test_governed_purge_is_registered_immediately_after_product_publication():
    assert _entries()[-2:] == [
        ("015_v3_derived_product_publication.sql",
         "sql/v3/migrations/015_v3_derived_product_publication.sql"),
        ("016_v3_governed_derived_purge.sql",
         "sql/v3/migrations/016_v3_governed_derived_purge.sql"),
    ]


def test_016_installs_the_governed_ledger_and_recovery_functions():
    source = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    for relation in ("derived_generation_purge_request", "derived_generation_purge_event"):
        assert f"CREATE TABLE v3_meta.{relation}" in source
    for function in (
        "begin_derived_generation_purge", "purge_derived_payload_batch",
        "complete_derived_payload_relation", "complete_derived_generation_purge",
        "purge_set_relation_autovacuum", "purge_set_writer_fence",
        "cancel_purge_rewrite", "cancel_purge_batch",
    ):
        assert f"CREATE FUNCTION v3_meta.{function}(" in source
    assert re.search(r"IF NOT EXISTS \(SELECT 1 FROM pg_roles WHERE rolname='v3_derived_purge_executor'\) THEN"
                     r".*?SET LOCAL createrole_self_grant = 'set';\s+CREATE ROLE v3_derived_purge_executor",
                     source, re.DOTALL)
    assert "m.set_option AND NOT m.inherit_option" in source
    assert "GRANT MAINTAIN ON" in source
    assert "SET search_path=pg_catalog" in source


def test_016_only_installs_capability_and_leaves_archetype_guards_intact():
    source = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    # Functions run only when later invoked; DO blocks execute at installation
    # and remain in the checked text so they cannot hide a payload mutation.
    top_level = re.sub(
        r"CREATE(?: OR REPLACE)? FUNCTION\b.*?\$\$.*?\$\$;", "", source,
        flags=re.DOTALL | re.IGNORECASE,
    )
    top_level = re.sub(r"--[^\n]*", "", top_level)
    assert not re.search(r"\b(?:DELETE\s+FROM|VACUUM)\b", top_level, re.IGNORECASE)
    assert not re.search(r"\b(?:SELECT|CALL)\s+v3_meta\.(?:begin_derived_generation_purge|purge_derived_payload_batch)",
                         top_level, re.IGNORECASE)
    assert not re.search(r"(?:CREATE|DROP)\s+TRIGGER[^;]*ON\s+v3_derived\.(?:system_archetype|archetype_build_chunk)",
                         source, re.IGNORECASE)


def test_016_event_enum_contains_every_design_recovery_event_and_no_other_kind():
    source = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    enum = re.search(r"event_kind text NOT NULL CHECK\(event_kind IN \((.*?)\)\)", source, re.DOTALL)
    assert enum is not None
    assert set(re.findall(r"'([A-Z_]+)'", enum.group(1))) == {
        "AUTHORIZED", "BATCH_STARTED", "BATCH_COMMITTED", "BATCH_ROLLED_BACK",
        "RELATION_LOGICALLY_EMPTY", "REWRITE_STARTED", "REWRITE_VERIFIED", "REWRITE_ROLLED_BACK",
        "COMPLETED", "FAILED_STOP", "SERVICES_QUIESCED", "SERVICES_RESTORED",
        "AUTOVACUUM_DISABLED", "AUTOVACUUM_RESTORED", "WRITER_FENCE_ENABLED", "WRITER_FENCE_RESTORED",
        "REWRITE_CANCEL_REQUESTED", "BATCH_CANCEL_REQUESTED",
    }


def test_016_writer_restore_acknowledgement_is_scoped_and_durable():
    source = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    assert "acknowledge_failed_stop_ bigint DEFAULT NULL" in source
    assert "p.plan_sha256=r.plan_sha256 AND e.event_sequence=acknowledge_failed_stop_" in source
    assert "e.event_kind='FAILED_STOP' AND e.failure_evidence->'integrity_failed'='true'::jsonb" in source
    assert "ack.event_kind IN ('FAILED_STOP','WRITER_FENCE_RESTORED')" in source
    assert "purge_assert_recovery_safe(purge_,acknowledge_failed_stop_)" in source
    assert "jsonb_build_object('acknowledge_failed_stop',acknowledge_failed_stop_)" in source
    assert "v3_meta.purge_set_writer_fence(uuid,boolean,bigint)" in source
    assert "RAISE EXCEPTION 'integrity failure stops purge'" in source


def test_016_acknowledged_failed_rewrite_restore_retains_backend_and_progress_guards():
    source = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    recovery = source.split("CREATE FUNCTION v3_meta.purge_assert_recovery_safe(", 1)[1].split("END $$;", 1)[0]
    assert "z.event_sequence=acknowledge_failed_stop_" in recovery
    assert "z.failure_evidence->'integrity_failed'='true'::jsonb" in recovery
    assert "z.failure_evidence->'rewrite_committed'='true'::jsonb" in recovery
    assert "z.failure_evidence->>'start_event'=e.event_sequence::text" in recovery
    assert "a.pid=e.backend_pid AND a.backend_start=e.backend_start" in recovery
    assert "pg_stat_progress_cluster WHERE relid=e.relation_oid" in recovery
    assert "pg_stat_progress_analyze WHERE relid=e.relation_oid" in recovery
