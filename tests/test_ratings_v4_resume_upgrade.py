"""Cross-version restart proof using the real old files, not a patched guard."""
from contextlib import contextmanager
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from domain.ratings_v4_canonical import load_source_fixture  # noqa: E402
from scripts.ratings_v4 import production_generation as generation  # noqa: E402
from scripts.ratings_v4 import resume_upgrade  # noqa: E402
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.resume_upgrade import (  # noqa: E402
    LEGACY_CODE, LEGACY_SOURCE_SHA, CommittedPrefix, accept_verified_prefix,
    committed_prefix, verify_origin,
)
from scripts.ratings_v4.run_generation import build_generation  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture(scope='module')
def legacy_root(tmp_path_factory):
    if not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'):
        pytest.skip('isolated PostgreSQL validation URL not set')
    root = tmp_path_factory.mktemp('legacy-v4')
    freeze = 'docs/development/ratings-v4-freeze/manifest.json'
    recovery = 'docs/development/v3-canonical-source-recovery.json'
    paths = {freeze, recovery, *LEGACY_CODE}
    paths.update(json.loads((ROOT / freeze).read_text())['text_files_sha256_lf'])
    paths.update(json.loads((ROOT / recovery).read_text())['files_sha256'])
    for pattern in ('scripts/ratings_v4/*.py', 'docs/development/ratings-v4-freeze/*',
                    'tests/fixtures/ratings_v4_sources/*'):
        paths.update(str(path.relative_to(ROOT)) for path in ROOT.glob(pattern) if path.is_file())
    for name in paths:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name in LEGACY_CODE:
            raw = subprocess.check_output(['git', 'show', f'{LEGACY_SOURCE_SHA}:{name}'], cwd=ROOT)
            assert hashlib.sha256(raw.decode().replace('\r\n', '\n').encode()).hexdigest() == LEGACY_CODE[name]
            destination.write_bytes(raw)
        else:
            shutil.copyfile(ROOT / name, destination)
    return root


def old_run(root, connection, source, *, stop_after=2):
    request = {'database': connection.info.dbname, 'legacy_root': str(root),
               'expected_identity': LEGACY_CODE, 'source': str(source),
               'key': 'upgrade_fixture', 'stop_after': stop_after}
    result = subprocess.run([sys.executable, str(ROOT / 'tests/ratings_v4_legacy_resume_fixture.py')],
                            input=json.dumps(request), text=True, capture_output=True, timeout=90,
                            cwd=root, check=True)
    return json.loads(result.stdout)


@contextmanager
def interrupted_database(tmp_path, legacy_root, *, install_upgrade=True):
    _, _, payloads = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    compressed = gzip.compress(json.dumps([item['system'] for item in payloads]).encode(), mtime=0)
    source = tmp_path / 'galaxy.json.gz'
    source.write_bytes(compressed)

    def prepare(_canonical, metadata):
        metadata['artifact']['content_sha256'] = '\\x' + hashlib.sha256(compressed).hexdigest()
        metadata['artifact']['size_bytes'] = len(compressed)
        return ()

    with canonical_database(prepare=prepare) as (connection, _, _, _):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        if install_upgrade:
            connection.execute((ROOT / 'sql/v3/proposals/007_ratings_v4_code_upgrade.sql').read_text())
            # Load a separately committed policy, never derive expected hashes
            # from the candidate at test time. CI must catch any target drift.
            target = json.loads((ROOT / 'sql/v3/proposals/007_ratings_v4_code_upgrade_target.json').read_text())
            connection.execute('''INSERT INTO v3_meta.derived_code_upgrade_target(
                upgrade_id,code_sha256_lf) VALUES (%s,%s::jsonb)''',
                (target['upgrade_id'], json.dumps(target['code_sha256_lf'])))
        assert old_run(legacy_root, connection, source)['status'] == 'INTERRUPTED'
        identifier, manifest, digest = connection.execute('''SELECT derived_generation_id,
            manifest,manifest_sha256 FROM v3_meta.derived_generation''').fetchone()
        assert manifest['code_sha256_lf'] == LEGACY_CODE
        assert len(committed_prefix(connection, identifier).rows) == 2
        yield connection, source, identifier, manifest, bytes(digest)


def saved_rows(connection, identifier):
    return [generation._read_chunk(connection, identifier, ordinal) for ordinal in (0, 1)]


def resume(connection, source, **kwargs):
    return build_generation(connection, connection, source, 'upgrade_fixture',
                            chunk_size=3, workers=2, **kwargs)


def test_real_old_builder_upgrades_same_generation_without_rewriting_saved_chunks(tmp_path, legacy_root, monkeypatch):
    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, manifest, digest):
        saved = saved_rows(connection, identifier)
        checkpoints = committed_prefix(connection, identifier).rows
        with pytest.raises(ValueError, match='code identity changed'):
            resume(connection, source)
        exported = []
        original = CanonicalSnapshot.export_chunk

        def count_export(self, read_connection, identifiers):
            exported.append(identifiers)
            return original(self, read_connection, identifiers)

        monkeypatch.setattr(CanonicalSnapshot, 'export_chunk', count_export)
        progress = []
        result = resume(connection, source, upgrade_actor='disposable-test', progress=progress.append)
        assert result['derived_generation_id'] == str(identifier)
        assert result['status'] == 'VERIFIED' and result['lifecycle_state'] == 'READY'
        assert result['publication_performed'] is False and result['chunks_written'] == 2
        assert result['chunks_seen'] == 4 and result['chunks_reused'] == 2
        assert len(exported) == 2  # Saved chunks caused no canonical reads or encoding.
        assert [item['chunk_ordinal'] for item in progress if item.get('resume_verified')] == [0, 1]
        assert saved_rows(connection, identifier) == saved
        assert committed_prefix(connection, identifier).rows[:2] == checkpoints
        assert connection.execute('SELECT manifest,manifest_sha256 FROM v3_meta.derived_generation').fetchone() == (manifest, digest)
        audit = result['validation_receipt']['code_upgrade']
        assert audit['prefix_chunks'] == 2 and audit['prefix_systems'] == 6
        assert audit['from_code_sha256_lf'] == LEGACY_CODE
        assert audit['to_code_sha256_lf'] == generation.code_identity()
        assert result['validation_receipt']['every_system_replayed']
        assert resume(connection, source)['chunks_written'] == 0


@pytest.mark.parametrize('rollback', [False, True], ids=['new-builder-resume', 'old-builder-rollback'])
def test_interrupted_upgrade_can_resume_or_roll_back_without_losing_chunks(tmp_path, legacy_root, rollback):
    class StopAfterNewChunk(Exception):
        pass

    def stop(item):
        if item['written']:
            raise StopAfterNewChunk

    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, _, _):
        with pytest.raises(StopAfterNewChunk):
            resume(connection, source, upgrade_actor='disposable-test', progress=stop)
        saved = [generation._read_chunk(connection, identifier, ordinal) for ordinal in range(3)]
        assert len(committed_prefix(connection, identifier).rows) == 3
        if rollback:
            result = old_run(legacy_root, connection, source, stop_after=0)
        else:
            result = resume(connection, source)  # No second approval/registration required.
        assert result['status'] == 'VERIFIED' and result['chunks_written'] == 1
        assert [generation._read_chunk(connection, identifier, ordinal) for ordinal in range(3)] == saved
        assert connection.execute('SELECT count(*) FROM v3_meta.derived_code_upgrade').fetchone()[0] == 1


@pytest.mark.parametrize('fault', ['source-checkpoint', 'chunk-size', 'concurrent-writer'])
def test_bad_prefix_or_moving_frontier_cannot_register_upgrade(tmp_path, legacy_root, fault):
    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, _, _):
        if fault == 'source-checkpoint':
            connection.execute('UPDATE v3_derived.build_chunk SET source_projection_sha256=%s WHERE chunk_ordinal=0',
                               (bytes(32),))

        def progress(item):
            if fault == 'concurrent-writer' and item['chunk_ordinal'] == 1:
                old_run(legacy_root, connection, source, stop_after=3)

        with pytest.raises(ValueError, match='prefix mismatch|frontier changed'):
            build_generation(connection, connection, source, 'upgrade_fixture', workers=2,
                             chunk_size=4 if fault == 'chunk-size' else 3,
                             upgrade_actor='disposable-test', progress=progress)
        assert connection.execute('SELECT count(*) FROM v3_meta.derived_code_upgrade').fetchone()[0] == 0
        assert len(committed_prefix(connection, identifier).rows) == (3 if fault == 'concurrent-writer' else 2)


def test_missing_migration_fails_before_changing_any_rows(tmp_path, legacy_root):
    with interrupted_database(tmp_path, legacy_root, install_upgrade=False) as (connection, source, identifier, _, _):
        with pytest.raises(ValueError, match='migration is not installed'):
            resume(connection, source, upgrade_actor='disposable-test')
        assert len(committed_prefix(connection, identifier).rows) == 2


def test_final_validation_still_detects_corrupt_saved_output(tmp_path, legacy_root):
    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, _, _):
        connection.execute("UPDATE v3_derived.body_mechanics SET body_class=CASE WHEN body_class='Rocky body' THEN 'Water world' ELSE 'Rocky body' END WHERE system_id64=(SELECT min(system_id64) FROM v3_derived.body_mechanics)")
        with pytest.raises(ValueError, match='content checksum mismatch'):
            resume(connection, source, upgrade_actor='disposable-test')
        assert connection.execute('SELECT lifecycle_state FROM v3_meta.derived_generation').fetchone()[0] == 'VALIDATING'


def test_upgrade_attestation_is_immutable_and_rejects_different_target_code(tmp_path, legacy_root, monkeypatch):
    import psycopg

    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, manifest, _):
        resume(connection, source, upgrade_actor='disposable-test')
        for sql in ("UPDATE v3_meta.derived_code_upgrade SET receipt='{}'::jsonb",
                    'DELETE FROM v3_meta.derived_code_upgrade', 'TRUNCATE v3_meta.derived_code_upgrade',
                    "UPDATE v3_meta.derived_code_upgrade_target SET code_sha256_lf='{}'::jsonb",
                    'DELETE FROM v3_meta.derived_code_upgrade_target',
                    'TRUNCATE v3_meta.derived_code_upgrade_target'):
            with pytest.raises(psycopg.errors.RaiseException, match='retained and immutable'):
                connection.execute(sql)
        changed = {**generation.code_identity(), 'scripts/ratings_v4/run_generation.py': '0' * 64}
        monkeypatch.setattr(generation, 'code_identity', lambda: changed)
        with pytest.raises(ValueError, match='independently approved identity'):
            generation._verify_code(manifest, connection, identifier)


def test_first_handoff_refuses_unknown_target_before_reading_source(tmp_path, legacy_root, monkeypatch):
    import psycopg

    with interrupted_database(tmp_path, legacy_root) as (connection, source, identifier, manifest, _):
        changed = {**generation.code_identity(), 'scripts/ratings_v4/run_generation.py': '0' * 64}
        monkeypatch.setattr(generation, 'code_identity', lambda: changed)
        with pytest.raises(ValueError, match='independently approved identity'):
            resume(connection, source, upgrade_actor='disposable-test')
        assert len(committed_prefix(connection, identifier).rows) == 2
        assert connection.execute('SELECT count(*) FROM v3_meta.derived_code_upgrade').fetchone()[0] == 0
        unapproved = {'upgrade_id': resume_upgrade.UPGRADE_ID, 'derived_generation_id': str(identifier),
                      'manifest_sha256': generation._digest(manifest).hex(),
                      'from_code_sha256_lf': LEGACY_CODE, 'to_code_sha256_lf': changed}
        with pytest.raises(psycopg.errors.RaiseException, match='independently approved target'):
            connection.execute('''INSERT INTO v3_meta.derived_code_upgrade(
                derived_generation_id,receipt,receipt_sha256) VALUES (%s,%s::jsonb,%s)''',
                (identifier, generation._json(unapproved), generation._digest(unapproved)))


def test_committed_approval_matches_this_exact_candidate():
    target = json.loads((ROOT / 'sql/v3/proposals/007_ratings_v4_code_upgrade_target.json').read_text())
    assert target['code_sha256_lf'] == generation.code_identity()


def test_unknown_origin_and_unverified_prefix_fail_before_database_access():
    changed = deepcopy(LEGACY_CODE)
    changed['scripts/ratings_v4/canonical_stream.py'] = '0' * 64
    with pytest.raises(ValueError, match='unsupported parser upgrade origin'):
        verify_origin({'code_sha256_lf': changed})
    with pytest.raises(ValueError, match='every committed source chunk'):
        accept_verified_prefix(None, None, {}, CommittedPrefix(((0,),)), actor='test')


def test_transition_rejects_another_parser_and_changed_attested_prefix(monkeypatch):
    monkeypatch.setattr(resume_upgrade, 'DIRECT_PARSER_SHA256_LF', '0' * 64)
    with pytest.raises(ValueError, match='unsupported parser upgrade target'):
        verify_origin({'code_sha256_lf': LEGACY_CODE})
    prefix = CommittedPrefix(((0, bytes(32), bytes(32), bytes(32), 3, 0, 0, 0),))
    receipt = {'prefix_chunks': 1, 'prefix_sha256': prefix.digest.hex(), 'prefix_systems': 3}
    prefix.verify_attestation(receipt)
    with pytest.raises(ValueError, match='attested checkpoint prefix changed'):
        prefix.verify_attestation({**receipt, 'prefix_sha256': 'f' * 64})
    with pytest.raises(ValueError, match='attested checkpoint prefix is missing'):
        CommittedPrefix(()).verify_attestation(receipt)
