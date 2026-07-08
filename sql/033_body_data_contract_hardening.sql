-- Keep systems.has_body_data/body_count coherent with actual bodies rows.
--
-- Stage 17N.2c originally let body triggers mark systems dirty and set
-- has_body_data=TRUE without recomputing body_count. Under mixed EDDN/Spansh
-- ingest that allows impossible states like:
--   has_body_data = TRUE
--   body_count    = 0
--   no ratings row yet
--
-- This migration hardens the trigger contract for future body writes. It does
-- not attempt a fleet-wide backfill of existing inconsistent systems; run that
-- separately when production load allows.

CREATE OR REPLACE FUNCTION fn_mark_body_system_dirty()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    old_system_id64 BIGINT;
    new_system_id64 BIGINT;
BEGIN
    old_system_id64 := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.system_id64 ELSE NULL END;
    new_system_id64 := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.system_id64 ELSE NULL END;

    WITH affected AS (
        SELECT DISTINCT id64
        FROM (VALUES (old_system_id64), (new_system_id64)) AS ids(id64)
        WHERE id64 IS NOT NULL
    ),
    counts AS (
        SELECT a.id64,
               COUNT(b.id)::INTEGER AS actual_body_count
        FROM affected a
        LEFT JOIN bodies b ON b.system_id64 = a.id64
        GROUP BY a.id64
    )
    UPDATE systems s
       SET rating_dirty  = TRUE,
           cluster_dirty = TRUE,
           has_body_data = (c.actual_body_count > 0),
           body_count    = c.actual_body_count,
           updated_at    = NOW()
      FROM counts c
     WHERE s.id64 = c.id64;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;
