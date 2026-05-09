"""Ratings re-rank endpoint — applies user weights to existing rating rows."""
from typing import Any, List, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from config import settings, limiter, log
from deps   import get_pool, get_redis
from models import RerankResponse, RerankWeights
from search_economies import ratings_score_column, ECONOMIES

router = APIRouter(tags=['ratings'])


# ---------------------------------------------------------------------------
# Ratings rerank — v3.1
# ---------------------------------------------------------------------------
# Applies user-tunable weights to the stored dimensional scores without
# recomputing anything from bodies.  The `score` column in DB is the canonical
# v3.1 score (42/23/18/10/5/2 weights); this endpoint lets a CMDR reweight
# "show me the top 50 but weight Tourism-strategic 40% and slots only 10%"
# and get an instantly reordered list.
#
# Request:
#   POST /api/ratings/rerank
#   {
#     "id64s":  [12345, 67890, ...]   # from a prior search
#     "weights": {                    # any subset; unspecified = defaults
#       "economy":       0.42,
#       "slots":         0.23,
#       "strategic":     0.18,
#       "safety":        0.10,
#       "terraforming":  0.05,
#       "diversity":     0.02
#     },
#     "economy": "Tourism"  # optional — which economy score drives "economy"
#                           # dimension.  Default: the stored economy_suggestion
#   }
#
# Response:
#   [{ "id64": ..., "reranked_score": 87, "original_score": 74,
#      "rationale": "Tourism-leaning via 2 ELW; 3 landable; neutron nearby" }]
# ---------------------------------------------------------------------------

# Default v3.1 weights — must sum to 1.0 for reranked_score to be in 0-100.
_DEFAULT_WEIGHTS = {
    'economy':      0.42,
    'slots':        0.23,
    'strategic':    0.18,
    'safety':       0.10,
    'terraforming': 0.05,
    'diversity':    0.02,
}


class RerankRequest(BaseModel):
    id64s:   List[int]               = Field(..., min_length=1, max_length=500)
    # Partial overrides allowed; missing keys fall back to _DEFAULT_WEIGHTS.
    weights: Optional[RerankWeights] = None
    economy: Optional[str]           = None      # e.g. 'Tourism'; None = use stored primary

@router.post('/api/ratings/rerank', response_model=RerankResponse)
@limiter.limit('60/minute')
async def ratings_rerank(
    request: Request,
    body: RerankRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    # ── Normalise weights: accept partial user input, fill gaps from defaults
    w = dict(_DEFAULT_WEIGHTS)
    if body.weights:
        # body.weights is a Pydantic model; iterate the declared dimensions
        # and overlay any values the client supplied (defaults are also
        # set on RerankWeights, so a client that sends an empty {} just
        # gets the canonical defaults).
        for k, v in body.weights.model_dump().items():
            if k in w and v is not None:
                try:
                    w[k] = max(0.0, min(1.0, float(v)))
                except (TypeError, ValueError):
                    pass
    total = sum(w.values()) or 1.0
    w = {k: v / total for k, v in w.items()}   # normalise to sum=1.0

    # ── Resolve which economy drives the "economy" dimension.
    # ratings_score_column() returns the canonical 'score_<eco>' column
    # name (or 'score' for unknown/None). We treat '' as "no override".
    eco_col: Optional[str] = None
    if body.economy:
        col = ratings_score_column(body.economy)
        if col != 'score':         # an actual per-economy column was matched
            eco_col = col

    # Build the eco-score expression: either the requested column, or the
    # stored `economy_suggestion` column pulled dynamically per row.
    if eco_col:
        eco_expr = f"COALESCE({eco_col}, 0)"
    else:
        # Pick the highest of the seven per-row (handles rows missing
        # economy_suggestion gracefully).
        eco_expr = "GREATEST(" + ", ".join(
            f"COALESCE({ratings_score_column(e)},0)" for e in ECONOMIES
        ) + ")"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                system_id64 AS id64,
                score                             AS original_score,
                {eco_expr}                        AS eco_score,
                COALESCE(slots, 0)                AS slots,
                COALESCE(body_quality, 0)         AS strategic,
                COALESCE(orbital_safety, 0)       AS safety,
                COALESCE(terraforming_potential,0) AS terraforming,
                COALESCE(body_diversity, 0)       AS diversity,
                confidence,
                rationale,
                economy_suggestion
            FROM ratings
            WHERE system_id64 = ANY($1::bigint[])
            """,
            body.id64s,
        )

    # ── Apply weights in Python (trivial math; keeps the SQL readable)
    result = []
    for r in rows:
        reranked = (
            r['eco_score']     * w['economy']      +
            r['slots']         * w['slots']        +
            r['strategic']     * w['strategic']    +
            r['safety']        * w['safety']       +
            r['terraforming']  * w['terraforming'] +
            r['diversity']     * w['diversity'] * (100.0 / 30.0)  # diversity is 0-30
        )
        # Optional confidence multiplier: stale data nudges score down slightly.
        if r['confidence'] is not None:
            reranked *= r['confidence']
        result.append({
            'id64':           r['id64'],
            'reranked_score': int(round(reranked)),
            'original_score': r['original_score'],
            'confidence':     float(r['confidence']) if r['confidence'] is not None else None,
            'rationale':      r['rationale'],
            'economy_used':   body.economy or r['economy_suggestion'],
        })

    # Return sorted descending by reranked_score
    result.sort(key=lambda x: x['reranked_score'], reverse=True)
    return {
        'weights_applied': w,
        'economy_used':    body.economy,
        'results':         result,
    }
