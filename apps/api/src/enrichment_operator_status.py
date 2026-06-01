"""Read-only, sanitized enrichment status snapshot helpers.

The API must not run the enrichment guard, invoke Docker, or call live APIs
from a request handler. Operators can publish the output of
``station_enrichment_status.py --json`` to a shared JSON artifact, and this
module reduces that artifact to a UI-safe status model.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MAX_STATUS_ARTIFACT_BYTES = 1_000_000
SENSITIVE_TEXT_MARKERS = (
    '://',
    'api_key',
    'apikey',
    'database_url',
    'dsn',
    'password',
    'secret',
    'token',
)


def read_enrichment_status_snapshot(path_value: str | None) -> dict[str, Any]:
    """Read and sanitize a station enrichment status JSON artifact.

    Missing configuration or artifacts are represented as unavailable, not as
    zero progress. Full filesystem paths from the helper payload are never
    returned.
    """
    if not path_value:
        return _unavailable('not_configured', 'Enrichment status artifact is not configured.')

    path = Path(path_value).expanduser()
    if not path.exists():
        return {
            **_unavailable('missing', 'Enrichment status artifact is unavailable.'),
            'artifact': _artifact_info(path, exists=False),
        }
    if not path.is_file():
        return {
            **_unavailable('invalid', 'Enrichment status artifact is not a regular file.'),
            'artifact': _artifact_info(path, exists=True),
        }

    try:
        size = path.stat().st_size
    except OSError:
        size = None
    if size is not None and size > MAX_STATUS_ARTIFACT_BYTES:
        return {
            **_unavailable('too_large', 'Enrichment status artifact is too large to display safely.'),
            'artifact': _artifact_info(path, exists=True),
        }

    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {
            **_unavailable('invalid_json', 'Enrichment status artifact is not valid JSON.'),
            'artifact': _artifact_info(path, exists=True),
        }
    except OSError:
        return {
            **_unavailable('unreadable', 'Enrichment status artifact could not be read.'),
            'artifact': _artifact_info(path, exists=True),
        }
    if not isinstance(payload, Mapping):
        return {
            **_unavailable('invalid_json', 'Enrichment status artifact payload is not an object.'),
            'artifact': _artifact_info(path, exists=True),
        }

    return sanitize_station_enrichment_status(payload, artifact_path=path)


def sanitize_station_enrichment_status(
    payload: Mapping[str, Any],
    *,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    checkpoint = _mapping(payload.get('checkpoint'))
    latest_run = _mapping(payload.get('latest_run'))
    latest_batch = _mapping(payload.get('latest_batch'))
    latest_report = _mapping(payload.get('latest_report_summary'))
    latest_progress = _mapping(payload.get('latest_progress'))
    rate_limit = _mapping(payload.get('rate_limit_summary'))

    checkpoint_valid = checkpoint.get('valid') is True
    report_valid = latest_report.get('valid') is True
    progress_counter = _mapping(latest_progress.get('counter'))

    warnings = []
    for item in payload.get('warnings', []):
        warning = _safe_text(item)
        if warning:
            warnings.append(warning)
    state = _overall_state(checkpoint, latest_batch, latest_report, warnings)

    return {
        'available': True,
        'configured': True,
        'state': state,
        'message': _message_for_state(state),
        'source': 'station_enrichment_status_json',
        'artifact': _artifact_info(artifact_path, exists=True),
        'checkpoint': {
            'exists': checkpoint.get('exists') if isinstance(checkpoint.get('exists'), bool) else None,
            'valid': checkpoint.get('valid') if isinstance(checkpoint.get('valid'), bool) else None,
            'processed_count': _int_or_none(checkpoint.get('processed_count')) if checkpoint_valid else None,
            'last_system_id64': _int_or_none(checkpoint.get('last_system_id64')) if checkpoint_valid else None,
            'invalid_entry_count': _int_or_none(checkpoint.get('invalid_entry_count')) if checkpoint_valid else None,
            'error': _safe_error(checkpoint.get('error')),
        },
        'latest_run': {
            'output_root_exists': _bool_or_none(latest_run.get('output_root_exists')),
            'output_dir_name': _basename(latest_run.get('output_dir')),
            'latest_all_records_output_dir_name': _basename(latest_run.get('latest_all_records_output_dir')),
            'latest_any_output_dir_name': _basename(latest_run.get('latest_any_output_dir')),
            'latest_log_file_name': _basename(latest_run.get('latest_log_file')),
            'latest_log_file_exists': _bool_or_none(latest_run.get('latest_log_file_exists')),
        },
        'latest_batch': {
            'number': _int_or_none(latest_batch.get('number')),
            'state': _text_or_none(latest_batch.get('state')),
            'latest_phase_name': _text_or_none(latest_batch.get('latest_phase_name')),
            'latest_report_file_name': _basename(latest_batch.get('latest_report')),
            'latest_stderr_file_name': _basename(latest_batch.get('latest_stderr')),
        },
        'latest_report': {
            'valid': _bool_or_none(latest_report.get('valid')),
            'phase_name': _text_or_none(latest_report.get('phase_name')),
            'systems_processed': _int_or_none(latest_report.get('systems_processed')) if report_valid else None,
            'metadata_updates': _int_or_none(latest_report.get('metadata_updates')) if report_valid else None,
            'confirmed_links': _int_or_none(latest_report.get('confirmed_links')) if report_valid else None,
            'conflicts': _int_or_none(latest_report.get('conflicts')) if report_valid else None,
            'skipped': _int_or_none(latest_report.get('skipped')) if report_valid else None,
            'fetch_errors': _int_or_none(latest_report.get('fetch_errors')) if report_valid else None,
            'systems_fetch_failed': _int_or_none(latest_report.get('systems_fetch_failed')) if report_valid else None,
            'suppressed_station_writes': (
                _int_or_none(latest_report.get('suppressed_station_writes')) if report_valid else None
            ),
            'ignored_transient_non_slot': (
                _int_or_none(latest_report.get('ignored_transient_non_slot')) if report_valid else None
            ),
            'dirty_marked_planned': _text_or_none(latest_report.get('dirty_marked_planned')) if report_valid else None,
            'error': _safe_error(latest_report.get('error')),
        },
        'latest_progress': {
            'current': _int_or_none(progress_counter.get('current')),
            'total': _int_or_none(progress_counter.get('total')),
            'batch_progress_percent': _number_or_none(latest_progress.get('batch_progress_percent')),
            'latest_system_name': _text_or_none(latest_progress.get('latest_system_name')),
            'latest_system_id64': _int_or_none(latest_progress.get('latest_system_id64')),
            'fetch_errors': _int_or_none(latest_progress.get('fetch_errors')),
            'systems_fetch_failed': _int_or_none(latest_progress.get('systems_fetch_failed')),
            'all_records_aborted': _bool_or_none(latest_progress.get('all_records_aborted')),
        },
        'rate_limit': {
            'recent_429_lines': _int_or_none(rate_limit.get('recent_429_lines')),
            'max_consecutive_429_lines': _int_or_none(rate_limit.get('max_consecutive_429_lines')),
            'repeated_429_detected': _bool_or_none(rate_limit.get('repeated_429_detected')),
            'guard_warning_429_count': _int_or_none(rate_limit.get('guard_warning_429_count')),
            'most_recent_429_system': _text_or_none(rate_limit.get('most_recent_429_system')),
            'most_recent_429_system_id64': _int_or_none(rate_limit.get('most_recent_429_system_id64')),
            'most_recent_retry_after': _text_or_none(rate_limit.get('most_recent_retry_after')),
            'most_recent_backoff_seconds': _number_or_none(rate_limit.get('most_recent_backoff_seconds')),
        },
        'warnings': warnings,
    }


def _unavailable(state: str, message: str) -> dict[str, Any]:
    return {
        'available': False,
        'configured': state != 'not_configured',
        'state': state,
        'message': message,
        'source': 'station_enrichment_status_json',
        'artifact': None,
        'checkpoint': None,
        'latest_run': None,
        'latest_batch': None,
        'latest_report': None,
        'latest_progress': None,
        'rate_limit': None,
        'warnings': [],
    }


def _artifact_info(path: Path | None, *, exists: bool) -> dict[str, Any] | None:
    if path is None:
        return None
    updated_at = None
    age_seconds = None
    try:
        stat = path.stat()
    except OSError:
        stat = None
    if stat is not None:
        updated = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        updated_at = updated.isoformat()
        age_seconds = max(0, int((datetime.now(timezone.utc) - updated).total_seconds()))
    return {
        'file_name': path.name,
        'exists': exists,
        'updated_at': updated_at,
        'age_seconds': age_seconds,
        'path_visible': False,
    }


def _overall_state(
    checkpoint: Mapping[str, Any],
    latest_batch: Mapping[str, Any],
    latest_report: Mapping[str, Any],
    warnings: list[str],
) -> str:
    if latest_batch.get('state') == 'failed':
        return 'failed'
    if any('rate limits' in warning.lower() for warning in warnings):
        return 'rate_limited'
    if latest_report.get('valid') and (
        _int_or_none(latest_report.get('fetch_errors')) or _int_or_none(latest_report.get('systems_fetch_failed'))
    ):
        return 'warning'
    if checkpoint.get('valid') is False or latest_report.get('valid') is False:
        return 'warning'
    if latest_batch.get('state') == 'in_progress':
        return 'running'
    if latest_batch.get('state') == 'completed':
        return 'completed'
    return 'available'


def _message_for_state(state: str) -> str:
    return {
        'available': 'Enrichment status artifact loaded.',
        'completed': 'Latest enrichment batch is recorded as completed.',
        'failed': 'Latest enrichment batch reported a failure state.',
        'rate_limited': 'Latest enrichment status includes rate-limit warnings.',
        'running': 'Latest enrichment batch appears to be in progress.',
        'warning': 'Enrichment status loaded with warnings.',
    }.get(state, 'Enrichment status artifact loaded.')


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _basename(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).name


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_error(value: Any) -> str | None:
    return _safe_text(value)


def _safe_text(value: Any) -> str | None:
    text = _text_or_none(value)
    if not text:
        return None
    lowered = text.lower()
    if '/' in text or '\\' in text or any(marker in lowered for marker in SENSITIVE_TEXT_MARKERS):
        return 'unavailable'
    return text


def _int_or_none(value: Any) -> int | None:
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


def _number_or_none(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
