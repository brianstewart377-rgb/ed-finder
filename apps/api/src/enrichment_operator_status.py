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


def read_warehouse_status_snapshot(path_value: str | None) -> dict[str, Any]:
    """Read and sanitize a warehouse reconciliation/status JSON artifact.

    The API deliberately does not invoke warehouse scripts or open a database
    connection. Operators publish a JSON artifact, usually a reconciliation
    report, and this helper exposes only compact review counters and safe
    artifact identifiers.
    """
    if not path_value:
        return _warehouse_unavailable('not_configured', 'Warehouse status artifact is not configured.')

    path = Path(path_value).expanduser()
    if not path.exists():
        return {
            **_warehouse_unavailable('missing', 'Warehouse status artifact is unavailable.'),
            'artifact': _artifact_info(path, exists=False),
        }
    if not path.is_file():
        return {
            **_warehouse_unavailable('invalid', 'Warehouse status artifact is not a regular file.'),
            'artifact': _artifact_info(path, exists=True),
        }

    try:
        size = path.stat().st_size
    except OSError:
        size = None
    if size is not None and size > MAX_STATUS_ARTIFACT_BYTES:
        return {
            **_warehouse_unavailable('too_large', 'Warehouse status artifact is too large to display safely.'),
            'artifact': _artifact_info(path, exists=True),
        }

    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {
            **_warehouse_unavailable('invalid_json', 'Warehouse status artifact is not valid JSON.'),
            'artifact': _artifact_info(path, exists=True),
        }
    except OSError:
        return {
            **_warehouse_unavailable('unreadable', 'Warehouse status artifact could not be read.'),
            'artifact': _artifact_info(path, exists=True),
        }
    if not isinstance(payload, Mapping):
        return {
            **_warehouse_unavailable('invalid_json', 'Warehouse status artifact payload is not an object.'),
            'artifact': _artifact_info(path, exists=True),
        }

    return sanitize_warehouse_status(payload, artifact_path=path)


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



def _compact_summary_report_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt compact reconciliation summaries into the warehouse status model.

    Stage 18J-Q8 compact summaries are deliberately reduced/sanitized versions
    of larger reconciliation artifacts. They do not have the exact full
    reconciliation shape, so this adapter maps known compact fields into the
    existing UI-safe status contract while leaving missing values unavailable.
    """
    schema_version = _safe_schema_version(payload.get('schema_version'))
    source_schema_version = _safe_schema_version(
        payload.get('artifact_schema_version')
        or payload.get('source_schema_version')
        or payload.get('source_artifact_schema_version')
    )

    summary = _mapping(payload.get('summary'))
    counts = _mapping(payload.get('counts'))
    candidates = _mapping(payload.get('candidates'))
    distributions = _mapping(payload.get('distributions'))
    confidence = _mapping(payload.get('confidence_risk_summary'))
    source_coverage = _mapping(payload.get('source_coverage_summary'))
    warehouse_coverage = _mapping(payload.get('warehouse_coverage_summary'))
    artifact = _mapping(payload.get('artifact'))
    filters = _mapping(payload.get('filters'))

    # Compact summaries have varied naming across iterations. Pull the same
    # logical counters from several safe places.
    canonical_writes = _first_int(
        payload.get('canonical_writes_planned'),
        summary.get('canonical_writes_planned'),
        counts.get('canonical_writes_planned'),
    )
    station_candidates = _first_int(
        payload.get('station_candidate_count'),
        summary.get('station_candidate_count'),
        summary.get('station_candidates'),
        counts.get('station_candidate_count'),
        counts.get('station_candidates'),
        candidates.get('station_candidate_count'),
        candidates.get('station_candidates'),
    )
    body_candidates = _first_int(
        payload.get('body_candidate_count'),
        summary.get('body_candidate_count'),
        summary.get('body_candidates'),
        counts.get('body_candidate_count'),
        counts.get('body_candidates'),
        candidates.get('body_candidate_count'),
        candidates.get('body_candidates'),
    )
    ring_candidates = _first_int(
        payload.get('ring_candidate_count'),
        summary.get('ring_candidate_count'),
        summary.get('ring_candidates'),
        counts.get('ring_candidate_count'),
        counts.get('ring_candidates'),
        candidates.get('ring_candidate_count'),
        candidates.get('ring_candidates'),
    )

    candidate_action_counts = _first_distribution(
        payload.get('candidate_action_counts'),
        summary.get('candidate_action_counts'),
        counts.get('candidate_action_counts'),
        distributions.get('candidate_action_counts'),
        payload.get('action_counts'),
        summary.get('action_counts'),
        distributions.get('action_counts'),
    )
    risk_distribution = _first_distribution(
        confidence.get('risk_class_distribution'),
        payload.get('risk_class_distribution'),
        summary.get('risk_class_distribution'),
        distributions.get('risk_class_distribution'),
    )
    confidence_distribution = _first_distribution(
        confidence.get('confidence_distribution'),
        payload.get('confidence_distribution'),
        summary.get('confidence_distribution'),
        distributions.get('confidence_distribution'),
    )
    reconciliation_state_distribution = _first_distribution(
        payload.get('reconciliation_state_counts'),
        summary.get('reconciliation_state_counts'),
        distributions.get('reconciliation_state_counts'),
        payload.get('reconciliation_state_distribution'),
        distributions.get('reconciliation_state_distribution'),
    )

    blocked_count = _dist_count(risk_distribution, 'blocked')
    risky_count = _dist_count(risk_distribution, 'risky')
    stale_count = _dist_count(risk_distribution, 'stale')
    volatile_count = _dist_count(risk_distribution, 'volatile')

    source_entities = _mapping(source_coverage.get('entities'))
    ring_evidence = _mapping(source_coverage.get('ring_evidence'))
    coverage_summary = _mapping(warehouse_coverage.get('summary'))

    warnings = _safe_warning_rows(payload.get('warnings'))
    errors = _safe_warning_rows(payload.get('errors'))

    return {
        'available': True,
        'configured': True,
        'state': _warehouse_state(
            canonical_writes=canonical_writes,
            errors=len(errors) if errors else _int_or_none(summary.get('errors')),
            blocked=blocked_count,
            risky=risky_count,
            stale=stale_count,
            volatile=volatile_count,
            warning_count=len(warnings) if warnings else _int_or_none(summary.get('warnings')),
        ),
        'message': 'Compact warehouse reconciliation summary loaded.',
        'source': 'warehouse_reconciliation_status_json',
        'artifact': None,  # caller adds the real published artifact metadata
        'latest_snapshot_load': {
            'source_run_key': _safe_text(filters.get('source_run_key')),
            'source_file_key': _safe_text(filters.get('source_file_key')),
            'source': _safe_text(filters.get('source') or artifact.get('source_artifact_basename')),
            'source_files_considered': _first_int(
                source_coverage.get('source_files_considered'),
                coverage_summary.get('source_files_considered'),
            ),
            'source_type_distribution': _first_distribution(
                payload.get('source_type_distribution'),
                summary.get('source_type_distribution'),
                distributions.get('source_type_distribution'),
            ),
            'source_format_distribution': _first_distribution(
                payload.get('source_format_distribution'),
                summary.get('source_format_distribution'),
                distributions.get('source_format_distribution'),
            ),
        },
        'latest_reconciliation_run': {
            'schema_version': schema_version,
            'coverage_schema_version': source_schema_version,
            'dry_run': _bool_or_none(payload.get('dry_run')),
            'report_only': _bool_or_none(payload.get('report_only')),
            'canonical_writes_planned': canonical_writes,
            'staged_station_rows_considered': _first_int(
                summary.get('staged_station_rows_considered'),
                counts.get('staged_station_rows_considered'),
                station_candidates,
            ),
            'staged_body_rows_considered': _first_int(
                summary.get('staged_body_rows_considered'),
                counts.get('staged_body_rows_considered'),
                body_candidates,
            ),
            'staged_ring_rows_considered': _first_int(
                summary.get('staged_ring_rows_considered'),
                counts.get('staged_ring_rows_considered'),
                ring_candidates,
            ),
            'canonical_matches_found': _first_int(
                summary.get('canonical_matches_found'),
                counts.get('canonical_matches_found'),
            ),
            'canonical_misses': _first_int(
                summary.get('canonical_misses'),
                counts.get('canonical_misses'),
            ),
            'ambiguous_matches': _first_int(
                summary.get('ambiguous_matches'),
                counts.get('ambiguous_matches'),
            ),
            'insufficient_evidence': _first_int(
                summary.get('insufficient_evidence'),
                counts.get('insufficient_evidence'),
            ),
            'warnings': len(warnings) if warnings else _int_or_none(summary.get('warnings')),
            'errors': len(errors) if errors else _int_or_none(summary.get('errors')),
        },
        'source_coverage': {
            'station_candidates': _first_int(station_candidates, _entity_candidate_count(source_entities, 'station')),
            'body_candidates': _first_int(body_candidates, _entity_candidate_count(source_entities, 'body')),
            'ring_candidates': _first_int(ring_candidates, _entity_candidate_count(source_entities, 'ring')),
            'systems_with_station_evidence': _first_int(
                source_coverage.get('systems_with_station_evidence'),
                coverage_summary.get('systems_with_station_evidence'),
            ),
            'systems_missing_station_evidence': _first_int(
                source_coverage.get('systems_missing_station_evidence'),
                coverage_summary.get('systems_missing_station_evidence'),
            ),
            'trusted_ring_evidence_bodies': _first_int(
                source_coverage.get('trusted_ring_evidence_bodies'),
                coverage_summary.get('trusted_ring_evidence_bodies'),
            ),
            'unknown_ring_evidence_bodies': _first_int(
                source_coverage.get('unknown_ring_evidence_bodies'),
                coverage_summary.get('unknown_ring_evidence_bodies'),
            ),
            'explicit_no_ring_evidence_bodies': _first_int(
                source_coverage.get('explicit_no_ring_evidence_bodies'),
                coverage_summary.get('explicit_no_ring_evidence_bodies'),
            ),
            'staged_ring_candidates': _first_int(
                ring_evidence.get('staged_ring_candidates'),
                ring_candidates,
            ),
            'trusted_local_matched_ring_candidates': _int_or_none(
                ring_evidence.get('trusted_local_matched_ring_candidates')
            ),
        },
        'evidence_health': {
            'unresolved_stations': _first_int(
                summary.get('unresolved_stations'),
                coverage_summary.get('unresolved_stations'),
            ),
            'blocked_conflicts': blocked_count,
            'risky_conflicts': risky_count,
            'stale_records': stale_count,
            'volatile_records': volatile_count,
            'stale_or_undated_source_records': _first_int(
                summary.get('stale_or_undated_source_records'),
                coverage_summary.get('stale_or_undated_source_records'),
            ),
            'malformed_or_skipped_rows': _first_int(
                summary.get('malformed_or_skipped_rows'),
                coverage_summary.get('malformed_or_skipped_rows'),
            ),
            'duplicate_source_records': _first_int(
                summary.get('duplicate_source_records'),
                coverage_summary.get('duplicate_source_records'),
            ),
            'source_identity_conflicts': _first_int(
                summary.get('source_identity_conflicts'),
                coverage_summary.get('source_identity_conflicts'),
            ),
            'high_value_systems_needing_better_evidence': _first_int(
                summary.get('high_value_systems_needing_better_evidence'),
                coverage_summary.get('high_value_systems_needing_better_evidence'),
            ),
        },
        'canonical_safety': {
            'canonical_tables_untouched': canonical_writes == 0 if canonical_writes is not None else None,
            'canonical_writes_planned': canonical_writes,
            'dry_run': _bool_or_none(payload.get('dry_run')),
            'report_only': _bool_or_none(payload.get('report_only')),
        },
        'warnings': warnings[:8],
        'errors': errors[:8],
        'compact_summary_distributions': {
            'candidate_action_counts': _safe_distribution(candidate_action_counts),
            'risk_class_distribution': _safe_distribution(risk_distribution),
            'confidence_distribution': _safe_distribution(confidence_distribution),
            'reconciliation_state_distribution': _safe_distribution(reconciliation_state_distribution),
        },
    }


def sanitize_warehouse_status(
    payload: Mapping[str, Any],
    *,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    if payload.get('schema_version') == 'enrichment_reconciliation_artifact_summary/v1':
        compact_status = _compact_summary_report_payload(payload)
        compact_status['artifact'] = _artifact_info(artifact_path, exists=True)
        return compact_status

    report = _warehouse_report_payload(payload)
    summary = _mapping(report.get('summary'))
    filters = _mapping(report.get('filters'))
    coverage = _mapping(report.get('warehouse_coverage_report'))
    coverage_summary = _mapping(coverage.get('summary'))
    coverage_operator = _mapping(coverage.get('operator_review'))
    needs_attention = _mapping(coverage_operator.get('needs_attention_buckets'))
    source_freshness = _mapping(coverage.get('source_freshness'))
    stale_or_undated = _mapping(source_freshness.get('stale_or_undated_evidence'))
    source_quality = _mapping(coverage.get('source_quality'))
    source_formats = _mapping(coverage.get('source_formats'))
    confidence = _mapping(report.get('confidence_risk_summary'))
    source_coverage = _mapping(report.get('source_coverage_summary'))
    source_entities = _mapping(source_coverage.get('entities'))
    ring_evidence = _mapping(source_coverage.get('ring_evidence'))
    risk_classes = _mapping(confidence.get('risk_class_distribution'))

    canonical_writes = _first_int(
        summary.get('canonical_writes_planned'),
        coverage.get('canonical_writes_planned'),
        coverage_summary.get('canonical_writes_planned'),
    )
    report_only = _bool_or_none(coverage.get('report_only'))
    dry_run = _bool_or_none(report.get('dry_run'))
    errors_count = _first_int(summary.get('errors'), _length_or_none(report.get('errors')))
    blocked_count = _dist_count(risk_classes, 'blocked')
    risky_count = _dist_count(risk_classes, 'risky')
    stale_count = _dist_count(risk_classes, 'stale')
    volatile_count = _dist_count(risk_classes, 'volatile')
    warning_count = _first_int(summary.get('warnings'), _length_or_none(report.get('warnings')))
    state = _warehouse_state(
        canonical_writes=canonical_writes,
        errors=errors_count,
        blocked=blocked_count,
        risky=risky_count,
        stale=stale_count,
        volatile=volatile_count,
        warning_count=warning_count,
    )

    return {
        'available': True,
        'configured': True,
        'state': state,
        'message': _warehouse_message_for_state(state),
        'source': 'warehouse_reconciliation_status_json',
        'artifact': _artifact_info(artifact_path, exists=True),
        'latest_snapshot_load': {
            'source_run_key': _safe_text(filters.get('source_run_key')),
            'source_file_key': _safe_text(filters.get('source_file_key')),
            'source': _safe_text(filters.get('source')),
            'source_files_considered': _int_or_none(coverage_summary.get('source_files_considered')),
            'source_type_distribution': _safe_distribution(source_formats.get('source_type_distribution')),
            'source_format_distribution': _safe_distribution(source_formats.get('source_format_distribution')),
        },
        'latest_reconciliation_run': {
            'schema_version': _safe_schema_version(report.get('schema_version')),
            'coverage_schema_version': _safe_schema_version(coverage.get('schema_version')),
            'dry_run': dry_run,
            'report_only': report_only,
            'canonical_writes_planned': canonical_writes,
            'staged_station_rows_considered': _int_or_none(summary.get('staged_station_rows_considered')),
            'staged_body_rows_considered': _int_or_none(summary.get('staged_body_rows_considered')),
            'staged_ring_rows_considered': _int_or_none(summary.get('staged_ring_rows_considered')),
            'canonical_matches_found': _int_or_none(summary.get('canonical_matches_found')),
            'canonical_misses': _int_or_none(summary.get('canonical_misses')),
            'ambiguous_matches': _int_or_none(summary.get('ambiguous_matches')),
            'insufficient_evidence': _int_or_none(summary.get('insufficient_evidence')),
            'warnings': warning_count,
            'errors': errors_count,
        },
        'source_coverage': {
            'station_candidates': _entity_candidate_count(source_entities, 'station'),
            'body_candidates': _entity_candidate_count(source_entities, 'body'),
            'ring_candidates': _entity_candidate_count(source_entities, 'ring'),
            'systems_with_station_evidence': _int_or_none(coverage_summary.get('systems_with_station_evidence')),
            'systems_missing_station_evidence': _int_or_none(coverage_summary.get('systems_missing_station_evidence')),
            'trusted_ring_evidence_bodies': _int_or_none(coverage_summary.get('trusted_ring_evidence_bodies')),
            'unknown_ring_evidence_bodies': _int_or_none(coverage_summary.get('unknown_ring_evidence_bodies')),
            'explicit_no_ring_evidence_bodies': _int_or_none(coverage_summary.get('explicit_no_ring_evidence_bodies')),
            'staged_ring_candidates': _int_or_none(ring_evidence.get('staged_ring_candidates')),
            'trusted_local_matched_ring_candidates': _int_or_none(
                ring_evidence.get('trusted_local_matched_ring_candidates')
            ),
        },
        'evidence_health': {
            'unresolved_stations': _int_or_none(coverage_summary.get('unresolved_stations')),
            'blocked_conflicts': blocked_count,
            'risky_conflicts': risky_count,
            'stale_records': stale_count,
            'volatile_records': volatile_count,
            'stale_or_undated_source_records': _first_int(
                stale_or_undated.get('records_without_source_updated_at'),
                needs_attention.get('stale_or_undated_sources'),
            ),
            'malformed_or_skipped_rows': _first_int(
                coverage_summary.get('malformed_or_skipped_source_rows'),
                needs_attention.get('skipped_or_malformed_raw_records'),
                _mapping(source_quality.get('malformed_or_skipped_source_rows')).get('count'),
            ),
            'duplicate_source_records': _first_int(
                needs_attention.get('duplicate_source_records'),
                _mapping(source_quality.get('duplicate_source_records')).get('duplicate_records'),
            ),
            'source_identity_conflicts': _first_int(
                coverage_summary.get('source_identity_conflicts'),
                needs_attention.get('source_identity_conflicts'),
                _mapping(source_quality.get('source_identity_conflicts')).get('count'),
            ),
            'high_value_systems_needing_better_evidence': _first_int(
                coverage_summary.get('high_value_systems_needing_better_evidence'),
                needs_attention.get('high_value_systems_needing_better_evidence'),
            ),
        },
        'canonical_safety': {
            'canonical_tables_untouched': canonical_writes == 0 if canonical_writes is not None else None,
            'canonical_writes_planned': canonical_writes,
            'dry_run': dry_run,
            'report_only': report_only,
        },
        'warnings': _safe_warning_rows(report.get('warnings')),
        'errors': _safe_warning_rows(report.get('errors')),
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


def _warehouse_unavailable(state: str, message: str) -> dict[str, Any]:
    return {
        'available': False,
        'configured': state != 'not_configured',
        'state': state,
        'message': message,
        'source': 'warehouse_reconciliation_status_json',
        'artifact': None,
        'latest_snapshot_load': None,
        'latest_reconciliation_run': None,
        'source_coverage': None,
        'evidence_health': None,
        'canonical_safety': None,
        'warnings': [],
        'errors': [],
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


def _warehouse_state(
    *,
    canonical_writes: int | None,
    errors: int | None,
    blocked: int | None,
    risky: int | None,
    stale: int | None,
    volatile: int | None,
    warning_count: int | None,
) -> str:
    if canonical_writes is not None and canonical_writes != 0:
        return 'unsafe'
    if errors:
        return 'error'
    if blocked:
        return 'blocked'
    if risky or stale or volatile or warning_count:
        return 'warning'
    return 'available'


def _warehouse_message_for_state(state: str) -> str:
    return {
        'available': 'Warehouse status artifact loaded.',
        'blocked': 'Warehouse status has blocked reconciliation evidence for review.',
        'error': 'Warehouse status artifact reports errors.',
        'missing': 'Warehouse status artifact is unavailable.',
        'unsafe': 'Warehouse status reports planned canonical writes.',
        'warning': 'Warehouse status loaded with review warnings.',
    }.get(state, 'Warehouse status artifact loaded.')


def _warehouse_report_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    embedded = payload.get('reconciliation_report')
    if isinstance(embedded, Mapping):
        return embedded
    return payload


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


def _safe_schema_version(value: Any) -> str | None:
    text = _text_or_none(value)
    if not text:
        return None
    parts = text.split('/')
    if len(parts) == 2:
        family, version = parts
        family_safe = family.replace('_', '').replace('-', '').replace('.', '').isalnum()
        version_safe = version.startswith('v') and version[1:].isdigit()
        if family_safe and version_safe:
            return text
    return _safe_text(text)


def _safe_distribution(value: Any) -> dict[str, int] | None:
    mapping = _mapping(value)
    if not mapping:
        return None
    safe: dict[str, int] = {}
    for key, item in mapping.items():
        safe_key = _safe_text(key)
        safe_value = _int_or_none(item)
        if safe_key is not None and safe_value is not None:
            safe[safe_key] = safe_value
    return dict(sorted(safe.items()))


def _safe_warning_rows(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    warnings: list[str] = []
    for item in value[:5]:
        if isinstance(item, Mapping):
            text = _safe_text(item.get('reason') or item.get('message') or item.get('error'))
        else:
            text = _safe_text(item)
        if text:
            warnings.append(text)
    return warnings


def _entity_candidate_count(entities: Mapping[str, Any], entity: str) -> int | None:
    return _int_or_none(_mapping(entities.get(entity)).get('candidates'))


def _dist_count(mapping: Mapping[str, Any], key: str) -> int | None:
    if not mapping:
        return None
    value = _int_or_none(mapping.get(key))
    return value if value is not None else 0



def _first_distribution(*values: Any) -> dict[str, int] | None:
    for value in values:
        dist = _safe_distribution(value)
        if dist:
            return dist
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _length_or_none(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    return None


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
