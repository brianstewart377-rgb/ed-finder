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

Strictness policy (2026-05-09 follow-up to the search-503 RCA):

* **Row models** (`SystemRow`, `SystemDetailRow`, `BodyModel`,
  `StationModel`, `RatingModel`, `RerankRow`, `AutocompleteHit`,
  `RangeFilter`, `BodyCountFilter`, `BodyFilters`,
  `ExplorationValueModel`) → `extra='allow'`. SQL projections
  legitimately drift; silently dropping an existing field would be a
  worse bug than passing through an unknown one.
* **Response envelopes** (`SearchResponse`, `AutocompleteResponse`,
  `StatusResponse`, `CacheStatsResponse`, `RerankResponse`,
  `SystemDetailResponse`, `HealthResponse`) → `extra='forbid'`. The
  top-level envelope shape changes rarely and intentionally;
  forgetting to update the model when adding a key should be a loud
  failure (Pydantic ValidationError → 500), not silently shipped
  back to the client where typed consumers would 'unknown'-out the
  field. The drift-check CI job already protects the wire contract,
  so model_config drift can't go un-noticed.

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

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field, field_validator


# ══════════════════════════════════════════════════════════════════════
# Economy enum — single source of truth for request-side typing.
# ══════════════════════════════════════════════════════════════════════
# These are the *wire* values, matching the PostgreSQL `economy_type`
# enum literal exactly (sql/001_schema.sql). The TypeScript codegen
# then emits this as a strict string union, which is what catches
# "frontend ships 'High Tech' but PG enum is 'HighTech'"-class bugs
# at PR time instead of at runtime via a 503 problem-detail.
#
# Canonical form is Title-cased PG enum literal. Any of the historical
# input forms (lowercase, spaced, hyphenated) get normalised through
# the BeforeValidator below, so old clients keep working.
EconomyName = Literal[
    'Agriculture',
    'Refinery',
    'Industrial',
    'HighTech',
    'Military',
    'Tourism',
    'Extraction',
]
# Allowed in *filter* fields (`SearchFilters.economy`,
# `GalaxySearchRequest.economy`, …). 'any' opts out of the filter.
EconomyFilter = Union[Literal['any'], EconomyName]


def _normalise_economy_name(v: Any) -> Any:
    """Normalise any historical wire form to the PG enum literal.

    Runs at Pydantic validation time as a BeforeValidator so the field
    type itself can stay strict (`EconomyName` / `EconomyFilter`) while
    still accepting old inputs gracefully:

      'high tech', 'High Tech', 'high-tech', 'hightech' → 'HighTech'
      '', None, 'unknown' → 'any' (for filter fields) / None (otherwise)

    Imported lazily so this module stays free of side-effects at
    import time (search_economies.py is part of apps/api/src/ which
    isn't always on the path during pure-model unit tests).
    """
    if v is None:
        return v
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    # Fast path: already canonical
    if s in ('Agriculture', 'Refinery', 'Industrial', 'HighTech',
             'Military', 'Tourism', 'Extraction', 'any'):
        return s
    if s.lower() in ('any', 'unknown'):
        return 'any'
    # Lazy import to avoid hard dep at model-import time
    try:
        from search_economies import economy_enum_value  # type: ignore
    except ImportError:  # pragma: no cover — only triggered in pure-model tests
        return s
    enum_val = economy_enum_value(s)
    return enum_val if enum_val is not None else s


# Annotated alias the request models use directly so the validator
# only has to be specified once.
EconomyFilterField = Annotated[
    Optional[EconomyFilter],
    BeforeValidator(_normalise_economy_name),
]
EconomyNameField = Annotated[
    EconomyName,
    BeforeValidator(_normalise_economy_name),
]


# ══════════════════════════════════════════════════════════════════════
# Shared mixins / sub-models
# ══════════════════════════════════════════════════════════════════════
class CoordsModel(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


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
    ratingVersion:          Optional[str]   = None
    # v3.1 fields — mirrored in camelCase for frontend parity.
    terraformingPotential:  Optional[float] = None
    bodyDiversity:          Optional[float] = None
    confidence:             Optional[float] = None
    rationale:              Optional[str]   = None


class BodyRingModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    ring_name:    Optional[str]   = None
    ring_type:    Optional[str]   = None
    ring_class:   Optional[str]   = None
    mass_mt:      Optional[float] = None
    inner_radius: Optional[float] = None
    outer_radius: Optional[float] = None
    source:       Optional[str]   = None
    confidence:   Optional[str]   = None
    updated_at:   Optional[Any]   = None


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
    is_ringed:               Optional[bool]  = None
    ring_state:              Optional[Literal['ringed', 'not_ringed', 'unknown']] = None
    rings:                   Optional[list[BodyRingModel]] = None
    ring_count:              Optional[int]   = None
    ring_source:             Optional[str]   = None
    ring_confidence:         Optional[str]   = None
    body_sort_key:           Optional[str]   = None


class StationModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    id:                 Optional[int]   = None
    market_id:          Optional[int]   = None
    name:               Optional[str]   = None
    station_type:       Optional[str]   = None
    distance_from_star: Optional[float] = None
    distance_source:    Optional[str]   = None
    distance_confidence: Optional[str]  = None
    distance_updated_at: Optional[Any]  = None
    station_type_source: Optional[str]  = None
    station_type_confidence: Optional[str] = None
    station_type_updated_at: Optional[Any] = None
    body_id:            Optional[int]   = None
    body_name:          Optional[str]   = None
    station_body_name:  Optional[str]   = None
    body_name_source:   Optional[str]   = None
    body_name_confidence: Optional[str] = None
    body_name_updated_at: Optional[Any] = None
    lane:               Optional[str]   = None
    association_status: Optional[str]   = None
    association_confidence: Optional[str] = None
    association_source: Optional[str]   = None
    resolver_notes:     Optional[str]   = None
    landing_pad_size:   Optional[str]   = None
    primary_economy:    Optional[str]   = None
    secondary_economy:  Optional[str]   = None
    has_market:         Optional[bool]  = None
    has_shipyard:       Optional[bool]  = None
    has_outfitting:     Optional[bool]  = None
    has_refuel:         Optional[bool]  = None
    has_repair:         Optional[bool]  = None
    has_rearm:          Optional[bool]  = None


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
    population:          Optional[int]         = None
    primaryEconomy:      Optional[str]         = None
    secondaryEconomy:    Optional[str]         = None
    security:            Optional[str]         = None
    allegiance:          Optional[str]         = None
    government:          Optional[str]         = None
    is_colonised:        Optional[bool]        = None
    is_being_colonised:  Optional[bool]        = None
    main_star_type:      Optional[str]         = None
    main_star_subtype:   Optional[str]         = None
    archetype_score:     Optional[float]       = None
    archetype_tier:      Optional[TierValue]   = None
    primary_archetype:   Optional[str]         = None
    secondary_archetype: Optional[str]         = None
    archetype_confidence: Optional[float]      = None
    overall_development_potential: Optional[float] = None
    buildability_score:  Optional[float]       = None
    build_complexity:    Optional[str]         = None
    purity_score:        Optional[float]       = None
    contamination_risk:  Optional[float]       = None
    est_total_slots:     Optional[int]         = None
    tags:                list[str]             = Field(default_factory=list)

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
    x:                  Optional[float] = None
    y:                  Optional[float] = None
    z:                  Optional[float] = None
    population:         Optional[int] = None
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
    rating_version:         Optional[str]   = None

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
    # Envelope-level forbid: any unrecognised top-level key is a sign
    # the model is out of date with what `local_search.py` returns —
    # surface that loudly via Pydantic ValidationError (→ 500) so it
    # gets fixed in the same PR. Row-level extras flow through under
    # `results: list[SystemRow]` where SystemRow keeps `extra='allow'`.
    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

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
    x:              Optional[float] = None
    y:              Optional[float] = None
    z:              Optional[float] = None
    population:     Optional[int] = None
    primaryEconomy: Optional[str] = None


class AutocompleteResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    results: list[AutocompleteHit]
    source:  Optional[str] = None


class StatusResponse(BaseModel):
    """`/api/status` and `/api/local/status`."""
    model_config = ConfigDict(extra='forbid')

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
    # Optional fields surfaced by /api/local/status (real DB-backed
    # variant of /api/status). Listed here so the envelope can be
    # `forbid` without breaking that endpoint.
    backend:              Optional[str]   = None
    pg_version:           Optional[str]   = None
    station_count:        Optional[int]   = None
    cluster_count:        Optional[int]   = None
    grid_cells:           Optional[int]   = None
    macro_grid_cells:     Optional[int]   = None
    galaxy_regions:       Optional[int]   = None
    db_size_mb:           Optional[float] = None
    import_status:        Optional[Any]   = None
    cluster_radius_ly:    Optional[int]   = None
    has_cluster_summary:  Optional[bool]  = None
    has_bodies:           Optional[bool]  = None
    reason:               Optional[str]   = None  # populated when available=False


class CacheStatsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

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


class RerankContributions(BaseModel):
    economy:      float
    slots:        float
    strategic:    float
    safety:       float
    terraforming: float
    diversity:    float


class RerankSignals(BaseModel):
    economy_score:              Optional[float] = None
    slots:                      Optional[float] = None
    body_quality:               Optional[float] = None
    orbital_safety:             Optional[float] = None
    terraforming_potential:     Optional[float] = None
    body_diversity:             Optional[float] = None
    confidence:                 Optional[float] = None


class RerankRow(BaseModel):
    model_config = ConfigDict(extra='allow')

    id64:           int
    reranked_score: int
    original_score: Optional[float] = None
    confidence:     Optional[float] = None
    rationale:      Optional[str]   = None
    economy_used:   Optional[str]   = None
    contributions:  Optional[RerankContributions] = None
    signals:        Optional[RerankSignals] = None


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    weights_applied: RerankWeights
    economy_used:    Optional[str] = None
    results:         list[RerankRow]


class WatchlistAlert(BaseModel):
    min_development_score: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices('min_development_score', 'min_score'),
        serialization_alias='min_development_score',
    )
    economy:   Optional[str] = None

    model_config = {'populate_by_name': True}


class NoteBody(BaseModel):
    note: str


# ══════════════════════════════════════════════════════════════════════
# Request models
# ══════════════════════════════════════════════════════════════════════
class SearchFilters(BaseModel):
    distance:   Optional[RangeFilter] = None
    population: Optional[RangeFilter] = None
    # economy: strict typed union (Agriculture, Refinery, Industrial,
    # HighTech, Military, Tourism, Extraction, 'any'). The validator
    # normalises historical wire forms ('high tech', 'High Tech',
    # 'hightech', …) to the canonical PG enum literal — see
    # _normalise_economy_name for the full mapping. Unknown strings
    # fall through and are caught by Pydantic's union check, returning
    # a 422 with a clear "input should be 'Agriculture' or 'Refinery'
    # or …" message instead of the previous 503 from PostgreSQL.
    economy:    EconomyFilterField    = None


class LocalSearchRequest(BaseModel):
    filters:          Optional[SearchFilters] = None
    reference_coords: Optional[CoordsModel]   = None
    sort_by:          Optional[str]            = 'development'
    size:             int                      = Field(default=50, le=500)
    from_:            int                      = Field(default=0, alias='from')
    body_filters:     Optional[BodyFilters]    = None
    require_bio:      Optional[bool]           = None
    require_geo:      Optional[bool]           = None
    require_terra:    Optional[bool]           = None
    star_types:       Optional[list[str]]      = None
    min_development_score: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices('min_development_score', 'min_rating'),
        serialization_alias='min_development_score',
    )
    galaxy_wide:      bool                     = False

    model_config = {'populate_by_name': True}

    @field_validator('sort_by', mode='before')
    @classmethod
    def _normalise_sort_by(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == 'rating':
                return 'development'
        return value


class GalaxySearchRequest(BaseModel):
    # `EconomyFilter` — Agriculture | Refinery | Industrial | HighTech
    # | Military | Tourism | Extraction | 'any'. Old wire forms are
    # accepted via the model's normalising validator; see SearchFilters.
    economy:   EconomyFilterField = 'any'
    min_score: int = Field(default=0, ge=0, le=100)
    limit:     int = Field(default=100, le=500)
    offset:    int = 0


class ClusterRequirement(BaseModel):
    # Cluster requirements MUST name a real economy — there's no
    # 'any' here, an empty cluster requirement is meaningless.
    economy:   EconomyNameField
    min_count: int = Field(default=1, ge=1)
    min_score: int = Field(default=40, ge=0, le=100)


class ClusterSearchRequest(BaseModel):
    requirements:     list[ClusterRequirement]
    limit:            int = Field(default=50, le=200)
    offset:           int = 0
    reference_coords: Optional[CoordsModel] = None


# ══════════════════════════════════════════════════════════════════════
# Archetype engine models (v4.0 — Phase 3)
#
# Strictness policy (consistent with existing models above):
#   • Row / result models  → extra='allow'   (SQL projections legitimately drift)
#   • Response envelopes   → extra='forbid'  (loud failure if contract breaks)
#   • Request models       → extra='forbid'  (prevent silent input discarding)
# ══════════════════════════════════════════════════════════════════════

# ── Valid archetype keys (single source of truth) ────────────────────
ArchetypeKey = Literal[
    'refinery_industrial',
    'extraction_refinery',
    'agriculture_terraforming',
    'hitech_tourism',
    'expansion_capital',
    'trade_logistics',
    'population_capital',
    'ax_forward_base',
    'military_industrial',
    'flexible_multirole',
]

# ── Valid tier values ─────────────────────────────────────────────────
TierValue = Literal['S', 'A', 'B', 'C', 'D']

# ── Build complexity ──────────────────────────────────────────────────
BuildComplexity = Literal['trivial', 'simple', 'moderate', 'advanced', 'expert']


class ArchetypeRerankWeights(BaseModel):
    """
    Weight dimensions for archetype-based reranking.
    All weights should sum to ~1.0 but are not enforced to do so
    (allows intentional emphasis on a single dimension).

    Default profile: balanced across purity, buildability, slots, expansion, logistics.
    """
    model_config = ConfigDict(extra='forbid')

    purity:       float = Field(default=0.30, ge=0.0, le=1.0,
                                description='Clean economy stack, low contamination')
    buildability: float = Field(default=0.25, ge=0.0, le=1.0,
                                description='Ease of build, CP efficiency, T3 scaling')
    slots:        float = Field(default=0.20, ge=0.0, le=1.0,
                                description='Total slot count and topology quality')
    expansion:    float = Field(default=0.15, ge=0.0, le=1.0,
                                description='Overall development potential, growth headroom')
    logistics:    float = Field(default=0.10, ge=0.0, le=1.0,
                                description='Distance from hub, scoopable star accessibility')


class ArchetypeScoreBreakdown(BaseModel):
    """Per-component score decomposition for a single archetype."""
    model_config = ConfigDict(extra='allow')

    body_composition:   Optional[float] = None   # 0-60
    topology:           Optional[float] = None   # 0-25
    pair_synergy_pts:   Optional[float] = None   # 0-15
    purity_factor:      Optional[float] = None   # multiplier
    contamination_risk: Optional[float] = None   # 0-1
    diversity_factor:   Optional[float] = None   # multiplier


class ArchetypeRationale(BaseModel):
    """
    Structured JSONB rationale for a system's primary archetype.
    Schema is intentionally flexible (extra='allow') so Frontier
    mechanic changes can be absorbed without breaking existing consumers.
    """
    model_config = ConfigDict(extra='allow')

    summary:        Optional[str]                     = None
    tier:           Optional[TierValue]               = None
    headline:       Optional[str]                     = None
    positives:      list[str]                         = Field(default_factory=list)
    risks:          list[str]                         = Field(default_factory=list)
    complexity:     Optional[str]                     = None
    build_path:     Optional[str]                     = None
    tags:           list[str]                         = Field(default_factory=list)
    score_breakdown: Optional[ArchetypeScoreBreakdown] = None
    data_confidence: Optional[float]                  = None


class ArchetypeScore(BaseModel):
    """One archetype entry inside SystemArchetypeResponse.archetypes."""
    model_config = ConfigDict(extra='allow')

    score:      float
    tier:       TierValue
    label:      str
    rationale:  Optional[ArchetypeRationale] = None   # only on primary archetype
    rank_global: Optional[int]               = None   # populated in Phase 4


class TopologyDetail(BaseModel):
    """Topology metrics block inside SystemArchetypeResponse."""
    model_config = ConfigDict(extra='allow')

    estimated_orbital_slots: Optional[int]   = None
    estimated_ground_slots:  Optional[int]   = None
    estimated_total_slots:   Optional[int]   = None
    strong_link_potential:   Optional[float] = None
    weak_link_stability:     Optional[float] = None
    contamination_risk:      Optional[float] = None
    orbital_synergy:         Optional[float] = None
    ground_synergy:          Optional[float] = None
    nesting_potential:       Optional[float] = None
    build_flexibility:       Optional[float] = None
    has_viable_surface_port: Optional[bool]  = None
    has_deep_orbital_anchor: Optional[bool]  = None


class EconomyPairDetail(BaseModel):
    """One economy pair synergy entry inside SystemArchetypeResponse."""
    model_config = ConfigDict(extra='allow')

    economy_a:           str
    economy_b:           str
    synergy_score:       float
    purity_achievable:   Optional[float] = None
    contamination_paths: list[Any]       = Field(default_factory=list)


# ── Response: GET /api/archetypes/system/{id64} ───────────────────────
class SystemArchetypeResponse(BaseModel):
    """Full archetype breakdown for one system."""
    model_config = ConfigDict(extra='forbid')

    id64:             int
    name:             str
    coords:           Optional[CoordsModel] = None
    distance_to_sol:  Optional[float]       = None
    main_star_type:   Optional[str]         = None

    # Per-archetype score map: archetype_key → ArchetypeScore
    archetypes:       dict[str, ArchetypeScore]

    primary_archetype:    Optional[str]   = None
    secondary_archetype:  Optional[str]   = None
    archetype_confidence: Optional[float] = None

    overall_development_potential: Optional[float] = None
    buildability_score:  Optional[float]  = None
    build_complexity:    Optional[str]    = None
    cp_efficiency:       Optional[float]  = None
    t3_scaling_viability: Optional[float] = None
    slot_efficiency:     Optional[float]  = None
    purity_score:        Optional[float]  = None
    contamination_risk:  Optional[float]  = None
    stable_top_two_prob: Optional[float]  = None
    confidence:          Optional[float]  = None

    topology:       Optional[TopologyDetail]    = None
    economy_pairs:  list[EconomyPairDetail]     = Field(default_factory=list)
    tags:           list[str]                   = Field(default_factory=list)
    query_ms:       Optional[int]               = None
    _cached:        Optional[bool]              = None


# ── Result row: GET /api/archetypes/rankings ─────────────────────────
class ArchetypeRankingRow(BaseModel):
    """One result row inside ArchetypeRankingsResponse."""
    model_config = ConfigDict(extra='allow')

    id64:             int
    name:             str
    coords:           Optional[CoordsModel] = None
    distance_to_sol:  Optional[float]       = None
    score:            float
    tier:             TierValue
    primary_archetype:    Optional[str]   = None
    secondary_archetype:  Optional[str]   = None
    archetype_confidence: Optional[float] = None
    overall_development_potential: Optional[float] = None
    buildability_score:  Optional[float]  = None
    build_complexity:    Optional[str]    = None
    purity_score:        Optional[float]  = None
    contamination_risk:  Optional[float]  = None
    confidence:          Optional[float]  = None
    has_elw:             Optional[bool]   = None
    elw_count:           Optional[int]    = None
    landable_count:      Optional[int]    = None
    est_total_slots:     Optional[int]    = None
    tags:                list[str]        = Field(default_factory=list)


# ── Response: GET /api/archetypes/rankings ───────────────────────────
class ArchetypeRankingsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    archetype:       str
    archetype_label: str
    results:         list[ArchetypeRankingRow]
    total:           int = 0
    count:           int = 0
    source:          Optional[str] = None
    query_ms:        Optional[int] = None
    _cached:         Optional[bool] = None


# ── Request: POST /api/archetypes/rerank ─────────────────────────────
class ArchetypeRerankRequest(BaseModel):
    """
    Rerank a set of systems by custom archetype weights.

    Either provide explicit weights OR a profile ID.
    If both are given, the profile takes precedence.
    If neither, default ArchetypeRerankWeights are applied.
    """
    model_config = ConfigDict(extra='forbid')

    id64s:     list[int]                      = Field(..., min_length=1, max_length=500)
    archetype: Optional[ArchetypeKey]         = None
    weights:   Optional[ArchetypeRerankWeights] = None
    profile:   Optional[str]                  = None   # profile ID from /api/archetypes/profiles


# ── Result row: POST /api/archetypes/rerank ───────────────────────────
class ArchetypeRerankRow(BaseModel):
    model_config = ConfigDict(extra='allow')

    id64:             int
    reranked_score:   int
    original_score:   Optional[float]        = None
    confidence:       Optional[float]        = None
    rationale:        Optional[ArchetypeRationale] = None


# ── Response: POST /api/archetypes/rerank ─────────────────────────────
class ArchetypeRerankResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    archetype:       Optional[str]              = None
    profile_applied: Optional[str]              = None
    weights_applied: ArchetypeRerankWeights
    results:         list[ArchetypeRerankRow]
    query_ms:        Optional[int]              = None
    _cached:         Optional[bool]             = None


# Backward-compat alias used in ratings.py POST /api/ratings/rerank
RerankedSystemRow = ArchetypeRerankRow


# ── Request: POST /api/archetypes/simulate ───────────────────────────
class PlannedFacility(BaseModel):
    """One facility in a build simulation plan."""
    model_config = ConfigDict(extra='allow')

    type:   str                   # e.g. 'StarPort', 'RefineryHub', 'IndustrialHub'
    tier:   Optional[int] = None  # 1, 2, or 3
    body:   Optional[str] = None  # body key or name


class BuildSimulateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id64:              int
    planned_archetype: ArchetypeKey
    planned_facilities: list[PlannedFacility] = Field(default_factory=list)


# ── Response: POST /api/archetypes/simulate ──────────────────────────
class BuildSimulateResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id64:               int
    planned_archetype:  str
    simulation_score:   int
    contamination_risk: Optional[float] = None
    purity_score:       Optional[float] = None
    buildability_score: Optional[float] = None
    recommendations:    list[str]       = Field(default_factory=list)
    disclaimer:         Optional[str]   = None


# ── Response: simulation/buildability endpoints ───────────────────────
# -- Request/response: POST /api/simulate/build -----------------------------
class SimulateBuildPlacement(BaseModel):
    """One user-selected facility placement in Simulation Preview."""
    model_config = ConfigDict(extra='forbid')

    facility_template_id: str
    local_body_id:        Optional[str] = None
    is_primary_port:      bool          = False
    build_order:          int           = Field(default=1, ge=1)


class SimulateBuildRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:       int
    target_archetype:  str
    placements:        list[SimulateBuildPlacement] = Field(default_factory=list)


class SimulationCPResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    yellow_cp_final:     int
    green_cp_final:      int
    yellow_cp_generated: int = 0
    green_cp_generated:  int = 0
    yellow_cp_spent:     int = 0
    green_cp_spent:      int = 0
    t2_ports:            int
    t3_ports:            int
    warnings:            list[str] = Field(default_factory=list)


class SimulationLink(BaseModel):
    model_config = ConfigDict(extra='forbid')

    port_facility_id:    Optional[str] = None
    support_facility_id: str
    local_body_id:       Optional[str] = None
    economy:             Optional[str] = None
    value:               float = 0.0
    note:                str


class SimulationLinks(BaseModel):
    model_config = ConfigDict(extra='forbid')

    strong_links: list[SimulationLink] = Field(default_factory=list)
    weak_links:   list[SimulationLink] = Field(default_factory=list)


class SimulationInheritedEconomy(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source_body_id:     Optional[str] = None
    source_body_name:   Optional[str] = None
    base_economies:     list[str] = Field(default_factory=list)
    modifier_economies: list[str] = Field(default_factory=list)
    weights:            dict[str, float] = Field(default_factory=dict)
    purity:             float
    confidence:         float
    caveats:            list[str] = Field(default_factory=list)
    strategic_tags:     list[str] = Field(default_factory=list)


class SimulateBuildResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:         int
    mechanics_version:   str = ''
    target_archetype:    str
    final_score:         float
    composition_score:   float
    buildability_score:  float
    build_complexity:    Literal['simple', 'moderate', 'advanced', 'expert']
    confidence:          float
    cp:                  SimulationCPResult
    cp_timeline:         list[dict[str, Any]] = Field(default_factory=list)
    cp_repair_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    observation_summary: dict[str, Any] = Field(default_factory=dict)
    prediction_observation_diffs: list[dict[str, Any]] = Field(default_factory=list)
    economy_composition: dict[str, float] = Field(default_factory=dict)
    economy_order:       list[str] = Field(default_factory=list)
    economy_stack:       dict[str, Any] = Field(default_factory=dict)
    port_economy_states: list[dict[str, Any]] = Field(default_factory=list)
    influence_ledger:    list[dict[str, Any]] = Field(default_factory=list)
    inherited_economies: list[SimulationInheritedEconomy] = Field(default_factory=list)
    topology:            dict[str, Any] = Field(default_factory=dict)
    services:            dict[str, Any] = Field(default_factory=dict)
    port_service_states: list[dict[str, Any]] = Field(default_factory=list)
    service_unlock_ledger: list[dict[str, Any]] = Field(default_factory=list)
    data_quality:        dict[str, str] = Field(default_factory=dict)
    confidence_signals:  list[dict[str, Any]] = Field(default_factory=list)
    mechanics_trace:     dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    top_two_alignment:   str
    contamination_risk:  str
    warnings:            list[str] = Field(default_factory=list)
    strengths:           list[str] = Field(default_factory=list)
    recommendations:     list[str] = Field(default_factory=list)
    mechanics_notes:     list[str] = Field(default_factory=list)
    links:               SimulationLinks


class RecommendedBuildPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id:                 str
    label:              str
    summary:            str
    complexity:         Literal['simple', 'moderate', 'advanced', 'expert']
    confidence:         float
    final_score:        float
    composition_score:  float
    buildability_score: float
    economy_result:     dict[str, float] = Field(default_factory=dict)
    port_economy_summary: list[str] = Field(default_factory=list)
    cp_result:          SimulationCPResult
    build_order:        list[SimulateBuildPlacement] = Field(default_factory=list)
    strengths:          list[str] = Field(default_factory=list)
    warnings:           list[str] = Field(default_factory=list)
    tradeoffs:          list[str] = Field(default_factory=list)
    next_actions:       list[str] = Field(default_factory=list)
    selected_body_id:   Optional[str] = None
    selected_body_name: Optional[str] = None
    body_selection_reason: str = ''
    mechanics_basis:    list[str] = Field(default_factory=list)
    economy_caveats:    list[str] = Field(default_factory=list)
    assumptions:        list[str] = Field(default_factory=list)
    regional_role:      Optional[str] = None
    nearest_colony_distance: Optional[float] = None
    archetype_regional_fit: Optional[float] = None
    regional_rationale: dict[str, Any] = Field(default_factory=dict)
    decision_explanation: dict[str, Any] = Field(default_factory=dict)
    rank_breakdown:     dict[str, float] = Field(default_factory=dict)
    simulation_request: SimulateBuildRequest
    is_default:         bool = False


class RecommendedBuildsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:              int
    mechanics_version:        str = ''
    target_archetype:         str
    best_suggested_archetype: str
    recommended_next_action:  str
    plans:                   list[RecommendedBuildPlan] = Field(default_factory=list)
    warnings:                list[str] = Field(default_factory=list)


class RegionalAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:                 int
    mechanics_version:           str = ''
    nearest_colonised_system:    Optional[dict[str, Any]] = None
    counts:                      dict[str, int] = Field(default_factory=dict)
    scores:                      dict[str, float] = Field(default_factory=dict)
    regional_role:               str = 'unknown'
    archetype_regional_fit:      dict[str, float] = Field(default_factory=dict)
    rationale:                   dict[str, Any] = Field(default_factory=dict)
    data_quality:                dict[str, str] = Field(default_factory=dict)
    confidence_signals:          list[dict[str, Any]] = Field(default_factory=list)
    computed_at:                 Optional[Any] = None


class FacilityTemplateResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id:                  str
    name:                str
    category:            str
    tier:                int
    economy:             Optional[str] = None
    is_port:             bool
    is_support_facility: bool
    allowed_location:    str
    pad_size:            Optional[str] = None
    confidence:          Optional[str] = None
    notes:               Optional[str] = None
    prerequisites:       list[dict[str, Any]] = Field(default_factory=list)
    economy_effects:     dict[str, Any] = Field(default_factory=dict)
    yellow_cp_generated: int = 0
    green_cp_generated:  int = 0
    yellow_cp_cost:      int = 0
    green_cp_cost:       int = 0
    stat_effects:        dict[str, Any] = Field(default_factory=dict)


SimulationSource = Literal['precomputed', 'computed', 'insufficient_data']
SlotDataSource = Literal['eddn', 'spansh', 'none']
SlotPredictionStatus = Literal['predicted', 'unknown', 'observed']


class SlotReason(BaseModel):
    """One explainability note for a per-body slot prediction."""
    model_config = ConfigDict(extra='allow')

    factor:       str
    delta:        Optional[float] = None
    note:         Optional[str]   = None


class BodySlotPrediction(BaseModel):
    """One body row returned by GET /api/systems/{id64}/slot-predictions."""
    model_config = ConfigDict(extra='allow')

    system_address: int
    body_id:        int
    body_name:      Optional[str]   = None
    planet_class:   Optional[str]   = None
    predicted_ground_slots: Optional[int] = None
    predicted_orbital_slots: Optional[int] = None
    prediction_status: SlotPredictionStatus = 'unknown'
    confidence_label: Optional[str] = None
    prediction_version: Optional[str] = None
    validation_note: Optional[str] = None
    required_input_missing: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    source_label: Optional[str] = None
    estimated_surface_slots: Optional[int] = None
    estimated_orbital_slots: Optional[int] = None
    slot_confidence: Optional[float] = None
    slot_source:    Optional[str] = None
    reasons:        list[SlotReason]= Field(default_factory=list)
    is_ringed:      Optional[bool]  = None
    is_landable:    Optional[bool]  = None
    radius:         Optional[float] = None


class SlotPredictionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:             int
    data_source:             SlotDataSource
    body_count:              int
    predicted_orbital_slots_total: Optional[int] = None
    predicted_ground_slots_total:  Optional[int] = None
    prediction_status: SlotPredictionStatus = 'unknown'
    prediction_version: str
    confidence_label: Optional[str] = None
    disclaimer: str
    validation_note: str
    required_input_missing: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    source_label: Optional[str] = None
    estimated_orbital_slots: Optional[int] = None
    estimated_ground_slots:  Optional[int] = None
    slot_confidence:         Optional[float] = None
    slot_confidence_label:   Optional[str] = None
    predictions:             list[BodySlotPrediction] = Field(default_factory=list)
    note:                    Optional[str] = None


class BuildabilityIssue(BaseModel):
    """Bottleneck/opportunity item with frontend-friendly wording."""
    model_config = ConfigDict(extra='allow')

    type:        str
    description: str
    severity:    Optional[str] = None
    detail:      Optional[str] = None


class BuildabilityBottleneck(BuildabilityIssue):
    """A buildability limitation surfaced to the frontend."""


class BuildabilityOpportunity(BuildabilityIssue):
    """A buildability advantage surfaced to the frontend."""


class RecommendedBuildStep(BaseModel):
    model_config = ConfigDict(extra='allow')

    step:                 int
    facility_id:          Optional[str] = None
    facility_name:        Optional[str] = None
    location:             Optional[str] = None
    notes:                Optional[str] = None
    cumulative_yellow_cp: Optional[int] = None
    cumulative_green_cp:  Optional[int] = None


class BuildabilityData(BaseModel):
    """Stable buildability payload used both directly and inside summaries."""
    model_config = ConfigDict(extra='allow')

    source:                  SimulationSource
    estimated_orbital_slots: Optional[int]   = None
    estimated_ground_slots:  Optional[int]   = None
    slot_confidence:         Optional[float] = None
    slot_confidence_label:   Optional[str]   = None
    estimated_yellow_cp:     Optional[int]   = None
    estimated_green_cp:      Optional[int]   = None
    max_t2_ports:            Optional[int]   = None
    max_t3_ports:            Optional[int]   = None
    cp_bottleneck_score:     Optional[float] = None
    slot_exhaustion_risk:    Optional[float] = None
    build_order_sensitivity: Optional[float] = None
    build_complexity:        Optional[str]   = None
    bottlenecks:             list[BuildabilityBottleneck] = Field(default_factory=list)
    opportunities:           list[BuildabilityOpportunity] = Field(default_factory=list)
    recommended_build_order: list[RecommendedBuildStep] = Field(default_factory=list)
    warnings:                list[str]       = Field(default_factory=list)
    note:                    Optional[str]   = None


class TopologyContextResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    orbital_slots:          int   = 0
    surface_slots:          int   = 0
    has_ringed_body:        bool  = False
    has_viable_surface:     bool  = True
    has_deep_anchor:        bool  = False
    orbital_synergy:        float = 0.0
    ground_synergy:         float = 0.0
    build_flexibility:      float = 0.0
    contamination_risk:     float = 0.0
    strong_link_potential:  float = 0.0
    weak_link_stability:    float = 0.0
    nesting_potential:      float = 0.0
    slot_confidence:        float = 0.0


class BuildabilityResponse(BuildabilityData):
    model_config = ConfigDict(extra='forbid')

    system_id64:      int
    system_name:      Optional[str] = None
    archetype:        Optional[str] = None
    topology_summary: list[str] = Field(default_factory=list)
    topology:         Optional[TopologyContextResponse] = None


# Backwards-compatible public name used by older imports/docs.
SystemBuildabilityResponse = BuildabilityResponse


class SimulationClassification(BaseModel):
    model_config = ConfigDict(extra='allow')

    primary_archetype:   Optional[str]   = None
    secondary_archetype: Optional[str]   = None
    confidence:          Optional[float] = None
    overall_potential:   Optional[float] = None
    purity_score:        Optional[float] = None
    display_tags:        list[str]       = Field(default_factory=list)
    data_confidence:     Optional[float] = None
    rationale:           Optional[Any]   = None


class SimulationBodySummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    elw_count:           int = 0
    hmc_count:           int = 0
    gas_giant_count:     int = 0
    terraformable_count: int = 0
    bio_signal_total:    int = 0
    geo_signal_total:    int = 0
    scanned_body_count:  int = 0


class SimulationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_id64:       int
    mechanics_version: str = ''
    system_name:       Optional[str] = None
    archetype:         Optional[str] = None
    classification:    Optional[SimulationClassification] = None
    archetype_scores:  dict[str, float] = Field(default_factory=dict)
    body_summary:      Optional[SimulationBodySummary] = None
    buildability:      BuildabilityData
    topology_summary:  list[str] = Field(default_factory=list)
    regional_context:  Optional[RegionalAnalysisResponse] = None
    distance_to_sol:   Optional[float] = None
    main_star_type:    Optional[str] = None


# ── Profile entry: GET /api/archetypes/profiles ──────────────────────
class ArchetypeProfile(BaseModel):
    model_config = ConfigDict(extra='allow')

    id:          str
    label:       str
    description: str
    archetype:   Optional[str]             = None
    weights:     ArchetypeRerankWeights


# ── Response: GET /api/archetypes/profiles ───────────────────────────
class ArchetypesProfilesResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    profiles: list[ArchetypeProfile]


# ── Optimiser V1: Candidate Generation (Stage 5A) ────────────────────
class OptimiserCandidatePlacement(BaseModel):
    """One facility placement in an optimiser candidate."""
    model_config = ConfigDict(extra='forbid')

    facility_template_id: str
    local_body_id: Optional[str] = None
    is_primary_port: bool = False
    build_order: int = Field(default=1, ge=1)


class OptimiserCandidatePreviewSummary(BaseModel):
    """Lightweight optimiser-specific summary of Simulation Preview output."""
    model_config = ConfigDict(extra='forbid')

    final_score: Optional[float] = None
    composition_score: Optional[float] = None
    buildability_score: Optional[float] = None
    confidence: Optional[float] = None
    build_complexity: Optional[str] = None
    warnings_count: int = 0
    cp_negative: Optional[bool] = None
    top_two_alignment: Optional[str] = None


class OptimiserCandidate(BaseModel):
    """A single bounded Stage 5A candidate plan."""
    model_config = ConfigDict(extra='forbid')

    candidate_id: str
    label: str
    target_archetype: str
    strategy: str
    placements: list[OptimiserCandidatePlacement]
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    preview_summary: Optional[OptimiserCandidatePreviewSummary] = None


class OptimiserRankBreakdown(BaseModel):
    """Structured explanation for a ranked optimiser candidate."""
    model_config = ConfigDict(extra='forbid')

    preview_score_component: float = 0.0
    composition_component: float = 0.0
    buildability_component: float = 0.0
    confidence_component: float = 0.0
    alignment_component: float = 0.0
    warning_penalty: float = 0.0
    cp_penalty: float = 0.0
    strategy_modifier: float = 0.0
    total_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class OptimiserRankedCandidate(BaseModel):
    """Ranking entry that references a candidate by ID without duplicating it."""
    model_config = ConfigDict(extra='forbid')

    candidate_id: str
    rank: int = Field(ge=1)
    rank_score: float = Field(ge=0.0, le=100.0)
    rank_tier: str
    rank_breakdown: OptimiserRankBreakdown


class OptimiserRankingResponse(BaseModel):
    """Top-level optional Stage 5B ranking result."""
    model_config = ConfigDict(extra='forbid')

    target_archetype: str
    ranked_candidates: list[OptimiserRankedCandidate]
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class OptimiserCandidatesRequest(BaseModel):
    """Request for bounded deterministic Stage 5A candidate generation."""
    model_config = ConfigDict(extra='forbid')

    system_id64: int
    target_archetype: Optional[str] = None
    target_archetype_key: Optional[str] = None
    max_candidates: int = Field(default=5, ge=1, le=10)
    preferred_body_ids: list[str] = Field(default_factory=list)
    allow_estimated_data: bool = True
    run_preview: bool = True
    include_ranking: bool = False


class OptimiserCandidatesResponse(BaseModel):
    """Response envelope for bounded deterministic Stage 5A candidates."""
    model_config = ConfigDict(extra='forbid')

    system_id64: int
    target_archetype: str
    candidate_count: int
    candidates: list[OptimiserCandidate]
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ranking: Optional[OptimiserRankingResponse] = None


# Backwards-compatible singular names for older imports.
OptimiserCandidateRequest = OptimiserCandidatesRequest
OptimiserCandidateResponse = OptimiserCandidatesResponse
