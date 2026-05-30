#!/usr/bin/env python3
"""Read-only status helper for the guarded EDSM station enrichment.

This script is intentionally file-only. It never calls EDSM, never opens a
database connection, never invokes Docker, and never writes state. It inspects
the stable all-records checkpoint, guard output directories, JSON reports,
stderr captures, and an optional operator log file.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import station_enrichment_guard as guard  # noqa: E402


DEFAULT_TAIL_LINES = 80
RATE_LIMIT_WARNING_THRESHOLD = 3

PROGRESS_COUNTER_RE = re.compile(r'\bStation enrichment progress\s+(?P<current>\d+)/(?P<total>\d+)\b')
PROGRESS_SYSTEM_RE = re.compile(
    r'\bStation enrichment\s+(?P<current>\d+)/(?P<total>\d+):\s+'
    r'system=(?P<system>\'[^\'\n]*\'|"[^"\n]*"|[^\s]+)'
    r'(?:\s+id64=(?P<id64>-?\d+))?'
)
FETCHING_SYSTEM_RE = re.compile(
    r'\b(?:Fetching|Skipping) EDSM station enrichment\s+'
    r'system=(?P<system>\'[^\'\n]*\'|"[^"\n]*"|[^\s]+)'
    r'(?:\s+id64=(?P<id64>-?\d+))?'
)
SYSTEM_VALUE_RE = re.compile(r'\bsystem=(?P<system>\'[^\'\n]*\'|"[^"\n]*"|[^\s]+)')
ID64_RE = re.compile(r'\bid64=(?P<id64>-?\d+)\b')
FETCH_ERRORS_RE = re.compile(r'\bfetch_errors=(?P<count>\d+)\b')
SYSTEMS_FETCH_FAILED_RE = re.compile(r'\bsystems_fetch_failed=(?P<count>\d+)\b')
FETCH_FAILED_RE = re.compile(r'\bfetch_failed=(?P<count>\d+)\b')
BACKOFF_RE = re.compile(r'\bbackoff_seconds=(?P<seconds>-?\d+(?:\.\d+)?)\b')
RETRY_AFTER_RE = re.compile(r'\bretry_after=(?P<value>\'[^\'\n]*\'|"[^"\n]*"|[^\s]+)')
RETRY_AFTER_HEADER_RE = re.compile(r'\bRetry-After[=: ]+(?P<value>-?\d+(?:\.\d+)?)\b', re.IGNORECASE)
BATCH_DIR_RE = re.compile(r'^batch-(?P<number>\d+)$')
BATCH_HEADER_RE = re.compile(r'=== all-records batch (?P<number>\d+) ===')
BATCH_CHECKPOINT_RE = re.compile(
    r'all-records batch (?P<number>\d+):\s+'
    r'checkpoint_added=(?P<added>\d+)\s+'
    r'checkpoint_total=(?P<total>\d+)\s+'
    r'fetch_failed_this_batch=(?P<failed>\d+)'
)
BATCH_SKIP_FAILED_RE = re.compile(
    r'all-records batch (?P<number>\d+): skipping checkpoint append for systems_fetch_failed=(?P<count>\d+)'
)
GUARD_429_WARNING_RE = re.compile(r'\[guard\] EDSM 429 observed (?P<count>\d+) times')


@dataclass(frozen=True)
class LatestRun:
    output_root: Path
    output_dir: Path | None
    latest_all_records_output_dir: Path | None
    latest_any_output_dir: Path | None
    batch_dir: Path | None
    batch_number: int | None
    latest_report: Path | None
    latest_stderr: Path | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Inspect guarded station enrichment progress from local files only.',
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
        '--root',
        '--output-root',
        dest='root',
        default=None,
        help=(
            'Root directory where the guard writes per-run output dirs. '
            f'Defaults to {guard.DEFAULT_OUTPUT_ROOT}.'
        ),
    )
    parser.add_argument(
        '--log-file',
        default=None,
        help='Optional explicit guard/operator log file to tail for progress and rate-limit lines.',
    )
    parser.add_argument(
        '--tail-lines',
        type=int,
        default=DEFAULT_TAIL_LINES,
        help=f'Number of recent stderr/log lines to inspect. Default: {DEFAULT_TAIL_LINES}.',
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
        help='Emit machine-readable JSON instead of the human dashboard.',
    )
    return parser.parse_args(argv)


def load_checkpoint(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        'path': str(path),
        'exists': False,
        'valid': False,
        'error': None,
        'processed_count': 0,
        'last_system_id64': None,
        'processed_system_id64s': [],
        'invalid_entry_count': 0,
    }
    if not path.exists():
        return result

    result['exists'] = True
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError as exc:
        result['error'] = f'unreadable checkpoint: {exc}'
        return result
    if not raw.strip():
        result['error'] = 'checkpoint file is empty'
        return result
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        result['error'] = f'invalid JSON: {exc}'
        return result
    if not isinstance(payload, Mapping):
        result['error'] = 'checkpoint payload is not an object'
        return result

    processed_values = payload.get('processed_system_id64s', [])
    if not isinstance(processed_values, list):
        result['error'] = 'processed_system_id64s is not a list'
        return result

    processed: list[int] = []
    invalid_entries = 0
    for value in processed_values:
        id64 = _coerce_int(value)
        if id64 is None:
            invalid_entries += 1
            continue
        processed.append(id64)

    last_system_id64 = _coerce_int(payload.get('last_system_id64'))
    if last_system_id64 is None and processed:
        last_system_id64 = max(processed)

    result.update({
        'valid': True,
        'processed_count': len(processed),
        'last_system_id64': last_system_id64,
        'processed_system_id64s': processed,
        'invalid_entry_count': invalid_entries,
    })
    return result


def find_latest_run(output_root: Path) -> LatestRun:
    if not output_root.exists():
        return LatestRun(output_root, None, None, None, None, None, None, None)

    try:
        run_dirs = [child for child in output_root.iterdir() if child.is_dir()]
    except OSError:
        return LatestRun(output_root, None, None, None, None, None, None, None)
    if not run_dirs:
        return LatestRun(output_root, None, None, None, None, None, None, None)

    latest_any = _latest_by_mtime(run_dirs)
    all_record_dirs = [child for child in run_dirs if 'all-records' in child.name]
    latest_all_records = _latest_by_mtime(all_record_dirs) if all_record_dirs else None
    output_dir = latest_all_records or latest_any

    batch_dirs = _batch_dirs(output_dir) if output_dir else []
    latest_batch = batch_dirs[-1] if batch_dirs else None
    batch_number = _batch_number(latest_batch) if latest_batch else None
    candidate_dir = latest_batch or output_dir
    latest_report = _latest_report(candidate_dir)
    latest_stderr = _latest_stderr(candidate_dir, latest_report)
    return LatestRun(
        output_root=output_root,
        output_dir=output_dir,
        latest_all_records_output_dir=latest_all_records,
        latest_any_output_dir=latest_any,
        batch_dir=latest_batch,
        batch_number=batch_number,
        latest_report=latest_report,
        latest_stderr=latest_stderr,
    )


def report_summary(report_path: Path | None) -> dict[str, Any] | None:
    if report_path is None:
        return None
    base = {
        'path': str(report_path),
        'file_name': report_path.name,
        'phase_name': _phase_name(report_path),
        'exists': report_path.exists(),
        'valid': False,
        'error': None,
    }
    if not report_path.exists():
        base['error'] = 'report file is missing'
        return base
    try:
        payload = json.loads(report_path.read_text(encoding='utf-8'))
    except OSError as exc:
        base['error'] = f'unreadable report: {exc}'
        return base
    except json.JSONDecodeError as exc:
        base['error'] = f'invalid JSON: {exc}'
        return base
    if not isinstance(payload, Mapping):
        base['error'] = 'report is not an object'
        return base

    summary = guard.compact_summary(payload, report_path)
    touched_ids = guard.report_system_id64s(payload)
    successful_ids = guard.successful_system_id64s(payload)
    base.update({
        'valid': True,
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
        'dirty_marked_planned': f'{summary.dirty_systems_marked}/{summary.dirty_systems_planned}',
        'touched_system_ids_count': len(touched_ids),
        'successful_system_ids_count': len(successful_ids),
        'successful_system_id64s': sorted(successful_ids),
    })
    return base


def build_status(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = (
        Path(args.checkpoint_file).expanduser()
        if args.checkpoint_file
        else guard.DEFAULT_ALL_RECORDS_CHECKPOINT
    )
    root_value = getattr(args, 'root', None) or getattr(args, 'output_root', None)
    output_root = Path(root_value).expanduser() if root_value else guard.DEFAULT_OUTPUT_ROOT
    tail_lines = max(0, int(getattr(args, 'tail_lines', DEFAULT_TAIL_LINES)))

    checkpoint = load_checkpoint(checkpoint_path)
    latest = find_latest_run(output_root)
    latest_report = report_summary(latest.latest_report)
    log_file = discover_log_file(
        explicit=Path(args.log_file).expanduser() if getattr(args, 'log_file', None) else None,
        output_root=output_root,
        latest_run_dir=latest.output_dir,
    )
    progress_sources = _progress_sources(log_file, latest.latest_stderr)
    progress_lines = _read_progress_lines(progress_sources, tail_lines)
    latest_progress = parse_recent_progress(progress_lines, tail_lines=tail_lines, source_files=progress_sources)
    latest_batch = build_latest_batch(latest, latest_report, latest_progress, checkpoint)
    system_query = build_system_query(args.system_id64, checkpoint)

    status: dict[str, Any] = {
        'checkpoint': checkpoint,
        'latest_run': {
            'output_root': str(output_root),
            'output_root_exists': output_root.exists(),
            'latest_all_records_output_dir': (
                str(latest.latest_all_records_output_dir) if latest.latest_all_records_output_dir else None
            ),
            'latest_any_output_dir': str(latest.latest_any_output_dir) if latest.latest_any_output_dir else None,
            'output_dir': str(latest.output_dir) if latest.output_dir else None,
            'latest_log_file': str(log_file) if log_file else None,
            'latest_log_file_exists': bool(log_file and log_file.exists()),
        },
        'latest_batch': latest_batch,
        'latest_report_summary': latest_report,
        'latest_progress': latest_progress,
        'rate_limit_summary': latest_progress['rate_limit_summary'],
        'warnings': [],
        'system_query': system_query,
    }
    status['warnings'] = build_warnings(status)
    return status


def build_latest_batch(
    latest: LatestRun,
    latest_report: Mapping[str, Any] | None,
    latest_progress: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    report_path = latest.latest_report
    checkpoint_updates = latest_progress.get('batch_checkpoint_updates') or []
    latest_update = _checkpoint_update_for_batch(checkpoint_updates, latest.batch_number)
    state = infer_batch_state(
        latest.batch_number,
        latest_report,
        latest_progress,
        latest_update,
        checkpoint,
    )
    return {
        'path': str(latest.batch_dir) if latest.batch_dir else None,
        'number': latest.batch_number,
        'latest_report': str(report_path) if report_path else None,
        'latest_stderr': str(latest.latest_stderr) if latest.latest_stderr else None,
        'latest_phase_name': latest_report.get('phase_name') if latest_report else None,
        'checkpoint_update': latest_update,
        'state': state,
    }


def infer_batch_state(
    batch_number: int | None,
    latest_report: Mapping[str, Any] | None,
    latest_progress: Mapping[str, Any],
    checkpoint_update: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any],
) -> str:
    if batch_number is None:
        return 'no_batch'
    if latest_progress.get('all_records_aborted'):
        return 'failed'
    if checkpoint_update:
        if _coerce_int(checkpoint_update.get('added')) == 0 and _coerce_int(checkpoint_update.get('failed')) not in (None, 0):
            return 'failed'
        return 'completed'
    if latest_progress.get('counter'):
        counter = latest_progress['counter']
        current = _coerce_int(counter.get('current'))
        total = _coerce_int(counter.get('total'))
        if current is not None and total is not None and current < total:
            return 'in_progress'
    if _report_looks_ready_for_checkpoint(latest_report):
        successful = set(latest_report.get('successful_system_id64s') or [])
        checkpointed = set(checkpoint.get('processed_system_id64s') or [])
        if successful and not successful.issubset(checkpointed):
            return 'interrupted'
    if latest_report and latest_report.get('valid'):
        return 'unknown'
    return 'unknown'


def parse_recent_progress(
    lines: Sequence[str],
    *,
    tail_lines: int,
    source_files: Sequence[Path],
) -> dict[str, Any]:
    latest_progress_line: str | None = None
    latest_counter_line: str | None = None
    latest_system_name: str | None = None
    latest_system_id64: int | None = None
    counter: dict[str, int] | None = None
    latest_fetch_errors: int | None = None
    latest_systems_fetch_failed: int | None = None
    recent_429_count = 0
    max_consecutive_429 = 0
    consecutive_429 = 0
    latest_429_line: str | None = None
    latest_429_system: str | None = None
    latest_429_system_id64: int | None = None
    latest_retry_after: str | None = None
    latest_backoff_seconds: float | None = None
    guard_429_warning_count: int | None = None
    batch_headers: list[int] = []
    batch_checkpoint_updates: list[dict[str, int]] = []
    batch_fetch_failure_skips: list[dict[str, int]] = []
    all_records_aborted = False

    for raw_line in lines:
        line = raw_line.rstrip('\n')
        progress_match = PROGRESS_SYSTEM_RE.search(line)
        if progress_match:
            latest_progress_line = line
            latest_counter_line = line
            counter = {
                'current': int(progress_match.group('current')),
                'total': int(progress_match.group('total')),
            }
            latest_system_name = _unquote(progress_match.group('system'))
            latest_system_id64 = _coerce_int(progress_match.group('id64'))
        else:
            counter_match = PROGRESS_COUNTER_RE.search(line)
            if counter_match:
                latest_progress_line = line
                latest_counter_line = line
                counter = {
                    'current': int(counter_match.group('current')),
                    'total': int(counter_match.group('total')),
                }

        fetching_match = FETCHING_SYSTEM_RE.search(line)
        if fetching_match:
            latest_system_name = _unquote(fetching_match.group('system'))
            latest_system_id64 = _coerce_int(fetching_match.group('id64'))

        fetch_errors_match = FETCH_ERRORS_RE.search(line)
        if fetch_errors_match:
            latest_fetch_errors = int(fetch_errors_match.group('count'))
        systems_failed_match = SYSTEMS_FETCH_FAILED_RE.search(line)
        if systems_failed_match:
            latest_systems_fetch_failed = int(systems_failed_match.group('count'))
        else:
            fetch_failed_match = FETCH_FAILED_RE.search(line)
            if fetch_failed_match:
                latest_systems_fetch_failed = int(fetch_failed_match.group('count'))

        header_match = BATCH_HEADER_RE.search(line)
        if header_match:
            batch_headers.append(int(header_match.group('number')))
        update_match = BATCH_CHECKPOINT_RE.search(line)
        if update_match:
            batch_checkpoint_updates.append({
                'number': int(update_match.group('number')),
                'added': int(update_match.group('added')),
                'total': int(update_match.group('total')),
                'failed': int(update_match.group('failed')),
            })
        skip_match = BATCH_SKIP_FAILED_RE.search(line)
        if skip_match:
            batch_fetch_failure_skips.append({
                'number': int(skip_match.group('number')),
                'systems_fetch_failed': int(skip_match.group('count')),
            })
        if 'all-records aborted:' in line:
            all_records_aborted = True

        if _is_rate_limit_line(line):
            recent_429_count += 1
            consecutive_429 += 1
            max_consecutive_429 = max(max_consecutive_429, consecutive_429)
            latest_429_line = line
            system_name, system_id64 = _parse_system_from_line(line)
            if system_name is not None:
                latest_429_system = system_name
            if system_id64 is not None:
                latest_429_system_id64 = system_id64
            retry_after = _parse_retry_after(line)
            if retry_after is not None:
                latest_retry_after = retry_after
            backoff_seconds = _parse_backoff_seconds(line)
            if backoff_seconds is not None:
                latest_backoff_seconds = backoff_seconds
        else:
            consecutive_429 = 0

        guard_warning = GUARD_429_WARNING_RE.search(line)
        if guard_warning:
            guard_429_warning_count = int(guard_warning.group('count'))

    percent = None
    if counter and counter['total'] > 0:
        percent = round((counter['current'] / counter['total']) * 100, 1)

    repeated_429 = (
        recent_429_count >= RATE_LIMIT_WARNING_THRESHOLD
        or max_consecutive_429 >= RATE_LIMIT_WARNING_THRESHOLD
        or (guard_429_warning_count is not None and guard_429_warning_count >= RATE_LIMIT_WARNING_THRESHOLD)
    )
    return {
        'source_files': [str(path) for path in source_files],
        'tail_lines_requested': tail_lines,
        'lines_considered': len(lines),
        'latest_progress_line': latest_progress_line,
        'latest_progress_counter_line': latest_counter_line,
        'counter': counter,
        'batch_progress_percent': percent,
        'latest_system_name': latest_system_name,
        'latest_system_id64': latest_system_id64,
        'fetch_errors': latest_fetch_errors,
        'systems_fetch_failed': latest_systems_fetch_failed,
        'batch_headers': batch_headers,
        'batch_checkpoint_updates': batch_checkpoint_updates,
        'batch_fetch_failure_skips': batch_fetch_failure_skips,
        'all_records_aborted': all_records_aborted,
        'rate_limit_summary': {
            'recent_429_lines': recent_429_count,
            'max_consecutive_429_lines': max_consecutive_429,
            'repeated_429_detected': repeated_429,
            'guard_warning_429_count': guard_429_warning_count,
            'most_recent_429_line': latest_429_line,
            'most_recent_429_system': latest_429_system,
            'most_recent_429_system_id64': latest_429_system_id64,
            'most_recent_retry_after': latest_retry_after,
            'most_recent_backoff_seconds': latest_backoff_seconds,
        },
    }


def build_system_query(system_id64: int | None, checkpoint: Mapping[str, Any]) -> dict[str, Any] | None:
    requested = _coerce_int(system_id64)
    if requested is None:
        return None
    processed = list(checkpoint.get('processed_system_id64s') or [])
    index = None
    try:
        index = processed.index(requested)
    except ValueError:
        pass
    present = index is not None
    result = {
        'system_id64': requested,
        'is_checkpointed': present,
        'index': index,
        'position': index + 1 if index is not None else None,
        'processed_count': checkpoint.get('processed_count', 0),
        'note': None,
    }
    if not checkpoint.get('valid'):
        result['note'] = 'checkpoint is missing or invalid, so lookup may be incomplete'
    elif not present:
        result['note'] = 'not checkpointed; it may still be pending or may have failed in an incomplete batch'
    return result


def build_warnings(status: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    checkpoint = status['checkpoint']
    latest_report = status.get('latest_report_summary')
    latest_batch = status['latest_batch']
    rate_limit = status['rate_limit_summary']

    if not checkpoint.get('exists'):
        warnings.append('WARNING: checkpoint file missing')
    elif not checkpoint.get('valid'):
        warnings.append('WARNING: checkpoint file invalid')
    elif checkpoint.get('processed_count') == 0 and status['latest_run'].get('output_dir'):
        warnings.append('WARNING: no checkpoint progress detected')

    if latest_report is None or not latest_report.get('valid'):
        warnings.append('WARNING: latest report missing or invalid')
    elif _coerce_int(latest_report.get('fetch_errors')) or _coerce_int(latest_report.get('systems_fetch_failed')):
        warnings.append('WARNING: latest batch has fetch failures')

    if rate_limit.get('repeated_429_detected'):
        warnings.append('WARNING: repeated EDSM 429 rate limits detected')

    if latest_batch.get('state') == 'interrupted':
        warnings.append('WARNING: latest run appears interrupted before checkpoint update')

    checkpoint_update = latest_batch.get('checkpoint_update') or {}
    if (
        checkpoint_update
        and _coerce_int(checkpoint_update.get('added')) == 0
        and _coerce_int(checkpoint_update.get('failed')) not in (None, 0)
    ):
        warnings.append('WARNING: latest batch completed with zero successful systems')
    elif (
        latest_report
        and latest_report.get('valid')
        and _coerce_int(latest_report.get('successful_system_ids_count')) == 0
        and _coerce_int(latest_report.get('systems_fetch_failed')) not in (None, 0)
    ):
        warnings.append('WARNING: latest batch completed with zero successful systems')

    return warnings


def render_human(status: Mapping[str, Any]) -> str:
    lines: list[str] = ['Station enrichment status']
    checkpoint = status['checkpoint']
    lines.append('')
    lines.append('Checkpoint')
    lines.append(f"  path: {checkpoint['path']}")
    if checkpoint.get('exists') and checkpoint.get('valid'):
        lines.append('  state: exists, valid')
    elif checkpoint.get('exists'):
        lines.append(f"  state: exists, invalid ({checkpoint.get('error')})")
    else:
        lines.append('  state: missing')
    lines.append(f"  checkpointed systems: {checkpoint.get('processed_count', 0)}")
    lines.append(f"  last checkpointed id64: {_display(checkpoint.get('last_system_id64'))}")

    latest_run = status['latest_run']
    latest_batch = status['latest_batch']
    lines.append('')
    lines.append('Run artifacts')
    lines.append(f"  output root: {latest_run['output_root']}")
    lines.append(f"  latest all-record output directory: {_display(latest_run.get('latest_all_records_output_dir'))}")
    lines.append(f"  latest batch directory: {_display(latest_batch.get('path'))}")
    lines.append(f"  latest report file: {_display(latest_batch.get('latest_report'))}")
    lines.append(f"  latest stderr file: {_display(latest_batch.get('latest_stderr'))}")
    lines.append(f"  latest log file: {_display(latest_run.get('latest_log_file'))}")
    lines.append(f"  latest batch number: {_display(latest_batch.get('number'))}")
    lines.append(f"  latest phase/report: {_display(latest_batch.get('latest_phase_name'))}")
    lines.append(f"  latest batch state: {latest_batch.get('state', 'unknown')}")

    summary = status.get('latest_report_summary')
    lines.append('')
    lines.append('Latest report summary')
    if not summary:
        lines.append('  (none)')
    elif not summary.get('valid'):
        lines.append(f"  error: {summary.get('error')}")
    else:
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
        ):
            lines.append(f"  {key}: {summary[key]}")
        lines.append(f"  dirty_marked/planned: {summary['dirty_marked_planned']}")

    progress = status['latest_progress']
    lines.append('')
    lines.append('Recent progress')
    lines.append(f"  latest progress counter line: {_display(progress.get('latest_progress_counter_line'))}")
    lines.append(f"  latest progress line: {_display(progress.get('latest_progress_line'))}")
    lines.append(f"  latest system name: {_display(progress.get('latest_system_name'))}")
    lines.append(f"  latest system id64: {_display(progress.get('latest_system_id64'))}")
    lines.append(f"  batch progress percent: {_display(progress.get('batch_progress_percent'))}")
    lines.append(f"  current/last fetch_errors: {_display(progress.get('fetch_errors'))}")
    lines.append(f"  current/last systems_fetch_failed: {_display(progress.get('systems_fetch_failed'))}")

    rate_limit = status['rate_limit_summary']
    lines.append('')
    lines.append('Rate limits')
    lines.append(f"  recent 429 lines: {rate_limit.get('recent_429_lines', 0)}")
    lines.append(f"  repeated 429s: {'yes' if rate_limit.get('repeated_429_detected') else 'no'}")
    lines.append(f"  most recent 429 system: {_display(rate_limit.get('most_recent_429_system'))}")
    lines.append(f"  most recent 429 system id64: {_display(rate_limit.get('most_recent_429_system_id64'))}")
    lines.append(f"  most recent Retry-After: {_display(rate_limit.get('most_recent_retry_after'))}")
    lines.append(f"  most recent backoff seconds: {_display(rate_limit.get('most_recent_backoff_seconds'))}")

    if status.get('system_query') is not None:
        query = status['system_query']
        lines.append('')
        lines.append('System lookup')
        if query['is_checkpointed']:
            lines.append(
                f"  system_id64 {query['system_id64']}: checkpointed "
                f"(index={query['index']}, position={query['position']} of {query['processed_count']})"
            )
        else:
            lines.append(f"  system_id64 {query['system_id64']}: not checkpointed")
            if query.get('note'):
                lines.append(f"  note: {query['note']}")

    lines.append('')
    lines.append('Warnings')
    if status.get('warnings'):
        lines.extend(f"  {warning}" for warning in status['warnings'])
    else:
        lines.append('  (none)')
    return '\n'.join(lines)


def discover_log_file(*, explicit: Path | None, output_root: Path, latest_run_dir: Path | None) -> Path | None:
    if explicit is not None:
        return explicit

    candidates: list[Path] = []
    for root in (latest_run_dir, output_root):
        if root is None or not root.exists():
            continue
        try:
            candidates.extend(path for path in root.glob('*.log') if path.is_file())
        except OSError:
            pass

    var_log = Path('/var/log/edfinder')
    if var_log.exists():
        try:
            candidates.extend(path for path in var_log.glob('station-enrichment*.log') if path.is_file())
        except OSError:
            pass

    return _latest_by_mtime(candidates) if candidates else None


def _progress_sources(log_file: Path | None, stderr_file: Path | None) -> list[Path]:
    if log_file is not None and log_file.exists():
        return [log_file]
    if stderr_file is not None and stderr_file.exists():
        return [stderr_file]
    return []


def _read_progress_lines(paths: Sequence[Path], tail_lines: int) -> list[str]:
    if tail_lines <= 0:
        return []
    lines: list[str] = []
    for path in paths:
        lines.extend(_tail_lines(path, tail_lines))
    return lines[-tail_lines:]


def _tail_lines(path: Path, line_count: int) -> list[str]:
    if line_count <= 0:
        return []
    try:
        with path.open('rb') as handle:
            handle.seek(0, 2)
            pos = handle.tell()
            data = bytearray()
            while pos > 0 and data.count(b'\n') <= line_count:
                read_size = min(8192, pos)
                pos -= read_size
                handle.seek(pos)
                data[:0] = handle.read(read_size)
    except OSError:
        return []
    return data.decode('utf-8', errors='replace').splitlines()[-line_count:]


def _batch_dirs(output_dir: Path | None) -> list[Path]:
    if output_dir is None:
        return []
    try:
        dirs = [child for child in output_dir.iterdir() if child.is_dir() and _batch_number(child) is not None]
    except OSError:
        return []
    return sorted(dirs, key=lambda path: (_batch_number(path) or -1, path.name))


def _latest_report(directory: Path | None) -> Path | None:
    if directory is None or not directory.exists():
        return None
    try:
        reports = [path for path in directory.glob('*.json') if path.is_file()]
    except OSError:
        return None
    return _latest_by_mtime(reports) if reports else None


def _latest_stderr(directory: Path | None, latest_report: Path | None) -> Path | None:
    if latest_report is not None:
        sibling = latest_report.with_name(f'{latest_report.name}.stderr.txt')
        if sibling.exists():
            return sibling
    if directory is None or not directory.exists():
        return None
    try:
        stderr_files = [path for path in directory.glob('*.stderr.txt') if path.is_file()]
    except OSError:
        return None
    return _latest_by_mtime(stderr_files) if stderr_files else None


def _latest_by_mtime(paths: Sequence[Path]) -> Path | None:
    if not paths:
        return None

    def key(path: Path) -> tuple[float, str]:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (mtime, path.name)

    return max(paths, key=key)


def _checkpoint_update_for_batch(
    updates: Sequence[Mapping[str, Any]],
    batch_number: int | None,
) -> dict[str, int] | None:
    if batch_number is None:
        return dict(updates[-1]) if updates else None
    for update in reversed(updates):
        if _coerce_int(update.get('number')) == batch_number:
            return {
                'number': int(update['number']),
                'added': int(update['added']),
                'total': int(update['total']),
                'failed': int(update['failed']),
            }
    return None


def _report_looks_ready_for_checkpoint(latest_report: Mapping[str, Any] | None) -> bool:
    if not latest_report or not latest_report.get('valid'):
        return False
    phase = str(latest_report.get('phase_name') or '')
    if phase == 'final dry-run':
        return True
    return (
        phase == 'initial dry-run'
        and _coerce_int(latest_report.get('metadata_updates')) == 0
        and _coerce_int(latest_report.get('confirmed_links')) == 0
    )


def _phase_name(path: Path) -> str:
    name = path.name
    if name.endswith('.json'):
        name = name[:-5]
    if re.match(r'^\d\d_', name):
        name = name[3:]
    name = name.replace('_', ' ')
    return name.replace('dryrun', 'dry-run')


def _batch_number(path: Path | None) -> int | None:
    if path is None:
        return None
    match = BATCH_DIR_RE.match(path.name)
    return int(match.group('number')) if match else None


def _is_rate_limit_line(line: str) -> bool:
    text = line.lower()
    return (
        'too many requests' in text
        or 'http 429' in text
        or 'status=429' in text
        or 'rate limit retry' in text
        or 'edsm 429 observed' in text
    )


def _parse_system_from_line(line: str) -> tuple[str | None, int | None]:
    system_match = SYSTEM_VALUE_RE.search(line)
    id64_match = ID64_RE.search(line)
    return (
        _unquote(system_match.group('system')) if system_match else None,
        _coerce_int(id64_match.group('id64')) if id64_match else None,
    )


def _parse_retry_after(line: str) -> str | None:
    match = RETRY_AFTER_RE.search(line) or RETRY_AFTER_HEADER_RE.search(line)
    if not match:
        return None
    return _unquote(match.group('value'))


def _parse_backoff_seconds(line: str) -> float | None:
    match = BACKOFF_RE.search(line)
    if not match:
        return None
    try:
        return float(match.group('seconds'))
    except ValueError:
        return None


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) >= 2 and text[0] in {'"', "'"} and text[-1] == text[0]:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return text[1:-1]
        return str(parsed)
    return text


def _display(value: Any) -> str:
    return '(none)' if value is None else str(value)


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
