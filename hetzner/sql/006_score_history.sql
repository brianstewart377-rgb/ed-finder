-- ─────────────────────────────────────────────────────────────────────────────
-- 006_score_history.sql
-- Historical score tracking for ED Finder systems.
-- Allows the API to show score trends over time (e.g. "was 45, now 62").
--
-- Run manually after the initial import is complete:
--   docker exec -i ed-postgres psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/006_score_history.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Table: score_history ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS score_history (
    id              BIGSERIAL PRIMARY KEY,
    system_id64     BIGINT      NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score           SMALLINT    NOT NULL,
    score_agri      SMALLINT,
    score_refinery  SMALLINT,
    score_industrial SMALLINT,
    score_hightech  SMALLINT,
    score_military  SMALLINT,
    score_tourism   SMALLINT,
    trigger         TEXT        NOT NULL DEFAULT 'nightly'  -- 'nightly', 'eddn', 'manual'
);

CREATE INDEX IF NOT EXISTS idx_score_history_system_id64
    ON score_history (system_id64, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_score_history_recorded_at
    ON score_history (recorded_at DESC);

-- ── Function: record_score_snapshot ──────────────────────────────────────────
-- Called by the nightly update script to snapshot all recently-changed systems.
CREATE OR REPLACE FUNCTION record_score_snapshots(p_trigger TEXT DEFAULT 'nightly')
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_count INTEGER;
BEGIN
    INSERT INTO score_history (system_id64, recorded_at, score,
        score_agri, score_refinery, score_industrial,
        score_hightech, score_military, score_tourism, trigger)
    SELECT
        r.system_id64,
        NOW(),
        r.score,
        r.score_agriculture,
        r.score_refinery,
        r.score_industrial,
        r.score_hightech,
        r.score_military,
        r.score_tourism,
        p_trigger
    FROM ratings r
    WHERE r.updated_at > NOW() - INTERVAL '25 hours'  -- Only systems updated in last nightly cycle
      AND r.score IS NOT NULL;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- ── View: score_trends ────────────────────────────────────────────────────────
-- Shows the most recent two snapshots for each system to compute delta
CREATE OR REPLACE VIEW score_trends AS
SELECT
    s1.system_id64,
    s1.score        AS score_now,
    s2.score        AS score_prev,
    s1.score - COALESCE(s2.score, s1.score) AS score_delta,
    s1.recorded_at  AS snapshot_at
FROM (
    SELECT DISTINCT ON (system_id64)
        system_id64, score, recorded_at
    FROM score_history
    ORDER BY system_id64, recorded_at DESC
) s1
LEFT JOIN LATERAL (
    SELECT score, recorded_at
    FROM score_history h
    WHERE h.system_id64 = s1.system_id64
      AND h.recorded_at < s1.recorded_at
    ORDER BY h.recorded_at DESC
    LIMIT 1
) s2 ON TRUE;

COMMENT ON VIEW score_trends IS
    'Shows current score vs previous snapshot and the delta for each system.';

-- ── Table: app_meta additions ─────────────────────────────────────────────────
INSERT INTO app_meta (key, value) VALUES
    ('score_history_enabled', 'true'),
    ('score_history_last_snapshot', NULL)
ON CONFLICT (key) DO NOTHING;
