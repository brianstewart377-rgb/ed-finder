"""Exercise purge fixture relation selection without a PostgreSQL service."""
import sqlite3
from types import SimpleNamespace

from tests.test_v3_governed_derived_purge import _set_fixture_maintenance_options


def test_maintenance_selection_covers_other_schemas_and_toast_without_shared_or_temporary_tables():
    # The catalog selection uses portable SQL. Execute it over representative
    # catalog rows so this catches a schema filter that would omit real heaps.
    with sqlite3.connect(':memory:') as catalog:
        catalog.execute('CREATE TABLE pg_namespace (oid integer, nspname text)')
        catalog.execute('''CREATE TABLE pg_class (
            relnamespace integer, relname text, reltoastrelid integer,
            relkind text, relisshared boolean, relpersistence text)''')
        catalog.executemany('INSERT INTO pg_namespace VALUES (?,?)', (
            (1, 'information_schema'), (2, 'public'), (3, 'pg_catalog'),
            (4, 'v3_gen_fixture'), (5, 'v3_derived'), (6, 'pg_toast'), (7, 'pg_temp_1'),
        ))
        catalog.executemany('INSERT INTO pg_class VALUES (?,?,?,?,?,?)', (
            (1, 'sql_features', 100, 'r', False, 'p'),
            (2, 'extension_table', 101, 'r', False, 'p'),
            (3, 'pg_class', 0, 'r', False, 'p'),
            (3, 'pg_authid', 102, 'r', True, 'p'),
            (4, 'systems', 103, 'r', False, 'p'),
            (5, 'system_search', 104, 'r', False, 'p'),
            (5, 'system_rating_vector', 0, 'r', False, 'p'),
            (6, 'pg_toast_100', 0, 't', False, 'p'),
            (6, 'pg_toast_102', 0, 't', True, 'p'),
            (7, 'temporary_table', 105, 'r', False, 't'),
            (2, 'extension_index', 0, 'i', False, 'p'),
        ))
        alterations = []

        def execute(statement):
            if isinstance(statement, str):
                return catalog.execute(statement)
            alterations.append(' '.join(statement.as_string().split()))

        _set_fixture_maintenance_options(SimpleNamespace(execute=execute))

    assert len(alterations) == 6
    for schema, table in (
        ('information_schema', 'sql_features'), ('public', 'extension_table'),
        ('v3_gen_fixture', 'systems'),
    ):
        assert (f'ALTER TABLE "{schema}"."{table}" SET '
                '(autovacuum_enabled=false,toast.autovacuum_enabled=false)') in alterations
    assert 'ALTER TABLE "pg_catalog"."pg_class" SET (autovacuum_enabled=false)' in alterations
    assert not any(name in statement for statement in alterations
                   for name in ('pg_authid', 'pg_toast_100', 'pg_toast_102', 'temporary_table', 'extension_index'))

    for table in ('system_search', 'system_rating_vector'):
        statement, = [statement for statement in alterations if f'"{table}"' in statement]
        assert 'autovacuum_enabled' not in statement
        assert 'autovacuum_analyze_threshold=2147483647' in statement
        assert 'autovacuum_analyze_scale_factor=0' in statement
        assert 'autovacuum_vacuum_threshold=2147483647' in statement
        assert 'autovacuum_vacuum_scale_factor=0' in statement
        assert 'autovacuum_vacuum_insert_threshold=-1' in statement
        if table == 'system_search':
            assert 'toast.autovacuum_vacuum_threshold=2147483647' in statement
            assert 'toast.autovacuum_vacuum_scale_factor=0' in statement
            assert 'toast.autovacuum_vacuum_insert_threshold=-1' in statement
        else:
            assert 'toast.' not in statement
