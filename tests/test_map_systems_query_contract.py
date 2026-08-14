"""Static performance contract for the production real-star viewport query."""

from pathlib import Path


MAP_ROUTER = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "api"
    / "src"
    / "routers"
    / "map.py"
)


def test_viewport_query_caps_index_scan_before_notable_ranking():
    source = MAP_ROUTER.read_text(encoding="utf-8")
    candidate_start = source.index("WITH candidates AS MATERIALIZED")
    coordinate_order = source.index("ORDER BY x, y, z", candidate_start)
    candidate_limit = source.index("LIMIT  $7", coordinate_order)
    notable_ranking = source.index("ORDER BY populated DESC", candidate_limit)

    assert candidate_start < coordinate_order < candidate_limit < notable_ranking
    assert "map:systems:v3" in source
