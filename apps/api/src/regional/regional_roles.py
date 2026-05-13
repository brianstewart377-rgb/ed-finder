"""Regional role classification from raw colonisation-distance metrics."""
from __future__ import annotations

from typing import Optional


def classify_regional_role(
    *,
    nearest_distance_ly: Optional[float],
    within_25: int,
    within_50: int,
    within_100: int,
    within_250: int,
) -> str:
    if nearest_distance_ly is None:
        return 'unknown'
    if nearest_distance_ly > 150 and within_100 == 0:
        return 'isolated_frontier'
    if within_50 >= 12 or within_100 >= 35:
        return 'oversaturated_region'
    if nearest_distance_ly < 25 and within_50 >= 6:
        return 'dense_developed_cluster'
    if 20 <= nearest_distance_ly <= 80 and 3 <= within_100 <= 10:
        return 'emerging_cluster'
    if 50 <= nearest_distance_ly <= 150 and within_100 <= 3:
        return 'frontier_hub'
    if 40 <= nearest_distance_ly <= 160 and 3 < within_100 <= 12 and 2 <= within_250 <= 24 and within_50 <= 3:
        return 'bridge_system'
    return 'unknown'
