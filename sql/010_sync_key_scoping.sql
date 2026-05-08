-- ============================================================================
-- ED Finder — sync_key scoping for watchlist & system_notes
-- ============================================================================
-- Audit fix (2026-05-08, AUDIT_REPORT.md §H1 / Phase 3):
--
-- Before this migration, /api/watchlist and /api/systems/*/note were a
-- single global namespace — every visitor to ed-finder.app shared the
-- same watchlist and could overwrite anyone's notes. The sync_key
-- pattern from /api/profile/sync (sql/007_profile_sync.sql) is now
-- extended to these two tables.
--
-- The sync_key IS the credential — same trust model as profile_sync.
-- Validation (16-128 chars, A-Za-z0-9_-) lives at the API layer; this
-- migration only enforces the column shape with a CHECK constraint.
--
-- Backwards compat:
--   * Existing rows are tagged sync_key='legacy' so /api/watchlist/legacy
--     and /api/systems/{id64}/note?sync_key=legacy continue to read
--     them. The legacy sync_key is reserved for migration only — new
--     writes from new clients use a real, user-chosen key.
--   * Old un-scoped endpoints (no sync_key) now return HTTP 410 Gone in
--     the API layer.
-- ============================================================================

\echo === Phase 3: sync_key scoping migration ===

BEGIN;

-- ── watchlist ──────────────────────────────────────────────────────────────
ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS sync_key TEXT NOT NULL DEFAULT 'legacy'
        CHECK (sync_key ~ '^[A-Za-z0-9_-]{1,128}$');

-- Drop the global UNIQUE on system_id64; replace with (sync_key, system_id64).
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_system_id64_key;
DROP INDEX IF EXISTS watchlist_sync_system_uq;
CREATE UNIQUE INDEX watchlist_sync_system_uq
    ON watchlist (sync_key, system_id64);

CREATE INDEX IF NOT EXISTS idx_wl_sync_key ON watchlist (sync_key);

-- ── system_notes ───────────────────────────────────────────────────────────
ALTER TABLE system_notes
    ADD COLUMN IF NOT EXISTS sync_key TEXT NOT NULL DEFAULT 'legacy'
        CHECK (sync_key ~ '^[A-Za-z0-9_-]{1,128}$');

-- Drop the global PK on system_id64; replace with composite PK.
ALTER TABLE system_notes DROP CONSTRAINT IF EXISTS system_notes_pkey;
ALTER TABLE system_notes
    ADD CONSTRAINT system_notes_pkey PRIMARY KEY (sync_key, system_id64);

CREATE INDEX IF NOT EXISTS idx_notes_sync_key ON system_notes (sync_key);

COMMIT;

\echo === Phase 3 migration complete ===
