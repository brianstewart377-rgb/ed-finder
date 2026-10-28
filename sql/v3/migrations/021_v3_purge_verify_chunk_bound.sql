-- Copy-and-drop verification bound. Capability only: replaces one 019 function,
-- v3_meta.purge_copy_verify, changing only how it re-reads each copied chunk.
-- Installation copies, swaps, drops and deletes no payload row and changes no
-- table, view, grant or ledger row.
--
-- Why (one_percent purge rehearsal run 40571954621, 2026-10-28): verification
-- grew faster than the tables. From the smoke rehearsal (run 40535321292) to the
-- one_percent rehearsal the rows grew 6.67 times; body_mechanics verification
-- took 13.6 times as long (8.4 s -> 114.7 s) and economy_opportunity 14.7 times
-- (11.0 s -> 161.7 s), while the copy of the same rows took 8.5 and 9.5 times
-- as long. The receipt's straight-line production estimates (3.2 h and 4.5 h)
-- already exceeded the reviewed 7,200 s envelope, and the true trend is worse.
--
-- Cause: 019 bounds each chunk with two row comparisons that start with
-- derived_generation_id, plus a separate derived_generation_id=$1. With that
-- equality on the index's leading column, the btree scan's end condition is the
-- end of the generation, not the chunk's high key: it reads index entries from
-- the chunk's low key to the end of the survivor generation and filters out
-- everything after the chunk. Every chunk therefore costs in proportion to the
-- rest of the table, and the whole verification in proportion to the square of
-- its size. (The planner also estimates a row comparison by its first column
-- only, so it costs every chunk as if it were the whole table.) Measured on
-- PostgreSQL 18.4 with a body_mechanics-shaped table: one 100,000-row chunk read
-- 4,976 buffers in a 600,000-row table and 23,158 in a 3,600,000-row table.
--
-- What changes: each chunk is re-read exactly the way purge_copy_chunk read it
-- from the live table: rows at or after the chunk's low key, in primary-key
-- order, LIMIT the ledgered row count (CHUNK_COPIED rows always carry
-- rows_affected > 0, by 019's table check). The same chunk then read 2,670
-- buffers at both table sizes. The checks are unchanged and prove the same
-- thing: the staging primary key exists before verification (phase
-- INDEXES_BUILT), so keys are unique, and the first rows_affected rows at or
-- after the low key end exactly at the high key only if the rows between the
-- two keys are exactly those rows; their count, lowest and highest keys and
-- digest are compared with the ledger as before. Everything else in the
-- function (counts, chunk receipts, generations, foreign keys, catalog shape,
-- the VERIFIED event) is byte-for-byte 019's. CREATE OR REPLACE keeps the
-- function's owner and its EXECUTE grant to v3_derived_purge_executor.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
BEGIN
    IF to_regprocedure('v3_meta.purge_copy_verify(uuid,text)') IS NULL
       OR to_regprocedure('v3_meta.purge_copy_lock_relocation(text,regclass)') IS NULL THEN
        RAISE EXCEPTION 'verification bound requires the copy-and-drop migrations 019 and 020';
    END IF;
    IF (SELECT proowner FROM pg_proc WHERE oid='v3_meta.purge_copy_verify(uuid,text)'::regprocedure)
       <>current_user::regrole THEN
        RAISE EXCEPTION 'verification bound must be installed by the owner of the 019 definers';
    END IF;
END $$;

-- 019's verification; only the per-chunk re-read changes (see the header).
CREATE OR REPLACE FUNCTION v3_meta.purge_copy_verify(purge_ uuid, code_ text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET lock_timeout='5s' AS $$
DECLARE r v3_meta.derived_generation_purge_request; q v3_meta.derived_purge_copy_request; s v3_meta.purge_copy_relation_state;
        live_ regclass; staging_ regclass; e record; k record; low_ bigint[]; high_ bigint[];
        n bigint; total_ bigint; digest_ text; min_ bigint[]; max_ bigint[]; mismatch_ bigint;
        frozen_ bigint; order_ text; key_ text; after_ text; fks_ text[] := '{}'; event_ bigint; output_ jsonb;
BEGIN
    r := v3_meta.purge_copy_context(purge_,false);
    q := v3_meta.purge_copy_request_for(r);
    PERFORM v3_meta.purge_copy_assert_order(q.copy_id,code_);
    s := v3_meta.purge_copy_assert_position(q.copy_id,code_);
    IF s.copy_position<>'staged' OR s.failed OR s.phase NOT IN ('INDEXES_BUILT','SWAPPED_BACK') THEN
        RAISE EXCEPTION 'index build or swap-back required before verification';
    END IF;
    live_ := v3_meta.purge_relation(code_);
    staging_ := v3_meta.purge_copy_table(code_,'staging');
    frozen_ := (q.frozen_survivors->>code_)::bigint;
    -- Maintenance: the manual VACUUM (FREEZE, ANALYZE) after the final insert.
    PERFORM pg_stat_clear_snapshot();
    IF NOT EXISTS (SELECT 1 FROM pg_stat_user_tables WHERE relid=staging_
        AND last_vacuum>s.last_copy_at AND last_analyze>s.last_copy_at) THEN
        RAISE EXCEPTION 'staging VACUUM and ANALYZE after the final copy chunk required';
    END IF;
    -- Counts: frozen survivors, the copy ledger, and Search's published proof.
    EXECUTE format('SELECT count(*),count(*) FILTER (WHERE derived_generation_id=$1) FROM %s',staging_)
        INTO total_,n USING q.survivor_generation_id;
    IF total_<>frozen_ OR n<>frozen_ OR s.rows_total<>frozen_
       OR (code_='system_search' AND q.published_search_survivors IS NOT NULL
           AND q.published_search_survivors<>frozen_) THEN
        RAISE EXCEPTION 'survivor count mismatch: staging %, ledger %, frozen %', total_,s.rows_total,frozen_;
    END IF;
    -- Content: every ledgered chunk's range recounted and re-digested.
    order_ := v3_meta.purge_copy_order_columns(code_);
    key_ := v3_meta.purge_key_expression(code_);
    -- 021: each chunk is re-read the way purge_copy_chunk read it (keyset from
    -- the chunk's low key, primary-key order, LIMIT the ledgered row count),
    -- so the scan stops after that chunk; see the header.
    after_ := format('(%s) >= ($1,%s)',order_,v3_meta.purge_copy_key_params(code_,2));
    total_ := 0;
    output_ := v3_meta.purge_copy_output_settings(NULL);
    FOR e IN SELECT * FROM v3_meta.derived_purge_copy_event WHERE copy_id=q.copy_id AND relation_code=code_
             AND event_kind='CHUNK_COPIED' AND event_sequence>s.copy_started ORDER BY event_sequence LOOP
        SELECT array_agg(value::bigint ORDER BY ordinality) INTO low_ FROM jsonb_array_elements_text(e.chunk_low) WITH ORDINALITY;
        SELECT array_agg(value::bigint ORDER BY ordinality) INTO high_ FROM jsonb_array_elements_text(e.chunk_high) WITH ORDINALITY;
        EXECUTE format('WITH chosen AS MATERIALIZED (SELECT * FROM %3$s WHERE derived_generation_id=$1 AND %4$s
                ORDER BY %2$s LIMIT $3)
            SELECT count(*),min(%1$s),max(%1$s),
            encode(sha256(convert_to(COALESCE(string_agg(md5(c::text),'''' ORDER BY %2$s),''''),''UTF8'')),''hex'')
            FROM chosen c',key_,order_,staging_,after_)
            INTO n,min_,max_,digest_ USING q.survivor_generation_id,low_,e.rows_affected;
        IF n<>e.rows_affected OR min_ IS DISTINCT FROM low_ OR max_ IS DISTINCT FROM high_
           OR digest_<>e.source_digest THEN
            RAISE EXCEPTION 'copied chunk % content mismatch', e.event_sequence;
        END IF;
        total_ := total_+n;
    END LOOP;
    PERFORM v3_meta.purge_copy_output_settings(output_);
    IF total_<>frozen_ THEN RAISE EXCEPTION 'chunk ledger does not cover the survivors'; END IF;
    -- Chunk receipts: rows per Ratings chunk equal the survivor's build receipts.
    -- vector: systems; body: physical_bodies; opportunity: eligible_opportunities;
    -- Search: search_build_chunk.systems. Non-vector rows map through the live vector.
    EXECUTE format('WITH observed AS (SELECT %1$s AS chunk_ordinal,count(*) AS n FROM %2$s x %3$s
            WHERE x.derived_generation_id=$1 GROUP BY 1),
        expected AS (SELECT chunk_ordinal,%4$s AS n FROM %5$s WHERE derived_generation_id=$1)
        SELECT count(*) FROM observed o FULL JOIN expected e USING (chunk_ordinal)
        WHERE o.n IS DISTINCT FROM e.n AND COALESCE(o.n,0)+COALESCE(e.n,0)<>0',
        CASE code_ WHEN 'system_rating_vector' THEN 'x.chunk_ordinal' ELSE 'v.chunk_ordinal' END,
        staging_,
        CASE code_ WHEN 'system_rating_vector' THEN '' ELSE
            'JOIN v3_derived.system_rating_vector v ON v.derived_generation_id=x.derived_generation_id AND v.system_id64=x.system_id64' END,
        CASE code_ WHEN 'system_rating_vector' THEN 'systems::bigint' WHEN 'body_mechanics' THEN 'physical_bodies::bigint'
            WHEN 'economy_opportunity' THEN 'eligible_opportunities::bigint' ELSE 'systems::bigint' END,
        CASE code_ WHEN 'system_search' THEN 'v3_derived.search_build_chunk' ELSE 'v3_derived.build_chunk' END)
        INTO mismatch_ USING q.survivor_generation_id;
    IF mismatch_<>0 THEN RAISE EXCEPTION 'chunk receipt count mismatch in % chunks', mismatch_; END IF;
    -- The live table holds nothing beyond the survivors and the purge targets.
    PERFORM v3_meta.purge_copy_assert_generations(q,code_);
    -- FKs to live parents: added NOT VALID with canonical names, then validated.
    FOR k IN SELECT oid,conname FROM pg_constraint WHERE conrelid=live_ AND contype='f' ORDER BY conname LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=staging_ AND conname=k.conname) THEN
            EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s NOT VALID',staging_,k.conname,
                regexp_replace(pg_get_constraintdef(k.oid),' NOT VALID$',''));
            IF obj_description(k.oid,'pg_constraint') IS NOT NULL THEN
                EXECUTE format('COMMENT ON CONSTRAINT %I ON %s IS %L',k.conname,staging_,obj_description(k.oid,'pg_constraint'));
            END IF;
        END IF;
        EXECUTE format('ALTER TABLE %s VALIDATE CONSTRAINT %I',staging_,k.conname);
        fks_ := array_append(fks_,k.conname::text);
    END LOOP;
    -- Catalog: fingerprint, the exact copy guard, staging reloptions, valid indexes.
    PERFORM v3_meta.purge_copy_assert_staging_shape(live_,staging_,false);
    IF EXISTS (SELECT 1 FROM pg_index WHERE indrelid=staging_ AND (NOT indisvalid OR NOT indisready)) THEN
        RAISE EXCEPTION 'staging index not valid';
    END IF;
    INSERT INTO v3_meta.derived_purge_copy_event(copy_id,purge_id,event_kind,relation_code,live_oid,staging_oid,
        rows_total,relation_bytes,operational_payload)
        VALUES(q.copy_id,purge_,'VERIFIED',code_,live_,staging_,frozen_,pg_total_relation_size(staging_),
            jsonb_build_object('chunks',s.chunks,'foreign_keys',to_jsonb(fks_),
                'fingerprint_sha256',encode(sha256(convert_to(v3_meta.purge_copy_fingerprint(staging_)::text,'UTF8')),'hex')))
        RETURNING event_sequence INTO event_;
    RETURN event_;
END $$;

COMMIT;
