-- Keep OAuth callback session cleanup index-supported as the session table grows.
-- The callback deletes expired active and revoked sessions separately so each
-- statement matches one of these partial indexes without a cross-column OR.

CREATE INDEX IF NOT EXISTS web_sessions_expired_active_idx
    ON web_sessions (expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS web_sessions_revoked_idx
    ON web_sessions (revoked_at)
    WHERE revoked_at IS NOT NULL;
