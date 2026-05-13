"""Construction point mechanics constants."""
from __future__ import annotations


T2_PORT_COSTS_YELLOW = [16, 20, 26, 34, 44, 56]
T3_PORT_COSTS_YELLOW = [40, 52, 68, 88]
T2_PORT_COSTS_GREEN = [0, 0, 4, 8, 12, 16]
T3_PORT_COSTS_GREEN = [16, 24, 36, 52]

T2_YELLOW_EXTRAPOLATION_STEP = 14
T2_GREEN_EXTRAPOLATION_STEP = 6
T3_YELLOW_EXTRAPOLATION_STEP = 22
T3_GREEN_EXTRAPOLATION_STEP = 20

LATE_T3_BUILD_ORDER_THRESHOLD = 3

CP_COMPLEXITY_THRESHOLDS = [
    (90, 'expert'),
    (65, 'advanced'),
    (40, 'moderate'),
    (15, 'simple'),
    (0, 'trivial'),
]
