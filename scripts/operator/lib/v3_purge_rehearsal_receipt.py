"""Validate disposable purge measurements before a plan can trust their bounds.

Schema v3 (copy-and-drop route, migration 019). The disposable rehearsal runs
the real copy route per relation (preflight, copy, index build, VACUUM FREEZE,
verify, swap, FK validation, drop) and records, per relation: copy rows per
second, index-build, freeze, verify and FK-validation time, the copy's
free-space peak, WAL bytes per phase, the swap's lock hold, the worst Finder
read stall a concurrent reader saw during the swap, and the temporary-file
peak (sampled) and total (written). Whole-relation work is extrapolated by the recorded production
proportion; catalog-only swap figures are not scaled. Disk peaks in
``production`` stay raw: the copy controller applies the owner's 1.5 margin at
admission (``required_free_bytes_before_copy``), and ``margin_applied`` is kept
for review only. v1 (zero-survivor delete/rewrite) and v2 (delete/rewrite with
published survivors) receipts measured the disabled route and are refused.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'ed-finder/derived-purge-rehearsal/v3'
ROUTE = 'copy_and_drop'
RELATIONS = ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
CRASH_SCENARIOS = ('copy_chunk_client_killed', 'copy_postgres_restart', 'index_build_backend_terminated',
                   'verify_watchdog_cancel', 'swap_committed_client_killed',
                   'swap_back_committed_client_killed', 'swap_back_and_reswap', 'abandon_and_recopy',
                   'drop_committed_client_killed')
HARNESS_FILES = ('scripts/rehearsal/v3_derived_purge_rehearsal.py',
                 'scripts/rehearsal/v3_derived_purge_seed.py',
                 'scripts/rehearsal/v3_purge_crashes.py')
LIFECYCLE_RECEIPT = ROOT / 'docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json'
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
SURVIVOR_KEY = 'ratings_v4_prod_p4_parallel_v1'
TARGET_KEYS = ('ratings_v4_prod_p4', 'ratings_v4_prod_p4_opt1')
SURVIVOR_PRODUCTS = ('system_search', 'system_archetype')
FREE_FLOOR_BYTES = 100_000_000_000
# The copy route's reviewed long-phase statement envelope (v3_purge_copy).
MAX_LONG_PHASE_SECONDS = 7_200
# Owner-run host speed benchmark, 2026-10-28
# (docs/operations/evidence/2026-10-28-v3-purge-host-speed-benchmark.json):
# one read-only query (3,000,000 generated rows rendered as row text, an md5
# per row, then an ordered md5 aggregate; the same result on both hosts), run
# twice on production and twice on the rehearsal host in the pinned rehearsal
# image. Verification is that work, so a rehearsal measured in that image has
# its extrapolated verification scaled by the slower production run over the
# faster rehearsal-host run (about 0.317). Index build, VACUUM FREEZE and FK
# validation keep rehearsal-host time.
PRODUCTION_BENCHMARK_MS = 5631.137
REHEARSAL_HOST_BENCHMARK_MS = 17766.579
BENCHMARKED_REHEARSAL_IMAGE = ('ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine'
                               '@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873')
RECEIPT_MODULE = 'scripts/operator/lib/v3_purge_rehearsal_receipt.py'
# One-percent rehearsals that ran before this module's production gate last
# changed (the action identity hashes this module). Each pins the receipt's
# content seal, the action identity it ran and the SHA-256 of every file that
# identity covered. It stays production authority only while every one of
# those files other than this module is byte-for-byte as rehearsed (the file
# list itself lives in v3_generation_purge.py, which is pinned) and the
# harness and migration set match; any other change needs a new rehearsal.
ACCEPTED_REHEARSALS = {
    # Run 40704251158 on main 065d1e56 (2026-10-28): 019, 020, 021 and #906.
    '5732f3b3ac48ede0fbde7b210de8cd1c59ece1be27df56987c141c3e936dda07': {
        'script_sha256': '4a1955b4b8edc26960351f3a48571f14606048d9d9546db692a71d1073f99ab4',
        'files': {
            'deploy/v3-production/backup/pgbackrest-operation.sh':
                'f22b2db951cd1932ca6c3a0c41858fa00fc3613dacc2a736553a0017c6517f72',
            'scripts/operator/actions/v3-derived-generation-purge.sh':
                'da14a92989ddf3c2ce796f068eb1ce14b759f4d2391f18f8696bba8b914c3065',
            'scripts/operator/actions/v3-derived-lifecycle-status.sh':
                '0ead803e384ba6c9e2fa37c2c118011695d532db3f8e2954359941aa9bcb254a',
            'scripts/operator/lib/f2d_evidence.py':
                'd58a3590dbc7c4131a633357be771e717f7c72c3507d9906ba1a462e1b57b4ea',
            'scripts/operator/lib/v3_generation_purge.py':
                '3d313a899f6d5feef3402a19c22d74b46a8341c2de908ab847d572c49477db0e',
            'scripts/operator/lib/v3_purge_copy.py':
                'deed2681f510044ee81f5879ed4c332a92b2b0d1f37a9801e4c902abef41a775',
            'scripts/operator/lib/v3_purge_copy_dispatch.py':
                '04ec4513df70982f67f93c8ddde8e166f3b1070fac132648df8fd46675b24577',
            'scripts/operator/lib/v3_purge_delete.py':
                '65f134fb6eca3701caf629e42bda323964894ea5e185c892c12fb3b56c189ec0',
            'scripts/operator/lib/v3_purge_rehearsal.py':
                '83eb82123ed160d836126f3fd34beb0a7892ce8d99c1e5829d0fbfe59f693472',
            'scripts/operator/lib/v3_purge_rehearsal_receipt.py':
                'fb985384f8a33b5ff308c6bf834d4b47ac7b54b9995c638be7d00db5cd06c510',
            'scripts/operator/lib/v3_purge_rewrite.py':
                'a4c2ce970f8255983ab8e3d0e67436775292dbdf2556a30750c85baea67f5b7e',
            'scripts/operator/lib/v3_purge_rewrite_dispatch.py':
                '6b0f2b7993b00f2ad427cad4d5263ed02b5e893dcbb1f97d85a1820308657cf1',
            'scripts/operator/lib/v3_purge_rewrite_monitor.py':
                '1ddbc0c0855d414136022b9cda2556a287433f439598225f0b593188eed67627',
            'scripts/operator/lib/v3_purge_state.py':
                '4b8e73550694bd3d4c4406dad7c6625c4607d6662c4dbfe76b4f125cf8d805cc',
            'scripts/operator/lib/v3_purge_transactions.py':
                'cdcea7b2d7b914faa3fd36898e9824323567c32fb70c8c7016a9234cc141b56f',
            'scripts/operator/v3_schema_identity.py':
                'af308cf196901f2b35180cf026e6cbef16e5bc1a9b7e54fa075817d95aaac013',
        },
    },
}
# The API's read statement timeout (apps/api/src/config.py): a Finder read that
# waits longer than this behind a swap fails as a 503.
API_READ_TIMEOUT_SECONDS = 15
WAL_PHASES = ('chunk', 'index_build', 'vacuum_freeze', 'verify', 'validate_fks', 'drop')
LONG_PHASES = ('index_build_seconds', 'vacuum_freeze_seconds', 'verify_seconds', 'fk_validation_seconds')
RAW_COUNTS = ('copied_rows', 'live_bytes_before', 'copy_bytes', 'swap_attempts', 'finder_reads_during_swap')
RAW_NONNEGATIVE = ('target_rows', 'copy_peak_bytes', 'temp_file_peak_bytes', 'temp_file_written_bytes',
                   'freed_bytes', 'filesystem_sample_count')
RAW_SECONDS = ('copy_seconds', *LONG_PHASES)
RAW_NONNEGATIVE_SECONDS = ('swap_lock_hold_seconds', 'finder_read_stall_seconds', 'drop_seconds')
# Owner-reported 2026-10-23 production v3_derived.system_search size (about
# 175 GB) across the published parallel_v1 Search rows and the opt1 target
# rows, one row per system each. Only used to keep the width check strict.
REPORTED_SEARCH_BYTES = 175_000_000_000
REPORTED_SEARCH_ROWS = 2 * 198_528_286


def expected_row_counts(proportion):
    """Bind declared seed counts to the dated, committed lifecycle evidence.

    The receipt predates go-live, so its surviving generation has no Search
    rows. Both Finder products have since been published on that generation
    with one row per system (``expected_rows`` = its 198,528,286 systems,
    publish run 39933842811), so the survivor Search count is its
    ``ratings_systems`` at the same proportion.
    """
    lifecycle = json.loads(LIFECYCLE_RECEIPT.read_text())
    columns = dict(system_search='search_systems', economy_opportunity='ratings_eligible_opportunities',
                   body_mechanics='ratings_physical_bodies', system_rating_vector='ratings_systems')
    rows = lifecycle['footprint']['rows_by_generation']
    result = {relation: {generation: max(1, round(counts[column] * proportion)) if counts[column] else 0
                         for generation, counts in rows.items()}
              for relation, column in columns.items()}
    result['system_search'][SURVIVOR_KEY] = max(1, round(rows[SURVIVOR_KEY]['ratings_systems'] * proportion))
    return result


def expected_survivor_products(proportion):
    """Published Finder product rows on the surviving generation (one per system)."""
    survivors = expected_row_counts(proportion)['system_search'][SURVIVOR_KEY]
    return {code: survivors for code in SURVIVOR_PRODUCTS}


def production_search_bytes_per_row():
    """The larger of the committed and the owner-reported production widths."""
    lifecycle = json.loads(LIFECYCLE_RECEIPT.read_text())
    measured = [item for item in lifecycle['footprint']['relations']
                if item.get('schema') == 'v3_derived' and item.get('name') == 'system_search']
    if len(measured) != 1 or not measured[0].get('n_live_tup'):
        raise ValueError('rehearsal_production_search_width_unknown')
    committed = measured[0]['total_bytes'] / measured[0]['n_live_tup']
    return max(committed, REPORTED_SEARCH_BYTES / REPORTED_SEARCH_ROWS)


def _load(name):
    spec = importlib.util.spec_from_file_location('purge_rehearsal_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence():
    return _load('f2d_evidence')


def code_identity():
    """Bind measurements to the executed action, harness, and verified lineage.

    Reuse the action's identity rather than maintaining a second source list.
    A Git SHA alone cannot authenticate the files a rehearsal actually ran.
    """
    controller = _load('v3_generation_purge')
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


def _nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def margin_bytes(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError('rehearsal_peak_invalid')
    return (3 * value + 1) // 2


def relation_figures(raw, proportion):
    """Extrapolate whole-relation copy work; keep catalog-only swap figures raw.

    Rates are measured throughput and are never multiplied by the scale. A
    long phase fits the copy route only if twice its extrapolated duration is
    within the reviewed 7,200 s statement envelope (the same 2x allowance the
    earlier route used for its rewrite timeout).
    """
    if not _positive(proportion) or proportion > 1 or not isinstance(raw, dict):
        raise ValueError('rehearsal_scale_invalid')
    for field in RAW_COUNTS:
        if type(raw.get(field)) is not int or not 0 < raw[field] < 2**63:
            raise ValueError('rehearsal_measurement_invalid')
    for field in RAW_NONNEGATIVE:
        if type(raw.get(field)) is not int or not 0 <= raw[field] < 2**63:
            raise ValueError('rehearsal_measurement_invalid')
    for field in RAW_SECONDS:
        if not _positive(raw.get(field)):
            raise ValueError('rehearsal_duration_invalid')
    for field in RAW_NONNEGATIVE_SECONDS:
        if not _nonnegative(raw.get(field)):
            raise ValueError('rehearsal_duration_invalid')
    wal = raw.get('wal_bytes')
    if (not isinstance(wal, dict) or set(wal) != set(WAL_PHASES)
            or any(type(value) is not int or not 0 <= value < 2**63 for value in wal.values())):
        raise ValueError('rehearsal_wal_bytes_invalid')
    scaled = {field: raw[field] / proportion for field in RAW_SECONDS}
    longest = max(scaled[field] for field in LONG_PHASES)
    peak = math.ceil(raw['copy_peak_bytes'] / proportion)
    temp = math.ceil(raw['temp_file_peak_bytes'] / proportion)
    production = {
        'copy_rows_per_second': raw['copied_rows'] / raw['copy_seconds'],
        **scaled,
        'long_phase_seconds_max': longest,
        'long_phase_fits_reviewed_timeout': 2 * longest <= MAX_LONG_PHASE_SECONDS,
        'copy_peak_bytes': peak,
        'required_free_bytes_before_copy': FREE_FLOOR_BYTES + margin_bytes(peak),
        'copy_bytes': math.ceil(raw['copy_bytes'] / proportion),
        'freed_bytes': math.ceil(raw['freed_bytes'] / proportion),
        'temp_file_peak_bytes': temp,
        'temp_file_written_bytes': math.ceil(raw['temp_file_written_bytes'] / proportion),
        'wal_bytes': {phase: math.ceil(wal[phase] / proportion) for phase in WAL_PHASES},
        # Catalog-only: a swap moves names, not rows; its stall does not scale.
        'swap_lock_hold_seconds': raw['swap_lock_hold_seconds'],
        'finder_read_stall_seconds': raw['finder_read_stall_seconds'],
        'method': 'whole_relation_work_divided_by_proportion_catalog_swap_unscaled',
    }
    return {'raw': dict(raw), 'production': production, 'margin_applied': {
        'copy_peak_bytes': margin_bytes(peak), 'temp_file_peak_bytes': margin_bytes(temp)}}


def verify_speed_factor(value):
    """Production over rehearsal-host verification time; 1 outside the benchmarked image."""
    if value.get('image_digest') != BENCHMARKED_REHEARSAL_IMAGE:
        return 1.0
    return PRODUCTION_BENCHMARK_MS / REHEARSAL_HOST_BENCHMARK_MS


def production_long_phase_seconds(measured, factor):
    """The longest extrapolated long phase, verification at production host speed.

    ``long_phase_fits_reviewed_timeout`` in the receipt keeps the rehearsal
    host's figure (it is part of the sealed maths); the production gate uses
    this one. Twice it must still fit the 7,200 s statement envelope.
    """
    return max(measured['index_build_seconds'], measured['vacuum_freeze_seconds'],
               measured['verify_seconds'] * factor, measured['fk_validation_seconds'])


def _accepted_before_gate_change(value):
    """True only for a pinned receipt whose rehearsed files, bar this module, are unchanged."""
    accepted = ACCEPTED_REHEARSALS.get(value.get('content_sha256'))
    if accepted is None or value.get('script_sha256') != accepted['script_sha256']:
        return False
    evidence = _evidence()
    body = {key: item for key, item in value.items() if key != 'content_sha256'}
    files = accepted['files']
    if (evidence.canonical_sha256(body) != value['content_sha256'] or RECEIPT_MODULE not in files
            or evidence.canonical_sha256(files) != accepted['script_sha256']):
        return False
    try:
        return all(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
                   for relative, digest in files.items() if relative != RECEIPT_MODULE)
    except OSError:
        return False


def _require_identity(value):
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


def validate(value, *, production=True):
    """Validate schema and recompute every derived bound, refusing forged maths."""
    if (not isinstance(value, dict) or value.get('schema_version') != SCHEMA
            or value.get('operation') != 'v3-derived-purge-rehearsal' or value.get('route') != ROUTE):
        raise ValueError('rehearsal_schema_invalid')
    _require_identity(value)
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
    # Zero published survivors cannot stand in for production since go-live.
    if value.get('survivor_products') != expected_survivor_products(proportion):
        raise ValueError('rehearsal_survivor_population_mismatch')
    for relation in RELATIONS:
        generations = counts[relation]
        if (not isinstance(generations, dict) or not generations
                or any(type(count) is not int or count < 0 for count in generations.values())):
            raise ValueError('rehearsal_row_counts_invalid')
        figure = figures[relation]
        raw = figure.get('raw') if isinstance(figure, dict) else None
        if not isinstance(raw, dict):
            raise ValueError('rehearsal_measurement_invalid')
        if raw.get('copied_rows') != generations[SURVIVOR_KEY]:
            raise ValueError('rehearsal_copied_rows_mismatch')
        if raw.get('target_rows') != sum(generations[key] for key in TARGET_KEYS):
            raise ValueError('rehearsal_target_rows_mismatch')
        recomputed = relation_figures(raw, proportion)
        if any(figure.get(key) != recomputed[key] for key in ('production', 'margin_applied')):
            raise ValueError('rehearsal_derived_figures_mismatch')
    # Synthetic Search rows narrower than production would understate the copy.
    search = figures['system_search']['raw']
    if search['copy_bytes'] / search['copied_rows'] < production_search_bytes_per_row():
        raise ValueError('rehearsal_search_survivor_width_unrepresentative')
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
        factor = verify_speed_factor(value)
        for relation in RELATIONS:
            measured = figures[relation]['production']
            if 2 * production_long_phase_seconds(measured, factor) > MAX_LONG_PHASE_SECONDS:
                raise ValueError('rehearsal_long_phase_exceeds_reviewed_timeout')
            if measured['finder_read_stall_seconds'] > API_READ_TIMEOUT_SECONDS:
                raise ValueError('rehearsal_finder_stall_exceeds_api_timeout')
        for field, expected in code_identity().items():
            if value[field] != expected and not (
                    field == 'script_sha256' and _accepted_before_gate_change(value)):
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

    ``authorize`` binds its plan immutably to the purge ledger, and every
    later copy reads its free-space requirement from the plan's ``copy`` block.
    A plan sealed without ``apply_to_plan`` could authorize but never copy.
    """
    binding = reviewed.get('rehearsal') if isinstance(reviewed, dict) else None
    if (not isinstance(binding, dict) or binding.get('scale') != 'one_percent'
            or binding.get('route') != ROUTE
            or binding.get('gate_10_crash_rehearsal_passed') is not True
            or not isinstance(binding.get('content_sha256'), str)
            or re.fullmatch('[0-9a-f]{64}', binding['content_sha256']) is None):
        raise ValueError('plan_rehearsal_figures_required')
    source = 'reviewed_rehearsal:' + binding['content_sha256']
    block = reviewed.get('copy')
    relations = block.get('relations') if isinstance(block, dict) else None
    if not isinstance(block, dict) or block.get('source') != source or not isinstance(relations, dict):
        raise ValueError('plan_rehearsal_figures_required')
    for relation in RELATIONS:
        figures = relations.get(relation)
        if (not isinstance(figures, dict) or figures.get('copy_peak_source') != source
                or type(figures.get('required_free_bytes_before_copy')) is not int
                or figures['required_free_bytes_before_copy'] < FREE_FLOOR_BYTES
                or not isinstance(figures.get('rehearsal'), dict)):
            raise ValueError('plan_rehearsal_figures_required')
    return binding


def apply_to_plan(reviewed, rehearsal):
    """Copy authenticated measured inputs into the real action's reviewed plan."""
    validate(rehearsal)
    body = {key: value for key, value in rehearsal.items() if key != 'content_sha256'}
    if rehearsal.get('content_sha256') != _evidence().canonical_sha256(body):
        raise ValueError('rehearsal_seal_invalid')
    source = 'reviewed_rehearsal:' + rehearsal['content_sha256']
    figures = {relation: rehearsal['per_relation'][relation]['production'] for relation in RELATIONS}
    reviewed['copy'] = _load('v3_purge_copy').plan_block(figures, source)
    factor = verify_speed_factor(rehearsal)
    reviewed['rehearsal'] = {
        'content_sha256': rehearsal['content_sha256'], 'source_git_sha': rehearsal['source_git_sha'],
        **{field: rehearsal[field] for field in (
            'script_sha256', 'rehearsal_script_sha256', 'migration_set_identity')},
        'route': ROUTE, 'scale': rehearsal['scale'], 'gate_10_crash_rehearsal_passed': True,
        'production_proportion': rehearsal['production_proportion'], 'disk_peak_margin': 1.5,
        'margin_application': 'raw_peaks_passed_to_controller_margin_applied_at_admission',
        # For review: the gate's figures (the copy block keeps the receipt's own).
        'verify_speed_factor': factor,
        'production_long_phase_seconds': {
            relation: production_long_phase_seconds(figures[relation], factor) for relation in RELATIONS},
        # The same check validate() used to admit a pinned receipt.
        'accepted_before_gate_change': (rehearsal['script_sha256'] != code_identity()['script_sha256']
                                        and _accepted_before_gate_change(rehearsal)),
    }
    return reviewed
