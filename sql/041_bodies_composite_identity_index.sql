-- Part 1 of the bodies composite-identity migration (see
-- docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md).
-- bodies.id is a source-supplied id (Spansh dump id, or the Elite Dangerous
-- journal's BodyID) that is unique only within a system, not globally — the
-- current bare `id BIGINT PRIMARY KEY` cannot represent that. This index is
-- the non-blocking first step; sql/042 swaps it in as the real primary key
-- once it's built and verified.
--
-- CONCURRENTLY: do not wrap this file in a transaction when applying. On the
-- ~573M-row bodies table this will take a long time — run it during a
-- monitored low-traffic window, not as part of a routine deploy. Existing
-- rows are already globally unique on id (the current PK enforces it), so
-- this cannot fail on a duplicate — it is purely an index build, no data
-- changes.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_bodies_system_id64_id
    ON bodies (system_id64, id);
