CREATE TABLE IF NOT EXISTS admin_job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_key TEXT NOT NULL,
    trigger_source TEXT NOT NULL DEFAULT 'admin',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    exit_code INTEGER NULL,
    error_text TEXT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_admin_job_runs_status
        CHECK (status IN ('running', 'completed', 'failed')),
    CONSTRAINT chk_admin_job_runs_finished_window
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS ix_admin_job_runs_job_key_started_at
    ON admin_job_runs (job_key, started_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS ix_admin_job_runs_status_started_at
    ON admin_job_runs (status, started_at DESC, id DESC);
