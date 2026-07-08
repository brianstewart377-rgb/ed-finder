-- =============================================================================
-- Stage 26 - Evidence store foundation
-- =============================================================================
-- Additive/idempotent migration. Creates the first unified evidence-store
-- tables for imported evidence records, derived features, and rule proposal
-- governance. This layer complements existing observed_facts and source_runs
-- rather than replacing them.

CREATE TABLE IF NOT EXISTS evidence_records (
    id                  BIGSERIAL       PRIMARY KEY,
    evidence_key        TEXT            NOT NULL UNIQUE,
    system_id64         BIGINT          NOT NULL,
    source_name         TEXT            NOT NULL,
    origin              TEXT            NOT NULL,
    subject_type        TEXT            NOT NULL,
    subject_id          TEXT            DEFAULT NULL,
    evidence_type       TEXT            NOT NULL,
    record_status       TEXT            NOT NULL DEFAULT 'active',
    freshness_status    TEXT            NOT NULL DEFAULT 'current',
    confidence          TEXT            NOT NULL DEFAULT 'medium',
    summary             TEXT            DEFAULT NULL,
    source_record_id    TEXT            DEFAULT NULL,
    source_run_key      TEXT            DEFAULT NULL,
    observed_at         TIMESTAMPTZ     DEFAULT NULL,
    collected_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NULL,
    value_json          JSONB           NOT NULL DEFAULT '{}'::jsonb,
    provenance_json     JSONB           NOT NULL DEFAULT '{}'::jsonb,
    tags_json           JSONB           NOT NULL DEFAULT '[]'::jsonb,
    metadata_json       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_evidence_records_source_name
        CHECK (source_name IN (
            'spansh',
            'eddn',
            'edsm',
            'inara',
            'daftmav',
            'mega_guide',
            'operator_artifact',
            'local_generated_artifact',
            'mission_observation',
            'frontier_journal',
            'edcd',
            'canonn',
            'planner_reference_archive',
            'manual_operator_source'
        )),
    CONSTRAINT chk_evidence_records_origin
        CHECK (origin IN ('manual', 'imported', 'inferred', 'derived', 'test_fixture')),
    CONSTRAINT chk_evidence_records_record_status
        CHECK (record_status IN ('active', 'superseded', 'rejected', 'archived')),
    CONSTRAINT chk_evidence_records_freshness
        CHECK (freshness_status IN ('current', 'stale', 'superseded', 'expired', 'unknown')),
    CONSTRAINT chk_evidence_records_confidence
        CHECK (confidence IN ('low', 'medium', 'high')),
    CONSTRAINT fk_evidence_records_source_run
        FOREIGN KEY (source_run_key)
        REFERENCES source_runs (source_run_key)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_records_system_observed
    ON evidence_records (system_id64, observed_at DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_records_source_origin
    ON evidence_records (source_name, origin, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_records_source_run
    ON evidence_records (source_run_key)
    WHERE source_run_key IS NOT NULL;


CREATE TABLE IF NOT EXISTS derived_features (
    id                  BIGSERIAL       PRIMARY KEY,
    feature_key         TEXT            NOT NULL UNIQUE,
    system_id64         BIGINT          NOT NULL,
    feature_name        TEXT            NOT NULL,
    feature_version     TEXT            NOT NULL DEFAULT 'v1',
    feature_status      TEXT            NOT NULL DEFAULT 'active',
    confidence          TEXT            NOT NULL DEFAULT 'medium',
    summary             TEXT            DEFAULT NULL,
    derived_from_run_key TEXT           DEFAULT NULL,
    derived_at          TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NULL,
    value_json          JSONB           NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs_json  JSONB           NOT NULL DEFAULT '[]'::jsonb,
    metadata_json       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_derived_features_status
        CHECK (feature_status IN ('active', 'stale', 'superseded')),
    CONSTRAINT chk_derived_features_confidence
        CHECK (confidence IN ('low', 'medium', 'high')),
    CONSTRAINT fk_derived_features_source_run
        FOREIGN KEY (derived_from_run_key)
        REFERENCES source_runs (source_run_key)
        ON DELETE SET NULL,
    CONSTRAINT uq_derived_features_system_name_version
        UNIQUE (system_id64, feature_name, feature_version)
);

CREATE INDEX IF NOT EXISTS idx_derived_features_system_status
    ON derived_features (system_id64, feature_status, derived_at DESC);


CREATE TABLE IF NOT EXISTS rule_proposals (
    id                      BIGSERIAL       PRIMARY KEY,
    proposal_key            TEXT            NOT NULL UNIQUE,
    proposal_type           TEXT            NOT NULL,
    domain                  TEXT            NOT NULL,
    scope_type              TEXT            NOT NULL,
    scope_key               TEXT            NOT NULL,
    status                  TEXT            NOT NULL DEFAULT 'pending_review',
    priority                TEXT            NOT NULL DEFAULT 'medium',
    risk_level              TEXT            NOT NULL DEFAULT 'medium',
    auto_approval_eligible  BOOLEAN         NOT NULL DEFAULT FALSE,
    summary                 TEXT            NOT NULL,
    proposed_by             TEXT            NOT NULL,
    decided_by              TEXT            DEFAULT NULL,
    decision_notes          TEXT            DEFAULT NULL,
    proposed_change_json    JSONB           NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs_json      JSONB           NOT NULL DEFAULT '[]'::jsonb,
    impact_summary_json     JSONB           NOT NULL DEFAULT '{}'::jsonb,
    metadata_json           JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    decided_at              TIMESTAMPTZ     DEFAULT NULL,

    CONSTRAINT chk_rule_proposals_status
        CHECK (status IN ('pending_review', 'approved', 'rejected', 'auto_approved', 'implemented', 'superseded')),
    CONSTRAINT chk_rule_proposals_priority
        CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT chk_rule_proposals_risk
        CHECK (risk_level IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS idx_rule_proposals_status_created
    ON rule_proposals (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rule_proposals_scope
    ON rule_proposals (scope_key, status, created_at DESC);


CREATE TABLE IF NOT EXISTS rule_decisions (
    id                  BIGSERIAL       PRIMARY KEY,
    proposal_key        TEXT            NOT NULL,
    decision            TEXT            NOT NULL,
    decided_by          TEXT            NOT NULL,
    reason              TEXT            DEFAULT NULL,
    metadata_json       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_rule_decisions_decision
        CHECK (decision IN ('approved', 'rejected', 'superseded', 'rolled_back')),
    CONSTRAINT fk_rule_decisions_proposal
        FOREIGN KEY (proposal_key)
        REFERENCES rule_proposals (proposal_key)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rule_decisions_proposal_created
    ON rule_decisions (proposal_key, created_at DESC);

COMMENT ON TABLE evidence_records
    IS 'Unified imported/manual/inferred evidence records linked to a system and optional source run.';

COMMENT ON TABLE derived_features
    IS 'Derived feature shelf backed by evidence records and source-run provenance.';

COMMENT ON TABLE rule_proposals
    IS 'Governed rule proposals backed by evidence references and impact summaries.';

COMMENT ON TABLE rule_decisions
    IS 'Audit trail for rule proposal decisions.';
