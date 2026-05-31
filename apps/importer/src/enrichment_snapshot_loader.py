#!/usr/bin/env python3
"""Offline enrichment snapshot loader.

This command reads local JSON/JSON.GZ source files and emits a deterministic
dry-run import plan. It deliberately has no network, container, or database path,
and any apply/write flag fails closed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from enrichment_staging import (
    ADAPTER_VERSION,
    build_enrichment_snapshot_load_plan,
    build_raw_record,
    classify_source_adapter,
    classify_source_field,
    first_present,
    normalise_json_array,
    normalise_edsm_body_ring_snapshot_records,
    normalise_edsm_body_snapshot_record,
    normalise_source_adapter,
    normalise_source_file_metadata,
    normalise_source_run_metadata,
    read_float,
    read_int,
    read_text,
    source_record_hash,
    validate_staging_record,
)


ADAPTER_NAME = 'enrichment_snapshot_loader'
SUPPORTED_SOURCES = {'edsm_nightly_stations', 'edsm_nightly_bodies'}
DEFAULT_CHUNK_SIZE = 64 * 1024


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build an offline enrichment staging dry-run report from a local snapshot file.',
    )
    parser.add_argument('--source-file', required=True, help='Local .json or .json.gz file to inspect.')
    parser.add_argument(
        '--source',
        required=True,
        help='Offline source adapter, e.g. edsm_nightly_stations or edsm_nightly_bodies.',
    )
    parser.add_argument('--limit', type=int, default=None, help='Maximum records to read from the local file.')
    parser.add_argument('--json', action='store_true', help='Emit JSON. Accepted for compatibility; output is always JSON.')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Dry-run mode. This is the only supported mode.')
    parser.add_argument('--apply', action='store_true', help='Unsupported. Apply/write mode is intentionally absent.')
    parser.add_argument('--write', action='store_true', help='Unsupported. Apply/write mode is intentionally absent.')
    parser.add_argument('--commit', action='store_true', help='Unsupported. Apply/write mode is intentionally absent.')
    args = parser.parse_args(argv)
    if args.apply or args.write or args.commit:
        parser.error('apply/write mode is intentionally not implemented for enrichment snapshot loading')
    if args.limit is not None and args.limit < 0:
        parser.error('--limit must be >= 0')
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_snapshot_load_report(
            source_file=Path(args.source_file),
            source=args.source,
            limit=args.limit,
        )
    except (OSError, ValueError) as exc:
        print(f'enrichment snapshot loader failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def build_snapshot_load_report(*, source_file: Path, source: str, limit: int | None = None) -> dict[str, Any]:
    """Build a deterministic dry-run report for a local offline source file."""
    normalised_source = normalise_source_adapter(source)
    if normalised_source not in SUPPORTED_SOURCES:
        raise ValueError(f'unsupported offline source {source!r}; supported sources: {sorted(SUPPORTED_SOURCES)}')
    if normalised_source == 'edsm_nightly_bodies':
        return build_body_ring_snapshot_load_report(
            source_file=source_file,
            source=normalised_source,
            limit=limit,
        )

    _assert_local_file(source_file)

    file_sha256, file_size_bytes = file_digest(source_file)
    source_file_summary = normalise_source_file_metadata(
        source=normalised_source,
        source_file=source_file,
        file_sha256=file_sha256,
        file_size_bytes=file_size_bytes,
    )
    source_run = normalise_source_run_metadata(
        source=normalised_source,
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        source_file_keys=[source_file_summary['source_file_key']],
        dry_run=True,
        metadata={'supported_adapter': 'edsm_station_snapshot'},
    )

    raw_records: list[dict[str, Any]] = []
    staged_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    records_seen = 0
    for record_index, record in enumerate(iter_json_records(source_file), start=1):
        if limit is not None and records_seen >= limit:
            break
        records_seen += 1
        if not isinstance(record, Mapping):
            skip = {
                'record_index': record_index,
                'reason': 'record_is_not_object',
                'raw_payload': record,
            }
            skipped_rows.append(skip)
            continue

        raw_record = build_raw_record(
            source=normalised_source,
            source_run=source_run,
            source_file=source_file_summary,
            record_index=record_index,
            payload=record,
            source_updated_at=source_updated_at_from_record(record),
        )
        raw_records.append(raw_record)
        row = normalise_edsm_station_snapshot_record(
            record,
            source=normalised_source,
            raw_record=raw_record,
        )
        validation = validate_staging_record(row, required_fields=('system_name', 'station_name'))
        row_warnings = list(validation['warnings'])
        if row.get('market_id') is None and row.get('edsm_station_id') is None:
            row_warnings.append({
                'field': 'market_id',
                'reason': 'missing_station_source_identity',
            })
        if not validation['valid']:
            raw_record['validation_status'] = 'skipped'
            raw_record['validation_warnings'] = row_warnings
            skipped_rows.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                'reason': 'invalid_station_snapshot_record',
                'warnings': row_warnings,
                'raw_payload': dict(record),
            })
            continue
        row['validation_warnings'] = row_warnings
        staged_rows.append(row)
        for warning in row_warnings:
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **warning,
            })

    return build_enrichment_snapshot_load_plan(
        source_run=source_run,
        source_file=source_file_summary,
        raw_records=raw_records,
        staged_rows=staged_rows,
        skipped_rows=skipped_rows,
        warnings=warnings,
        summary_extra={
            'source': normalised_source,
            'adapter_name': ADAPTER_NAME,
            'records_seen': records_seen,
            'staged_edsm_stations': len(staged_rows),
            'dry_run_only': True,
            'canonical_writes_planned': 0,
            'distance_to_arrival_classification': classify_source_field(normalised_source, 'distanceToArrival'),
        },
    )


def build_body_ring_snapshot_load_report(
    *,
    source_file: Path,
    source: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build a deterministic dry-run report for offline EDSM body/ring data."""
    normalised_source = normalise_source_adapter(source)
    if normalised_source != 'edsm_nightly_bodies':
        raise ValueError('body/ring snapshot loading requires source edsm_nightly_bodies')
    _assert_local_file(source_file)

    file_sha256, file_size_bytes = file_digest(source_file)
    source_file_summary = normalise_source_file_metadata(
        source=normalised_source,
        source_file=source_file,
        file_sha256=file_sha256,
        file_size_bytes=file_size_bytes,
    )
    source_run = normalise_source_run_metadata(
        source=normalised_source,
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        source_file_keys=[source_file_summary['source_file_key']],
        dry_run=True,
        metadata={'supported_adapter': 'edsm_body_ring_snapshot'},
    )

    raw_records: list[dict[str, Any]] = []
    body_rows: list[dict[str, Any]] = []
    ring_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    records_seen = 0
    for record_index, record in enumerate(iter_json_records(source_file), start=1):
        if limit is not None and records_seen >= limit:
            break
        records_seen += 1
        if not isinstance(record, Mapping):
            skipped_rows.append({
                'record_index': record_index,
                'reason': 'record_is_not_object',
                'raw_payload': record,
            })
            continue

        raw_record = build_raw_record(
            source=normalised_source,
            source_run=source_run,
            source_file=source_file_summary,
            record_index=record_index,
            payload=record,
            source_updated_at=source_updated_at_from_record(record),
        )
        raw_records.append(raw_record)
        body_row = normalise_edsm_body_snapshot_record(
            record,
            source=normalised_source,
            raw_record=raw_record,
        )
        validation = validate_staging_record(body_row, required_fields=('system_name', 'body_name'))
        row_warnings = list(validation['warnings'])
        if body_row.get('source_body_id') is None:
            row_warnings.append({
                'field': 'source_body_id',
                'reason': 'missing_body_source_identity',
            })
        if not validation['valid']:
            raw_record['validation_status'] = 'skipped'
            raw_record['validation_warnings'] = row_warnings
            skipped_rows.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                'reason': 'invalid_body_snapshot_record',
                'warnings': row_warnings,
                'raw_payload': dict(record),
            })
            continue

        body_row['validation_warnings'] = row_warnings
        body_rows.append(body_row)
        for warning in row_warnings:
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **warning,
            })

        for ring_row in normalise_edsm_body_ring_snapshot_records(
            record,
            source=normalised_source,
            body_row=body_row,
            raw_record=raw_record,
        ):
            if not ring_row.get('ring_name'):
                warnings.append({
                    'record_index': record_index,
                    'source_record_hash': ring_row['source_record_hash'],
                    'field': 'ring_name',
                    'reason': 'missing_ring_identity',
                })
                continue
            ring_rows.append(ring_row)

    report = build_enrichment_snapshot_load_plan(
        source_run=source_run,
        source_file=source_file_summary,
        raw_records=raw_records,
        staged_rows=body_rows,
        planned_rows=ring_rows,
        skipped_rows=skipped_rows,
        warnings=warnings,
        summary_extra={
            'source': normalised_source,
            'adapter_name': ADAPTER_NAME,
            'records_seen': records_seen,
            'staged_edsm_bodies': len(body_rows),
            'staged_body_rings': len(ring_rows),
            'dry_run_only': True,
            'canonical_writes_planned': 0,
            'distance_to_arrival_classification': classify_source_field(normalised_source, 'distanceToArrival'),
        },
    )
    report['staged_body_rows'] = report['staged_rows']
    report['staged_ring_rows'] = report['planned_rows']
    return report


def normalise_edsm_station_snapshot_record(
    record: Mapping[str, Any],
    *,
    source: str,
    raw_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalise one local EDSM station snapshot-style record into staging shape."""
    source_hash = (
        str(raw_record.get('source_record_hash'))
        if raw_record and raw_record.get('source_record_hash') is not None
        else source_record_hash(source, record)
    )
    source_updated_at = source_updated_at_from_record(record)
    controlling_faction = first_present(record, 'controllingFaction', 'controlling_faction', 'faction')
    if isinstance(controlling_faction, Mapping):
        controlling_faction = first_present(controlling_faction, 'name', 'factionName', 'faction_name')

    economies = first_present(record, 'economies', 'stationEconomies', 'station_economies')
    if economies is None:
        economies = [
            value
            for value in (
                first_present(record, 'economy', 'primaryEconomy', 'primary_economy'),
                first_present(record, 'secondEconomy', 'secondaryEconomy', 'secondary_economy'),
            )
            if value is not None
        ]

    row = {
        'source_run_key': raw_record.get('source_run_key') if raw_record else None,
        'source_file_key': raw_record.get('source_file_key') if raw_record else None,
        'source_record_key': raw_record.get('source_record_key') if raw_record else None,
        'source_record_hash': source_hash,
        'system_id64': read_int(first_present(record, 'systemId64', 'system_id64', 'systemAddress', 'id64')),
        'system_name': read_text(first_present(record, 'systemName', 'system_name', 'system')),
        'market_id': read_int(first_present(record, 'marketId', 'market_id', 'marketID')),
        'edsm_station_id': read_int(first_present(record, 'id', 'edsmStationId', 'edsm_station_id')),
        'station_name': read_text(first_present(record, 'name', 'stationName', 'station_name')),
        'station_type': read_text(first_present(record, 'type', 'stationType', 'station_type')),
        'distance_to_arrival': read_float(first_present(
            record,
            'distanceToArrival',
            'distance_to_arrival',
            'distanceFromStar',
            'distance_from_star',
        )),
        'body_name': read_text(first_present(record, 'bodyName', 'body_name')),
        'services': normalise_json_array(first_present(record, 'services', 'otherServices', 'stationServices')),
        'economies': normalise_json_array(economies),
        'controlling_faction': read_text(controlling_faction),
        'allegiance': read_text(first_present(record, 'allegiance', 'stationAllegiance')),
        'government': read_text(first_present(record, 'government', 'stationGovernment')),
        'source_class': classify_source_adapter(source),
        'confidence': 'source_station_snapshot',
        'freshness_class': 'source_updated_at' if source_updated_at else 'file_snapshot',
        'source_updated_at': source_updated_at,
        'raw_payload': dict(record),
        'provenance': {
            'source': normalise_source_adapter(source),
            'distance_to_arrival_classification': classify_source_field(source, 'distanceToArrival'),
            'canonical_write_allowed': False,
        },
    }
    return row


def iter_json_records(source_file: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[Any]:
    """Yield records from a local JSON array, NDJSON file, or small object wrapper."""
    decoder = json.JSONDecoder()
    with _open_text(source_file) as handle:
        buffer = ''
        eof = False
        mode: str | None = None
        while True:
            if not eof and (mode is None or not buffer.strip()):
                chunk = handle.read(chunk_size)
                if chunk:
                    buffer += chunk
                else:
                    eof = True

            if mode is None:
                buffer = buffer.lstrip()
                if not buffer:
                    if eof:
                        return
                    continue
                if buffer.startswith('['):
                    mode = 'array'
                    buffer = buffer[1:]
                else:
                    mode = 'lines'

            if mode == 'array':
                buffer = buffer.lstrip()
                if buffer.startswith(','):
                    buffer = buffer[1:]
                    continue
                if buffer.startswith(']'):
                    return
                if not buffer and eof:
                    raise ValueError(f'{source_file} ended before JSON array closed')
                try:
                    value, end_index = decoder.raw_decode(buffer)
                except json.JSONDecodeError as exc:
                    if eof:
                        raise ValueError(f'invalid JSON array in {source_file}: {exc}') from exc
                    chunk = handle.read(chunk_size)
                    if chunk:
                        buffer += chunk
                    else:
                        eof = True
                    continue
                yield from _records_from_json_value(value)
                buffer = buffer[end_index:]
                continue

            if mode == 'lines':
                newline = buffer.find('\n')
                if newline == -1:
                    if eof:
                        line = buffer.strip()
                        if line:
                            yield from _records_from_json_value(json.loads(line))
                        return
                    chunk = handle.read(chunk_size)
                    if chunk:
                        buffer += chunk
                    else:
                        eof = True
                    continue
                line = buffer[:newline].strip()
                buffer = buffer[newline + 1:]
                if line:
                    yield from _records_from_json_value(json.loads(line))


def source_updated_at_from_record(record: Mapping[str, Any]) -> str | None:
    return read_text(first_present(
        record,
        'updatedAt',
        'updated_at',
        'updateTime',
        'lastUpdate',
        'lastUpdated',
        'date',
    ))


def file_digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(DEFAULT_CHUNK_SIZE), b''):
            size += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), size


def _records_from_json_value(value: Any) -> Iterator[Any]:
    if isinstance(value, Mapping) and isinstance(value.get('stations'), list):
        system_context = {
            key: item
            for key, item in value.items()
            if key != 'stations'
        }
        for station in value['stations']:
            if isinstance(station, Mapping):
                merged = dict(system_context)
                merged.update(station)
                yield merged
            else:
                yield station
        return
    yield value


def _assert_local_file(path: Path) -> None:
    parsed = urlparse(str(path))
    if parsed.scheme and parsed.scheme not in {'', 'file'}:
        raise ValueError('source file must be a local path, not a URL')
    if not path.exists():
        raise ValueError(f'source file does not exist: {path}')
    if not path.is_file():
        raise ValueError(f'source file is not a regular file: {path}')


def _open_text(path: Path):
    if path.name.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8')
    return path.open('rt', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
