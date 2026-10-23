#!/usr/bin/env python3.14
"""Disposable PG18 measurements using the governed purge action itself.

No port is published, no external network exists, and every database command
runs inside the one marked container. This module has no DSN/host argument.
Filesystem samples bound a whole action invocation (conservatively also each
batch in that invocation), including WAL and temporary files on its data mount.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operator.lib import f2d_evidence as evidence  # noqa: E402
from scripts.operator.lib import v3_generation_purge as controller  # noqa: E402
from scripts.operator.lib import v3_purge_rehearsal_receipt as figures  # noqa: E402
from scripts.rehearsal import v3_derived_purge_seed as seed  # noqa: E402

IMAGE = ('ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine@sha256:'
         '77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873')
DATABASE = 'edfinder_purge_rehearsal'
USER = 'edfinder_v3'
OBSERVER_USER = 'edfinder_purge_observer'
RECEIPT_PATH = ROOT / evidence.STEP0_RECEIPT
SCALE_SYSTEMS = {'smoke': 100_000, 'one_percent': 2_000_000, 'tiny': 200}
RELATIONS = tuple(controller.RELATIONS.values())
SEED_BATCH_ROWS = 50_000
SAMPLE_SECONDS = 0.1
CRASH_SCENARIOS = figures.CRASH_SCENARIOS
SURVIVOR_CONTROL_SQL = """SET default_transaction_read_only=off;
SELECT extract(epoch FROM clock_timestamp());
VACUUM (FULL, ANALYZE) v3_derived.system_search;
SELECT extract(epoch FROM clock_timestamp());
"""
OBSERVER_SETUP = """
CREATE ROLE edfinder_purge_observer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE edfinder_purge_observer SET default_transaction_read_only=on;
GRANT pg_read_all_stats TO edfinder_purge_observer;
GRANT USAGE ON SCHEMA v3_meta,v3_derived,v3_spatial TO edfinder_purge_observer;
GRANT SELECT ON ALL TABLES IN SCHEMA v3_meta,v3_derived,v3_spatial TO edfinder_purge_observer;
"""


def seeding_proportions(scale):
    """Use receipt rows, including the incomplete BUILDING generation.

    The receipt validator's own function supplies the counts, so the seed and
    its admission check cannot drift; it adds the post-go-live published
    survivor Search population (one row per surviving system).
    """
    lifecycle = json.loads(RECEIPT_PATH.read_text())
    production_systems = lifecycle['derived_generations'][1]['expected_systems']
    proportion = SCALE_SYSTEMS[scale] / production_systems
    return proportion, figures.expected_row_counts(proportion)


def bind_sql(statement, parameters):
    """psql data binding, identical hex transport to the real action."""
    assignments = []
    statement = statement.replace('%%', '%')
    for key, value in parameters.items():
        if re.fullmatch('[a-z][a-z0-9_]*', key) is None:
            raise ValueError('invalid_parameter')
        encoded = str(value).encode().hex()
        assignments.append('\\set ' + key + " '" + encoded + "'")
        statement = statement.replace('%(' + key + ')s',
                                      "convert_from(decode(:'" + key + "','hex'),'UTF8')")
    if '%(' in statement:
        raise ValueError('unbound_parameter')
    return '\n'.join(assignments) + '\n' + statement


def maximum_drawdown(samples):
    """Largest decrease of free bytes after any earlier sample, never negative."""
    high = peak = 0
    for value in samples:
        if type(value) is not int or value < 0:
            raise ValueError('invalid_free_bytes_sample')
        high = max(high, value)
        peak = max(peak, high - value)
    return peak


def batch_peak_growth(observations):
    """Include the sample on both sides of each observed batch boundary.

    Several fast batches between samples are conservatively grouped. WAL is
    counted on the data filesystem, including retained segments. Sampling is a
    measurement, not a guarantee that a sub-interval transient was observed.
    """
    peak = 0
    window = []
    previous_event = None
    for event, free in observations:
        if previous_event is not None and event != previous_event:
            window.append(free)
            peak = max(peak, maximum_drawdown(window))
            window = window[-2:]
        else:
            window.append(free)
        previous_event = event
    return max(peak, maximum_drawdown(window))


class Harness:
    def __init__(self, scale, run_id, output_dir):
        if scale not in SCALE_SYSTEMS or re.fullmatch('[A-Za-z0-9_-]{1,80}', run_id) is None:
            raise ValueError('invalid_rehearsal_identity')
        self.scale, self.run_id = scale, run_id
        self.output = Path(output_dir)
        self.output.mkdir(parents=True, exist_ok=True)
        self.container = 'edfinder-purge-rehearsal-' + uuid4().hex
        self.volume = self.container + '-data'
        self.token = secrets.token_hex(32)
        self.proportion, self.counts = seeding_proportions(scale)
        self.survivors = figures.expected_survivor_products(self.proportion)
        self.plan = self.verification = None
        self.refused_action = None
        self.phase = 'not_started'
        self.statements = []
        self.filesystem_receipts = []
        self.call_number = 0
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(('PG', 'DOCKER_', 'V3_PRODUCTION_', 'ED_NEW_OPERATOR_',
                                                   'ED_PURGE_REHEARSAL_FAULT'))}
        self.environment['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
        # The controller authenticates the wrapper/loop process lifetime with a
        # numeric run identity. Local disposable runs use this harness PID;
        # GitHub executions retain the actual workflow run ID.
        self.environment.setdefault('GITHUB_RUN_ID', str(os.getpid()))

    def command(self, argv, *, body=None, timeout=3600, check=True):
        result = subprocess.run(argv, input=body, capture_output=True, text=True,
                                env=self.environment, timeout=timeout, check=False)
        if check and result.returncode:
            # Do not surface SQL, environment, or token-bearing Docker output.
            raise RuntimeError('rehearsal_command_failed')
        return result

    def docker(self, *arguments, **kwargs):
        return self.command(['docker', '--context', 'default', *arguments], **kwargs).stdout.strip()

    def sql(self, statement, parameters=None):
        return self._sql(statement, parameters, user=USER)

    def observe(self, statement, parameters=None):
        """Read probes survive application-role session recycling at either fence."""
        return self._sql(statement, parameters, user=OBSERVER_USER)

    def _sql(self, statement, parameters, *, user):
        started = time.monotonic()
        result = self.docker('exec', '-i', self.container, 'psql', '-X', '--no-psqlrc',
                             '--no-password', '-U', user, '-d', DATABASE, '-Atq',
                             '--set', 'ON_ERROR_STOP=1', '--file=-',
                             body=bind_sql(statement, parameters or {}))
        self.statements.append({'statement_sha256': hashlib.sha256(statement.encode()).hexdigest(),
                                'duration_seconds': time.monotonic() - started})
        return result

    def start(self):
        labels = ['--label', 'edfinder.purge-rehearsal=' + self.token,
                  '--label', 'io.ed-finder.purge-rehearsal=true',
                  '--label', 'io.ed-finder.purge-rehearsal.run-id=' + self.run_id]
        self.docker('volume', 'create', *labels, self.volume)
        self.docker('run', '--detach', '--name', self.container, '--hostname', self.container, *labels,
                    '--network', 'none', '--mount', 'type=volume,src=' + self.volume + ',dst=/var/lib/postgresql',
                    '--env', 'POSTGRES_USER=' + USER, '--env', 'POSTGRES_DB=' + DATABASE,
                    '--env', 'POSTGRES_HOST_AUTH_METHOD=trust', '--shm-size', '256m',
                    IMAGE, '-c', 'wal_level=replica', '-c', 'archive_mode=on',
                    '-c', 'archive_command=/bin/true', '-c', 'autovacuum=on',
                    '-c', 'max_wal_size=1GB', '-c', 'checkpoint_timeout=5min',
                    '-c', 'shared_buffers=256MB', '-c', 'maintenance_work_mem=256MB')
        deadline = time.monotonic() + 120
        # The image's first-start initdb runs a temporary server that answers on
        # the Unix socket only (listen_addresses=''), then restarts. Readiness
        # over container loopback TCP is answered only by the final server.
        while self.command(['docker', '--context', 'default', 'exec', self.container,
                            'pg_isready', '-h', '127.0.0.1', '-p', '5432',
                            '-U', USER, '-d', DATABASE], check=False).returncode:
            if time.monotonic() > deadline:
                raise RuntimeError('postgres_start_timeout')
            time.sleep(0.2)
        self.sql("SELECT format('COMMENT ON DATABASE edfinder_purge_rehearsal IS %L',%(marker)s) \\gexec",
                 {'marker': 'edfinder-disposable-purge-rehearsal:' + self.token})

    def migrate(self):
        for line in (ROOT / 'sql/v3/migration-manifest.txt').read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            digest, name, relative = line.split()
            path = ROOT / 'sql' / relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('migration_manifest_hash_mismatch')
            # Migrations contain their own BEGIN/COMMIT; loading the committed
            # bytes unchanged also exercises 016's actual capability install.
            self.sql(path.read_text())
            self.sql('INSERT INTO v3_meta.schema_migration(migration_name,migration_sha256) '
                     'VALUES(%(name)s,decode(%(digest)s,\'hex\'));', {'name': name, 'digest': digest})
            if name == controller.MIGRATION:
                break
        else:
            raise ValueError('migration_016_missing')
        # Only this private container owns the role. Grant table reads after
        # migrations so monitoring never needs application/executor privileges.
        self.sql(OBSERVER_SETUP)

    def seed(self):
        self.sql(seed.METADATA)
        identifiers = {key: value[0] for key, value in controller.TARGETS.items()}
        identifiers[controller.PUBLISHED_KEY] = controller.PUBLISHED_ID
        for key, generation in identifiers.items():
            systems = self.counts['system_rating_vector'][key]
            bodies = self.counts['body_mechanics'][key]
            parameters = dict(generation=generation, key=key, systems=systems, bodies=bodies)
            # The survivor's Search rows are a published product built after
            # its ratings base was published, exactly as production got them.
            survivor = key == controller.PUBLISHED_KEY
            target_search = self.counts['system_search'][key] and not survivor
            self.sql(seed.GENERATION, parameters)
            if target_search:
                self.sql(seed.SEARCH_PRODUCT, parameters)
            for relation, statement in (('system_rating_vector', seed.VECTOR), ('body_mechanics', seed.BODY),
                                        ('economy_opportunity', seed.ECONOMY), ('system_search', seed.SEARCH)):
                if survivor and relation == 'system_search':
                    continue
                self.insert(statement, parameters, self.counts[relation][key])
            if target_search:
                self.sql(seed.SEARCH_PRODUCT_READY, {'generation': generation})
            if key != 'ratings_v4_prod_p4':
                self.sql(seed.FINALIZE, {'generation': generation})
            if survivor:
                self.sql(seed.PUBLISH, {'generation': generation})
                self.publish_survivor_products(generation)
        self.sql('ANALYZE; CHECKPOINT;')
        for relation in RELATIONS:
            actual = json.loads(self.sql('SELECT COALESCE(json_object_agg(derived_generation_id::text,n),\'{}\') '
                                         'FROM (SELECT derived_generation_id,count(*) n FROM v3_derived.' + relation +
                                         ' GROUP BY derived_generation_id) counted;'))
            for key, generation in identifiers.items():
                if actual.get(generation, 0) != self.counts[relation][key]:
                    raise ValueError('seed_count_mismatch')
        published = json.loads(self.sql(seed.SURVIVOR_PUBLICATION, {'generation': controller.PUBLISHED_ID}))
        expected = {code: {'version': version, 'state': 'READY', 'status': 'VERIFIED',
                           'expected_rows': self.survivor_rows(code), 'published': True}
                    for code, version in seed.SURVIVOR_PRODUCTS}
        if (published.get('products') != expected or published.get('audit_rows') != len(expected)
                or published.get('search_rows') != self.survivor_rows('system_search')
                or published.get('archetype_rows') != self.survivor_rows('system_archetype')
                or published.get('app_search_rows') != self.survivor_rows('system_search')
                or published.get('app_archetype_rows') != self.survivor_rows('system_archetype')):
            raise ValueError('seed_survivor_publication_unproven')

    def insert(self, statement, parameters, count):
        for first in range(1, count + 1, SEED_BATCH_ROWS):
            self.sql(statement, {**parameters, 'first': first, 'last': min(count, first + SEED_BATCH_ROWS - 1)})

    def survivor_rows(self, code):
        # Search survivors are part of the relation counts the receipt binds;
        # archetype rows reference one survivor rating vector each.
        rows = (self.counts['system_search'][controller.PUBLISHED_KEY] if code == 'system_search'
                else self.survivors[code])
        if not 0 < rows <= self.counts['system_rating_vector'][controller.PUBLISHED_KEY]:
            raise ValueError('seed_survivor_population_invalid')
        return rows

    def publish_survivor_products(self, generation):
        """Register, build, validate and publish both Finder products (015)."""
        for code, version in seed.SURVIVOR_PRODUCTS:
            rows = self.survivor_rows(code)
            self.sql(seed.SURVIVOR_PRODUCT, {'generation': generation, 'product': code,
                                             'version': version, 'rows': rows})
            self.insert(seed.SEARCH if code == 'system_search' else seed.ARCHETYPE,
                        {'generation': generation}, rows)
            self.sql(seed.PRODUCT_READY, {'generation': generation, 'product': code})
        self.sql(seed.PUBLISH_PRODUCTS, {'generation': generation})

    def survivor_control_rewrite(self):
        """Rewrite the survivor-only Search relation once more, after complete.

        The governed rewrite copied the published survivors and also scanned
        the deleted target tuples. This unaudited VACUUM in the disposable
        fixture copies the same survivors with no dead target tuples, so the
        receipt can separate survivor work from target work. Server clock
        bounds the statement; free-space samples bound its disk peak.
        """
        self.sql('CHECKPOINT;')
        samples, failures, stop = [self.free_bytes()], [], threading.Event()
        def sample():
            while not stop.is_set():
                try:
                    samples.append(self.free_bytes())
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
                    failures.append('filesystem_sampling_failed')
                    return
                stop.wait(SAMPLE_SECONDS)
        worker = threading.Thread(target=sample)
        worker.start()
        try:
            clock = self.sql(SURVIVOR_CONTROL_SQL).split()
        finally:
            stop.set()
            worker.join(timeout=30)
        samples.append(self.free_bytes())
        if failures or worker.is_alive() or len(clock) != 2:
            raise RuntimeError('survivor_control_rewrite_unmeasured')
        seconds = float(clock[1]) - float(clock[0])
        if not seconds > 0:
            raise RuntimeError('survivor_control_rewrite_unmeasured')
        receipt = evidence.seal({'phase': 'survivor-control-rewrite-system-search', 'container': self.container,
                                 'sample_interval_minimum_seconds': SAMPLE_SECONDS,
                                 'sample_transport': 'docker_exec_stat', 'free_bytes_samples': samples,
                                 'peak_growth_bytes': maximum_drawdown(samples), 'server_seconds': seconds})
        path = self.output / 'survivor-control-rewrite-system-search-filesystem-samples.json'
        path.write_text(evidence.canonical_json(receipt) + '\n')
        self.filesystem_receipts.append({'path': path.name, 'content_sha256': receipt['content_sha256']})
        return seconds, maximum_drawdown(samples), len(samples)

    def free_bytes(self):
        fields = self.docker('exec', self.container, 'stat', '-f', '-c', '%a %S', '/var/lib/postgresql').split()
        if len(fields) != 2 or not all(value.isdecimal() for value in fields):
            raise ValueError('filesystem_sample_unavailable')
        return int(fields[0]) * int(fields[1])

    def action_argv(self, mode):
        argv = ['bash', str(ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), mode,
                '--rehearsal-container', self.container, '--rehearsal-token', self.token]
        # Mirror the controller's admission exactly: status takes no plan and
        # may take the verification; authorize/verify take only the plan.
        phase = mode == 'restore-services' or mode.startswith(('delete-', 'rewrite-', 'abort-relation-'))
        admitted = {'plan': mode in ('authorize', 'verify-system-archetype-empty', 'complete') or phase,
                    'verification': mode in ('status', 'complete') or phase}
        for flag, proof in (('plan', self.plan), ('verification', self.verification)):
            if proof is not None and admitted[flag]:
                argv += ['--' + flag, str(proof[0]), '--' + flag + '-sha256', proof[1]]
        if mode.startswith(('delete-', 'rewrite-')):
            argv += ['--wall-clock-seconds', '1800']
        return argv

    def action(self, mode, *, measure=False, allow_partial_delete=False):
        self.call_number += 1
        argv = self.action_argv(mode)
        samples = []
        batch_observations = []
        failures = []
        stop = threading.Event()
        def sample():
            while not stop.is_set():
                try:
                    free = self.free_bytes()
                    samples.append(free)
                    if mode.startswith('delete-'):
                        event = int(self.observe("SELECT COALESCE(max(event_sequence),0) FROM "
                                             "v3_meta.derived_generation_purge_event WHERE event_kind='BATCH_STARTED';"))
                        batch_observations.append((event, free))
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
                    failures.append('filesystem_sampling_failed')
                    return
                stop.wait(SAMPLE_SECONDS)
        worker = threading.Thread(target=sample) if measure else None
        if worker:
            free = self.free_bytes()
            samples.append(free)
            if mode.startswith('delete-'):
                event = int(self.observe("SELECT COALESCE(max(event_sequence),0) FROM "
                                     "v3_meta.derived_generation_purge_event WHERE event_kind='BATCH_STARTED';"))
                batch_observations.append((event, free))
            worker.start()
        started = time.monotonic()
        try:
            result = self.command(argv, check=False, timeout=3600)
        finally:
            stop.set()
            if worker:
                worker.join(timeout=30)
        duration = time.monotonic() - started
        if worker:
            free = self.free_bytes()
            samples.append(free)
            if mode.startswith('delete-'):
                event = int(self.observe("SELECT COALESCE(max(event_sequence),0) FROM "
                                     "v3_meta.derived_generation_purge_event WHERE event_kind='BATCH_STARTED';"))
                batch_observations.append((event, free))
        if failures or worker and worker.is_alive():
            raise RuntimeError('filesystem_sampling_failed')
        report = json.loads(result.stdout)
        self.statements.extend({**item, 'phase': mode} for item in report.get('statement_durations', []))
        self.statements.append({'phase': mode, 'kind': 'action_wall_clock', 'duration_seconds': duration})
        path = self.output / f'{self.call_number:03d}-{mode}.json'
        path.write_text(evidence.canonical_json(report) + '\n')
        evidence.load_sealed(path)
        if measure:
            sample_receipt = evidence.seal({
                'phase': mode, 'container': self.container,
                'sample_interval_minimum_seconds': SAMPLE_SECONDS,
                'sample_transport': 'docker_exec_stat_and_batch_ledger_observation',
                'free_bytes_samples': samples, 'batch_event_and_free_bytes_samples': batch_observations,
                'peak_growth_bytes': (batch_peak_growth(batch_observations) if mode.startswith('delete-')
                                      else maximum_drawdown(samples)),
                'caveat': 'shorter_transients_may_be_unobserved_fast_batches_conservatively_grouped'})
            sample_path = self.output / f'{self.call_number:03d}-{mode}-filesystem-samples.json'
            sample_path.write_text(evidence.canonical_json(sample_receipt) + '\n')
            self.filesystem_receipts.append({'path': sample_path.name,
                                             'content_sha256': sample_receipt['content_sha256']})
        # A bounded delete may stop between committed batches. Only its exact
        # non-integrity budget stop, with the loop joined and writers restored,
        # is safe to redispatch; every other stopped action fails the rehearsal.
        partial = (allow_partial_delete and mode.startswith('delete-')
                   and report.get('failures') == ['delete_wall_clock_budget_exhausted']
                   and report.get('integrity_failed') is False
                   and report.get('runner_state', {}).get('loop_exited') is True
                   and isinstance(report.get('writer_restore'), dict)
                   and report['writer_restore'].get('verified') is True
                   and bool(report.get('failed_stop_recorded')))
        if (result.returncode or report.get('status') != 'success') and not partial:
            # Failure codes are fixed identifiers; anything else is withheld.
            codes = report.get('failures') if isinstance(report.get('failures'), list) else []
            self.refused_action = {'mode': mode, 'report': path.name, 'failures': [
                code for code in codes if isinstance(code, str)
                and re.fullmatch('[A-Za-z0-9_,]{1,120}', code)][:20]}
            raise RuntimeError('real_action_refused_' + mode.replace('-', '_'))
        peak = batch_peak_growth(batch_observations) if mode.startswith('delete-') else maximum_drawdown(samples)
        return report, path, duration, peak, len(samples)

    def journey(self):
        report, path, *_ = self.action('plan')
        self.plan = (path, report['content_sha256'])
        self.action('authorize')
        report, path, *_ = self.action('verify-system-archetype-empty')
        self.verification = (path, report['content_sha256'])
        measurements, raws = {}, {}
        split = None
        for name, relation in controller.RELATIONS.items():
            heap = int(self.sql('SELECT pg_total_relation_size(%(relation)s::regclass);',
                                {'relation': 'v3_derived.' + relation}))
            total_rows = sum(self.counts[relation][key] for key in controller.TARGETS)
            deleted = 0
            delete_seconds = 0.0
            delete_dispatch_seconds = 0.0
            batch_peak = samples = 0
            for _ in range(1000):
                report, _, elapsed, peak, count = self.action('delete-' + name, measure=True, allow_partial_delete=True)
                deleted += report.get('rows_affected_this_run') or 0
                delete_dispatch_seconds += elapsed
                delete_seconds += sum(item['duration_seconds'] for item in report.get('statement_durations', [])
                                      if item['kind'] == 'payload_batch')
                batch_peak = max(batch_peak, peak)
                samples += count
                remaining = int(self.sql('SELECT count(*) FROM v3_derived.' + relation +
                                        ' WHERE derived_generation_id<>%(published)s::uuid;',
                                        {'published': controller.PUBLISHED_ID}))
                if remaining == 0:
                    break
            else:
                raise RuntimeError('delete_dispatch_bound_exceeded')
            report, _, elapsed, peak, count = self.action('rewrite-' + name, measure=True)
            rewrite_seconds = sum(item['duration_seconds'] for item in report.get('statement_durations', [])
                                  if item['kind'] == 'vacuum_full_analyze')
            if deleted != total_rows or delete_seconds <= 0 or rewrite_seconds <= 0:
                raise ValueError('payload_count_or_statement_timing_unproven')
            raw = dict(deleted_rows=total_rows, delete_seconds=delete_dispatch_seconds,
                       batch_limit=self.plan_batch_limit(relation), batch_peak_bytes=batch_peak,
                       rewrite_seconds=rewrite_seconds, rewrite_peak_bytes=peak, heap_index_bytes=heap,
                       delete_dispatch_seconds=delete_dispatch_seconds, rewrite_dispatch_seconds=elapsed,
                       delete_statement_seconds=delete_seconds,
                       delete_statement_rows_per_second=total_rows / delete_seconds,
                       delete_rate_basis='sustained_dispatch_wall_clock_including_safety_gates',
                       filesystem_sample_count=samples + count,
                       autovacuum_budget_source='heap_plus_index_lower_bound',
                       delete_rows_reported=deleted,
                       batch_measurement_scope='sampled_batch_boundaries_with_overlapping_samples',
                       rewrite_measurement_scope='entire_dispatch_conservative_bound_for_vacuum_full_analyze',
                       sample_interval_seconds=SAMPLE_SECONDS)
            raws[relation] = raw
            if relation == 'system_search':
                survivors = self.counts[relation][controller.PUBLISHED_KEY]
                after = int(self.sql('SELECT pg_total_relation_size(%(relation)s::regclass);',
                                     {'relation': 'v3_derived.' + relation}))
                split = dict(survivor_rows=survivors, target_rows=total_rows,
                             heap_index_bytes_before_delete=heap,
                             survivor_heap_index_bytes_after_rewrite=after,
                             governed_rewrite_seconds=rewrite_seconds, governed_rewrite_peak_bytes=peak,
                             target_delete_seconds=delete_dispatch_seconds)
        self.action('complete')
        seconds, control_peak, count = self.survivor_control_rewrite()
        split.update(survivor_rewrite_seconds=seconds, survivor_rewrite_peak_bytes=control_peak)
        search = raws['system_search']
        # The plan carries the larger of the two measured peaks (fail-closed).
        search['rewrite_peak_bytes'] = max(search['rewrite_peak_bytes'], control_peak)
        search['filesystem_sample_count'] += count
        for relation, raw in raws.items():
            measurements[relation] = figures.relation_figures(raw, self.proportion)
        measurements['system_search']['survivor_target_split'] = figures.search_split_figures(split, self.proportion)
        return measurements

    def plan_batch_limit(self, relation):
        return json.loads(self.plan[0].read_text())['reviewed_plan']['delete'][relation]['batch_limit']

    def cleanup(self):
        # Only identities created by this instance are eligible; label/token
        # equality is checked before removal even on failure paths.
        for kind, name in (('container', self.container), ('volume', self.volume)):
            result = self.command(['docker', '--context', 'default', kind, 'inspect', name], check=False)
            if result.returncode:
                # A daemon/transport failure is not proof of absence. A fresh,
                # successful list must independently prove our name is gone.
                self.verify_absent(kind, name)
                continue
            item = json.loads(result.stdout)[0]
            labels = item['Config']['Labels'] if kind == 'container' else item['Labels']
            if labels.get('edfinder.purge-rehearsal') != self.token:
                raise ValueError('cleanup_marker_mismatch')
            arguments = ('rm', '--force', name) if kind == 'container' else ('volume', 'rm', name)
            self.docker(*arguments)
            self.verify_absent(kind, name)

    def verify_absent(self, kind, name):
        arguments = (('container', 'ls', '--all', '--format', '{{.Names}}') if kind == 'container'
                     else ('volume', 'ls', '--format', '{{.Name}}'))
        if name in self.docker(*arguments).splitlines():
            raise RuntimeError('cleanup_resource_still_present')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scale', choices=tuple(SCALE_SYSTEMS), default='smoke')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(argv)
    if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 14):
        parser.error('CPython 3.14 required')
    harness = Harness(args.scale, args.run_id, args.output_dir)
    receipt = dict(schema_version=figures.SCHEMA, operation='v3-derived-purge-rehearsal',
                   status='stopped', created_at=datetime.now(timezone.utc).isoformat(),
                   scale=args.scale, source_git_sha=harness.command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).stdout.strip(),
                   **figures.code_identity(),
                   image_digest=IMAGE, production_proportion=harness.proportion,
                   lifecycle_receipt_sha256=hashlib.sha256(RECEIPT_PATH.read_bytes()).hexdigest(),
                   row_counts=harness.counts, survivor_products=harness.survivors, per_relation={},
                   crash_scenarios={name: {'passed': False, 'reason': 'not_executed'} for name in CRASH_SCENARIOS},
                   gate_10_crash_rehearsal_passed=False,
                   settings={}, statement_durations=harness.statements,
                   filesystem_sample_receipts=harness.filesystem_receipts, failures=[])
    receipt['seeding'] = {'source': str(evidence.STEP0_RECEIPT),
                          'canonical_systems_in_source': 198_528_286,
                          'requested_systems': SCALE_SYSTEMS[args.scale],
                          'batch_rows': SEED_BATCH_ROWS,
                          'shape': 'typed synthetic vectors, mechanics and opportunities with generation-specific receipt row proportions',
                          'survivor_search_rows': 'published system_search and system_archetype products on the '
                                                  'surviving generation, one row per surviving system, READY/VERIFIED '
                                                  'and published through 015 publish_derived_product as in production',
                          'survivor_product_versions': dict(seed.SURVIVOR_PRODUCTS),
                          'search_split_method': 'governed rewrite minus a survivor-only VACUUM FULL after complete',
                          'autovacuum_budget_source': 'heap_plus_index_lower_bound',
                          'autovacuum_budget_caveat': 'equivalent-copy maintenance not measured; current whole relation heap+index bytes used as design lower bound'}
    try:
        harness.phase = 'start'
        harness.start()
        harness.phase = 'migrate'
        harness.migrate()
        harness.phase = 'seed'
        harness.seed()
        harness.phase = 'journey'
        receipt['settings'] = json.loads(harness.sql("SELECT json_object_agg(name,setting) FROM pg_settings WHERE name IN "
                         "('server_version','wal_level','archive_mode','archive_command','autovacuum','max_wal_size',"
                         "'checkpoint_timeout','shared_buffers','maintenance_work_mem','fsync','full_page_writes');"))
        receipt['settings']['archive_caveat'] = 'synthetic archive_command=/bin/true; no durable archive or replication'
        receipt['per_relation'] = harness.journey()
        # Free the measured fixture before starting independently marked crash
        # fixtures. Each interruption gets a fresh database and its own cleanup.
        harness.cleanup()
        from scripts.rehearsal.v3_purge_crashes import run_crashes
        harness.phase = 'crash_scenarios'
        receipt['crash_scenarios'] = run_crashes(Harness, args.scale, args.run_id, harness.output)
        receipt['gate_10_crash_rehearsal_passed'] = all(
            receipt['crash_scenarios'][name].get('passed') is True for name in CRASH_SCENARIOS)
        receipt['status'] = 'success' if receipt['gate_10_crash_rehearsal_passed'] else 'stopped'
        if receipt['status'] != 'success':
            receipt['failures'].append('crash_gate_failed')
        figures.validate(receipt, production=False)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        receipt['status'] = 'stopped'
        code = str(exc)
        receipt['failures'].append(code if re.fullmatch('[a-zA-Z0-9_]+', code) else 'rehearsal_failed')
        if harness.refused_action is not None:
            receipt['refused_action'] = harness.refused_action
        receipt['stopped_phase'] = harness.phase
    finally:
        try:
            harness.cleanup()
            receipt['cleanup_verified'] = True
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
            receipt.update(status='stopped', cleanup_verified=False)
            receipt['failures'].append('cleanup_not_verified')
            receipt.setdefault('stopped_phase', 'cleanup')
        # Every stopped outcome names its stage, including a failed crash gate
        # that returns normally rather than raising.
        if receipt['status'] != 'success':
            receipt.setdefault('stopped_phase', harness.phase)
        sealed = evidence.seal(receipt)
        (harness.output / 'rehearsal-receipt.json').write_text(evidence.canonical_json(sealed) + '\n')
        print(evidence.canonical_json({'status': receipt['status'], 'scale': args.scale,
              'content_sha256': sealed['content_sha256'], 'gate_10_crash_rehearsal_passed':
              receipt['gate_10_crash_rehearsal_passed'], 'failures': receipt['failures'],
              'refused_action': receipt.get('refused_action'), 'stopped_phase': receipt.get('stopped_phase')}))
    return 0 if receipt['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
