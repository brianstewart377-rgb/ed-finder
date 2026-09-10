#!/usr/bin/env python3
"""Resume a complete Ratings V4 build and stop at a validated generation.

This runner never applies migrations or publishes a derived pointer. Production
execution still requires a current, reviewed V3 operation authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import (  # noqa: E402
    MAX_CHUNK_SYSTEMS, CanonicalSnapshot, RetainedArtifactStream,
)
from scripts.ratings_v4.production_generation import (  # noqa: E402
    _verify_code, create_generation, seal_source, validate_generation, write_chunk,
)

GENERATION_KEY = re.compile(r'[a-z][a-z0-9_]{0,62}\Z')
Progress = Callable[[dict], None]


def _artifact(snapshot: CanonicalSnapshot) -> tuple[str, int]:
    artifact = snapshot.metadata.get('artifact')
    if not isinstance(artifact, dict):
        raise ValueError('canonical snapshot has no retained source artifact')
    digest = artifact.get('content_sha256')
    size = artifact.get('size_bytes')
    if not isinstance(digest, str) or not re.fullmatch(r'(?:\\x)?[0-9a-f]{64}', digest):
        raise ValueError('canonical artifact checksum is invalid')
    if type(size) is not int or size <= 0:
        raise ValueError('canonical artifact size is invalid')
    return digest.removeprefix('\\x'), size


def _generation(connection, snapshot: CanonicalSnapshot, generation_key: str):
    if not GENERATION_KEY.fullmatch(generation_key):
        raise ValueError('invalid derived generation key')
    row = connection.execute('''SELECT derived_generation_id,lifecycle_state,manifest,
        validation_receipt FROM v3_meta.derived_generation WHERE generation_key=%s''',
        (generation_key,)).fetchone()
    if row is None:
        identifier = create_generation(connection, snapshot, generation_key)
        return identifier, 'BUILDING', None, False
    identifier, state, manifest, validation = row
    _verify_code(manifest)
    expected = {
        'canonical_generation_id': snapshot.generation_id,
        'canonical_publication_sequence': snapshot.publication_sequence,
        'canonical_schema': snapshot.schema,
        'source_metadata': snapshot.metadata,
        'expected_systems': snapshot.expected_systems,
        'expected_bodies': snapshot.expected_bodies,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('existing generation key belongs to another canonical input')
    return identifier, state, validation, True


def build_generation(read_connection, write_connection, source_path: Path,
                     generation_key: str, *, chunk_size: int = 500,
                     progress: Progress | None = None) -> dict:
    """Build or resume one exact generation, validate it, and never publish it."""
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SYSTEMS:
        raise ValueError('chunk size outside bounded contract')
    source_path = Path(source_path)
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError('retained artifact must be a regular non-symlink file')

    snapshot = CanonicalSnapshot.pin(read_connection)
    digest, size = _artifact(snapshot)
    if source_path.stat().st_size != size:
        raise ValueError('retained artifact size differs from canonical metadata')
    identifier, state, validation, resumed = _generation(
        write_connection, snapshot, generation_key,
    )
    chunks_seen = chunks_written = 0

    if state == 'BUILDING':
        stream = RetainedArtifactStream(source_path, sha256=digest, size_bytes=size)
        for ordinal, records in enumerate(stream.chunks(chunk_size)):
            canonical = snapshot.export_chunk(
                read_connection, [record['id64'] for record in records],
            )
            written = write_chunk(
                write_connection, identifier, ordinal, canonical,
                snapshot.metadata, records,
            )
            chunks_seen += 1
            chunks_written += int(written)
            if progress is not None:
                progress({
                    'derived_generation_id': str(identifier),
                    'chunk_ordinal': ordinal,
                    'systems': len(records),
                    'written': written,
                })
        if stream.receipt is None:
            raise ValueError('retained artifact did not produce a verified EOF receipt')
        seal_source(write_connection, identifier, stream.receipt)
        state = 'VALIDATING'

    if state == 'VALIDATING':
        validation = validate_generation(write_connection, identifier)
        state = 'READY'
    elif state not in {'READY', 'PUBLISHED', 'RETIRED'}:
        raise ValueError(f'generation cannot resume from lifecycle state {state}')
    if not isinstance(validation, dict) or validation.get('status') != 'VERIFIED':
        raise ValueError('generation has no verified validation receipt')

    return {
        'status': 'VERIFIED',
        'derived_generation_id': str(identifier),
        'generation_key': generation_key,
        'lifecycle_state': state,
        'canonical_generation_id': snapshot.generation_id,
        'canonical_publication_sequence': snapshot.publication_sequence,
        'chunks_seen': chunks_seen,
        'chunks_written': chunks_written,
        'resumed': resumed,
        'publication_performed': False,
        'validation_receipt': validation,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--chunk-size', type=int, default=500)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    read_dsn = os.environ.get('RATINGS_V4_CANONICAL_DATABASE_URL')
    write_dsn = os.environ.get('RATINGS_V4_DERIVED_DATABASE_URL')
    if not read_dsn or not write_dsn:
        print(json.dumps({'status': 'FAILED', 'error': 'database_authority_missing'}), file=sys.stderr)
        return 64
    try:
        import psycopg
        with (psycopg.connect(read_dsn, autocommit=True) as read_connection,
              psycopg.connect(write_dsn, autocommit=True) as write_connection):
            receipt = build_generation(
                read_connection, write_connection, args.source,
                args.generation_key, chunk_size=args.chunk_size,
                progress=lambda item: print(json.dumps({'status': 'PROGRESS', **item}, sort_keys=True)),
            )
    except Exception as exc:  # CLI emits no connection or source exception details.
        print(json.dumps({'status': 'FAILED', 'error': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
