"""Pydantic request + response models.

These are data-shape contracts — keep side-effects out, do not import
DB / Redis / config from here. All models referenced by more than one
router live here; router-local one-off shapes can stay next to their
endpoint.

Audit Phase 2 follow-up (2026-05-09 — see AUDIT_REPORT.md §M3 / Phase 7
follow-up): every response model below is now strictly typed *and*
allows extras (`model_config = {"extra": "allow"}`).

Why both?

* Strict fields → openapi-typescript can generate real TypeScript types
  from /openapi.json instead of `Record<string, never>` / `unknown`,
  which is what made the api.gen.ts CI drift-check toothless.
* Extras allowed → adding a column on the SQL side or a key in
  `helpers.sys_row_to_dict` will *not* be silently stripped by
  Pydantic's response serializer (which was the original bug behind
  the `source/query_ms/display_economy` regression in d43fde8).

If you tighten extras here, audit `helpers.sys_row_to_dict` and the
SQL projections in `routers/systems.py` + `local_search.py` first.

Note on dict-typed request fields (2026-05-09 follow-up): every
request-side `Optional[dict]` has been replaced with a proper sub-model
(RangeFilter, BodyFilters, RerankWeightsInput, etc.) or `Optional[Any]`
where the shape is genuinely opaque. Pydantic 2.10+ emits
`additionalProperties: false` for `dict` fields, which openapi-typescript
renders as the strict-empty `Record<string, never>` — strict-mode TS
then refuses to pass real values through that type. Using sub-models
keeps the schema portable across Pydantic versions and gives the
frontend useful types out of the box.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ══════════════════════════════════════════════════════════════════════
# Shared mixins / sub-models
# ══════════════════════════════════════════════════════════════════════
class CoordsModel(BaseModel):
    x: float
    y: float
    z: float


class RangeFilter(BaseModel):
    """Inclusive numeric range used by `SearchFilters.distance` /
    `.population`. Either bound is optional — omit `min` for an upper-
    only filter, omit `max` for a lower-only one. (Frontend always
    sends both today; keep them optional so a future client can omit.)"""
    model_config = ConfigDict(extra='allow')

    min: Optional[float] = None
    max: Optional[float] = None


class BodyCountFilter(BaseModel):
    """One body-count slider in `LocalSearchRequest.body_filters`. Each
    body-type key (`elw_count`, `ww_count`, …) maps to a min/max range,
    same shape as `RangeFilter` — duplicated here for naming clarity in
    the generated TS."""
    model_config = ConfigDict(extra='allow')

    min: Optional[int] = None
    max: Optional[int] = None


class BodyFilters(BaseModel):
    """`LocalSearchRequest.body_filters`. Keys mirror the
    `helpers.sys_row_to_dict` body-count column names. All optional —
    a missing key means "no filter on that body type"."""
    model_config = ConfigDict(extra='allow')

    elw_count:           Optional[BodyCountFilter] = None
    ww_count:            Optional[BodyCountFilter] = None
    ammonia_count:       Optional[BodyCountFilter] = None
    gas_giant_count:     Optional[BodyCountFilter] = None
    landable_count:      Optional[BodyCountFilter] = None
    terraformable_count: Optional[BodyCountFilter] = None
    bio_signal_total:    Optional[BodyCountFilter] = None
    geo_signal_total:    Optional[BodyCountFilter] = None
    neutron_count:       Optional[BodyCountFilter] = None
    black_hole_count:    Optional[BodyCountFilter] = None
    white_dwarf_count:   Optional[BodyCountFilter] = None
    hmc_count:           Optional[BodyCountFilter] = None
    metal_rich_count:    Optional[BodyCountFilter] = None
    rocky_count:         Optional[BodyCountFilter] = None
    rocky_ice_count:     Optional[BodyCountFilter] = None
    icy_count:           Optional[BodyCountFilter] = None
    other_star_count:    Optional[BodyCountFilter] = None
    ring_count:          Optional[BodyCountFilter] = None
    walkable_count:      Optional[BodyCountFilter] = None


class RatingModel(BaseModel):
    """camelCase rating block embedded inside SystemRow under `_rating`.

    Mirrors the shape produced by `helpers.sys_row_to_dict` so the
    generated TypeScript matches what the search response actually puts
    on the wire.
    """
    model_config = ConfigDict(extra='allow')

    score:                  Optional[float] = None
    scoreAgriculture:       Optional[float] = None
    scoreRefinery:          Optional[float] = None
    scoreIndustrial:        Optional[float] = None
    scoreHightech:          Optional[float] = None
    scoreMilitary:          Optional[float] = None
    scoreTourism:           Optional[float] = None
    scoreExtraction:        Optional[float] = None
    economySuggestion:      Optional[str]   = None
    breakdown:              Optional[Any]   = None  # opaque rationale payload
    # v3.1 fields — mirrored in camelCase for frontend parity.
    terraformingPotential:  Optional[float] = None
    bodyDiversity:          Optional[float] = None
    confidence:             Optional[float] = None
    rationale:              Optional[str]   = None


class BodyModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    id:                      Optional[int]   = None
    name:                    Optional[str]   = None
    subtype:                 Optional[str]   = None
    body_type:               Optional[str]   = None
    distance_from_star:      Optional[float] = None
    is_landable:             Optional[bool]  = None
    is_terraformable:        Optional[bool]  = None
    is_earth_like:           Optional[bool]  = None
    is_water_world:          Optional[bool]  = None
    is_ammonia_world:        Optional[bool]  = None
    bio_signal_count:        Optional[int]   = None
    geo_signal_count:        Optional[int]   = None
    surface_temp:            Optional[float] = None
    radius:                  Optional[float] = None
    mass:                    Optional[float] = None
    gravity:                 Optional[float] = None
    estimated_mapping_value: Optional[int]   = None
    estimated_scan_value:    Optional[int]   = None
    is_main_star:            Optional[bool]  = None
    spectral_class:          Optional[str]   = None
    is_scoopable:            Optional[bool]  = None


class StationModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    id:                 Optional[int]   = None
    name:               Optional[str]   = None
    station_type:       Optional[str]   = None
    distance_from_star: Optional[float] = None
    landing_pad_size:   Optional[str]   = None
    has_market:         Optional[bool]  = None
    has_shipyard:       Optional[bool]  = None
    has_outfitting:     Optional[bool]  = None


class ExplorationValueModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    total_scan_value:    int = 0
    total_mapping_value: int = 0
    combined_value:      int = 0


# ══════════════════════════════════════════════════════════════════════
# Search row (camelCase) — `/api/local/search`, `/api/systems/batch`
# ══════════════════════════════════════════════════════════════════════
class SystemRow(BaseModel):
    """One result row inside `SearchResponse.results`.

    Keep aligned with `helpers.sys_row_to_dict` (single source of truth
    for the camelCase translator).
    """
    model_config = ConfigDict(extra='allow')

    id64:                int
    name:                str                   = 'Unknown'
    coords:              Optional[CoordsModel] = None
    distance:            Optional[float]       = None
    population:          int                   = 0
    primaryEconomy:      Optional[str]         = None
    secondaryEconomy:    Optional[str]         = None
    security:            Optional[str]         = None
    allegiance:          Optional[str]         = None
    government:          Optional[str]         = None
    is_colonised:        Optional[bool]        = None
    is_being_colonised:  Optional[bool]        = None
    main_star_type:      Optional[str]         = None
    main_star_subtype:   Optional[str]         = None

    # Embedded rating block (also camelCase). Field name has a leading
    # underscore on the wire — Pydantic v2 keeps the raw alias.
    rating: Optional[RatingModel] = Field(default=None, alias='_rating')

    # Body counts surfaced flat for filter pills (the search SQL
    # projects these from the ratings row).
    elw_count:            Optional[int] = None
    ww_count:             Optional[int] = None
    ammonia_count:        Optional[int] = None
    gas_giant_count:      Optional[int] = None
    landable_count:       Optional[int] = None
    terraformable_count:  Optional[int] = None
    bio_signal_total:     Optional[int] = None
    geo_signal_total:     Optional[int] = None
    neutron_count:        Optional[int] = None
    black_hole_count:     Optional[int] = None
    white_dwarf_count:    Optional[int] = None


# Backwards-compatible alias — older imports used `SystemModel`.
SystemModel = SystemRow


# ══════════════════════════════════════════════════════════════════════
# Detail row (snake_case) — `/api/system/{id64}`
# ══════════════════════════════════════════════════════════════════════
class SystemDetailRow(BaseModel):
    """Full system detail returned by `/api/system/{id64}`.

    The detail endpoint does *not* go through the camelCase translator —
    it returns the joined ratings + bodies + stations rows snake_case
    as PostgreSQL emits them (see `routers/systems.py::get_system`).
    Frontend renders these strings directly.
    """
    model_config = ConfigDict(extra='allow')

    id64:               int
    name:               str
    x:                  float = 0
    y:                  float = 0
    z:                  float = 0
    population:         int   = 0
    primary_economy:    Optional[str]  = None
    secondary_economy:  Optional[str]  = None
    security:           Optional[str]  = None
    allegiance:         Optional[str]  = None
    government:         Optional[str]  = None
    is_colonised:       Optional[bool] = None
    main_star_type:     Optional[str]  = None
    main_star_subtype:  Optional[str]  = None

    # Flat rating fields (joined from ratings table; snake_case here).
    score:                  Optional[float] = None
    score_agriculture:      Optional[float] = None
    score_refinery:         Optional[float] = None
    score_industrial:       Optional[float] = None
    score_hightech:         Optional[float] = None
    score_military:         Optional[float] = None
    score_tourism:          Optional[float] = None
    score_extraction:       Optional[float] = None
    economy_suggestion:     Optional[str]   = None

    # Flat body counts.
    elw_count:              Optional[int] = None
    ww_count:               Optional[int] = None
    ammonia_count:          Optional[int] = None
    gas_giant_count:        Optional[int] = None
    landable_count:         Optional[int] = None
    terraformable_count:    Optional[int] = None
    bio_signal_total:       Optional[int] = None
    geo_signal_total:       Optional[int] = None
    neutron_count:          Optional[int] = None
    black_hole_count:       Optional[int] = None
    white_dwarf_count:      Optional[int] = None

    # v3.1 rating fields.
    terraforming_potential: Optional[float] = None
    body_diversity:         Optional[float] = None
    confidence:             Optional[float] = None
    rationale:              Optional[str]   = None

    bodies:   list[BodyModel]    = Field(default_factory=list)
    stations: list[StationModel] = Field(default_factory=list)

    exploration_value: Optional[ExplorationValueModel] = None


# ══════════════════════════════════════════════════════════════════════
# Response wrappers
# ══════════════════════════════════════════════════════════════════════
class SearchResponse(BaseModel):
    """`/api/local/search` response."""
    model_config = ConfigDict(extra='allow')

    results: list[SystemRow]
    total:   int = 0
    count:   int = 0
    # Optional — only set by local_db_search, helpful for ops visibility
    # so you can tell which code path served the response without
    # spelunking through logs. (FastAPI silently drops fields not in
    # the response model; without these, source/query_ms/display_economy
    # were being stripped before reaching the client — see d43fde8.)
    source:           Optional[str] = None
    query_ms:         Optional[int] = None
    display_economy:  Optional[str] = None
    # True when `total` was clamped at the galaxy-wide cap (currently
    # 10 000) instead of being a precise count of all matches. Render
    # as "X+" in the UI when set. Absent on local (distance-bounded)
    # searches where the precise count is cheap.
    total_is_capped:  Optional[bool] = None
    # Surfaces the radius-cap notice from `local_db_search`. UI can
    # render this as a small banner next to the results count.
    warning:          Optional[str] = None


class SystemDetailResponse(BaseModel):
    """`/api/system/{id64}` response. Backend returns the same row
    twice under `record` and `system` for legacy compat."""
    model_config = ConfigDict(extra='allow')

    record: SystemDetailRow
    system: SystemDetailRow


class HealthResponse(BaseModel):
    status:   str
    database: str
    version:  str


class AutocompleteHit(BaseModel):
    model_config = ConfigDict(extra='allow')

    id64:           int
    name:           str
    x:              float = 0
    y:              float = 0
    z:              float = 0
    population:     int = 0
    primaryEconomy: Optional[str] = None


class AutocompleteResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    results: list[AutocompleteHit]
    source:  Optional[str] = None


class StatusResponse(BaseModel):
    """`/api/status` and `/api/local/status`."""
    model_config = ConfigDict(extra='allow')

    available:            bool
    systems_count:        int = 0
    body_count:           int = 0
    rated_count:          int = 0
    clustered_count:      int = 0
    import_complete:      bool = False
    ratings_built:        bool = False
    grid_built:           bool = False
    clusters_built:       bool = False
    eddn_enabled:         bool = False
    last_nightly_update:  str = 'never'
    schema_version:       str = '1.0'
    max_search_radius_ly: int = 500
    has_body_data:        bool = False
    version:              str = ''


class CacheStatsResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    cache_hits:       int = 0
    cache_misses:     int = 0
    redis_hits:       Optional[int]   = None
    redis_misses:     Optional[int]   = None
    redis_memory_mb:  Optional[float] = None
    db_cache_rows:    int = 0


class RerankWeights(BaseModel):
    economy:      float = 0.42
    slots:        float = 0.23
    strategic:    float = 0.18
    safety:       float = 0.10
    terraforming: float = 0.05
    diversity:    float = 0.02


class RerankRow(BaseModel):
    model_config = ConfigDict(extra='allow')

    id64:           int
    reranked_score: int
    original_score: Optional[float] = None
    confidence:     Optional[float] = None
    rationale:      Optional[str]   = None
    economy_used:   Optional[str]   = None


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    weights_applied: RerankWeights
    economy_used:    Optional[str] = None
    results:         list[RerankRow]


class WatchlistAlert(BaseModel):
    min_score: Optional[int] = None
    economy:   Optional[str] = None


class NoteBody(BaseModel):
    note: str


# ══════════════════════════════════════════════════════════════════════
# Request models
# ══════════════════════════════════════════════════════════════════════
class SearchFilters(BaseModel):
    distance:   Optional[RangeFilter] = None
    population: Optional[RangeFilter] = None
    economy:    Optional[str]         = None


class LocalSearchRequest(BaseModel):
    filters:          Optional[SearchFilters] = None
    reference_coords: Optional[CoordsModel]   = None
    sort_by:          Optional[str]            = 'rating'
    size:             int                      = Field(default=50, le=500)
    from_:            int                      = Field(default=0, alias='from')
    body_filters:     Optional[BodyFilters]    = None
    require_bio:      Optional[bool]           = None
    require_geo:      Optional[bool]           = None
    require_terra:    Optional[bool]           = None
    star_types:       Optional[list[str]]      = None
    min_rating:       Optional[int]            = None
    galaxy_wide:      bool                     = False

    model_config = {'populate_by_name': True}


class GalaxySearchRequest(BaseModel):
    economy:   str = 'any'
    min_score: int = Field(default=0, ge=0, le=100)
    limit:     int = Field(default=100, le=500)
    offset:    int = 0


class ClusterRequirement(BaseModel):
    economy:   str
    min_count: int = Field(default=1, ge=1)
    min_score: int = Field(default=40, ge=0, le=100)


class ClusterSearchRequest(BaseModel):
    requirements:     list[ClusterRequirement]
    limit:            int = Field(default=50, le=200)
    offset:           int = 0
    reference_coords: Optional[CoordsModel] = None
