-- 011_autocomplete_index.sql — fast case-insensitive name prefix lookup.
--
-- Background
-- ----------
-- `idx_sys_name` is `btree (name)` with the default `text_ops` operator
-- class. That index cannot service `WHERE name ILIKE 'Sol%'` — case-
-- insensitive prefix matching requires either `text_pattern_ops` or a
-- functional index on `lower(name)`. With neither, the planner falls
-- back to the GIN trigram (`idx_sys_name_trgm`), which on a 3-character
-- query like 'Sol' has terrible selectivity (every trigram-match set
-- has to be re-verified against the original string). On 186 M rows
-- this consistently takes >300 s and trips the API's 5-min timeout.
--
-- This migration adds a `(lower(name) text_pattern_ops)` btree, and
-- `apps/api/src/local_search.py::local_db_autocomplete` is updated in
-- the same commit to query `WHERE lower(name) LIKE lower($1) || '%'`,
-- which is a sub-millisecond range scan on the new index.
--
-- The index takes ~10-15 min to build on 186 M rows and is built
-- CONCURRENTLY so the live API is unaffected during the build.
--
-- The legacy `idx_sys_name` is intentionally left in place — it's still
-- useful for `ORDER BY name` operations and exact-match lookups. Cost
-- is one extra ~3 GB index, well worth the autocomplete unblock.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sys_name_lower_pattern
  ON systems (lower(name) text_pattern_ops);
