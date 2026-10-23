"""Validate disposable purge measurements before a plan can trust their bounds.

Disk peaks in ``production`` remain raw: the production controllers apply the
owner's 1.5 margin immediately before admission. ``margin_applied`` is retained
for review, never fed back to those controllers. Batch peaks are not multiplied
by database scale because production uses the exact measured batch row bound.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'ed-finder/derived-purge-rehearsal/v1'
RELATIONS = ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
CRASH_SCENARIOS = ('batch_client_before_commit', 'batch_client_after_commit',
                   'rewrite_monitor_cancel', 'rewrite_terminate_backend',
                   'rewrite_postgres_restart', 'wrapper_after_rewrite_commit',
                   'rewrite_verified_transaction_failure')
HARNESS_FILES = ('scripts/rehearsal/v3_derived_purge_rehearsal.py',
                 'scripts/rehearsal/v3_derived_purge_seed.py',
                 'scripts/rehearsal/v3_purge_crashes.py')
LIFECYCLE_RECEIPT = ROOT / 'docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json'
MAX_RECEIPT_BYTES = 8 * 1024 * 1024


def expected_row_counts(proportion):
    """Bind declared seed counts to the dated, committed lifecycle evidence."""
    lifecycle = json.loads(LIFECYCLE_RECEIPT.read_text())
    columns = dict(system_search='search_systems', economy_opportunity='ratings_eligible_opportunities',
                   body_mechanics='ratings_physical_bodies', system_rating_vector='ratings_systems')
    return {relation: {generation: max(1, round(counts[column] * proportion)) if counts[column] else 0
                       for generation, counts in lifecycle['footprint']['rows_by_generation'].items()}
            for relation, column in columns.items()}


def _evidence():
    spec = importlib.util.spec_from_file_location('purge_rehearsal_evidence', Path(__file__).with_name('f2d_evidence.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code_identity():
    """Bind measurements to the executed action, harness, and verified lineage.

    Reuse the action's identity rather than maintaining a second source list.
    A Git SHA alone cannot authenticate the files a rehearsal actually ran.
    """
    spec = importlib.util.spec_from_file_location(
        'purge_rehearsal_controller_identity', Path(__file__).with_name('v3_generation_purge.py'))
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    return {
        'script_sha256': controller.script_identity(),
        'rehearsal_script_sha256': _evidence().canonical_sha256({
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in HARNESS_FILES}),
        'migration_set_identity': controller.schema_identity.migration_set_identity(
            controller.schema_identity.derive_entries(ROOT)),
    }


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def margin_bytes(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError('rehearsal_peak_invalid')
    return (3 * value + 1) // 2


def relation_figures(raw, proportion):
    """Extrapolate only whole-relation work; preserve actual bounded-batch work.

    Twice the extrapolated duration (minimum 60 seconds) is an explicit finite
    timeout/cadence allowance, not the owner's disk-peak multiplier. Rates are
    measured throughput and are never multiplied by the database scale.
    Autovacuum uses the documented heap-plus-index lower bound, with 1.5 margin.
    """
    if not _positive(proportion) or proportion > 1 or not isinstance(raw, dict):
        raise ValueError('rehearsal_scale_invalid')
    for field in ('deleted_rows', 'batch_limit', 'heap_index_bytes'):
        if type(raw.get(field)) is not int or not 0 < raw[field] < 2**63:
            raise ValueError('rehearsal_measurement_invalid')
    if not 1 <= raw['batch_limit'] <= 100_000:
        raise ValueError('rehearsal_batch_limit_invalid')
    for field in ('delete_seconds', 'rewrite_seconds'):
        if not _positive(raw.get(field)):
            raise ValueError('rehearsal_duration_invalid')
    for field in ('batch_peak_bytes', 'rewrite_peak_bytes'):
        margin_bytes(raw.get(field))
    if raw['batch_peak_bytes'] >= 1_000_000_000:
        raise ValueError('rehearsal_batch_peak_requires_lower_bound')
    duration = raw['rewrite_seconds'] / proportion * 2
    rate = raw['deleted_rows'] / raw['delete_seconds']
    if not _positive(duration) or not _positive(rate) or duration > 2_147_483:
        raise ValueError('rehearsal_statement_timeout_exceeds_bound')
    rewrite_allowance = max(60, math.ceil(duration))
    timeout_ms = rewrite_allowance * 1000
    if timeout_ms > 2_147_483_647:
        raise ValueError('rehearsal_statement_timeout_exceeds_bound')
    rewrite_peak = math.ceil(raw['rewrite_peak_bytes'] / proportion)
    heap_index = math.ceil(raw['heap_index_bytes'] / proportion)
    production = {
        'rows_per_second': rate,
        'rewrite_allowance_seconds': rewrite_allowance,
        'batch_limit': raw['batch_limit'], 'batch_peak_bytes': raw['batch_peak_bytes'],
        'rewrite_peak_bytes': rewrite_peak, 'statement_timeout_ms': timeout_ms,
        'autovacuum_budget_bytes': margin_bytes(heap_index),
        'autovacuum_budget_source': 'heap_plus_index_lower_bound',
    }
    return {'raw': dict(raw), 'production': production, 'margin_applied': {
        'batch_peak_bytes': margin_bytes(raw['batch_peak_bytes']),
        'rewrite_peak_bytes': margin_bytes(rewrite_peak),
        'autovacuum_budget_bytes': margin_bytes(heap_index),
    }}


def validate(value, *, production=True):
    """Validate schema and recompute every derived bound, refusing forged maths."""
    if (not isinstance(value, dict) or value.get('schema_version') != SCHEMA
            or value.get('operation') != 'v3-derived-purge-rehearsal'):
        raise ValueError('rehearsal_schema_invalid')
    if (not isinstance(value.get('source_git_sha'), str)
            or re.fullmatch('[0-9a-f]{40}', value['source_git_sha']) is None):
        raise ValueError('rehearsal_source_invalid')
    for field in ('script_sha256', 'rehearsal_script_sha256'):
        if (not isinstance(value.get(field), str)
                or re.fullmatch('[0-9a-f]{64}', value[field]) is None):
            raise ValueError('rehearsal_' + field + '_invalid')
    if (not isinstance(value.get('migration_set_identity'), str)
            or re.fullmatch('sha256:[0-9a-f]{64}', value['migration_set_identity']) is None):
        raise ValueError('rehearsal_migration_set_identity_invalid')
    if (not isinstance(value.get('image_digest'), str)
            or re.fullmatch(r'(?:[a-z0-9./_-]+(?::[a-z0-9._-]+)?)?@sha256:[0-9a-f]{64}', value['image_digest']) is None):
        raise ValueError('rehearsal_image_not_pinned')
    if value.get('scale') not in ('tiny', 'smoke', 'one_percent'):
        raise ValueError('rehearsal_scale_invalid')
    proportion = value.get('production_proportion')
    if not _positive(proportion) or proportion > 1:
        raise ValueError('rehearsal_scale_invalid')
    if (value['scale'] == 'one_percent' and not 0.0075 <= proportion <= 0.0125):
        raise ValueError('rehearsal_scale_invalid')
    settings = value.get('settings')
    if not isinstance(settings, dict) or settings.get('autovacuum') not in ('on', True):
        raise ValueError('rehearsal_autovacuum_not_enabled')
    counts, figures = value.get('row_counts'), value.get('per_relation')
    if (not isinstance(counts, dict) or set(counts) != set(RELATIONS)
            or not isinstance(figures, dict) or set(figures) != set(RELATIONS)):
        raise ValueError('rehearsal_relations_invalid')
    if counts != expected_row_counts(proportion):
        raise ValueError('rehearsal_row_counts_proportion_mismatch')
    for relation in RELATIONS:
        generations = counts[relation]
        if (not isinstance(generations, dict) or not generations
                or any(type(count) is not int or count < 0 for count in generations.values())):
            raise ValueError('rehearsal_row_counts_invalid')
        figure = figures[relation]
        if not isinstance(figure, dict):
            raise ValueError('rehearsal_measurement_invalid')
        raw = figure.get('raw')
        if not isinstance(raw, dict):
            raise ValueError('rehearsal_measurement_invalid')
        if raw.get('deleted_rows') != sum(
                generations[key] for key in ('ratings_v4_prod_p4', 'ratings_v4_prod_p4_opt1')):
            raise ValueError('rehearsal_deleted_rows_mismatch')
        recomputed = relation_figures(figure.get('raw'), proportion)
        if any(figure.get(key) != recomputed[key] for key in ('production', 'margin_applied')):
            raise ValueError('rehearsal_derived_figures_mismatch')
    if type(value.get('gate_10_crash_rehearsal_passed')) is not bool:
        raise ValueError('rehearsal_crash_gate_invalid')
    scenarios = value.get('crash_scenarios')
    passed = (isinstance(scenarios, dict) and all(
        isinstance(scenarios.get(name), dict) and scenarios[name].get('passed') is True
        for name in CRASH_SCENARIOS))
    if value['gate_10_crash_rehearsal_passed'] and not passed:
        raise ValueError('rehearsal_crash_scenarios_incomplete')
    if production:
        if value.get('status') != 'success' or value['scale'] != 'one_percent':
            raise ValueError('rehearsal_production_scale_required')
        if value.get('failures') != []:
            raise ValueError('rehearsal_failures_not_empty')
        if not value['gate_10_crash_rehearsal_passed']:
            raise ValueError('rehearsal_crash_gate_not_passed')
        if value.get('cleanup_verified') is not True:
            raise ValueError('rehearsal_cleanup_not_verified')
        if value.get('lifecycle_receipt_sha256') != hashlib.sha256(LIFECYCLE_RECEIPT.read_bytes()).hexdigest():
            raise ValueError('rehearsal_lifecycle_proportions_unbound')
        for field, expected in code_identity().items():
            if value[field] != expected:
                raise ValueError('rehearsal_' + field + '_mismatch')
    return value


def load_reviewed(path, expected_sha):
    """Bind a human-reviewed receipt by canonical content seal and explicit SHA."""
    if not isinstance(expected_sha, str) or re.fullmatch('[0-9a-f]{64}', expected_sha) is None:
        raise ValueError('rehearsal_expected_sha256_invalid')
    try:
        if Path(path).stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError('rehearsal_size_exceeded')
        value = _evidence().load_sealed(path)
    except (ValueError, OSError):
        raise ValueError('rehearsal_seal_invalid') from None
    if value['content_sha256'] != expected_sha:
        raise ValueError('rehearsal_expected_sha256_mismatch')
    return validate(value)


def require_plan_binding(reviewed):
    """Refuse a production plan that does not carry reviewed one-percent figures.

    ``authorize`` binds its plan immutably to the purge ledger, and every later
    delete, rewrite and abort reads its measured bounds from that plan. A plan
    sealed without ``apply_to_plan`` would leave the purge unable to proceed.
    """
    binding = reviewed.get('rehearsal') if isinstance(reviewed, dict) else None
    if (not isinstance(binding, dict) or binding.get('scale') != 'one_percent'
            or binding.get('gate_10_crash_rehearsal_passed') is not True
            or not isinstance(binding.get('content_sha256'), str)
            or re.fullmatch('[0-9a-f]{64}', binding['content_sha256']) is None):
        raise ValueError('plan_rehearsal_figures_required')
    source = 'reviewed_rehearsal:' + binding['content_sha256']
    delete, rewrite = reviewed.get('delete'), reviewed.get('rewrite')
    for relation in RELATIONS:
        figures = delete.get(relation) if isinstance(delete, dict) else None
        bounds = rewrite.get(relation) if isinstance(rewrite, dict) else None
        if (not isinstance(figures, dict) or figures.get('rows_per_second_source') != source
                or any(key not in figures for key in (
                    'batch_limit', 'batch_peak_bytes', 'rows_per_second',
                    'rewrite_allowance_seconds', 'autovacuum_budget_bytes'))
                or not isinstance(bounds, dict)
                or any(key not in bounds for key in ('rewrite_peak_bytes', 'statement_timeout_ms'))):
            raise ValueError('plan_rehearsal_figures_required')
    return binding


def apply_to_plan(reviewed, rehearsal):
    """Copy authenticated measured inputs into the real action's reviewed plan."""
    validate(rehearsal)
    body = {key: value for key, value in rehearsal.items() if key != 'content_sha256'}
    if rehearsal.get('content_sha256') != _evidence().canonical_sha256(body):
        raise ValueError('rehearsal_seal_invalid')
    source = 'reviewed_rehearsal:' + rehearsal['content_sha256']
    delete, rewrite = {}, {}
    for relation in RELATIONS:
        measured = rehearsal['per_relation'][relation]['production']
        delete[relation] = {key: measured[key] for key in (
            'batch_limit', 'batch_peak_bytes', 'rows_per_second', 'rewrite_allowance_seconds',
            'autovacuum_budget_bytes', 'autovacuum_budget_source')}
        delete[relation]['rows_per_second_source'] = source
        rewrite[relation] = {key: measured[key] for key in ('rewrite_peak_bytes', 'statement_timeout_ms')}
    reviewed.update(delete=delete, rewrite=rewrite, rehearsal={
        'content_sha256': rehearsal['content_sha256'], 'source_git_sha': rehearsal['source_git_sha'],
        **{field: rehearsal[field] for field in (
            'script_sha256', 'rehearsal_script_sha256', 'migration_set_identity')},
        'scale': rehearsal['scale'], 'gate_10_crash_rehearsal_passed': True,
        'production_proportion': rehearsal['production_proportion'], 'disk_peak_margin': 1.5,
        'margin_application': 'raw_peaks_passed_to_controller_margin_applied_at_admission',
    })
    return reviewed
