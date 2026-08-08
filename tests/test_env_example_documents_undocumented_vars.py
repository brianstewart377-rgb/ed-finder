"""Regression test for Emergent recurrence report A5 (2026-08-08): nine
real, code-read env vars (all with working defaults, none previously
documented anywhere in env.example) were only discoverable by grepping
source. Asserts each now has an entry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UNDOCUMENTED_VARS = (
    'CLUSTER_RADIUS_LY',
    'MAX_SEARCH_RADIUS_LY',
    'CELL_SIZE',
    'INARA_API_KEY',
    'INARA_APP_NAME',
    'INARA_APP_VERSION',
    'REGION_MAP_JSON',
    'DB_DSN_DIRECT',
    'DIRTY_CLEANUP_CHUNK_SIZE',
)


def test_a5_env_vars_are_documented_in_env_example():
    env_example = (ROOT / 'env.example').read_text(encoding='utf-8')
    lines = env_example.splitlines()

    for var in UNDOCUMENTED_VARS:
        assert any(line.startswith(f'{var}=') for line in lines), (
            f'{var} is read via os.getenv() in apps/ but has no entry in env.example'
        )
