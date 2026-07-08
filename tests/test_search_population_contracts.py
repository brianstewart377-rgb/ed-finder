import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from local_search import SearchSqlBuilder, _apply_local_search_filters, _parse_local_search_context  # noqa: E402


def test_populated_filter_uses_population_comparator():
    ctx = _parse_local_search_context(
        {
            "galaxy_wide": True,
            "filters": {
                "population": {"comparison": ">", "value": 0},
            },
        }
    )
    builder = SearchSqlBuilder()

    _apply_local_search_filters(ctx, builder)

    assert ctx.require_empty is False
    assert builder.params == [0]
    assert any(where == "s.population > $1" for where in builder.wheres)


def test_uninhabited_filter_stays_conservative_for_zero_population():
    ctx = _parse_local_search_context(
        {
            "galaxy_wide": True,
            "filters": {
                "population": {"comparison": "equal", "value": 0},
            },
        }
    )
    builder = SearchSqlBuilder()

    _apply_local_search_filters(ctx, builder)

    assert ctx.require_empty is True
    assert "s.population = 0" in builder.wheres
    assert "s.is_colonised = FALSE" in builder.wheres
