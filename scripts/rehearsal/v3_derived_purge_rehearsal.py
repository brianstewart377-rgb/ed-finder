#!/usr/bin/env python3.14
"""Disposable PG18 measurements using the governed purge action itself.

No port is published, no external network exists, and every database command
runs inside the one marked container. This module has no DSN/host argument.
The journey runs the copy-and-drop route (migration 019) through the real
action, relation by relation in 019's order: read-only preflight, copy-R until
the staging copy is verified (chunks, index build, VACUUM FREEZE, verify),
swap-R (swap, FK validation, Finder smoke and, for economy_opportunity, the
planner-statistics recalibration) while a separate read-only Finder reader
measures read stalls, then drop-R; finally complete. Filesystem and temp-file
samples bound each copy's free-space peak, including WAL on its data mount.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
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
COPY_MIGRATION = '019_v3_purge_copy_and_drop.sql'
SEED_BATCH_ROWS = 50_000
SAMPLE_SECONDS = 0.1
READ_INTERVAL_SECONDS = 0.05
COPY_WALL_CLOCK_SECONDS = 1800
COPY_DISPATCH_LIMIT = 200
ACTION_TIMEOUT_SECONDS = 10_800
ARCHIVER_READY_SECONDS = 120
CRASH_SCENARIOS = figures.CRASH_SCENARIOS
OBSERVER_QUERY_SECONDS = 30
# pg_monitor (which includes pg_read_all_stats) lets the observer sample the
# server's temporary files (pg_ls_tmpdir) without any write privilege.
OBSERVER_SETUP = """
CREATE ROLE edfinder_purge_observer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE edfinder_purge_observer SET default_transaction_read_only=on;
GRANT pg_monitor TO edfinder_purge_observer;
GRANT USAGE ON SCHEMA v3_meta,v3_derived,v3_spatial,v3_app TO edfinder_purge_observer;
GRANT SELECT ON ALL TABLES IN SCHEMA v3_meta,v3_derived,v3_spatial,v3_app TO edfinder_purge_observer;
"""
# The reviewed production prerequisite the copy runbook names (019 does not
# grant it): long phases bound their temporary files with SET LOCAL.
EXECUTOR_PARAMETER_SETUP = 'GRANT SET ON PARAMETER temp_file_limit TO v3_derived_purge_executor;'
TEMP_SAMPLE_SQL = 'SELECT COALESCE(sum(size),0)::bigint FROM pg_ls_tmpdir();'
TEMP_WRITTEN_SQL = 'SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database();'
ARCHIVER_SQL = "SELECT pg_switch_wal() IS NOT NULL, (SELECT last_archived_wal IS NOT NULL FROM pg_stat_archiver);"
ARCHIVED_SQL = 'SELECT last_archived_wal IS NOT NULL FROM pg_stat_archiver;'
# One read per Finder-facing surface that each relation's swap locks: the
# published Search and economy views, and the published generation's rows.
FINDER_READS = {
    'system_search': 'SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_search ORDER BY system_id64 LIMIT 25) s;',
    'economy_opportunity': ("SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.economy_opportunity WHERE "
                            "derived_generation_id='" + controller.PUBLISHED_ID + "' LIMIT 25) s;"),
    'body_mechanics': ("SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.body_mechanics WHERE "
                       "derived_generation_id='" + controller.PUBLISHED_ID + "' LIMIT 25) s;"),
    'system_rating_vector': 'SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_economy_rating LIMIT 25) s;',
}
# Bytes and row counts read by the owner around each step (fixed identifiers).
RELATION_BYTES_SQL = 'SELECT COALESCE(pg_total_relation_size(to_regclass(%(relation)s)),0);'
TARGET_ROWS_SQL = {relation: ('SELECT count(*) FROM v3_derived.' + relation
                              + " WHERE derived_generation_id<>'" + controller.PUBLISHED_ID + "';")
                   for relation in RELATIONS}


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


class ObserverSession:
    """One read-only observer login that answers one line per fixed query.

    psql flushes each result when reading a pipe. A dead client, an error
    (ON_ERROR_STOP) or a silent server ends the session; it is never reopened
    while an action runs, because a new login is itself a competing backend.
    """

    def __init__(self, argv, env):
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, env=env, text=True, bufsize=1)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def query(self, statement):
        if '\n' in statement or not statement.endswith(';'):
            raise ValueError('observer_statement_invalid')
        try:
            self.process.stdin.write(statement + '\n')
            self.process.stdin.flush()
            line = self.lines.get(timeout=OBSERVER_QUERY_SECONDS)
        except (OSError, ValueError, queue.Empty):
            raise RuntimeError('observer_session_failed') from None
        if line is None:
            raise RuntimeError('observer_session_failed')
        return line.strip()

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)


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

    def observer_session(self):
        """Open the observer login before an action starts; see action()."""
        return ObserverSession(['docker', '--context', 'default', 'exec', '-i', self.container, 'psql', '-X',
                                '--no-psqlrc', '--no-password', '-U', OBSERVER_USER, '-d', DATABASE, '-Atq',
                                '--set', 'ON_ERROR_STOP=1'], self.environment)

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
        applied = []
        for line in (ROOT / 'sql/v3/migration-manifest.txt').read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            digest, name, relative = line.split()
            path = ROOT / 'sql' / relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('migration_manifest_hash_mismatch')
            # Migrations contain their own BEGIN/COMMIT; loading the committed
            # bytes unchanged also exercises 016's and 019's capability installs.
            self.sql(path.read_text())
            self.sql('INSERT INTO v3_meta.schema_migration(migration_name,migration_sha256) '
                     'VALUES(%(name)s,decode(%(digest)s,\'hex\'));', {'name': name, 'digest': digest})
            applied.append(name)
        # The whole reviewed manifest, as production's ledger holds it.
        if controller.MIGRATION not in applied or COPY_MIGRATION not in applied:
            raise ValueError('migration_016_or_019_missing')
        # Only this private container owns the role. Grant table reads after
        # migrations so monitoring never needs application/executor privileges.
        self.sql(OBSERVER_SETUP)
        self.sql(EXECUTOR_PARAMETER_SETUP)

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
            # Build receipts as the builder records them, while still BUILDING.
            self.sql(seed.CHUNK_RECEIPTS, {'generation': generation})
            if target_search:
                self.sql(seed.SEARCH_PRODUCT_READY, {'generation': generation})
            if key != 'ratings_v4_prod_p4':
                self.sql(seed.FINALIZE, {'generation': generation})
            if survivor:
                self.sql(seed.PUBLISH, {'generation': generation})
                self.publish_survivor_products(generation)
        self.sql(seed.PLANNER_STATISTICS)
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
        self.archived()

    def archived(self):
        """The copy route reads the archiver's position: complete one segment."""
        self.sql(ARCHIVER_SQL)
        deadline = time.monotonic() + ARCHIVER_READY_SECONDS
        while self.sql(ARCHIVED_SQL) != 't':
            if time.monotonic() >= deadline:
                raise RuntimeError('rehearsal_archiver_not_ready')
            time.sleep(0.5)

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
            if code == 'system_search':
                self.sql(seed.SEARCH_CHUNK_RECEIPTS, {'generation': generation, 'version': version})
            self.sql(seed.PRODUCT_READY, {'generation': generation, 'product': code})
        self.sql(seed.PUBLISH_PRODUCTS, {'generation': generation})

    def free_bytes(self):
        fields = self.docker('exec', self.container, 'stat', '-f', '-c', '%a %S', '/var/lib/postgresql').split()
        if len(fields) != 2 or not all(value.isdecimal() for value in fields):
            raise ValueError('filesystem_sample_unavailable')
        return int(fields[0]) * int(fields[1])

    def number(self, statement, parameters=None):
        value = self.sql(statement, parameters)
        if not value.isdecimal():
            raise ValueError('rehearsal_measurement_unavailable')
        return int(value)

    def action_argv(self, mode):
        argv = ['bash', str(ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), mode,
                '--rehearsal-container', self.container, '--rehearsal-token', self.token]
        # Mirror the controller's admission exactly: status takes no plan and
        # may take the verification; authorize/verify take only the plan; a
        # preflight takes only the plan; every other copy mode and complete
        # take both.
        copy_mode = controller.is_copy_mode(mode)
        preflight = mode.startswith('preflight-')
        admitted = {'plan': mode in ('authorize', 'verify-system-archetype-empty', 'complete') or copy_mode,
                    'verification': mode in ('status', 'complete') or (copy_mode and not preflight)}
        for flag, proof in (('plan', self.plan), ('verification', self.verification)):
            if proof is not None and admitted[flag]:
                argv += ['--' + flag, str(proof[0]), '--' + flag + '-sha256', proof[1]]
        if mode.startswith('copy-'):
            argv += ['--wall-clock-seconds', str(COPY_WALL_CLOCK_SECONDS)]
        return argv

    def action(self, mode, *, measure=False, reader=None):
        """Run the real action once; optionally sample free and temp-file bytes
        (``measure``) and run one Finder read loop (``reader``) beside it.

        Each sampler or reader uses its own observer login opened before the
        action starts and closed after it exits.
        """
        self.call_number += 1
        argv = self.action_argv(mode)
        samples, temp_samples, reads, failures = [], [], [], []
        stop = threading.Event()
        sampler_session = self.observer_session() if measure else None
        reader_session = self.observer_session() if reader else None
        def sample():
            while not stop.is_set():
                try:
                    samples.append(self.free_bytes())
                    temp_samples.append(int(sampler_session.query(TEMP_SAMPLE_SQL)))
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
                    failures.append('filesystem_sampling_failed')
                    return
                stop.wait(SAMPLE_SECONDS)
        def read():
            while not stop.is_set():
                started = time.monotonic()
                try:
                    reader_session.query(reader)
                except (ValueError, RuntimeError):
                    failures.append('finder_reader_failed')
                    return
                reads.append(time.monotonic() - started)
                stop.wait(READ_INTERVAL_SECONDS)
        workers = [threading.Thread(target=target) for target, enabled in
                   ((sample, measure), (read, reader)) if enabled]
        try:
            if measure:
                samples.append(self.free_bytes())
                temp_samples.append(int(sampler_session.query(TEMP_SAMPLE_SQL)))
            for worker in workers:
                worker.start()
            started = time.monotonic()
            try:
                result = self.command(argv, check=False, timeout=ACTION_TIMEOUT_SECONDS)
            finally:
                stop.set()
                for worker in workers:
                    worker.join(timeout=60)
            duration = time.monotonic() - started
            if any(worker.is_alive() for worker in workers):
                # Never share a session with a worker still waiting on it.
                raise RuntimeError('rehearsal_sampler_did_not_stop')
            if measure:
                samples.append(self.free_bytes())
                temp_samples.append(int(sampler_session.query(TEMP_SAMPLE_SQL)))
        finally:
            for session in (sampler_session, reader_session):
                if session is not None:
                    session.close()
        if failures:
            raise RuntimeError(failures[0])
        report = json.loads(result.stdout)
        self.statements.extend({**item, 'phase': mode} for item in report.get('statement_durations', []))
        self.statements.append({'phase': mode, 'kind': 'action_wall_clock', 'duration_seconds': duration})
        path = self.output / f'{self.call_number:03d}-{mode}.json'
        path.write_text(evidence.canonical_json(report) + '\n')
        evidence.load_sealed(path)
        if measure or reader:
            sample_receipt = evidence.seal({
                'phase': mode, 'container': self.container,
                'sample_interval_minimum_seconds': SAMPLE_SECONDS,
                'sample_transport': 'docker_exec_stat_and_observer_pg_ls_tmpdir',
                'free_bytes_samples': samples, 'temp_file_bytes_samples': temp_samples,
                'finder_read_seconds': reads,
                'caveat': 'shorter_transients_may_be_unobserved'})
            sample_path = self.output / f'{self.call_number:03d}-{mode}-samples.json'
            sample_path.write_text(evidence.canonical_json(sample_receipt) + '\n')
            self.filesystem_receipts.append({'path': sample_path.name,
                                             'content_sha256': sample_receipt['content_sha256']})
        if result.returncode or report.get('status') != 'success':
            # Failure codes are fixed identifiers; anything else is withheld.
            codes = report.get('failures') if isinstance(report.get('failures'), list) else []
            self.refused_action = {'mode': mode, 'report': path.name, 'failures': [
                code for code in codes if isinstance(code, str)
                and re.fullmatch('[A-Za-z0-9_,]{1,120}', code)][:20]}
            raise RuntimeError('real_action_refused_' + mode.replace('-', '_'))
        return {'report': report, 'path': path, 'duration': duration, 'free_bytes_samples': samples,
                'temp_file_bytes_samples': temp_samples, 'finder_read_seconds': reads}

    def authorize(self):
        outcome = self.action('plan')
        self.plan = (outcome['path'], outcome['report']['content_sha256'])
        self.action('authorize')
        outcome = self.action('verify-system-archetype-empty')
        self.verification = (outcome['path'], outcome['report']['content_sha256'])

    def copy_until_verified(self, name, *, measure=False):
        """Dispatch copy-R until 019 records VERIFIED (each dispatch is bounded)."""
        outcomes = []
        for _ in range(COPY_DISPATCH_LIMIT):
            outcome = self.action('copy-' + name, measure=measure)
            outcomes.append(outcome)
            if outcome['report'].get('result') == 'copy_verified_ready_for_swap':
                return outcomes
        raise RuntimeError('copy_dispatch_bound_exceeded')

    def journey(self):
        self.authorize()
        measurements = {}
        for name, relation in controller.RELATIONS.items():
            raw = self.copy_relation(name, relation)
            measurements[relation] = figures.relation_figures(raw, self.proportion)
        self.action('complete')
        for relation in RELATIONS:
            if self.number(TARGET_ROWS_SQL[relation]) != 0:
                raise ValueError('rehearsal_target_rows_remain')
        return measurements

    def copy_relation(self, name, relation):
        """One relation through preflight, copy, swap and drop, measured."""
        self.action('preflight-' + name)
        live_bytes = self.number(RELATION_BYTES_SQL, {'relation': 'v3_derived.' + relation})
        target_rows = self.number(TARGET_ROWS_SQL[relation])
        written_before = self.number(TEMP_WRITTEN_SQL)
        copies = self.copy_until_verified(name, measure=True)
        copy_bytes = self.number(RELATION_BYTES_SQL, {'relation': 'v3_purge_staging.' + relation})
        swap = self.action('swap-' + name, reader=FINDER_READS[relation])
        freed = self.number(RELATION_BYTES_SQL, {'relation': 'v3_retired.' + relation})
        drop = self.action('drop-' + name)
        written_after = self.number(TEMP_WRITTEN_SQL)
        reports = [outcome['report'] for outcome in copies]
        seconds = {phase: sum(step.get('seconds') or 0 for report in reports for step in report.get('copy_steps') or []
                              if step.get('phase') == phase)
                   for phase in ('index_build', 'vacuum_freeze', 'verify')}
        wal = {phase: sum((report.get('wal_phase_bytes') or {}).get(phase) or 0 for report in reports)
               for phase in ('chunk', 'index_build', 'vacuum_freeze', 'verify')}
        swap_report, drop_report = swap['report'], drop['report']
        wal['validate_fks'] = (swap_report.get('wal_phase_bytes') or {}).get('validate_fks')
        wal['drop'] = (drop_report.get('wal_phase_bytes') or {}).get('drop')
        free = [value for outcome in copies for value in outcome['free_bytes_samples']]
        temp = [value for outcome in copies for value in outcome['temp_file_bytes_samples']]
        copied = (reports[-1].get('copy_state_after') or {}).get('rows_total')
        if (type(copied) is not int or copied != self.counts[relation][controller.PUBLISHED_KEY]
                or not swap['finder_read_seconds'] or not isinstance(swap_report.get('swap_attempts'), list)
                or any(type(value) is not int for value in wal.values())):
            raise ValueError('copy_count_or_measurement_unproven')
        fk_seconds = sum(step.get('seconds') or 0 for step in swap_report.get('copy_steps') or []
                         if step.get('phase') == 'validate_fks')
        return dict(
            copied_rows=copied, target_rows=target_rows, live_bytes_before=live_bytes, copy_bytes=copy_bytes,
            copy_peak_bytes=maximum_drawdown(free), temp_file_peak_bytes=max(temp),
            temp_file_written_bytes=max(0, written_after - written_before), freed_bytes=freed,
            swap_attempts=len(swap_report['swap_attempts']), finder_reads_during_swap=len(swap['finder_read_seconds']),
            filesystem_sample_count=len(free),
            copy_seconds=sum(report.get('copy_chunk_statement_seconds') or 0 for report in reports),
            index_build_seconds=seconds['index_build'], vacuum_freeze_seconds=seconds['vacuum_freeze'],
            verify_seconds=seconds['verify'], fk_validation_seconds=fk_seconds,
            swap_lock_hold_seconds=swap_report.get('measured_stall_seconds'),
            finder_read_stall_seconds=max(swap['finder_read_seconds']),
            drop_seconds=drop_report.get('measured_stall_seconds'),
            wal_bytes=wal, copy_dispatches=len(copies),
            sample_interval_seconds=SAMPLE_SECONDS,
            copy_measurement_scope='every_copy_dispatch_sampled_from_before_the_first_chunk',
            temp_file_measurement_scope='sampled_pg_ls_tmpdir_peak_and_pg_stat_database_written_total',
            swap_measurement_scope='swap_statement_seconds_and_concurrent_observer_read_latency')

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
                   route=figures.ROUTE, status='stopped', created_at=datetime.now(timezone.utc).isoformat(),
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
                          'route': 'copy-and-drop (migration 019) through the real action, relation by relation',
                          'build_receipts': 'build_chunk and survivor search_build_chunk receipts recorded from the seeded rows',
                          'planner_statistics': 'economy_opportunity.system_id64 STATISTICS 1000 and n_distinct -0.13, as production'}
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
