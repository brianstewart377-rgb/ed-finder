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
    assert _entries()[-7:] == [
        ("015_v3_derived_product_publication.sql",
         "sql/v3/migrations/015_v3_derived_product_publication.sql"),
        ("016_v3_governed_derived_purge.sql",
         "sql/v3/migrations/016_v3_governed_derived_purge.sql"),
        ("019_v3_purge_copy_and_drop.sql",
         "sql/v3/migrations/019_v3_purge_copy_and_drop.sql"),
        ("020_v3_purge_swap_lock_order.sql",
         "sql/v3/migrations/020_v3_purge_swap_lock_order.sql"),
        ("021_v3_purge_long_phase_bounds.sql",
         "sql/v3/migrations/021_v3_purge_long_phase_bounds.sql"),
        ("022_v3_purge_keyset_start.sql",
         "sql/v3/migrations/022_v3_purge_keyset_start.sql"),
        ("023_v3_system_search_name_prefix_index.sql",
         "sql/v3/migrations/023_v3_system_search_name_prefix_index.sql"),
    ]


def test_023_adds_only_a_transactional_bounded_generation_prefix_index():
    source = (ROOT / "sql/v3/migrations/023_v3_system_search_name_prefix_index.sql").read_text()
    statements = re.sub(r"--[^\n]*", "", source)
    assert "CREATE INDEX IF NOT EXISTS system_search_name_prefix" in statements
    assert "ON v3_derived.system_search (derived_generation_id, lower(name) text_pattern_ops)" in statements
    assert "SET LOCAL lock_timeout = '5s';" in statements
    assert "SET LOCAL statement_timeout = '4h';" in statements
    assert "i.indisvalid AND i.indisready" in statements
    assert "incompatible definition" in statements
    assert not re.search(r"\b(?:CONCURRENTLY|DROP|INSERT|UPDATE|DELETE|TRUNCATE|ALTER)\b", statements)


def _function(source, name):
    match = re.search(rf"^CREATE (?:OR REPLACE )?FUNCTION v3_meta\.{name}\(.*?^END \$\$;$", source,
                      flags=re.DOTALL | re.MULTILINE)
    assert match, name
    return match.group(0)


def test_021_only_bounds_the_copy_long_phases():
    source = (ROOT / "sql/v3/migrations/021_v3_purge_long_phase_bounds.sql").read_text()
    assert re.findall(r"CREATE (?:OR REPLACE )?FUNCTION v3_meta\.(\w+)\(", source) == [
        "purge_copy_prepare", "purge_copy_build_indexes", "purge_copy_verify",
    ]
    assert source.count("CREATE OR REPLACE FUNCTION") == 3
    top_level = re.sub(r"CREATE(?: OR REPLACE)? FUNCTION\b.*?\$\$.*?\$\$;", "", source,
                       flags=re.DOTALL | re.IGNORECASE)
    top_level = re.sub(r"--[^\n]*", "", top_level)
    top_level = re.sub(r"'[^']*'", "''", top_level)
    # Installation creates no relation, writes no row and changes no grant
    # (CREATE OR REPLACE keeps 019's owner and EXECUTE grant).
    assert not re.search(r"\b(?:CREATE\s+(?:TABLE|VIEW|SCHEMA|INDEX|ROLE)|ALTER\s+(?:TABLE|VIEW|FUNCTION)|DROP|"
                         r"INSERT|UPDATE|DELETE|TRUNCATE|VACUUM|GRANT|REVOKE)\b", top_level, re.IGNORECASE)
    # Byte-for-byte 019's verification apart from the per-chunk re-read: the
    # copy's keyset read (low key, primary-key order, LIMIT the ledgered rows)
    # in place of 019's two-sided row-comparison range.
    original = _function((ROOT / "sql/v3/migrations/019_v3_purge_copy_and_drop.sql").read_text(),
                         "purge_copy_verify")
    expected = original.replace(
        "CREATE FUNCTION v3_meta.purge_copy_verify(", "CREATE OR REPLACE FUNCTION v3_meta.purge_copy_verify(", 1,
    ).replace(
        "key_ text; range_ text;", "key_ text; after_ text;", 1,
    ).replace(
        "    range_ := format('(%s) >= ($1,%s) AND (%s) <= ($1,%s)',order_,v3_meta.purge_copy_key_params(code_,2),\n"
        "                     order_,v3_meta.purge_copy_key_params(code_,3));\n",
        "    -- 021: each chunk is re-read the way purge_copy_chunk read it (keyset from\n"
        "    -- the chunk's low key, primary-key order, LIMIT the ledgered row count),\n"
        "    -- so the scan stops after that chunk; see the header.\n"
        "    after_ := format('(%s) >= ($1,%s)',order_,v3_meta.purge_copy_key_params(code_,2));\n", 1,
    ).replace(
        "        EXECUTE format('SELECT count(*),min(%1$s),max(%1$s),\n",
        "        EXECUTE format('WITH chosen AS MATERIALIZED (SELECT * FROM %3$s WHERE derived_generation_id=$1 AND %4$s\n"
        "                ORDER BY %2$s LIMIT $3)\n"
        "            SELECT count(*),min(%1$s),max(%1$s),\n", 1,
    ).replace(
        "            FROM %3$s c WHERE derived_generation_id=$1 AND %4$s',key_,order_,staging_,range_)\n"
        "            INTO n,min_,max_,digest_ USING q.survivor_generation_id,low_,high_;\n",
        "            FROM chosen c',key_,order_,staging_,after_)\n"
        "            INTO n,min_,max_,digest_ USING q.survivor_generation_id,low_,e.rows_affected;\n", 1,
    )
    assert expected != original
    assert _function(source, "purge_copy_verify") == expected
    # Prepare and the index build are 019's plus the marked 021 blocks only:
    # prepare creates the live GiST indexes on the empty staging table, and the
    # index build leaves exactly such an index alone.
    migration_019 = (ROOT / "sql/v3/migrations/019_v3_purge_copy_and_drop.sql").read_text()
    for name in ("purge_copy_prepare", "purge_copy_build_indexes"):
        replaced = _function(source, name)
        blocks = re.findall(r"^ *-- 021 begin.*?^ *-- 021 end\n", replaced, flags=re.DOTALL | re.MULTILINE)
        assert blocks, name
        stripped = re.sub(r"^ *-- 021 begin.*?^ *-- 021 end\n", "", replaced, flags=re.DOTALL | re.MULTILINE)
        assert stripped == _function(migration_019, name).replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1), name
    prepare_blocks = "".join(re.findall(r"^ *-- 021 begin.*?^ *-- 021 end\n", _function(source, "purge_copy_prepare"),
                                        flags=re.DOTALL | re.MULTILINE))
    assert "m.amname='gist'" in prepare_blocks and "EXECUTE format('CREATE %sINDEX %I ON %s USING '" in prepare_blocks
    build_blocks = "".join(re.findall(r"^ *-- 021 begin.*?^ *-- 021 end\n", _function(source, "purge_copy_build_indexes"),
                                      flags=re.DOTALL | re.MULTILINE))
    assert "<>'gist'" in build_blocks and "CONTINUE;" in build_blocks and "EXECUTE" not in build_blocks
    # The chunk read is the copy's own shape (019's purge_copy_chunk).
    chunk = _function((ROOT / "sql/v3/migrations/019_v3_purge_copy_and_drop.sql").read_text(), "purge_copy_chunk")
    assert "WHERE derived_generation_id=$1%2$s ORDER BY %3$s LIMIT $3" in chunk
    assert "CASCADE" not in source


def test_022_only_moves_the_keyset_start_and_tolerates_its_own_ledger_row():
    source = (ROOT / "sql/v3/migrations/022_v3_purge_keyset_start.sql").read_text()
    assert re.findall(r"CREATE (?:OR REPLACE )?FUNCTION v3_meta\.(\w+)\(", source) == [
        "purge_copy_keyset", "purge_copy_chunk", "purge_copy_verify", "purge_assert_request",
    ]
    assert source.count("CREATE OR REPLACE FUNCTION") == 3 and source.count("CREATE FUNCTION") == 1
    top_level = re.sub(r"CREATE(?: OR REPLACE)? FUNCTION\b.*?\$\$.*?\$\$;", "", source,
                       flags=re.DOTALL | re.IGNORECASE)
    top_level = re.sub(r"--[^\n]*", "", top_level)
    top_level = re.sub(r"'[^']*'", "''", top_level)
    # Installation creates no relation and writes no row; the only privilege
    # statement takes the new internal helper away from PUBLIC.
    assert re.findall(r"\b(?:GRANT|REVOKE)\b.*", top_level) == [
        "REVOKE ALL ON FUNCTION v3_meta.purge_copy_keyset(text,boolean) FROM PUBLIC;"]
    assert not re.search(r"\b(?:CREATE\s+(?:TABLE|VIEW|SCHEMA|INDEX|ROLE)|ALTER\s+(?:TABLE|VIEW|FUNCTION)|DROP|"
                         r"INSERT|UPDATE|DELETE|TRUNCATE|VACUUM|GRANT)\b", top_level, re.IGNORECASE)
    assert "CASCADE" not in source
    migration_016 = (ROOT / "sql/v3/migrations/016_v3_governed_derived_purge.sql").read_text()
    migration_019 = (ROOT / "sql/v3/migrations/019_v3_purge_copy_and_drop.sql").read_text()
    migration_021 = (ROOT / "sql/v3/migrations/021_v3_purge_long_phase_bounds.sql").read_text()

    def replaced(text, *pairs):
        for old, new in pairs:
            assert text.count(old) == 1, old
            text = text.replace(old, new, 1)
        return text

    # 019's chunk copy with only the keyset predicate moved into the helper.
    assert _function(source, "purge_copy_chunk") == replaced(
        _function(migration_019, "purge_copy_chunk"),
        ("CREATE FUNCTION v3_meta.purge_copy_chunk(", "CREATE OR REPLACE FUNCTION v3_meta.purge_copy_chunk("),
        ("order_ text; key_ text; after_ text;", "order_ text; key_ text; keyset_ text;"),
        ("    after_ := CASE WHEN last_ IS NULL THEN '' ELSE\n"
         "        format(' AND (%s) > ($1,%s)',order_,v3_meta.purge_copy_key_params(code_,2)) END;\n",
         "    -- 022: the first chunk reads from the start of the generation, every later\n"
         "    -- chunk from the row after the last copied key (see the header).\n"
         "    keyset_ := CASE WHEN last_ IS NULL THEN 'derived_generation_id=$1'\n"
         "        ELSE v3_meta.purge_copy_keyset(code_,false) END;\n"),
        ("SELECT * FROM %1$s WHERE derived_generation_id=$1%2$s ORDER BY %3$s LIMIT $3)",
         "SELECT * FROM %1$s WHERE %2$s ORDER BY %3$s LIMIT $3)"),
        ("FROM chosen c',live_,after_,order_,staging_,key_)", "FROM chosen c',live_,keyset_,order_,staging_,key_)"),
    )
    # 021's verification with only the per-chunk re-read's predicate replaced.
    assert _function(source, "purge_copy_verify") == replaced(
        _function(migration_021, "purge_copy_verify"),
        ("frozen_ bigint; order_ text; key_ text; after_ text;", "frozen_ bigint; order_ text; key_ text; keyset_ text;"),
        ("    -- so the scan stops after that chunk; see the header.\n"
         "    after_ := format('(%s) >= ($1,%s)',order_,v3_meta.purge_copy_key_params(code_,2));\n",
         "    -- so the scan stops after that chunk; see the header. 022: and it starts\n"
         "    -- at that low key, not at the start of the generation (022's header).\n"
         "    keyset_ := v3_meta.purge_copy_keyset(code_,true);\n"),
        ("SELECT * FROM %3$s WHERE derived_generation_id=$1 AND %4$s\n", "SELECT * FROM %3$s WHERE %4$s\n"),
        ("FROM chosen c',key_,order_,staging_,after_)", "FROM chosen c',key_,order_,staging_,keyset_)"),
    )
    # 016's request check: the marked block is the only change, and it is the
    # same ledger hash, compared whole or without exactly 022's own row.
    request = _function(source, "purge_assert_request")
    blocks = re.findall(r"^ *-- 022 begin.*?^ *-- 022 end\n", request, flags=re.DOTALL | re.MULTILINE)
    assert len(blocks) == 1
    ledger = ("encode(sha256(convert_to(COALESCE(jsonb_agg(jsonb_build_array(migration_name,\n"
              "          encode(migration_sha256,'hex')) ORDER BY migration_name)::text,'[]'),'UTF8')),'hex')\n")
    original_check = ("    IF (SELECT " + ledger + "          FROM v3_meta.schema_migration) IS DISTINCT FROM "
                      "r.frozen_snapshot->>'schema_ledger_sha256' THEN\n"
                      "        RAISE EXCEPTION 'purge schema ledger drift';\n    END IF;\n")
    assert re.sub(r"^ *-- 022 begin.*?^ *-- 022 end\n", original_check, request,
                  flags=re.DOTALL | re.MULTILINE) == replaced(
        _function(migration_016, "purge_assert_request"),
        ("CREATE FUNCTION v3_meta.purge_assert_request(", "CREATE OR REPLACE FUNCTION v3_meta.purge_assert_request("))
    assert blocks[0].count("FROM v3_meta.schema_migration") == 2 and blocks[0].count(ledger) == 2
    assert "WHERE migration_name<>'022_v3_purge_keyset_start.sql')" in blocks[0]
    assert blocks[0].count("RAISE EXCEPTION 'purge schema ledger drift';") == 1 and " AND (SELECT " in blocks[0]
    # The helper bounds the generation with <= (never =) and reuses 019's key text.
    helper = _function(source, "purge_copy_keyset")
    assert "derived_generation_id<=$1 AND (%s) %s ($1,%s)" in helper
    assert "v3_meta.purge_copy_order_columns(code_)" in helper and "v3_meta.purge_copy_key_params(code_,2)" in helper
    assert "LANGUAGE plpgsql STABLE SET search_path=pg_catalog" in helper and "SECURITY DEFINER" not in helper


def test_020_only_replaces_the_swap_locking():
    source = (ROOT / "sql/v3/migrations/020_v3_purge_swap_lock_order.sql").read_text()
    assert set(re.findall(r"CREATE (?:OR REPLACE )?FUNCTION v3_meta\.(\w+)\(", source)) == {
        "purge_copy_lock_relocation", "purge_copy_relocate", "purge_copy_swap", "purge_copy_swap_back",
    }
    assert "CREATE FUNCTION v3_meta.purge_copy_lock_relocation(" in source
    for replaced in ("purge_copy_relocate", "purge_copy_swap", "purge_copy_swap_back"):
        assert f"CREATE OR REPLACE FUNCTION v3_meta.{replaced}(" in source
    top_level = re.sub(r"CREATE(?: OR REPLACE)? FUNCTION\b.*?\$\$.*?\$\$;", "", source,
                       flags=re.DOTALL | re.IGNORECASE)
    top_level = re.sub(r"--[^\n]*", "", top_level)
    top_level = re.sub(r"'[^']*'", "''", top_level)
    # Installation creates no relation, writes no row and grants nothing new.
    assert not re.search(r"\b(?:CREATE\s+(?:TABLE|VIEW|SCHEMA|INDEX|ROLE)|ALTER\s+(?:TABLE|VIEW)|DROP|INSERT|"
                         r"UPDATE|DELETE|TRUNCATE|VACUUM|GRANT)\b", top_level, re.IGNORECASE)
    assert re.search(r"REVOKE ALL ON FUNCTION v3_meta\.purge_copy_lock_relocation\(text,regclass\) FROM PUBLIC;",
                     top_level)
    body = re.sub(r"--[^\n]*", "", source)
    # The view is locked alone (never LOCK TABLE on a view, which locks what it
    # reads) and every later lock is NOWAIT.
    assert "ALTER VIEW %s OWNER TO %s" in body
    assert body.count("IN ACCESS EXCLUSIVE MODE NOWAIT") == 2
    assert "CASCADE" not in body


def test_019_only_installs_copy_and_drop_capability():
    source = (ROOT / "sql/v3/migrations/019_v3_purge_copy_and_drop.sql").read_text()
    for relation in ("derived_purge_copy_request", "derived_purge_copy_event"):
        assert f"CREATE TABLE v3_meta.{relation}" in source
    for function in (
        "purge_copy_prepare", "purge_copy_chunk", "purge_copy_build_indexes", "purge_copy_verify",
        "purge_copy_swap", "purge_copy_swap_back", "purge_copy_validate_fks", "purge_copy_drop",
        "purge_copy_complete", "purge_copy_fingerprint", "purge_copy_backup_skip",
    ):
        assert f"CREATE FUNCTION v3_meta.{function}(" in source
    # Function bodies run only when later invoked; everything left executes at
    # installation and must not copy, swap, drop or delete payload.
    top_level = re.sub(
        r"CREATE(?: OR REPLACE)? FUNCTION\b.*?\$\$.*?\$\$;", "", source,
        flags=re.DOTALL | re.IGNORECASE,
    )
    top_level = re.sub(r"--[^\n]*", "", top_level)
    assert not re.search(r"\b(?:DELETE\s+FROM|INSERT\s+INTO|DROP\s+TABLE|VACUUM|SET\s+SCHEMA|TRUNCATE\s+v3)\b",
                         top_level, re.IGNORECASE)
    assert not re.search(r"\b(?:SELECT|PERFORM|CALL)\s+v3_meta\.purge_copy_", top_level, re.IGNORECASE)
    # Every DROP (retired table, abandoned staging copy) is RESTRICT, never CASCADE.
    assert "CASCADE" not in re.sub(r"--[^\n]*", "", source)
    assert "SET search_path=pg_catalog" in source
    assert re.search(r"CHECK\(event_kind IN \((.*?)\)\)", source, re.DOTALL)
    kinds = set(re.findall(r"'([A-Z_]+)'", re.search(
        r"event_kind text NOT NULL CHECK\(event_kind IN \((.*?)\)\)", source, re.DOTALL).group(1)))
    assert kinds == {
        "COPY_STARTED", "CHUNK_COPIED", "INDEXES_BUILT", "VERIFIED", "SWAPPED",
        "SWAPPED_BACK", "FK_VALIDATED", "DROPPED", "COMPLETED", "FAILED_STOP",
    }


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
