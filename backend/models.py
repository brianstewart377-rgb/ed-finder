"""Pydantic request + response models.

These are data-shape contracts — keep side-effects out, do not import
DB / Redis / config from here. All models referenced by more than one
router live here; router-local one-off shapes can stay next to their
endpoint.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════
# Response models
# ══════════════════════════════════════════════════════════════════════
class CoordsModel(BaseModel):
    x: float
    y: float
    z: float


class RatingModel(BaseModel):
    score:             Optional[float] = None
    scoreAgriculture:  Optional[float] = None
    scoreRefinery:     Optional[float] = None
    scoreIndustrial:   Optional[float] = None
    scoreHightech:     Optional[float] = None
    scoreMilitary:     Optional[float] = None
    scoreTourism:      Optional[float] = None
    economySuggestion: Optional[str]   = None
    breakdown:         Optional[dict]  = None


class BodyModel(BaseModel):
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
    id:                 Optional[int]   = None
    name:               Optional[str]   = None
    station_type:       Optional[str]   = None
    distance_from_star: Optional[float] = None
    landing_pad_size:   Optional[str]   = None
    has_market:         Optional[bool]  = None
    has_shipyard:       Optional[bool]  = None
    has_outfitting:     Optional[bool]  = None


class SystemModel(BaseModel):
    id64:                Optional[int]   = None
    name:                str             = 'Unknown'
    coords:              Optional[CoordsModel] = None
    distance:            Optional[float] = None
    population:          int             = 0
    primaryEconomy:      Optional[str]   = None
    secondaryEconomy:    Optional[str]   = None
    security:            Optional[str]   = None
    allegiance:          Optional[str]   = None
    government:          Optional[str]   = None
    is_colonised:        bool            = False
    is_being_colonised:  bool            = False
    main_star_type:      Optional[str]   = None
    main_star_subtype:   Optional[str]   = None
    _rating:             Optional[RatingModel] = None
    bodies:              list[BodyModel]       = []
    stations:            list[StationModel]    = []


class SearchResponse(BaseModel):
    results: list[dict]
    total:   int
    count:   int


class SystemDetailResponse(BaseModel):
    record: dict
    system: dict


class HealthResponse(BaseModel):
    status:   str
    database: str
    version:  str


class WatchlistAlert(BaseModel):
    min_score: Optional[int] = None
    economy:   Optional[str] = None


class NoteBody(BaseModel):
    note: str


# ══════════════════════════════════════════════════════════════════════
# Request models
# ══════════════════════════════════════════════════════════════════════
class SearchFilters(BaseModel):
    distance:   Optional[dict] = None
    population: Optional[dict] = None
    economy:    Optional[str]  = None


class LocalSearchRequest(BaseModel):
    filters:          Optional[SearchFilters] = None
    reference_coords: Optional[dict]          = None
    sort_by:          Optional[str]            = 'rating'
    size:             int                      = Field(default=50, le=500)
    from_:            int                      = Field(default=0, alias='from')
    body_filters:     Optional[dict]           = None
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
    reference_coords: Optional[dict] = None
