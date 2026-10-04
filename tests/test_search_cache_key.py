"""F3 finding #9: the `/api/local/search` cache key must be scoped to the
ranking identity and the resolved published generation, so a warm entry can
never be served across a V3 cutover, a ranking-formula change, or a governed
publish. Pure/DB-free — exercises the `_search_cache_key` helper directly.
"""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

# Config import side effects need a couple of env defaults (mirrors the other
# API unit tests) before importing the router module.
os.environ.setdefault('CORS_ORIGINS', 'https://search-cache-key-test.invalid')

from edfinder_api.ranking.profile import RANKING_VERSION, ranking_sha256  # noqa: E402
from routers.search import _search_cache_key, SEARCH_CACHE_VERSION  # noqa: E402


def _gen(gen_id='gen-abc', seq=7):
    return {'derived_generation_id': gen_id, 'publication_sequence': seq}


def test_cache_key_includes_cutover_namespace_ranking_identity_and_generation():
    body = {'galaxy_wide': True, 'size': 5}
    key = _search_cache_key(body, _gen())
    assert key.startswith(f'search:{SEARCH_CACHE_VERSION}:')
    assert RANKING_VERSION in key
    assert ranking_sha256() in key
    assert 'ggen-abc' in key
    assert 's7' in key
    # cutover bumped the namespace off the legacy body-only 'v4' key
    assert SEARCH_CACHE_VERSION != 'v4'


def test_cache_key_changes_when_generation_changes():
    body = {'galaxy_wide': True, 'size': 5}
    k1 = _search_cache_key(body, _gen(gen_id='gen-1', seq=1))
    k2 = _search_cache_key(body, _gen(gen_id='gen-2', seq=2))
    assert k1 != k2, 'a new published generation must miss the prior key'


def test_cache_key_changes_when_body_changes_but_stable_otherwise():
    g = _gen()
    k1 = _search_cache_key({'galaxy_wide': True, 'size': 5}, g)
    k2 = _search_cache_key({'galaxy_wide': True, 'size': 6}, g)
    assert k1 != k2
    # deterministic for identical inputs
    assert _search_cache_key({'galaxy_wide': True, 'size': 5}, g) == k1
