-- Frontier OAuth account foundation.
--
-- Privacy boundary: ED-Finder retains only the stable Frontier account ID and
-- Commander name. Frontier access/refresh tokens and other CAPI profile data
-- are intentionally not stored by this first account slice.

CREATE TABLE IF NOT EXISTS app_users (
    id                    BIGSERIAL PRIMARY KEY,
    frontier_customer_id  TEXT NOT NULL UNIQUE,
    commander_name        TEXT,
    is_owner              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT app_users_frontier_customer_id_not_blank
        CHECK (BTRIM(frontier_customer_id) <> ''),
    CONSTRAINT app_users_commander_name_not_blank
        CHECK (commander_name IS NULL OR BTRIM(commander_name) <> '')
);

CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash       CHAR(64) PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NOT NULL,
    revoked_at       TIMESTAMPTZ,
    CONSTRAINT web_sessions_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS web_sessions_user_active_idx
    ON web_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS oauth_login_states (
    state_hash       CHAR(64) PRIMARY KEY,
    code_verifier    TEXT NOT NULL,
    return_to        TEXT NOT NULL DEFAULT '/',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NOT NULL,
    CONSTRAINT oauth_login_states_verifier_not_blank
        CHECK (BTRIM(code_verifier) <> ''),
    CONSTRAINT oauth_login_states_return_to_local
        CHECK (return_to LIKE '/%' AND return_to NOT LIKE '//%'),
    CONSTRAINT oauth_login_states_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS oauth_login_states_expiry_idx
    ON oauth_login_states (expires_at);
