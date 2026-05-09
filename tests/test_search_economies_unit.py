"""Pure-function unit coverage for ``apps/api/src/search_economies.py``.

Lives in ``tests/`` (the no-DB smoke directory) rather than
``tests/integration/`` because no PG/Redis is required — and being
outside the integration directory means the module-wide
``pytestmark = pytest.mark.asyncio`` doesn't apply, eliminating the
``test marked with asyncio but is not async`` warning we saw in the
original landing of this test.
"""
from pathlib import Path
import sys

# Make apps/api/src importable for these unit tests (mirrors what the
# integration conftest does).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'apps' / 'api' / 'src'))


def test_economy_enum_value():
    """Resolves every observed wire shape to the PG enum literal."""
    from search_economies import economy_enum_value

    assert economy_enum_value('Agriculture')  == 'Agriculture'
    assert economy_enum_value('agriculture')  == 'Agriculture'
    assert economy_enum_value('AGRICULTURE')  == 'Agriculture'
    assert economy_enum_value('  Agriculture  ') == 'Agriculture'
    assert economy_enum_value('High Tech')    == 'HighTech'
    assert economy_enum_value('high tech')    == 'HighTech'
    assert economy_enum_value('HIGH TECH')    == 'HighTech'
    assert economy_enum_value('high-tech')    == 'HighTech'
    assert economy_enum_value('hightech')     == 'HighTech'
    assert economy_enum_value('HighTech')     == 'HighTech'
    assert economy_enum_value('Extraction')   == 'Extraction'
    assert economy_enum_value('extraction')   == 'Extraction'
    assert economy_enum_value('Refinery')     == 'Refinery'
    assert economy_enum_value('Industrial')   == 'Industrial'
    assert economy_enum_value('Military')     == 'Military'
    assert economy_enum_value('Tourism')      == 'Tourism'

    # Unknown / blank → None (caller treats as no filter)
    assert economy_enum_value(None)           is None
    assert economy_enum_value('')             is None
    assert economy_enum_value('   ')          is None
    assert economy_enum_value('any')          is None
    assert economy_enum_value('Unknown')      is None
    assert economy_enum_value('Foo')          is None


def test_ratings_score_column():
    """Per-economy score column lookup, including the audit's §C5
    Extraction-was-missing regression."""
    from search_economies import ratings_score_column

    assert ratings_score_column('agriculture')             == 'score_agriculture'
    assert ratings_score_column('agriculture', alias='r')  == 'r.score_agriculture'
    assert ratings_score_column('Tourism', alias='r')      == 'r.score_tourism'
    assert ratings_score_column('Extraction', alias='r')   == 'r.score_extraction'
    assert ratings_score_column('High Tech', alias='r')    == 'r.score_hightech'

    # Unknown → overall score
    assert ratings_score_column(None)             == 'score'
    assert ratings_score_column('Foo', alias='r') == 'r.score'


def test_cluster_count_column():
    """cluster_summary doesn't carry an extraction column today."""
    from search_economies import cluster_count_column

    assert cluster_count_column('agriculture') == 'cs.agriculture_count'
    assert cluster_count_column('hightech')    == 'cs.hightech_count'
    assert cluster_count_column('extraction')  is None  # not in cluster_summary
    assert cluster_count_column(None)          is None
    assert cluster_count_column('Foo')         is None


def test_normalise_body_filters():
    """Resolves camelCase aliases to canonical snake_case."""
    from search_economies import normalise_body_filters

    out = normalise_body_filters({
        'gasGiant':  {'min': 1},
        'metalRich': {'min': 2},
        'elw_count': {'min': 3},  # already canonical
    })
    assert out['gas_giant']  == {'min': 1}
    assert out['metal_rich'] == {'min': 2}
    assert out['elw_count']  == {'min': 3}

    # Aliases that already collide with a canonical key must not overwrite
    out = normalise_body_filters({
        'gasGiant':  {'min': 99},
        'gas_giant': {'min': 7},
    })
    assert out['gas_giant'] == {'min': 7}
