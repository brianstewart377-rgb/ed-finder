"""Resolve existing station rows to body/lane associations.

The resolver is intentionally conservative. It can produce confirmed exact
matches, inferred matches with explicit source/notes, or unresolved records.
It never fabricates body ids and never converts unknown station types into
permanent colony-slot occupancy.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


DISTANCE_MATCH_TOLERANCE_LS = 0.01

LANE_ORBITAL_TYPES = {
    'Coriolis',
    'Orbis',
    'Ocellus',
    'Outpost',
    'AsteroidBase',
}

LANE_SURFACE_TYPES = {
    'PlanetaryPort',
    'PlanetaryOutpost',
}

LANE_NON_COLONY_TYPES = {
    'FleetCarrier',
    'MegaShip',
}

PERMANENT_COLONY_SLOT_TYPES = LANE_ORBITAL_TYPES | LANE_SURFACE_TYPES
TRANSIENT_NON_SLOT_TYPES = LANE_NON_COLONY_TYPES

STATION_TYPE_LABELS = {
    'coriolis': 'Coriolis',
    'coriolisstarport': 'Coriolis',
    'orbis': 'Orbis',
    'orbisstarport': 'Orbis',
    'ocellus': 'Ocellus',
    'ocellusstarport': 'Ocellus',
    'outpost': 'Outpost',
    'asteroidbase': 'AsteroidBase',
    'planetaryport': 'PlanetaryPort',
    'planetaryoutpost': 'PlanetaryOutpost',
    'planetarysettlement': 'PlanetaryOutpost',
    'settlement': 'PlanetaryOutpost',
    'surfacesettlement': 'PlanetaryOutpost',
    'surfacestation': 'PlanetaryPort',
    'craterport': 'PlanetaryPort',
    'crateroutpost': 'PlanetaryOutpost',
    'fleetcarrier': 'FleetCarrier',
    'carrier': 'FleetCarrier',
    'megaship': 'MegaShip',
    'unknown': 'Unknown',
}


@dataclass(frozen=True)
class StationBodyAssociation:
    station_id: int | None
    market_id: int | None
    system_id64: int | None
    body_id: int | None
    body_name: str | None
    lane: str
    association_status: str
    association_confidence: str
    association_source: str
    resolver_notes: str | None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            'body_id': self.body_id,
            'body_name': self.body_name,
            'lane': self.lane,
            'association_status': self.association_status,
            'association_confidence': self.association_confidence,
            'association_source': self.association_source,
            'resolver_notes': self.resolver_notes,
        }

    def to_db_tuple(self) -> tuple[Any, ...]:
        return (
            self.station_id,
            self.market_id,
            self.system_id64,
            self.body_id,
            self.body_name,
            self.lane,
            self.association_status,
            self.association_confidence,
            self.association_source,
            self.resolver_notes,
        )


def classify_station_lane(station_type: Any) -> tuple[str, str | None]:
    canonical = normalise_station_type_label(station_type)
    if canonical is None:
        return 'unknown', 'Station type missing; lane cannot be classified.'
    if canonical == 'Unknown':
        return 'unknown', f'Station type {station_type!s} is not mapped to a colony slot lane.'
    if canonical in LANE_NON_COLONY_TYPES:
        return 'unknown', f'{station_type} is not treated as permanent colony-slot infrastructure.'
    if canonical in LANE_SURFACE_TYPES:
        return 'surface', None
    if canonical in LANE_ORBITAL_TYPES:
        return 'orbital', None
    return 'unknown', f'Station type {station_type!s} is not mapped to a colony slot lane.'


def is_permanent_colony_slot_station_type(station_type: Any) -> bool:
    return normalise_station_type_label(station_type) in PERMANENT_COLONY_SLOT_TYPES


def is_transient_non_slot_station_type(station_type: Any) -> bool:
    return normalise_station_type_label(station_type) in TRANSIENT_NON_SLOT_TYPES


def normalise_station_type_label(station_type: Any) -> str | None:
    token = _normalise_token(station_type)
    if not token:
        return None
    return STATION_TYPE_LABELS.get(token, 'Unknown')


def resolve_station_body_association(
    station: Mapping[str, Any],
    bodies: Sequence[Mapping[str, Any]],
    *,
    existing_link: Mapping[str, Any] | None = None,
    no_overwrite_confirmed: bool = True,
    distance_tolerance_ls: float = DISTANCE_MATCH_TOLERANCE_LS,
) -> StationBodyAssociation:
    """Resolve one station against bodies in the same system.

    A current confirmed/manual link is preserved by default for permanent station
    types so a weaker resolver pass cannot downgrade curated truth.
    """
    station_type = station.get('station_type') or station.get('stationType') or station.get('type')
    station_id = _read_int(station.get('station_id')) or _read_int(station.get('id'))
    market_id = _read_int(station.get('market_id')) or station_id
    system_id64 = _read_int(station.get('system_id64'))
    raw_body_name = _clean_body_name(
        station.get('station_body_name'),
        station.get('body_name'),
        station.get('bodyName'),
        station.get('body'),
    )
    lane, lane_note = classify_station_lane(station_type)

    if is_transient_non_slot_station_type(station_type):
        return _unresolved(
            station_id,
            market_id,
            system_id64,
            None,
            lane,
            'Transient/mobile infrastructure is ignored for station_body_links.',
            'transient_non_slot',
            lane_note,
        )

    preserved = _preserved_confirmed_link(station, existing_link, no_overwrite_confirmed)
    if preserved is not None:
        return preserved

    explicit_body_id = _read_int(station.get('body_id')) or _read_int(station.get('local_body_id'))
    if explicit_body_id is not None:
        match = _body_by_id(bodies, explicit_body_id)
        if match is not None:
            return _association(
                station_id,
                market_id,
                system_id64,
                match,
                lane,
                'confirmed',
                'exact',
                'resolver_body_id',
                lane_note,
            )
        return _unresolved(
            station_id,
            market_id,
            system_id64,
            raw_body_name,
            lane,
            'Station body_id did not match a body in this system.',
            'resolver_body_id',
            lane_note,
        )

    if raw_body_name:
        name_matches = [body for body in bodies if _normalise_name(body.get('name')) == _normalise_name(raw_body_name)]
        if len(name_matches) == 1:
            return _association(
                station_id,
                market_id,
                system_id64,
                name_matches[0],
                lane,
                'confirmed',
                'exact',
                'resolver_body_name',
                lane_note,
            )
        if len(name_matches) > 1:
            return _unresolved(
                station_id,
                market_id,
                system_id64,
                raw_body_name,
                lane,
                'Station body_name matched multiple bodies in this system.',
                'resolver_body_name',
                lane_note,
            )

    station_distance = _first_float(
        station.get('distance_from_star'),
        station.get('distance_to_arrival'),
        station.get('distanceToArrival'),
        station.get('distanceFromArrival'),
        station.get('distanceFromArrivalLS'),
    )
    if station_distance is not None:
        distance_matches = [
            body for body in bodies
            if _distance_matches(station_distance, _read_float(body.get('distance_from_star')), distance_tolerance_ls)
        ]
        if len(distance_matches) == 1:
            return _association(
                station_id,
                market_id,
                system_id64,
                distance_matches[0],
                lane,
                'inferred',
                'strong_inference',
                'resolver_distance',
                _join_notes(
                    f'Unique distance_from_star match within {distance_tolerance_ls:g} ls.',
                    lane_note,
                ),
            )
        if len(distance_matches) > 1:
            return _unresolved(
                station_id,
                market_id,
                system_id64,
                raw_body_name,
                lane,
                f'distance_from_star matched {len(distance_matches)} bodies within {distance_tolerance_ls:g} ls.',
                'resolver_distance',
                lane_note,
            )

    return _unresolved(
        station_id,
        market_id,
        system_id64,
        raw_body_name,
        lane,
        'No exact body id, exact body_name, or unique distance_from_star match is available.',
        'unknown',
        lane_note,
    )


def build_station_body_link_rows(
    stations: Sequence[Mapping[str, Any]],
    bodies: Sequence[Mapping[str, Any]],
    existing_links: Mapping[int, Mapping[str, Any]] | None = None,
    *,
    no_overwrite_confirmed: bool = True,
) -> list[StationBodyAssociation]:
    links = existing_links or {}
    out: list[StationBodyAssociation] = []
    for station in stations:
        station_type = station.get('station_type') or station.get('stationType') or station.get('type')
        if is_transient_non_slot_station_type(station_type):
            continue
        station_id = _read_int(station.get('station_id')) or _read_int(station.get('id'))
        out.append(resolve_station_body_association(
            station,
            bodies,
            existing_link=links.get(station_id) if station_id is not None else None,
            no_overwrite_confirmed=no_overwrite_confirmed,
        ))
    return out


def _preserved_confirmed_link(
    station: Mapping[str, Any],
    existing_link: Mapping[str, Any] | None,
    no_overwrite_confirmed: bool,
) -> StationBodyAssociation | None:
    if not existing_link or not no_overwrite_confirmed:
        return None
    if existing_link.get('association_status') != 'confirmed':
        return None
    return StationBodyAssociation(
        station_id=_read_int(existing_link.get('station_id')) or _read_int(station.get('id')),
        market_id=_read_int(existing_link.get('market_id')) or _read_int(station.get('market_id')) or _read_int(station.get('id')),
        system_id64=_read_int(existing_link.get('system_id64')) or _read_int(station.get('system_id64')),
        body_id=_read_int(existing_link.get('body_id')),
        body_name=_clean_text(existing_link.get('body_name')) or _clean_text(station.get('body_name')),
        lane=_clean_text(existing_link.get('lane')) or 'unknown',
        association_status='confirmed',
        association_confidence=_clean_text(existing_link.get('association_confidence')) or 'exact',
        association_source=_clean_text(existing_link.get('association_source')) or 'manual',
        resolver_notes=_clean_text(existing_link.get('resolver_notes')),
    )


def _association(
    station_id: int | None,
    market_id: int | None,
    system_id64: int | None,
    body: Mapping[str, Any],
    lane: str,
    status: str,
    confidence: str,
    source: str,
    notes: str | None,
) -> StationBodyAssociation:
    return StationBodyAssociation(
        station_id=station_id,
        market_id=market_id,
        system_id64=system_id64 or _read_int(body.get('system_id64')),
        body_id=_read_int(body.get('id')) or _read_int(body.get('body_id')),
        body_name=_clean_text(body.get('name')) or _clean_text(body.get('body_name')),
        lane=lane,
        association_status=status,
        association_confidence=confidence,
        association_source=source,
        resolver_notes=notes,
    )


def _unresolved(
    station_id: int | None,
    market_id: int | None,
    system_id64: int | None,
    body_name: str | None,
    lane: str,
    notes: str,
    source: str,
    lane_note: str | None,
) -> StationBodyAssociation:
    return StationBodyAssociation(
        station_id=station_id,
        market_id=market_id,
        system_id64=system_id64,
        body_id=None,
        body_name=body_name,
        lane=lane,
        association_status='unresolved',
        association_confidence='unresolved',
        association_source=source,
        resolver_notes=_join_notes(notes, lane_note),
    )


def _body_by_id(bodies: Sequence[Mapping[str, Any]], body_id: int) -> Mapping[str, Any] | None:
    for body in bodies:
        candidate_id = _read_int(body.get('id')) or _read_int(body.get('body_id'))
        if candidate_id == body_id:
            return body
    return None


def _distance_matches(left: float, right: float | None, tolerance: float) -> bool:
    if right is None:
        return False
    return abs(left - right) <= tolerance


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _clean_body_name(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, Mapping):
            value = _clean_body_name(value.get('name'), value.get('bodyName'), value.get('body_name'))
        text = _clean_text(value)
        if text:
            return text
    return None


def _read_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _read_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and isfinite(value):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if isfinite(parsed) else None
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _read_float(value)
        if parsed is not None:
            return parsed
    return None


def _normalise_name(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.strip().lower().split())


def _normalise_token(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ''.join(ch for ch in value.lower() if ch.isalnum())


def _join_notes(*notes: str | None) -> str | None:
    clean = [note.strip() for note in notes if isinstance(note, str) and note.strip()]
    return ' '.join(clean) if clean else None
