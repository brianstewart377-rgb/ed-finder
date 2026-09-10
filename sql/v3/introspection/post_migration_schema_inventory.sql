-- Stable, database-name-independent structural inventory for repeatability
-- proof. Volatile timestamps, OIDs, sizes, and physical locations are excluded.
WITH
schemas AS (
    SELECT COALESCE(jsonb_agg(nspname ORDER BY nspname), '[]'::jsonb) AS value
    FROM pg_namespace
    WHERE nspname ~ '^v3_'
),
relations AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'name', relation.relname,
            'kind', relation.relkind,
            'persistence', relation.relpersistence
        ) ORDER BY namespace.nspname, relation.relname
    ), '[]'::jsonb) AS value
    FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname ~ '^v3_'
      AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
),
columns AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'table', relation.relname,
            'ordinal', attribute.attnum,
            'name', attribute.attname,
            'type', format_type(attribute.atttypid, attribute.atttypmod),
            'not_null', attribute.attnotnull,
            'identity', nullif(attribute.attidentity, ''),
            'default', pg_get_expr(default_value.adbin, default_value.adrelid)
        ) ORDER BY namespace.nspname, relation.relname, attribute.attnum
    ), '[]'::jsonb) AS value
    FROM pg_attribute AS attribute
    JOIN pg_class AS relation ON relation.oid = attribute.attrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_attrdef AS default_value
      ON default_value.adrelid = attribute.attrelid
     AND default_value.adnum = attribute.attnum
    WHERE namespace.nspname ~ '^v3_'
      AND relation.relkind IN ('r', 'p')
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
),
constraints AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'table', relation.relname,
            'name', constraint_row.conname,
            'kind', constraint_row.contype,
            'validated', constraint_row.convalidated,
            'definition', pg_get_constraintdef(constraint_row.oid, true)
        ) ORDER BY namespace.nspname, relation.relname, constraint_row.conname
    ), '[]'::jsonb) AS value
    FROM pg_constraint AS constraint_row
    JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname ~ '^v3_'
),
indexes AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'table', relation.relname,
            'name', index_relation.relname,
            'unique', index_row.indisunique,
            'primary', index_row.indisprimary,
            'valid', index_row.indisvalid,
            'definition', pg_get_indexdef(index_row.indexrelid)
        ) ORDER BY namespace.nspname, relation.relname, index_relation.relname
    ), '[]'::jsonb) AS value
    FROM pg_index AS index_row
    JOIN pg_class AS relation ON relation.oid = index_row.indrelid
    JOIN pg_class AS index_relation ON index_relation.oid = index_row.indexrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname ~ '^v3_'
),
functions AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'name', procedure.proname,
            'identity_arguments', pg_get_function_identity_arguments(procedure.oid),
            'result', pg_get_function_result(procedure.oid),
            'language', language.lanname,
            'definition', pg_get_functiondef(procedure.oid)
        ) ORDER BY namespace.nspname, procedure.proname,
                   pg_get_function_identity_arguments(procedure.oid)
    ), '[]'::jsonb) AS value
    FROM pg_proc AS procedure
    JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
    JOIN pg_language AS language ON language.oid = procedure.prolang
    WHERE namespace.nspname ~ '^v3_'
),
triggers AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'schema', namespace.nspname,
            'table', relation.relname,
            'name', trigger_row.tgname,
            'enabled', trigger_row.tgenabled,
            'definition', pg_get_triggerdef(trigger_row.oid, true)
        ) ORDER BY namespace.nspname, relation.relname, trigger_row.tgname
    ), '[]'::jsonb) AS value
    FROM pg_trigger AS trigger_row
    JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname ~ '^v3_'
      AND NOT trigger_row.tgisinternal
),
roles AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'role_id', role_id,
            'public_code', public_code,
            'description', description,
            'active', active
        ) ORDER BY role_id
    ), '[]'::jsonb) AS value
    FROM v3_identity.role
),
ledger AS (
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'migration_name', migration_name,
            'migration_sha256', encode(migration_sha256, 'hex')
        ) ORDER BY migration_name
    ), '[]'::jsonb) AS value
    FROM v3_meta.schema_migration
),
counts AS (
    SELECT jsonb_build_object(
        'schemas', (
            SELECT count(*) FROM pg_namespace WHERE nspname ~ '^v3_'
        ),
        'relations', (
            SELECT count(*) FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname ~ '^v3_'
              AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
        ),
        'columns', (
            SELECT count(*) FROM pg_attribute AS attribute
            JOIN pg_class AS relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname ~ '^v3_'
              AND relation.relkind IN ('r', 'p')
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
        ),
        'constraints', (
            SELECT count(*) FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname ~ '^v3_'
        ),
        'indexes', (
            SELECT count(*) FROM pg_index AS index_row
            JOIN pg_class AS relation ON relation.oid = index_row.indrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname ~ '^v3_'
        ),
        'functions', (
            SELECT count(*) FROM pg_proc AS procedure
            JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname ~ '^v3_'
        ),
        'triggers', (
            SELECT count(*) FROM pg_trigger AS trigger_row
            JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname ~ '^v3_'
              AND NOT trigger_row.tgisinternal
        )
    ) AS value
)
SELECT jsonb_pretty(jsonb_build_object(
    'inventory_format', 'edfinder-v3-post-migration-schema-inventory/v1',
    'postgresql_version_num', current_setting('server_version_num')::integer,
    'v2_lineage_used', false,
    'public_user_relation_count', (
        SELECT count(*)
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
    ),
    'counts', counts.value,
    'schemas', schemas.value,
    'relations', relations.value,
    'columns', columns.value,
    'constraints', constraints.value,
    'indexes', indexes.value,
    'functions', functions.value,
    'triggers', triggers.value,
    'identity_roles', roles.value,
    'migration_ledger', ledger.value
))
FROM schemas, relations, columns, constraints, indexes, functions, triggers,
     roles, ledger, counts;
