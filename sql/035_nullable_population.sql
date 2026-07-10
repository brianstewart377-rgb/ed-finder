-- Preserve unknown population as NULL instead of collapsing it to zero.
ALTER TABLE systems
    ALTER COLUMN population DROP NOT NULL,
    ALTER COLUMN population DROP DEFAULT;
