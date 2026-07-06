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


def test_canonical_economy_key():
    """Resolves user-facing economy forms to DB column suffixes."""
    from search_economies import canonical_economy_key

    assert canonical_economy_key('HighTech')  == 'hightech'
    assert canonical_economy_key('High Tech') == 'hightech'
    assert canonical_economy_key('high-tech') == 'hightech'
    assert canonical_economy_key('tourism')   == 'tourism'
    assert canonical_economy_key('Foo')       is None


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


def test_body_filter_columns_accept_public_count_keys():
    """Public API request keys like ``elw_count`` must resolve all the way
    through to SQL columns, not just the frontend's short aliases."""
    from search_economies import body_filter_column

    assert body_filter_column('elw_count', alias='r') == 'r.elw_count'
    assert body_filter_column('ww_count', alias='r') == 'r.ww_count'
    assert body_filter_column('ammonia_count', alias='r') == 'r.ammonia_count'


def test_sort_by_rating_alias_maps_to_development():
    """Legacy callers still send ``sort_by=rating``; preserve development
    ordering instead of silently falling back to distance sort."""
    from models import LocalSearchRequest

    body = LocalSearchRequest.model_validate({'sort_by': 'rating'})
    assert body.sort_by == 'development'


def test_build_system_record_preserves_flat_body_counts():
    """Finder rows still need flat body-count fields for chips and compare
    surfaces after the `_rating` retirement."""
    from local_search import _build_system_record

    row = {
        'id64': 42,
        'name': 'Handoff',
        'x': 1,
        'y': 2,
        'z': 3,
        'updated_at': None,
        'archetype_score': 91,
        'primary_archetype': 'refinery_industrial',
        'secondary_archetype': 'trade_logistics',
        'elw_count': 2,
        'ww_count': 4,
        'ammonia_count': 1,
        'gas_giant_count': 6,
        'neutron_count': 0,
        'black_hole_count': 0,
        'white_dwarf_count': 0,
        'landable_count': 12,
        'terraformable_count': 5,
        'bio_signal_total': 3,
        'geo_signal_total': 7,
        'display_tags': [],
    }

    rec = _build_system_record(row)

    assert rec['elw_count'] == 2
    assert rec['ww_count'] == 4
    assert rec['ammonia_count'] == 1
    assert rec['terraformable_count'] == 5
    assert rec['bio_signal_total'] == 3
