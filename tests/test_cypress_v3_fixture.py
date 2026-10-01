"""Task 2: the curated Cypress canonical fixture loads (checksum-locked),
carries the journey id64s, and -- crucially -- passes the stream's
``adapt_retained_chunk`` source/canonical inventory validator (no DB needed),
which is the hard constraint the full seed build depends on."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

FIXTURE = ROOT / 'tests/fixtures/cypress_v3_sources'

ACHENAR = 10477373803000
LOSSLESS = 9007199254740993


def test_cypress_fixture_has_journey_systems():
    from domain.ratings_v4_canonical import load_source_fixture

    canonical, _metadata, _subtypes = load_source_fixture(FIXTURE)
    ids = {s['id64']: s['name'] for s in canonical['systems']}
    assert ids.get(ACHENAR) == 'Achenar'
    assert ids.get(LOSSLESS) == 'V3 Lossless Reach'
    assert len(canonical['systems']) >= 3
    assert any(b['system_id64'] == ACHENAR for b in canonical['bodies'])
    # Achenar (ex-Sol) must retain a main-star body so detail/classification is real.
    assert any(b['system_id64'] == ACHENAR and b.get('is_main_star')
               for b in canonical['bodies'])


def test_cypress_fixture_passes_retained_chunk_inventory():
    """adapt_retained_chunk fails closed on any source/canonical body-inventory
    mismatch; a clean pass proves the curated fixture is build-ready without
    standing up PostgreSQL (plan Task 2 open item #3)."""
    from domain.ratings_v4_canonical import load_source_fixture
    from scripts.ratings_v4.canonical_stream import adapt_retained_chunk

    canonical, metadata, subtypes = load_source_fixture(FIXTURE)
    source_records = [payload['system'] for payload in subtypes]
    facts = adapt_retained_chunk(canonical, metadata, source_records)
    assert set(facts) == {s['id64'] for s in canonical['systems']}
    assert ACHENAR in facts and LOSSLESS in facts
