from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
SHARED_CONTRACTS = ROOT / 'shared_contracts'

if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from api_source_resolver import resolve_api_source  # noqa: E402


FLAT_IMPORTER_FILES = (
    'api_source_resolver.py',
    'backfill_station_body_links.py',
    'body_ring_enrichment_plan.py',
    'dirty_flags.py',
    'edsm_station_enrichment_probe.py',
    'enrich_system_data.py',
    'ring_facts.py',
    'station_type_canonical_pilot.py',
)
SMOKE_ENTRYPOINTS = (
    'edsm_station_enrichment_probe.py',
    'station_type_canonical_pilot.py',
    'enrich_system_data.py',
    'backfill_station_body_links.py',
)


def test_resolver_falls_back_to_repository_markers():
    resolved = resolve_api_source(
        IMPORTER_SRC / 'backfill_station_body_links.py',
        required_paths=('station_body_resolver.py',),
    )

    assert resolved == API_SRC


def test_resolver_fails_explicitly_when_api_source_is_missing(tmp_path):
    script_path = tmp_path / 'app' / 'backfill_station_body_links.py'
    script_path.parent.mkdir()

    with pytest.raises(RuntimeError, match='Could not locate the ED-Finder API source tree') as exc_info:
        resolve_api_source(script_path, required_paths=('station_body_resolver.py',))

    assert str(script_path.parent / 'apps_api_src') in str(exc_info.value)


def test_flat_importer_entrypoints_resolve_compose_api_mount_without_pythonpath(tmp_path):
    flat_app = tmp_path / 'app'
    flat_app.mkdir()
    for filename in FLAT_IMPORTER_FILES:
        shutil.copy2(IMPORTER_SRC / filename, flat_app / filename)

    shutil.copytree(
        SHARED_CONTRACTS,
        flat_app / 'shared_contracts',
        ignore=shutil.ignore_patterns('__pycache__'),
    )

    mounted_api = flat_app / 'apps_api_src'
    (mounted_api / 'edfinder_api').mkdir(parents=True)
    for filename in ('station_body_resolver.py', 'station_body_resolver_utils.py'):
        shutil.copy2(API_SRC / filename, mounted_api / filename)
    shutil.copy2(API_SRC / 'edfinder_api' / '__init__.py', mounted_api / 'edfinder_api' / '__init__.py')

    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONNOUSERSITE'] = '1'

    for entrypoint in SMOKE_ENTRYPOINTS:
        result = subprocess.run(
            [sys.executable, '-B', str(flat_app / entrypoint), '--help'],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f'{entrypoint} failed:\n{result.stderr}'
        assert 'usage:' in result.stdout.lower()
