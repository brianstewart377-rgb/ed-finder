from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SCRIPT_PATH = ROOT / 'scripts' / 'checks' / 'data_invariants.py'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

from routers import admin as admin_router  # noqa: E402
from shared_contracts import data_invariant_contracts  # noqa: E402


_SPEC = importlib.util.spec_from_file_location('repo_data_invariants_script', SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
script_invariants = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script_invariants)


def test_admin_shared_invariant_check_names_are_a_subset_of_script_checks():
    assert set(admin_router._ADMIN_DATA_INVARIANT_CHECK_KEYS).issubset(
        set(script_invariants.SCRIPT_DATA_INVARIANT_CHECK_KEYS)
    )


def test_shared_colonisation_bucket_normalisation_handles_rows_and_mappings():
    mapping_row = {
        'tracked_total': 9,
        'age_0_3d': 4,
        'age_3_7d': 3,
        'age_7_14d': 1,
        'age_over_14d': 1,
    }
    tuple_row = (9, 4, 3, 1, 1)

    assert data_invariant_contracts.normalise_colonisation_status_age_buckets(mapping_row) == {
        'tracked_total': 9,
        'age_0_3d': 4,
        'age_3_7d': 3,
        'age_7_14d': 1,
        'age_over_14d': 1,
    }
    assert data_invariant_contracts.normalise_colonisation_status_age_buckets(tuple_row) == {
        'tracked_total': 9,
        'age_0_3d': 4,
        'age_3_7d': 3,
        'age_7_14d': 1,
        'age_over_14d': 1,
    }
