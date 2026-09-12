from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operator.ratings_v4_resume_profile import (  # noqa: E402
    ArrayRootReader, builder_progress, direct_chunks, verify_chunk,
)
from scripts.ratings_v4.canonical_stream import _ArrayRootReader  # noqa: E402
from scripts.ratings_v4.production_generation import _digest, _projection  # noqa: E402


def test_observer_uses_equivalent_transparent_array_guard():
    raw = b' \t\r\n\v\f' * 2000 + b'[{"id64":1}]'
    for reader_type in (ArrayRootReader, _ArrayRootReader):
        reader = reader_type(io.BytesIO(raw))
        assert reader.read(0) == b''
        parts = []
        while part := reader.read(3):
            parts.append(part)
        assert b''.join(parts) == raw
    with pytest.raises(ValueError, match='JSON array'):
        list(direct_chunks(io.BytesIO(b'{"item":{"id64":1}}')))


def test_observer_verifies_source_order_projection_and_inventory():
    records = [{'id64': i, 'bodies': []} for i in range(3)]
    import json
    chunks = list(direct_chunks(io.BytesIO(json.dumps(records).encode()), chunk_size=2))
    assert chunks == [records[:2], records[2:]]
    checkpoint = (0, _digest([_projection(r) for r in chunks[0]]), 2, 0)
    verify_chunk(checkpoint, 0, chunks[0])
    for bad in (list(reversed(chunks[0])), chunks[0][:1], [{'id64': 9, 'bodies': []}, records[1]]):
        with pytest.raises(ValueError, match='source/checkpoint'):
            verify_chunk(checkpoint, 0, bad)


def test_observer_is_bounded_and_database_read_only():
    source = (ROOT / 'scripts/operator/ratings_v4_resume_profile.py').read_text()
    assert 'default_transaction_read_only=on' in source
    assert 'RLIMIT_AS' in source and 'RLIMIT_CPU' in source
    assert 'signal.alarm(150)' in source
    assert 'source_eof_verified=False' in source
    assert 'INSERT INTO' not in source and 'UPDATE v3_' not in source


def test_builder_rate_uses_database_snapshot_interval():
    started = datetime(2026, 9, 12, 23, 35, 33, tzinfo=timezone.utc)
    # A 120-second parser sample can have a longer database count interval.
    # Builder throughput must include that extra time in its denominator.
    ended = started + timedelta(seconds=123)
    result = builder_progress((78_510_000, started), (78_756_000, ended))
    assert result['builder_elapsed_seconds'] == 123
    assert result['builder_systems_per_second'] == 2000
    assert result['builder_systems_committed_during_sample'] == 246_000
    assert result['builder_systems_at_start'] == 78_510_000
    assert result['builder_systems_at_end'] == 78_756_000
    assert result['builder_snapshot_started_at'] == started.isoformat()
    assert result['builder_snapshot_ended_at'] == ended.isoformat()
    assert builder_progress((1000, started), (1000, ended))['builder_systems_per_second'] == 0


@pytest.mark.parametrize(('seconds', 'end_count'), [(0, 2000), (-1, 2000), (120, 999)])
def test_builder_rate_rejects_invalid_snapshot_interval(seconds, end_count):
    started = datetime(2026, 9, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='invalid builder snapshot interval'):
        builder_progress((1000, started), (end_count, started + timedelta(seconds=seconds)))


@pytest.mark.parametrize('wrong_source', [False, True])
def test_remote_wrapper_checks_exact_container_before_executing_observer(tmp_path, wrong_source):
    import yaml

    workflow = yaml.safe_load((ROOT / '.github/workflows/ratings-v4-resume-profile.yml').read_text())
    step = next(s for s in workflow['jobs']['profile']['steps']
                if s.get('name') == 'Run bounded read-only Ratings profile')
    lines = step['run'].splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "'")
    end = next(i for i, line in enumerate(lines[start+1:], start+1) if line.strip().startswith("' "))
    remote = '\n'.join(lines[start+1:end])
    hostname = tmp_path / 'hostname'
    hostname.write_text('#!/bin/sh\nif [ "$#" = 0 ]; then echo ed-finder-prod; else echo nb79a3d.mevnode.com; fi\n')
    hostname.chmod(0o700)
    docker = tmp_path / 'docker'
    docker.write_text('#!' + sys.executable + '\n' + '''import os,sys
args=sys.argv[1:]
if args==['context','show']: print('default')
elif args[:2]==['context','inspect']: print('unix:///var/run/docker.sock')
elif args[:2]==['inspect','-f']:
    values={'{{.State.Running}}':'true',
      '{{index .Config.Labels "ed-finder.source-sha"}}': 'wrong' if os.environ['WRONG_SOURCE']=='1' else 'fe0c058134b6fec33690fa937c2ac74338b401dc',
      '{{index .Config.Labels "ed-finder.generation-key"}}':'ratings_v4_prod_p4_opt1'}
    print(values[args[2]])
elif args==['exec','-i','-e','PYTHONPATH=/tmp/ratings-v4-deps:/work:/work/apps/api/src',
            'edfinder-ratings-v4-prod-p4-opt1','/app/.venv/bin/python','-']:
    print('observer launched')
else: raise SystemExit(64)
''')
    docker.chmod(0o700)
    result = subprocess.run(['bash', '-c', remote], text=True, capture_output=True,
                            env={**os.environ, 'PATH': str(tmp_path)+os.pathsep+os.environ['PATH'],
                                 'WRONG_SOURCE': str(int(wrong_source))}, timeout=5)
    assert result.returncode == int(wrong_source), result.stderr
    assert ('observer launched' in result.stdout) is not wrong_source
