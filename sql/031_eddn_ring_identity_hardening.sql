-- =============================================================================
-- Stage 17N.2d-Q — EDDN ring identity hardening
-- =============================================================================
-- body_rings.body_id is the ED-Finder local bodies.id foreign key only.
-- EDDN Journal BodyID is source identity and belongs in source_body_id.
-- Unresolved or ambiguous source evidence must not be counted by consumers.

ALTER TABLE body_rings
    ADD COLUMN IF NOT EXISTS source_body_id BIGINT DEFAULT NULL;

ALTER TABLE body_rings
    ADD COLUMN IF NOT EXISTS association_status TEXT NOT NULL DEFAULT 'local_matched';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'chk_body_rings_association_status'
           AND conrelid = 'body_rings'::regclass
    ) THEN
        ALTER TABLE body_rings
            ADD CONSTRAINT chk_body_rings_association_status
            CHECK (association_status IN (
                'local_matched',
                'unresolved_body_identity',
                'ambiguous_body_identity',
                'belt_source_evidence',
                'conflict'
            ));
    END IF;
END $$;

COMMENT ON COLUMN body_rings.body_id
    IS 'ED-Finder local bodies.id. Source-specific body identifiers must be stored in source_body_id.';

COMMENT ON COLUMN body_rings.source_body_id
    IS 'Nullable source/journal body identifier such as EDDN Journal BodyID; not a local body foreign key.';

COMMENT ON COLUMN body_rings.association_status
    IS 'Whether body_id is a trusted local bodies.id association. Consumers count only local_matched rows.';

WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id)::integer AS match_count
      FROM body_rings br
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
           END AS association_status
      FROM body_rings br
      LEFT JOIN bodies same_system_body
        ON same_system_body.system_id64 = br.system_id64
       AND same_system_body.id = br.body_id
      LEFT JOIN name_matches nm ON nm.ring_id = br.id
)
UPDATE body_rings br
   SET association_status = classified.association_status,
       updated_at = NOW()
  FROM classified
 WHERE br.id = classified.id
   AND br.association_status IS DISTINCT FROM classified.association_status;

-- Keep one canonical local row for duplicate local identities and mark the
-- rest as conflicts. This does not delete data; it only prevents duplicates
-- from being treated as independent local evidence.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY system_id64, body_id, ring_name, source
               ORDER BY id
           ) AS duplicate_rank
      FROM body_rings
     WHERE body_id IS NOT NULL
       AND association_status = 'local_matched'
)
UPDATE body_rings br
   SET association_status = 'conflict',
       updated_at = NOW()
  FROM ranked
 WHERE br.id = ranked.id
   AND ranked.duplicate_rank > 1
   AND br.association_status IS DISTINCT FROM 'conflict';

CREATE INDEX IF NOT EXISTS idx_body_rings_source_body_id
    ON body_rings (source, system_id64, source_body_id)
    WHERE source_body_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_body_rings_local_matched
    ON body_rings (system_id64, body_id)
    WHERE body_id IS NOT NULL AND association_status = 'local_matched';

CREATE INDEX IF NOT EXISTS idx_body_rings_association_status
    ON body_rings (association_status, source, system_id64);

CREATE OR REPLACE VIEW body_rings_eddn_identity_report AS
WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id)::integer AS match_count
      FROM body_rings br
      LEFT JOIN bodies b
        ON b.system_id64 = br.system_id64
       AND b.name = br.body_name
     WHERE br.source = 'eddn_scan'
     GROUP BY br.id
)
SELECT br.id,
       br.system_id64,
       br.body_id,
       br.source_body_id,
       br.body_name,
       br.ring_name,
       br.source,
       br.association_status,
       COALESCE(nm.match_count, 0) AS exact_name_match_count,
       CASE
           WHEN br.association_status = 'local_matched' THEN 'valid_local_id_row'
           WHEN br.association_status = 'unresolved_body_identity'
                AND COALESCE(nm.match_count, 0) = 1 THEN 'exact_name_repairable_row'
           WHEN br.association_status = 'unresolved_body_identity' THEN 'unresolved_source_only_row'
           WHEN br.association_status = 'ambiguous_body_identity' THEN 'ambiguous_row'
           WHEN br.association_status = 'belt_source_evidence' THEN 'belt_row'
           ELSE 'conflict'
       END AS report_bucket
  FROM body_rings br
  LEFT JOIN name_matches nm ON nm.ring_id = br.id
 WHERE br.source = 'eddn_scan';
