-- sql/v3/migrations/011_v3_system_archetype.sql
-- Archetype judgement product attached to one Ratings V4 generation. Additive;
-- does not touch canonical relations. Mirrors the system_search product
-- lifecycle from 004/006 but scoped to product_code='system_archetype'.
BEGIN;

CREATE TABLE v3_derived.system_archetype (
    derived_generation_id uuid NOT NULL REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK(system_id64 >= 0),
    archetype_key text NOT NULL CHECK(archetype_key ~ '^[a-z][a-z0-9_]{0,62}$'),
    archetype_version text NOT NULL CHECK(length(archetype_version) BETWEEN 1 AND 128),
    archetype_score smallint NOT NULL CHECK(archetype_score BETWEEN 0 AND 100),
    tier text NOT NULL CHECK(tier IN ('S','A','B','C','D')),
    confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    explanation jsonb NOT NULL CHECK(jsonb_typeof(explanation)='object'),
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(derived_generation_id,system_id64,archetype_key),
    FOREIGN KEY(derived_generation_id,system_id64)
        REFERENCES v3_derived.system_rating_vector DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE v3_derived.system_archetype_summary (
    derived_generation_id uuid NOT NULL REFERENCES v3_meta.derived_generation,
    system_id64 bigint NOT NULL CHECK(system_id64 >= 0),
    primary_archetype text NOT NULL CHECK(primary_archetype ~ '^[a-z][a-z0-9_]{0,62}$'),
    secondary_archetype text CHECK(secondary_archetype ~ '^[a-z][a-z0-9_]{0,62}$'),
    best_colony_potential smallint NOT NULL CHECK(best_colony_potential BETWEEN 0 AND 100),
    best_tier text NOT NULL CHECK(best_tier IN ('S','A','B','C','D')),
    archetype_confidence double precision NOT NULL CHECK(archetype_confidence BETWEEN 0 AND 1),
    PRIMARY KEY(derived_generation_id,system_id64),
    FOREIGN KEY(derived_generation_id,system_id64)
        REFERENCES v3_derived.system_rating_vector DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE v3_derived.archetype_build_chunk (
    derived_generation_id uuid NOT NULL,
    chunk_ordinal bigint NOT NULL CHECK(chunk_ordinal >= 0),
    product_code text NOT NULL DEFAULT 'system_archetype'
        CHECK(product_code='system_archetype'),
    archetype_version text NOT NULL CHECK(length(archetype_version) BETWEEN 1 AND 128),
    source_projection_sha256 bytea NOT NULL CHECK(octet_length(source_projection_sha256)=32),
    content_sha256 bytea NOT NULL CHECK(octet_length(content_sha256)=32),
    systems integer NOT NULL CHECK(systems BETWEEN 1 AND 1000),
    completed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(derived_generation_id,chunk_ordinal),
    FOREIGN KEY(derived_generation_id,chunk_ordinal)
        REFERENCES v3_derived.build_chunk(derived_generation_id,chunk_ordinal)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(derived_generation_id,product_code)
        REFERENCES v3_meta.derived_product(derived_generation_id,product_code)
        DEFERRABLE INITIALLY DEFERRED
);

-- Insert-only while the archetype product is BUILDING (mirrors 006 system_search).
CREATE FUNCTION v3_derived.guard_system_archetype_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identifier uuid; base_state text; product_state text;
BEGIN
    FOR identifier IN SELECT DISTINCT derived_generation_id FROM changed_rows ORDER BY 1 LOOP
        SELECT lifecycle_state INTO base_state
          FROM v3_meta.derived_generation
         WHERE derived_generation_id=identifier FOR SHARE;
        IF base_state NOT IN ('BUILDING','VALIDATING','READY') THEN
            RAISE EXCEPTION 'system_archetype generation % is immutable in state %',
                identifier, base_state;
        END IF;
        SELECT lifecycle_state INTO product_state
          FROM v3_meta.derived_product
         WHERE derived_generation_id=identifier AND product_code='system_archetype'
         FOR SHARE;
        IF product_state IS DISTINCT FROM 'BUILDING' THEN
            RAISE EXCEPTION 'system_archetype product % is not BUILDING', identifier;
        END IF;
    END LOOP;
    RETURN NULL;
END $$;

CREATE FUNCTION v3_derived.reject_system_archetype_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'system_archetype rows and receipts are insert-only';
END $$;

-- Attach the guard/reject triggers to all three archetype relations.
DO $triggers$
DECLARE relation text;
BEGIN
    FOREACH relation IN ARRAY ARRAY[
        'v3_derived.system_archetype',
        'v3_derived.system_archetype_summary',
        'v3_derived.archetype_build_chunk'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER product_insert AFTER INSERT ON %s '
            'REFERENCING NEW TABLE AS changed_rows FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.guard_system_archetype_insert()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_update BEFORE UPDATE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_delete BEFORE DELETE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
        EXECUTE format(
            'CREATE TRIGGER product_truncate BEFORE TRUNCATE ON %s FOR EACH STATEMENT '
            'EXECUTE FUNCTION v3_derived.reject_system_archetype_mutation()', relation);
    END LOOP;
END $triggers$;

-- Published-generation convenience reads.
CREATE VIEW v3_app.system_archetype AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_archetype s USING(derived_generation_id);

CREATE VIEW v3_app.system_archetype_summary AS
SELECT s.* FROM v3_meta.current_derived_generation c
JOIN v3_derived.system_archetype_summary s USING(derived_generation_id);

COMMIT;
