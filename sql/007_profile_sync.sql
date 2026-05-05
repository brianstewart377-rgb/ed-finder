-- ed-finder migration 007: profile sync slot table
--
-- Stores per-user "profiles" (Pinned + Compare + FC route + Colony tracker)
-- as a single JSONB blob, keyed by a user-chosen sync key. No per-key auth
-- — the sync key IS the credential, so users must pick something hard to
-- guess. A 16-char random string gives ~96 bits of entropy, which is fine.
--
-- This table is intentionally simple. We don't keep history (no
-- profile_sync_history) and we don't normalise the blob; the frontend is
-- the source of truth, the backend is a paste-bin with one slot per key.
--
-- Run via: docker compose exec postgres psql -U edfinder -d edfinder -f /sql/007_profile_sync.sql
--   (the postgres container mounts ./sql at /sql by default)

CREATE TABLE IF NOT EXISTS profile_sync (
    sync_key   TEXT        PRIMARY KEY
                            CHECK (length(sync_key) BETWEEN 16 AND 128
                                   AND sync_key ~ '^[A-Za-z0-9_-]+$'),
    blob       JSONB       NOT NULL,
    /* approx blob size, useful for the admin/quota dashboard */
    blob_bytes INTEGER     NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Hard cap per slot: 1 MiB JSON. The realistic Pinned+Compare+FC+Colony
-- payload is well under 100 KiB; 1 MiB is generous breathing room without
-- letting accidents fill the disk.
ALTER TABLE profile_sync
  ADD CONSTRAINT profile_sync_blob_max_size
  CHECK (blob_bytes <= 1048576) NOT VALID;
ALTER TABLE profile_sync VALIDATE CONSTRAINT profile_sync_blob_max_size;

-- Updated-at index supports the future "list slots updated in the last N
-- days" admin query.
CREATE INDEX IF NOT EXISTS idx_profile_sync_updated
  ON profile_sync (updated_at DESC);
