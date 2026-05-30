#!/usr/bin/env python3
"""Read-only status helper for the guarded EDSM station enrichment.

Operations call this between long --all-records runs (or while a run is in
flight) to answer questions like:

    * Where is the resumable checkpoint right now?
    * How many systems have been processed across all batches so far?
    * What is the latest run output directory?
    * What is the latest batch directory inside that run?
    * Was a particular system already checkpointed (so a re-run will skip it)?

The script never calls EDSM, never opens a database connection, never writes
state. It only reads files on disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import station_enrichment_guard as guard  # noqa: E402


@dataclass(frozen=True)
class LatestRun:
    output_dir: Path | None
    batch_dir: Path | None
    latest_report: Path | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Inspect guarded station enrichment progress (read-only).',
    )
    parser.add_argument(
        '--checkpoint-file',
        default=None,
        help=(
            'Checkpoint JSON to inspect. Defaults to the stable all-records '
            'checkpoint used by station_enrichment_guard.py --all-records.'
        ),
    )
    parser.add_argument(
        '--output-root',
        default=None,
        help=(
            'Root directory where the guard writes per-run output dirs. '
            f'Defaults to {guard.DEFAULT_OUTPUT_ROOT}.'
        ),
    )
    parser.add_argument(
        '--system-id64',
        type=int,
        default=None,
        help='Optional system id64 to test against the checkpoint.',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Emit machine-readable JSON instead of a human summary.',
    )
    return parser.parse_args(argv)


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            'path': str(path),
            'exists': False,
            'processed_count': 0,
            'last_system_id64': None,
            'processed_system_id64s': [],
        }
    raw = path.read_text(encoding='utf-8')
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            'path': str(path),
            'exists': True,
            'error': f'invalid JSON: {exc}',
            'processed_count': 0,
            'last_system_id64': None,
            'processed_system_id64s': [],
        }
    if not isinstance(payload, Mapping):
        return {
            'path': str(path),
            'exists': True,
            'error': 'checkpoint payload is not an object',
            'processed_count': 0,
            'last_system_id64': None,
            'processed_system_id64s': [],
        }
    processed = [int(value) for value in payload.get('processed_system_id64s', []) if _coerce_int(value) is not None]
    return {
        'path': str(path),
        'exists': True,
        'processed_count': len(processed),
        'last_system_id64': _coerce_int(payload.get('last_system_id64')),
        'processed_system_id64s': processed,
    }


def find_latest_run(output_root: Path) -> LatestRun:
    if not output_root.exists():
        return LatestRun(None, None, None)
    candidates = [child for child in output_root.iterdir() if child.is_dir()]
    if not candidates:
        return LatestRun(None, None, None)
    latest_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    batch_dirs = sorted(
        (child for child in latest_dir.iterdir() if child.is_dir() and child.name.startswith('batch-')),
        key=lambda path: path.name,
    )
    latest_batch = batch_dirs[-1] if batch_dirs else None
    candidate_dir = latest_batch or latest_dir
    json_reports = sorted(candidate_dir.glob('*.json'), key=lambda path: path.stat().st_mtime)
    latest_report = json_reports[-1] if json_reports else None
    return LatestRun(latest_dir, latest_batch, latest_report)


def report_summary(report_path: Path | None) -> dict[str, Any] | None:
    if report_path is None or not report_path.exists():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'path': str(report_path), 'error': 'unreadable JSON'}
    if not isinstance(payload, Mapping):
        return {'path': str(report_path), 'error': 'report is not an object'}
    summary = guard.compact_summary(payload, report_path)
    return {
        'path': str(report_path),
        'systems_processed': summary.systems_processed,
        'metadata_updates': summary.metadata_updates,
        'confirmed_links': summary.confirmed_links,
        'conflicts': summary.conflicts,
        'skipped': summary.skipped,
        'fetch_errors': summary.fetch_errors,
        'systems_fetch_failed': summary.systems_fetch_failed,
        'suppressed_station_writes': summary.suppressed_station_writes,
        'ignored_transient_non_slot': summary.ignored_transient_non_slot,
        'dirty_systems_planned': summary.dirty_systems_planned,
        'dirty_systems_marked': summary.dirty_systems_marked,
    }


def build_status(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = Path(args.checkpoint_file).expanduser() if args.checkpoint_file else guard.DEFAULT_ALL_RECORDS_CHECKPOINT
    output_root = Path(args.output_root).expanduser() if args.output_root else guard.DEFAULT_OUTPUT_ROOT
    checkpoint = load_checkpoint(checkpoint_path)
    latest = find_latest_run(output_root)

    requested = _coerce_int(args.system_id64)
    requested_known = (
        requested is not None
        and requested in set(checkpoint['processed_system_id64s'])
    )

    return {
        'checkpoint': checkpoint,
        'output_root': str(output_root),
        'latest_run': {
            'output_dir': str(latest.output_dir) if latest.output_dir else None,
            'batch_dir': str(latest.batch_dir) if latest.batch_dir else None,
            'latest_report': str(latest.latest_report) if latest.latest_report else None,
        },
        'latest_report_summary': report_summary(latest.latest_report),
        'system_query': {
            'system_id64': requested,
            'is_checkpointed': requested_known,
        } if requested is not None else None,
    }


def render_human(status: Mapping[str, Any]) -> str:
    lines: list[str] = []
    checkpoint = status['checkpoint']
    lines.append(f"Checkpoint file: {checkpoint['path']}")
    if not checkpoint['exists']:
        lines.append('  (no checkpoint yet — first --all-records run will create it)')
    elif checkpoint.get('error'):
        lines.append(f"  ERROR: {checkpoint['error']}")
    else:
        lines.append(f"  processed_count: {checkpoint['processed_count']}")
        last = checkpoint['last_system_id64']
        if last is not None:
            lines.append(f"  last_system_id64: {last}")
    lines.append(f"Output root:     {status['output_root']}")
    latest = status['latest_run']
    lines.append(f"Latest run dir:  {latest['output_dir'] or '(none)'}")
    lines.append(f"Latest batch:    {latest['batch_dir'] or '(no batches yet)'}")
    lines.append(f"Latest report:   {latest['latest_report'] or '(none)'}")
    summary = status.get('latest_report_summary')
    if summary:
        if summary.get('error'):
            lines.append(f"  report error: {summary['error']}")
        else:
            lines.append('  latest report summary:')
            for key in (
                'systems_processed',
                'metadata_updates',
                'confirmed_links',
                'conflicts',
                'skipped',
                'fetch_errors',
                'systems_fetch_failed',
                'suppressed_station_writes',
                'ignored_transient_non_slot',
                'dirty_systems_planned',
                'dirty_systems_marked',
            ):
                lines.append(f"    {key}={summary[key]}")
    if status.get('system_query') is not None:
        query = status['system_query']
        verdict = 'YES (will be skipped on resume)' if query['is_checkpointed'] else 'no (will be retried on resume)'
        lines.append(f"system_id64 {query['system_id64']} checkpointed: {verdict}")
    return '\n'.join(lines)


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    status = build_status(args)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(render_human(status))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
