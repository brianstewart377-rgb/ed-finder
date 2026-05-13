-- Regional positioning intelligence for colonisation planning.

CREATE TABLE IF NOT EXISTS system_regional_analysis (
    system_id64 BIGINT PRIMARY KEY REFERENCES systems(id64) ON DELETE CASCADE,

    nearest_colonised_system_id64 BIGINT,
    nearest_colonised_system_name TEXT,
    nearest_colonised_system_distance_ly DOUBLE PRECISION,

    colonised_within_25ly INTEGER NOT NULL DEFAULT 0,
    colonised_within_50ly INTEGER NOT NULL DEFAULT 0,
    colonised_within_100ly INTEGER NOT NULL DEFAULT 0,
    colonised_within_250ly INTEGER NOT NULL DEFAULT 0,

    regional_isolation_score DOUBLE PRECISION,
    regional_density_score DOUBLE PRECISION,
    regional_expansion_score DOUBLE PRECISION,
    regional_competition_score DOUBLE PRECISION,

    regional_role TEXT NOT NULL DEFAULT 'unknown',

    archetype_regional_fit JSONB NOT NULL DEFAULT '{}'::jsonb,
    rationale JSONB NOT NULL DEFAULT '{}'::jsonb,

    data_source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_system_regional_role
    ON system_regional_analysis (regional_role);

CREATE INDEX IF NOT EXISTS idx_system_regional_nearest
    ON system_regional_analysis (nearest_colonised_system_distance_ly);

CREATE INDEX IF NOT EXISTS idx_system_regional_100
    ON system_regional_analysis (colonised_within_100ly);

CREATE INDEX IF NOT EXISTS idx_system_regional_fit_gin
    ON system_regional_analysis USING gin (archetype_regional_fit);
