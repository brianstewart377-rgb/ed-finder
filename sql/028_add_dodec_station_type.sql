-- =============================================================================
-- Stage 18J-P18C - add Dodec station type
-- =============================================================================
-- Additive/idempotent migration. Adds Dodec as a canonical station_type enum
-- value so source evidence `Dodec Starport` can be mapped to canonical `Dodec`
-- in later bounded station-type dry-runs.
--
-- This migration does not update station rows, does not run a dry-run, and does
-- not approve station-type writes or downstream canonical operations.

ALTER TYPE station_type ADD VALUE IF NOT EXISTS 'Dodec';
