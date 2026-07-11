-- Keep body_rings.association_status coherent when local bodies rows change.
--
-- Stage 17N.2d hardened the ring identity contract and provided repair tools,
-- but body insert/update/delete only refreshed systems.has_body_data/body_count.
-- That allowed local_matched ring rows to linger after the referenced local
-- body row was renamed, moved, or deleted, which re-opened invariant drift
-- until a manual repair pass corrected the rows.

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

    WITH affected AS (
        SELECT DISTINCT id64
        FROM (VALUES (old_system_id64), (new_system_id64)) AS ids(id64)
        WHERE id64 IS NOT NULL
    ),
    name_matches AS (
        SELECT br.id AS ring_id,
               COUNT(b.id)::integer AS match_count
        FROM body_rings br
        JOIN affected a ON a.id64 = br.system_id64
        LEFT JOIN bodies b
          ON b.system_id64 = br.system_id64
         AND b.name = br.body_name
        GROUP BY br.id
    ),
    classified AS (
        SELECT br.id,
               CASE
                   WHEN br.source = 'eddn_scan'
                        AND same_system_body.id IS NULL
                        AND (
                            br.source_body_id = 0
                            OR br.body_id = 0
                            OR br.body_name ILIKE '% belt%'
                            OR br.ring_name ILIKE '% belt%'
                        )
                       THEN 'belt_source_evidence'
                   WHEN same_system_body.id IS NOT NULL
                        AND (
                            br.body_name IS NULL
                            OR same_system_body.name = br.body_name
                        )
                       THEN 'local_matched'
                   WHEN same_system_body.id IS NOT NULL
                        AND br.body_name IS DISTINCT FROM same_system_body.name
                       THEN 'conflict'
                   WHEN COALESCE(nm.match_count, 0) > 1
                       THEN 'ambiguous_body_identity'
                   WHEN br.body_id IS NULL OR same_system_body.id IS NULL
                       THEN 'unresolved_body_identity'
                   ELSE 'local_matched'
               END AS expected_association_status
        FROM body_rings br
        JOIN affected a ON a.id64 = br.system_id64
        LEFT JOIN bodies same_system_body
          ON same_system_body.system_id64 = br.system_id64
         AND same_system_body.id = br.body_id
        LEFT JOIN name_matches nm ON nm.ring_id = br.id
    ),
    ranked_local AS (
        SELECT br.id,
               ROW_NUMBER() OVER (
                   PARTITION BY br.system_id64, br.body_id, br.ring_name, br.source
                   ORDER BY br.id
               ) AS duplicate_rank
        FROM body_rings br
        JOIN classified c ON c.id = br.id
        WHERE br.body_id IS NOT NULL
          AND c.expected_association_status = 'local_matched'
    ),
    final_status AS (
        SELECT c.id,
               CASE
                   WHEN COALESCE(rl.duplicate_rank, 1) > 1 THEN 'conflict'
                   ELSE c.expected_association_status
               END AS expected_association_status
        FROM classified c
        LEFT JOIN ranked_local rl ON rl.id = c.id
    )
    UPDATE body_rings br
       SET association_status = fs.expected_association_status,
           updated_at = NOW()
      FROM final_status fs
     WHERE br.id = fs.id
       AND br.association_status IS DISTINCT FROM fs.expected_association_status;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;
