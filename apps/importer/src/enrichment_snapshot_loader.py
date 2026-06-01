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
from collections import Counter
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
SOURCE_FORMAT_VERSION = 'json_snapshot_stream/v1'
RING_ARRAY_UNKNOWN_STATE = 'unknown_not_false'


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
    file_format = source_file_format_metadata(source_file)
    source_file_summary = normalise_source_file_metadata(
        source=normalised_source,
        source_file=source_file,
        file_sha256=file_sha256,
        file_size_bytes=file_size_bytes,
        metadata=file_format,
    )
    source_run = normalise_source_run_metadata(
        source=normalised_source,
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        source_file_keys=[source_file_summary['source_file_key']],
        dry_run=True,
        metadata={
            'supported_adapter': 'edsm_station_snapshot',
            **file_format,
        },
    )

    raw_records: list[dict[str, Any]] = []
    staged_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

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
        unsupported_shape = unsupported_source_shape(record, normalised_source)
        if unsupported_shape is not None:
            shape_warning = {
                'field': unsupported_shape['field'],
                'reason': 'unsupported_source_shape',
                'source_shape': unsupported_shape['source_shape'],
            }
            raw_record['validation_status'] = 'skipped'
            raw_record['validation_warnings'] = [shape_warning]
            skipped_rows.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                'reason': unsupported_shape['skip_reason'],
                'warnings': [shape_warning],
                'raw_payload': dict(record),
            })
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **shape_warning,
            })
            continue
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

    conflicts = source_identity_conflicts(staged_rows, entity='station')
    source_summary = source_observability_summary(
        raw_records=raw_records,
        staged_rows=staged_rows,
        planned_rows=(),
        skipped_rows=skipped_rows,
        warnings=warnings,
        file_format=file_format,
    )
    apply_source_observability_metadata(
        source_run=source_run,
        source_file=source_file_summary,
        source_summary=source_summary,
    )

    return build_enrichment_snapshot_load_plan(
        source_run=source_run,
        source_file=source_file_summary,
        raw_records=raw_records,
        staged_rows=staged_rows,
        skipped_rows=skipped_rows,
        conflicts=conflicts,
        warnings=warnings,
        summary_extra={
            'source': normalised_source,
            'adapter_name': ADAPTER_NAME,
            'records_seen': records_seen,
            'staged_edsm_stations': len(staged_rows),
            'dry_run_only': True,
            'canonical_writes_planned': 0,
            'distance_to_arrival_classification': classify_source_field(normalised_source, 'distanceToArrival'),
            **source_summary,
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
    file_format = source_file_format_metadata(source_file)
    source_file_summary = normalise_source_file_metadata(
        source=normalised_source,
        source_file=source_file,
        file_sha256=file_sha256,
        file_size_bytes=file_size_bytes,
        metadata=file_format,
    )
    source_run = normalise_source_run_metadata(
        source=normalised_source,
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        source_file_keys=[source_file_summary['source_file_key']],
        dry_run=True,
        metadata={
            'supported_adapter': 'edsm_body_ring_snapshot',
            **file_format,
        },
    )

    raw_records: list[dict[str, Any]] = []
    body_rows: list[dict[str, Any]] = []
    ring_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    ring_array_evidence = empty_ring_array_evidence_summary()

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
        unsupported_shape = unsupported_source_shape(record, normalised_source)
        if unsupported_shape is not None:
            shape_warning = {
                'field': unsupported_shape['field'],
                'reason': 'unsupported_source_shape',
                'source_shape': unsupported_shape['source_shape'],
            }
            raw_record['validation_status'] = 'skipped'
            raw_record['validation_warnings'] = [shape_warning]
            skipped_rows.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                'reason': unsupported_shape['skip_reason'],
                'warnings': [shape_warning],
                'raw_payload': dict(record),
            })
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **shape_warning,
            })
            continue
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
        ring_state = classify_ring_array_evidence(record)
        annotate_body_ring_array_evidence(body_row, ring_state)
        update_ring_array_evidence_summary(ring_array_evidence, ring_state)
        body_rows.append(body_row)
        for warning in row_warnings:
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **warning,
            })

        if ring_state['state'] == 'non_array':
            ring_warning = {
                'field': 'rings',
                'reason': 'ring_array_not_sequence',
                'ring_array_state': 'non_array',
            }
            skipped_rows.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                'reason': 'invalid_ring_snapshot_record',
                'warnings': [ring_warning],
                'raw_payload': dict(record),
            })
            warnings.append({
                'record_index': record_index,
                'source_record_hash': raw_record['source_record_hash'],
                **ring_warning,
            })
            continue

        for ring_skip in skipped_ring_rows_for_record(record, record_index, raw_record):
            skipped_rows.append(ring_skip)

        for ring_row in normalise_edsm_body_ring_snapshot_records(
            record,
            source=normalised_source,
            body_row=body_row,
            raw_record=raw_record,
        ):
            if not ring_row.get('ring_name'):
                ring_warning = {
                    'field': 'ring_name',
                    'reason': 'missing_ring_identity',
                    'ring_index': ring_row['raw_payload']['ring_index'],
                }
                warnings.append({
                    'record_index': record_index,
                    'source_record_hash': ring_row['source_record_hash'],
                    **ring_warning,
                })
                skipped_rows.append({
                    'record_index': record_index,
                    'ring_index': ring_row['raw_payload']['ring_index'],
                    'source_record_hash': ring_row['source_record_hash'],
                    'reason': 'invalid_ring_snapshot_record',
                    'warnings': [ring_warning],
                    'raw_payload': ring_row['raw_payload'],
                })
                continue
            ring_rows.append(ring_row)

    conflicts = (
        source_identity_conflicts(body_rows, entity='body')
        + source_identity_conflicts(ring_rows, entity='ring')
    )
    source_summary = source_observability_summary(
        raw_records=raw_records,
        staged_rows=body_rows,
        planned_rows=ring_rows,
        skipped_rows=skipped_rows,
        warnings=warnings,
        file_format=file_format,
    )
    source_summary['ring_array_evidence'] = finalise_ring_array_evidence_summary(
        ring_array_evidence,
        source_only_ring_rows=len(ring_rows),
    )
    apply_source_observability_metadata(
        source_run=source_run,
        source_file=source_file_summary,
        source_summary=source_summary,
    )

    report = build_enrichment_snapshot_load_plan(
        source_run=source_run,
        source_file=source_file_summary,
        raw_records=raw_records,
        staged_rows=body_rows,
        planned_rows=ring_rows,
        skipped_rows=skipped_rows,
        conflicts=conflicts,
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
            **source_summary,
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


def source_file_format_metadata(source_file: Path) -> dict[str, Any]:
    first_char = _first_non_whitespace_char(source_file)
    if first_char == '[':
        record_stream_shape = 'json_array'
    elif first_char == '{':
        record_stream_shape = 'json_object_or_ndjson'
    elif first_char is None:
        record_stream_shape = 'empty'
    else:
        record_stream_shape = 'ndjson'
    return {
        'source_format': 'json',
        'source_format_version': SOURCE_FORMAT_VERSION,
        'record_stream_shape': record_stream_shape,
    }


def unsupported_source_shape(record: Mapping[str, Any], source: str) -> dict[str, str] | None:
    normalised_source = normalise_source_adapter(source)
    if normalised_source == 'edsm_nightly_stations':
        if isinstance(record.get('bodies'), list):
            return {
                'field': 'bodies',
                'source_shape': 'nested_body_collection',
                'skip_reason': 'unsupported_station_snapshot_source_shape',
            }
        if isinstance(record.get('systems'), list):
            return {
                'field': 'systems',
                'source_shape': 'nested_system_collection',
                'skip_reason': 'unsupported_station_snapshot_source_shape',
            }
    if normalised_source == 'edsm_nightly_bodies':
        if isinstance(record.get('stations'), list):
            return {
                'field': 'stations',
                'source_shape': 'nested_station_collection',
                'skip_reason': 'unsupported_body_snapshot_source_shape',
            }
        if isinstance(record.get('systems'), list):
            return {
                'field': 'systems',
                'source_shape': 'nested_system_collection',
                'skip_reason': 'unsupported_body_snapshot_source_shape',
            }
        if isinstance(record.get('bodies'), list):
            return {
                'field': 'bodies',
                'source_shape': 'nested_body_collection',
                'skip_reason': 'unsupported_body_snapshot_source_shape',
            }
    return None


def source_observability_summary(
    *,
    raw_records: Sequence[Mapping[str, Any]],
    staged_rows: Sequence[Mapping[str, Any]],
    planned_rows: Sequence[Mapping[str, Any]],
    skipped_rows: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
    file_format: Mapping[str, Any],
) -> dict[str, Any]:
    timestamp_summary = source_timestamp_summary(raw_records)
    staged_and_planned = list(staged_rows) + list(planned_rows)
    return {
        'source_format': file_format.get('source_format'),
        'source_format_version': file_format.get('source_format_version'),
        'record_stream_shape': file_format.get('record_stream_shape'),
        'source_timestamp_summary': timestamp_summary,
        'source_freshness_summary': {
            'freshness_distribution': field_distribution(staged_and_planned, 'freshness_class'),
            'records_with_source_updated_at': timestamp_summary['records_with_source_updated_at'],
            'records_without_source_updated_at': timestamp_summary['records_without_source_updated_at'],
            'freshness_preserves_unknown': True,
        },
        'unsupported_source_shapes': sum(
            1 for row in skipped_rows
            if str(row.get('reason', '')).startswith('unsupported_')
        ),
        'malformed_rows': sum(
            1 for row in skipped_rows
            if row.get('reason') in {
                'record_is_not_object',
                'invalid_station_snapshot_record',
                'invalid_body_snapshot_record',
                'invalid_ring_snapshot_record',
                'ring_record_is_not_object',
            }
        ),
        'warning_reason_distribution': field_distribution(warnings, 'reason'),
        'skipped_row_reason_distribution': field_distribution(skipped_rows, 'reason'),
    }


def apply_source_observability_metadata(
    *,
    source_run: dict[str, Any],
    source_file: dict[str, Any],
    source_summary: Mapping[str, Any],
) -> None:
    timestamp_summary = dict(source_summary.get('source_timestamp_summary') or {})
    latest_source_updated_at = timestamp_summary.get('latest_source_updated_at')
    if latest_source_updated_at is not None:
        source_file['source_updated_at'] = latest_source_updated_at
    source_file.setdefault('metadata', {}).update({
        'source_format': source_summary.get('source_format'),
        'source_format_version': source_summary.get('source_format_version'),
        'record_stream_shape': source_summary.get('record_stream_shape'),
        'source_timestamp_summary': timestamp_summary,
    })
    source_run.setdefault('metadata', {}).update({
        'source_format': source_summary.get('source_format'),
        'source_format_version': source_summary.get('source_format_version'),
        'record_stream_shape': source_summary.get('record_stream_shape'),
        'source_timestamp_summary': timestamp_summary,
        'source_freshness_summary': source_summary.get('source_freshness_summary'),
    })


def source_timestamp_summary(raw_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    timestamps = sorted({
        str(row.get('source_updated_at'))
        for row in raw_records
        if row.get('source_updated_at') is not None
    })
    records_with_timestamp = sum(1 for row in raw_records if row.get('source_updated_at') is not None)
    records_without_timestamp = len(raw_records) - records_with_timestamp
    return {
        'records_with_source_updated_at': records_with_timestamp,
        'records_without_source_updated_at': records_without_timestamp,
        'unique_source_updated_at_values': len(timestamps),
        'earliest_source_updated_at': timestamps[0] if timestamps else None,
        'latest_source_updated_at': timestamps[-1] if timestamps else None,
    }


def classify_ring_array_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    if 'rings' in record:
        field_name = 'rings'
    elif 'Rings' in record:
        field_name = 'Rings'
    else:
        return {
            'field': None,
            'state': 'missing',
            'ring_count': None,
            'meaning': RING_ARRAY_UNKNOWN_STATE,
        }
    rings = record.get(field_name)
    if not isinstance(rings, Sequence) or isinstance(rings, (str, bytes, bytearray)):
        return {
            'field': field_name,
            'state': 'non_array',
            'ring_count': None,
            'meaning': 'malformed_source_ring_array',
        }
    if len(rings) == 0:
        return {
            'field': field_name,
            'state': 'empty',
            'ring_count': 0,
            'meaning': 'explicit_empty_source_array_report_only',
        }
    return {
        'field': field_name,
        'state': 'present',
        'ring_count': len(rings),
        'meaning': 'source_only_ring_evidence',
    }


def annotate_body_ring_array_evidence(body_row: dict[str, Any], ring_state: Mapping[str, Any]) -> None:
    body_row['provenance'] = dict(body_row.get('provenance') or {})
    body_row['provenance']['ring_array_state'] = ring_state.get('state')
    body_row['provenance']['ring_array_meaning'] = ring_state.get('meaning')
    body_row['provenance']['missing_ring_arrays_state'] = RING_ARRAY_UNKNOWN_STATE


def empty_ring_array_evidence_summary() -> dict[str, int]:
    return {
        'body_rows_considered': 0,
        'ring_arrays_present': 0,
        'ring_arrays_empty': 0,
        'ring_arrays_missing': 0,
        'ring_arrays_non_array': 0,
    }


def update_ring_array_evidence_summary(summary: dict[str, int], ring_state: Mapping[str, Any]) -> None:
    summary['body_rows_considered'] += 1
    state = ring_state.get('state')
    if state == 'present':
        summary['ring_arrays_present'] += 1
    elif state == 'empty':
        summary['ring_arrays_empty'] += 1
    elif state == 'missing':
        summary['ring_arrays_missing'] += 1
    elif state == 'non_array':
        summary['ring_arrays_non_array'] += 1


def finalise_ring_array_evidence_summary(
    summary: Mapping[str, int],
    *,
    source_only_ring_rows: int,
) -> dict[str, Any]:
    return {
        **dict(summary),
        'source_only_ring_rows': source_only_ring_rows,
        'missing_ring_arrays_state': RING_ARRAY_UNKNOWN_STATE,
        'empty_ring_arrays_state': 'source_evidence_only_not_canonical_no_rings',
        'source_only_ring_evidence_state': 'source_only_not_confirmed_truth',
        'ringed_truth_requires_trusted_body_rings': True,
    }


def skipped_ring_rows_for_record(
    record: Mapping[str, Any],
    record_index: int,
    raw_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if 'rings' in record:
        rings = record.get('rings')
    elif 'Rings' in record:
        rings = record.get('Rings')
    else:
        return []
    if not isinstance(rings, Sequence) or isinstance(rings, (str, bytes, bytearray)):
        return []
    skipped = []
    for ring_index, ring in enumerate(rings):
        if isinstance(ring, Mapping):
            continue
        skipped.append({
            'record_index': record_index,
            'ring_index': ring_index,
            'source_record_hash': raw_record.get('source_record_hash'),
            'reason': 'ring_record_is_not_object',
            'warnings': [{'field': 'rings', 'reason': 'ring_record_is_not_object'}],
            'raw_payload': ring,
        })
    return skipped


def source_identity_conflicts(rows: Sequence[Mapping[str, Any]], *, entity: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        identity_key = source_identity_key(row, entity=entity)
        if identity_key is None:
            continue
        grouped.setdefault(identity_key, []).append(row)

    conflicts = []
    for identity_key, group in grouped.items():
        hashes = sorted({
            str(row.get('source_record_hash'))
            for row in group
            if row.get('source_record_hash') is not None
        })
        if len(hashes) < 2:
            continue
        conflicts.append({
            'entity': entity,
            'reason': 'duplicate_source_identity_conflict',
            'source_identity_key': identity_key,
            'source_record_hashes': hashes,
            'source_record_keys': sorted(
                str(row.get('source_record_key'))
                for row in group
                if row.get('source_record_key') is not None
            ),
            'handling': 'report_only_conflict_no_canonical_write',
        })
    return sorted(conflicts, key=lambda row: json.dumps(row, sort_keys=True, separators=(',', ':')))


def source_identity_key(row: Mapping[str, Any], *, entity: str) -> str | None:
    system_key = identity_part(row, 'system_id64', 'system_name')
    if system_key is None:
        return None
    if entity == 'station':
        entity_key = identity_part(row, 'market_id', 'edsm_station_id', 'station_name')
    elif entity == 'body':
        entity_key = identity_part(row, 'source_body_id', 'body_name')
    else:
        body_key = identity_part(row, 'source_body_id', 'body_name')
        ring_name = read_text(row.get('ring_name'))
        if body_key is None or ring_name is None:
            return None
        entity_key = f'{body_key}|ring:{ring_name.lower()}'
    if entity_key is None:
        return None
    return f'{entity}|{system_key}|{entity_key}'


def identity_part(row: Mapping[str, Any], *fields: str) -> str | None:
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return f'{field}:{text.lower()}'
            continue
        return f'{field}:{value}'
    return None


def field_distribution(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    return dict(sorted(Counter(
        str(row.get(field_name))
        for row in rows
        if row.get(field_name) is not None
    ).items()))


def _first_non_whitespace_char(source_file: Path) -> str | None:
    with _open_text(source_file) as handle:
        while True:
            chunk = handle.read(1024)
            if not chunk:
                return None
            stripped = chunk.lstrip()
            if stripped:
                return stripped[0]


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
