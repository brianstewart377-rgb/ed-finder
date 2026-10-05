"""Guard the chunk re-read query shape against the sequential-scan regression.

The production validator re-reads every written chunk before it will seal it.
That read originally selected chunk membership with ``t.system_id64 IN (SELECT
system_id64 FROM v3_derived.system_rating_vector ...)``. On the retained
production relation (602M rows, ~110GB) PostgreSQL prices that semi-join against
a parallel sequential scan of ``body_mechanics`` as a near-tie and then chooses
the scan, so every replayed chunk read the whole table. Measured on the retained
database for chunk 19058 at default planner settings:

    semi-join read   13594 ms, 8000718 buffers
    joined read         69 ms,    5117 buffers

This module cannot reproduce the misplan. The fixture database holds a few
hundred rows, so every candidate plan is an index lookup there and a plan
assertion would pass against the defective query too. The durable guard is
therefore the *shape* the planner cannot degrade -- chunk membership resolved by
an equi-join to the chunk receipt relation instead of by a semi-join -- with the
production measurements recorded in
``docs/development/ratings-v4-chunk-read-plan.md``.

A shape assertion is weak on its own, because any query could coincidentally
satisfy it, so two further tests keep it honest:
``test_guard_rejects_the_previous_semi_join_read`` runs the same check against
the previous query verbatim and requires it to fail, and
``test_joined_read_matches_the_previous_semi_join_read`` proves the joined form
returns the same rows, in the same order, wherever a validation database is
available.
"""
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    BODY_COLUMNS, OPPORTUNITY_COLUMNS, VECTOR_COLUMNS, _read_chunk, create_generation, write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

GENERATION = '403b2d43-820c-414a-ad57-0d4de0ca3e82'
ORDINAL = 19058

# Read key -> (relation, projected columns, ordering). Mirrors ``_read_chunk``.
READS = {
    'vectors': ('system_rating_vector', VECTOR_COLUMNS, ['system_id64']),
    'bodies': ('body_mechanics', BODY_COLUMNS, ['system_id64', 'body_pk']),
    'opportunities': ('economy_opportunity', OPPORTUNITY_COLUMNS,
                      ['system_id64', 'body_pk', 'economy_ordinal']),
}


class RecordingConnection:
    """Captures the compiled statement and bound parameters of each read."""

    def __init__(self):
        self.reads = []

    def execute(self, query, params=None):
        self.reads.append((query.as_string(None), params))
        return self

    def fetchall(self):
        return []


def semi_join_statement(table, columns, order):
    """The previous read, retained to prove the fix is equivalent and guarded."""
    return sql.SQL('''SELECT {} FROM v3_derived.{} t WHERE t.derived_generation_id=%s
        AND t.system_id64 IN (SELECT system_id64 FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=%s) ORDER BY {}''').format(
        sql.SQL(',').join(sql.Identifier('t', column) for column in columns), sql.Identifier(table),
        sql.SQL(',').join(sql.Identifier('t', column) for column in order))


def semi_join_read(connection, table, columns, order, generation_id, ordinal):
    return connection.execute(
        semi_join_statement(table, columns, order), (generation_id, generation_id, ordinal)).fetchall()


def normalize(statement):
    return ' '.join(statement.split())


def assert_reachable_by_receipt_join(statement, params, relation, order):
    """Chunk rows must be reached through the receipt relation, not a semi-join."""
    text = normalize(statement)
    assert f'FROM v3_derived."{relation}" t' in text
    assert 'JOIN v3_derived.system_rating_vector v' in text
    assert 'v.derived_generation_id=t.derived_generation_id' in text
    assert 'v.system_id64=t.system_id64' in text
    # The receipt filter is applied once, against the joined relation.
    assert 'WHERE v.derived_generation_id=%s AND v.chunk_ordinal=%s' in text
    # The semi-join is the form PostgreSQL degraded into a full sequential scan.
    assert ' IN (' not in text.upper()
    # Explicit ordering keeps replayed row order, and the sealed chunk digest,
    # identical to the order the chunk was written in.
    assert text.split('ORDER BY ', 1)[1] == ','.join(f'"t"."{column}"' for column in order)
    # Two bound parameters, not the semi-join's redundant three.
    assert params == (GENERATION, ORDINAL)


def test_chunk_reads_are_reachable_by_the_receipt_join():
    connection = RecordingConnection()
    assert _read_chunk(connection, GENERATION, ORDINAL) == {key: [] for key in READS}
    assert len(connection.reads) == len(READS)
    for (relation, _, order), (statement, params) in zip(READS.values(), connection.reads, strict=True):
        assert_reachable_by_receipt_join(statement, params, relation, order)


def test_receipt_filter_is_bound_once_per_read():
    connection = RecordingConnection()
    _read_chunk(connection, GENERATION, ORDINAL)
    assert {params for _, params in connection.reads} == {(GENERATION, ORDINAL)}


def test_guard_rejects_the_previous_semi_join_read():
    """The shape check has teeth: the previous query fails it."""
    _, columns, order = READS['bodies']
    with pytest.raises(AssertionError):
        assert_reachable_by_receipt_join(
            semi_join_statement('body_mechanics', columns, order).as_string(None),
            (GENERATION, GENERATION, ORDINAL), 'body_mechanics', order)


def test_joined_read_matches_the_previous_semi_join_read():
    """The joined form returns the same rows, in the same order, as before."""
    with canonical_database() as (connection, canonical, metadata, payloads):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        snapshot = CanonicalSnapshot.pin(connection)
        exported = snapshot.export_chunk(connection, [row['id64'] for row in canonical['systems']])
        records = [payload['system'] for payload in payloads]
        generation = create_generation(connection, snapshot, 'test_' + uuid4().hex)
        assert write_chunk(connection, generation, 0, exported, snapshot.metadata, records)
        replayed = _read_chunk(connection, generation, 0)
        for key, (relation, columns, order) in READS.items():
            assert replayed[key] == semi_join_read(
                connection, relation, columns, order, generation, 0), key