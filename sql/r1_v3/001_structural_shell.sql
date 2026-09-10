BEGIN;

-- R1 persistence is additive to the normalized V3 warehouse.
-- This migration intentionally creates no capability data, performs no backfill,
-- and changes no existing V3 relation.

CREATE SCHEMA r1_meta;
CREATE SCHEMA r1_cache;
CREATE SCHEMA r1_plan;

CREATE TABLE r1_meta.mechanics_revision (
    mechanics_revision_id   TEXT PRIMARY KEY,
    friendly_version        TEXT NOT NULL,
    game_patch              TEXT,
    rules_sha256            CHAR(64) NOT NULL UNIQUE,
    source_evidence_refs    JSONB NOT NULL DEFAULT '[]'::jsonb,
    effective_from          TIMESTAMPTZ,
    effective_to            TIMESTAMPTZ,
    status                  TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                   TEXT,
    CONSTRAINT chk_r1_mechanics_rules_sha256
        CHECK (rules_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_mechanics_source_refs_array
        CHECK (jsonb_typeof(source_evidence_refs) = 'array'),
    CONSTRAINT chk_r1_mechanics_status
        CHECK (status IN ('experimental', 'active', 'retired')),
    CONSTRAINT chk_r1_mechanics_effective_window
        CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);

CREATE UNIQUE INDEX uq_r1_mechanics_single_active
    ON r1_meta.mechanics_revision (status)
    WHERE status = 'active';

CREATE TABLE r1_meta.model_revision (
    model_revision_id             TEXT PRIMARY KEY,
    friendly_version              TEXT NOT NULL,
    code_commit_sha               CHAR(40) NOT NULL,
    model_sha256                  CHAR(64) NOT NULL UNIQUE,
    canonical_contract_revision   TEXT NOT NULL,
    capability_revision           TEXT NOT NULL,
    candidate_generator_revision  TEXT NOT NULL,
    fit_policy_revision           TEXT,
    status                        TEXT NOT NULL,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_from                TIMESTAMPTZ,
    effective_to                  TIMESTAMPTZ,
    notes                         TEXT,
    CONSTRAINT chk_r1_model_commit_sha
        CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT chk_r1_model_sha256
        CHECK (model_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_model_status
        CHECK (status IN ('experimental', 'shadow', 'active', 'retired')),
    CONSTRAINT chk_r1_model_effective_window
        CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);

CREATE UNIQUE INDEX uq_r1_model_single_active
    ON r1_meta.model_revision (status)
    WHERE status = 'active';

CREATE TABLE r1_meta.programme_revision (
    programme_id         TEXT NOT NULL,
    programme_revision   TEXT NOT NULL,
    programme_name       TEXT NOT NULL,
    definition_sha256    CHAR(64) NOT NULL,
    definition_json      JSONB NOT NULL,
    status               TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_from       TIMESTAMPTZ,
    effective_to         TIMESTAMPTZ,
    PRIMARY KEY (programme_id, programme_revision),
    CONSTRAINT uq_r1_programme_definition UNIQUE (programme_id, definition_sha256),
    CONSTRAINT chk_r1_programme_definition_sha256
        CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_programme_definition_object
        CHECK (jsonb_typeof(definition_json) = 'object'),
    CONSTRAINT chk_r1_programme_status
        CHECK (status IN ('draft', 'shadow', 'active', 'retired')),
    CONSTRAINT chk_r1_programme_effective_window
        CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);

CREATE TABLE r1_meta.capability_generation (
    capability_generation_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    generation_key            TEXT NOT NULL UNIQUE,
    relation_schema           TEXT NOT NULL UNIQUE,
    canonical_generation_id   UUID NOT NULL,
    capability_revision       TEXT NOT NULL,
    mechanics_revision_id     TEXT NOT NULL,
    builder_code_sha          CHAR(40) NOT NULL,
    builder_config_sha256     CHAR(64) NOT NULL,
    lifecycle_state           TEXT NOT NULL,
    row_count                 BIGINT,
    validation_receipt        JSONB,
    build_started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at              TIMESTAMPTZ,
    published_at              TIMESTAMPTZ,
    retired_at                TIMESTAMPTZ,
    failed_at                 TIMESTAMPTZ,
    failure_reason            TEXT,
    CONSTRAINT fk_r1_capability_canonical_generation
        FOREIGN KEY (canonical_generation_id)
        REFERENCES v3_meta.canonical_generation (generation_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_capability_mechanics_revision
        FOREIGN KEY (mechanics_revision_id)
        REFERENCES r1_meta.mechanics_revision (mechanics_revision_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_r1_capability_builder_commit_sha
        CHECK (builder_code_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT chk_r1_capability_builder_config_sha256
        CHECK (builder_config_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_capability_lifecycle
        CHECK (lifecycle_state IN ('building', 'validated', 'published', 'retired', 'failed')),
    CONSTRAINT chk_r1_capability_row_count
        CHECK (row_count IS NULL OR row_count >= 0),
    CONSTRAINT chk_r1_capability_validation_receipt
        CHECK (validation_receipt IS NULL OR jsonb_typeof(validation_receipt) = 'object')
);

CREATE INDEX idx_r1_capability_generation_canonical
    ON r1_meta.capability_generation (
        canonical_generation_id,
        capability_revision,
        mechanics_revision_id
    );

CREATE INDEX idx_r1_capability_generation_lifecycle
    ON r1_meta.capability_generation (lifecycle_state, build_started_at DESC);

CREATE TABLE r1_meta.current_capability_generation (
    singleton                 BOOLEAN PRIMARY KEY DEFAULT TRUE,
    capability_generation_id  BIGINT NOT NULL,
    publication_sequence      BIGINT NOT NULL,
    published_at              TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_r1_current_capability_singleton
        CHECK (singleton),
    CONSTRAINT chk_r1_current_capability_sequence
        CHECK (publication_sequence > 0),
    CONSTRAINT fk_r1_current_capability_generation
        FOREIGN KEY (capability_generation_id)
        REFERENCES r1_meta.capability_generation (capability_generation_id)
        ON DELETE RESTRICT
);

-- Typed zero-row logical surface. A later separately-authorised capability
-- publication replaces this view atomically with one pointing at a validated
-- immutable r1_cap_<generation>.system_capability relation.
CREATE VIEW r1_cache.system_capability_current AS
SELECT
    NULL::BIGINT            AS system_id64,
    NULL::INTEGER           AS source_body_count,
    NULL::INTEGER           AS loaded_body_count,
    NULL::SMALLINT          AS body_inventory_state,
    NULL::INTEGER           AS star_count,
    NULL::INTEGER           AS planet_count,
    NULL::INTEGER           AS hmc_count,
    NULL::INTEGER           AS metal_rich_body_count,
    NULL::INTEGER           AS rocky_body_count,
    NULL::INTEGER           AS rocky_ice_body_count,
    NULL::INTEGER           AS icy_body_count,
    NULL::INTEGER           AS water_world_count,
    NULL::INTEGER           AS earth_like_world_count,
    NULL::INTEGER           AS ammonia_world_count,
    NULL::INTEGER           AS gas_giant_count,
    NULL::INTEGER           AS neutron_star_count,
    NULL::INTEGER           AS black_hole_count,
    NULL::INTEGER           AS white_dwarf_count,
    NULL::INTEGER           AS body_subtype_unknown_count,
    NULL::INTEGER           AS landable_count,
    NULL::INTEGER           AS landable_unknown_count,
    NULL::INTEGER           AS terraformable_count,
    NULL::INTEGER           AS terraforming_unknown_count,
    NULL::INTEGER           AS ringed_body_count,
    NULL::INTEGER           AS geological_body_count,
    NULL::INTEGER           AS geological_unknown_count,
    NULL::INTEGER           AS biological_body_count,
    NULL::INTEGER           AS biological_unknown_count,
    NULL::INTEGER           AS volcanism_present_count,
    NULL::INTEGER           AS volcanism_unknown_count,
    NULL::INTEGER           AS atmosphere_present_count,
    NULL::INTEGER           AS atmosphere_unknown_count,
    NULL::INTEGER           AS tidally_locked_count,
    NULL::INTEGER           AS tidal_lock_unknown_count,
    NULL::INTEGER           AS signals_incomplete_body_count,
    NULL::INTEGER           AS genera_incomplete_body_count,
    NULL::INTEGER           AS distance_unknown_body_count,
    NULL::INTEGER           AS ring_count,
    NULL::INTEGER           AS rocky_ring_count,
    NULL::INTEGER           AS icy_ring_count,
    NULL::INTEGER           AS metal_rich_ring_count,
    NULL::INTEGER           AS metallic_ring_count,
    NULL::INTEGER           AS reserve_depleted_ring_count,
    NULL::INTEGER           AS reserve_low_ring_count,
    NULL::INTEGER           AS reserve_common_ring_count,
    NULL::INTEGER           AS reserve_major_ring_count,
    NULL::INTEGER           AS reserve_pristine_ring_count,
    NULL::INTEGER           AS reserve_unknown_ring_count,
    NULL::INTEGER           AS surface_buildable_body_count,
    NULL::INTEGER           AS surface_slot_known_body_count,
    NULL::INTEGER           AS surface_slot_unknown_body_count,
    NULL::INTEGER           AS surface_slot_total_known,
    NULL::INTEGER           AS surface_slot_max_known,
    NULL::INTEGER           AS gas_giant_orbital_slot_total_known,
    NULL::DOUBLE PRECISION  AS nearest_landable_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_hmc_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_metal_rich_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_ringed_body_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_water_world_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_earth_like_world_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_ammonia_world_distance_ls,
    NULL::DOUBLE PRECISION  AS nearest_terraformable_distance_ls,
    NULL::DOUBLE PRECISION  AS furthest_known_body_distance_ls
WHERE FALSE;

CREATE TABLE r1_plan.saved_plan (
    plan_id                  UUID PRIMARY KEY,
    owner_account_id         UUID NOT NULL,
    system_id64              BIGINT NOT NULL,
    plan_name                TEXT,
    plan_state               TEXT NOT NULL,
    current_revision_number  INTEGER NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at              TIMESTAMPTZ,
    CONSTRAINT fk_r1_saved_plan_owner
        FOREIGN KEY (owner_account_id)
        REFERENCES v3_identity.account (account_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_r1_saved_plan_state
        CHECK (plan_state IN ('draft', 'selected', 'build_pack', 'archived')),
    CONSTRAINT chk_r1_saved_plan_current_revision_positive
        CHECK (current_revision_number > 0)
);

CREATE INDEX idx_r1_saved_plan_owner_updated
    ON r1_plan.saved_plan (owner_account_id, updated_at DESC);

CREATE TABLE r1_plan.plan_revision (
    plan_revision_id                       UUID PRIMARY KEY,
    plan_id                                UUID NOT NULL,
    revision_number                        INTEGER NOT NULL,
    previous_plan_revision_id              UUID,
    programme_id                           TEXT NOT NULL,
    programme_revision                     TEXT NOT NULL,
    carrier_mode                           TEXT NOT NULL,
    created_from_model_revision_id         TEXT,
    created_from_mechanics_revision_id     TEXT,
    created_from_canonical_generation_id   UUID,
    created_from_evidence_snapshot_sha256  CHAR(64),
    candidate_plan_sha256                  CHAR(64) NOT NULL,
    change_kind                            TEXT NOT NULL,
    created_at                             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_r1_plan_revision_plan
        FOREIGN KEY (plan_id)
        REFERENCES r1_plan.saved_plan (plan_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_r1_plan_revision_programme
        FOREIGN KEY (programme_id, programme_revision)
        REFERENCES r1_meta.programme_revision (programme_id, programme_revision)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_plan_revision_model
        FOREIGN KEY (created_from_model_revision_id)
        REFERENCES r1_meta.model_revision (model_revision_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_plan_revision_mechanics
        FOREIGN KEY (created_from_mechanics_revision_id)
        REFERENCES r1_meta.mechanics_revision (mechanics_revision_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_plan_revision_canonical_generation
        FOREIGN KEY (created_from_canonical_generation_id)
        REFERENCES v3_meta.canonical_generation (generation_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_r1_plan_revision_number
        CHECK (revision_number > 0),
    CONSTRAINT chk_r1_plan_revision_carrier_mode
        CHECK (carrier_mode IN ('no_carrier', 'carrier_available')),
    CONSTRAINT chk_r1_plan_revision_evidence_sha256
        CHECK (
            created_from_evidence_snapshot_sha256 IS NULL
            OR created_from_evidence_snapshot_sha256 ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_r1_plan_revision_candidate_sha256
        CHECK (candidate_plan_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_plan_revision_change_kind
        CHECK (change_kind IN ('finder_generated', 'user_edit', 'programme_change', 'rebase')),
    CONSTRAINT uq_r1_plan_revision_number UNIQUE (plan_id, revision_number),
    CONSTRAINT uq_r1_plan_revision_candidate UNIQUE (plan_id, candidate_plan_sha256),
    CONSTRAINT uq_r1_plan_revision_same_plan_ref UNIQUE (plan_revision_id, plan_id),
    CONSTRAINT uq_r1_plan_revision_assessment_binding UNIQUE (
        plan_revision_id,
        programme_id,
        programme_revision,
        carrier_mode,
        candidate_plan_sha256
    ),
    CONSTRAINT fk_r1_plan_revision_previous_same_plan
        FOREIGN KEY (previous_plan_revision_id, plan_id)
        REFERENCES r1_plan.plan_revision (plan_revision_id, plan_id)
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE r1_plan.saved_plan
    ADD CONSTRAINT fk_r1_saved_plan_current_revision
    FOREIGN KEY (plan_id, current_revision_number)
    REFERENCES r1_plan.plan_revision (plan_id, revision_number)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE r1_plan.plan_node (
    plan_node_id                 UUID PRIMARY KEY,
    plan_revision_id             UUID NOT NULL,
    node_key                     TEXT NOT NULL,
    node_kind                    TEXT NOT NULL,
    parent_plan_node_id          UUID,
    facility_type_code           TEXT NOT NULL,
    intended_role_code           TEXT,
    locality_key                 TEXT,
    host_body_pk_snapshot        BIGINT,
    host_body_source_id64        BIGINT,
    host_body_frontier_id        INTEGER,
    host_body_name_snapshot      TEXT,
    ordinal                      INTEGER NOT NULL,
    metadata_json                JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_r1_plan_node_revision
        FOREIGN KEY (plan_revision_id)
        REFERENCES r1_plan.plan_revision (plan_revision_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_r1_plan_node_ordinal
        CHECK (ordinal >= 0),
    CONSTRAINT chk_r1_plan_node_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT uq_r1_plan_node_key UNIQUE (plan_revision_id, node_key),
    CONSTRAINT uq_r1_plan_node_ordinal UNIQUE (plan_revision_id, ordinal),
    CONSTRAINT uq_r1_plan_node_same_revision_ref UNIQUE (plan_node_id, plan_revision_id),
    CONSTRAINT fk_r1_plan_node_parent_same_revision
        FOREIGN KEY (parent_plan_node_id, plan_revision_id)
        REFERENCES r1_plan.plan_node (plan_node_id, plan_revision_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE r1_plan.plan_allocation (
    allocation_id          UUID PRIMARY KEY,
    plan_revision_id       UUID NOT NULL,
    requirement_id         TEXT NOT NULL,
    resource_kind          TEXT NOT NULL,
    resource_key           TEXT NOT NULL,
    plan_node_id           UUID,
    allocation_mode        TEXT NOT NULL,
    allocation_quantity    NUMERIC,
    evidence_refs_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    ordinal                INTEGER NOT NULL,
    CONSTRAINT fk_r1_plan_allocation_revision
        FOREIGN KEY (plan_revision_id)
        REFERENCES r1_plan.plan_revision (plan_revision_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_r1_plan_allocation_node_same_revision
        FOREIGN KEY (plan_node_id, plan_revision_id)
        REFERENCES r1_plan.plan_node (plan_node_id, plan_revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT chk_r1_plan_allocation_mode
        CHECK (allocation_mode IN ('exclusive', 'shared', 'capacity')),
    CONSTRAINT chk_r1_plan_allocation_quantity
        CHECK (allocation_quantity IS NULL OR allocation_quantity >= 0),
    CONSTRAINT chk_r1_plan_allocation_evidence_array
        CHECK (jsonb_typeof(evidence_refs_json) = 'array'),
    CONSTRAINT chk_r1_plan_allocation_ordinal
        CHECK (ordinal >= 0),
    CONSTRAINT uq_r1_plan_allocation_requirement_resource
        UNIQUE NULLS NOT DISTINCT (
            plan_revision_id,
            requirement_id,
            resource_kind,
            resource_key,
            plan_node_id
        ),
    CONSTRAINT uq_r1_plan_allocation_ordinal UNIQUE (plan_revision_id, ordinal)
);

CREATE UNIQUE INDEX uq_r1_plan_allocation_exclusive_resource
    ON r1_plan.plan_allocation (plan_revision_id, resource_kind, resource_key)
    WHERE allocation_mode = 'exclusive';

CREATE TABLE r1_plan.plan_assessment (
    assessment_id               UUID PRIMARY KEY,
    plan_revision_id            UUID NOT NULL,
    assessment_kind             TEXT NOT NULL,
    system_id64                 BIGINT NOT NULL,
    programme_id                TEXT NOT NULL,
    programme_revision          TEXT NOT NULL,
    model_revision_id           TEXT NOT NULL,
    mechanics_revision_id       TEXT NOT NULL,
    canonical_generation_id     UUID NOT NULL,
    evidence_snapshot_sha256    CHAR(64) NOT NULL,
    candidate_plan_sha256       CHAR(64) NOT NULL,
    carrier_mode                TEXT NOT NULL,
    assessment_state            TEXT NOT NULL,
    evidence_disposition        TEXT NOT NULL,
    reserve_capacity            TEXT,
    logistics_state             TEXT,
    plan_pair_resilience        TEXT,
    plan_fit                    SMALLINT,
    fit_policy_revision         TEXT,
    result_sha256               CHAR(64) NOT NULL UNIQUE,
    trace_json                  JSONB NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_r1_plan_assessment_plan_binding
        FOREIGN KEY (
            plan_revision_id,
            programme_id,
            programme_revision,
            carrier_mode,
            candidate_plan_sha256
        ) REFERENCES r1_plan.plan_revision (
            plan_revision_id,
            programme_id,
            programme_revision,
            carrier_mode,
            candidate_plan_sha256
        ) ON DELETE CASCADE,
    CONSTRAINT fk_r1_plan_assessment_model
        FOREIGN KEY (model_revision_id)
        REFERENCES r1_meta.model_revision (model_revision_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_plan_assessment_mechanics
        FOREIGN KEY (mechanics_revision_id)
        REFERENCES r1_meta.mechanics_revision (mechanics_revision_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_r1_plan_assessment_canonical_generation
        FOREIGN KEY (canonical_generation_id)
        REFERENCES v3_meta.canonical_generation (generation_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_r1_plan_assessment_kind
        CHECK (assessment_kind IN ('saved_plan', 'build_pack', 'plan_audit')),
    CONSTRAINT chk_r1_plan_assessment_carrier_mode
        CHECK (carrier_mode IN ('no_carrier', 'carrier_available')),
    CONSTRAINT chk_r1_plan_assessment_state
        CHECK (assessment_state IN (
            'not_assessable',
            'not_supported',
            'conditionally_supported',
            'supported'
        )),
    CONSTRAINT chk_r1_plan_assessment_evidence
        CHECK (evidence_disposition IN ('sufficient', 'partial', 'missing', 'ambiguous', 'conflicting')),
    CONSTRAINT chk_r1_plan_assessment_reserve
        CHECK (reserve_capacity IS NULL OR reserve_capacity IN ('tight', 'sufficient', 'resilient', 'expandable', 'unknown')),
    CONSTRAINT chk_r1_plan_assessment_logistics
        CHECK (logistics_state IS NULL OR logistics_state IN ('compact', 'moderate', 'spread', 'extreme', 'unknown')),
    CONSTRAINT chk_r1_plan_assessment_pair_resilience
        CHECK (plan_pair_resilience IS NULL OR plan_pair_resilience IN ('robust', 'fragile', 'mixed', 'unknown')),
    CONSTRAINT chk_r1_plan_assessment_plan_fit_range
        CHECK (plan_fit IS NULL OR plan_fit BETWEEN 0 AND 100),
    CONSTRAINT chk_r1_plan_assessment_plan_fit_state
        CHECK (
            plan_fit IS NULL
            OR assessment_state IN ('conditionally_supported', 'supported')
        ),
    CONSTRAINT chk_r1_plan_assessment_evidence_sha256
        CHECK (evidence_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_plan_assessment_candidate_sha256
        CHECK (candidate_plan_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_plan_assessment_result_sha256
        CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_r1_plan_assessment_trace_object
        CHECK (jsonb_typeof(trace_json) = 'object')
);

CREATE INDEX idx_r1_plan_assessment_revision_created
    ON r1_plan.plan_assessment (plan_revision_id, created_at DESC);

CREATE INDEX idx_r1_plan_assessment_system_programme_created
    ON r1_plan.plan_assessment (
        system_id64,
        programme_id,
        programme_revision,
        created_at DESC
    );

CREATE INDEX idx_r1_plan_assessment_kind_created
    ON r1_plan.plan_assessment (assessment_kind, created_at DESC);

COMMENT ON SCHEMA r1_meta IS
    'R1 immutable revision registries and capability-generation publication metadata.';
COMMENT ON SCHEMA r1_cache IS
    'R1 rebuildable, context-independent Finder capability surface; never a universal ratings store.';
COMMENT ON SCHEMA r1_plan IS
    'R1 private durable saved-plan revisions, allocations and immutable assessment snapshots.';

COMMENT ON VIEW r1_cache.system_capability_current IS
    'Typed zero-row shell until a separately authorised validated capability generation is atomically published.';

COMMIT;
