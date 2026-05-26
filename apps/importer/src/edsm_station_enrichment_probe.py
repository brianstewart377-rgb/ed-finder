#!/usr/bin/env python3
"""Targeted EDSM station/body enrichment dry-run.

This command compares one ED-Finder system against EDSM per-system station and
body payloads. It reports possible station-data and station/body-link
enrichment, but deliberately performs no database writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import RealDictCursor

def _station_resolver_import_paths(script_path: Path) -> list[Path]:
    """Return import paths for repo checkouts and flat importer container mounts."""
    resolved = script_path.resolve()
    candidates = [resolved.parent]
    if len(resolved.parents) > 2:
        candidates.insert(0, resolved.parents[2] / 'api' / 'src')
    return candidates


for import_path in _station_resolver_import_paths(Path(__file__)):
    if import_path.exists() and str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from station_body_resolver import (  # noqa: E402
    DISTANCE_MATCH_TOLERANCE_LS,
    classify_station_lane,
    is_permanent_colony_slot_station_type,
    is_transient_non_slot_station_type,
    normalise_station_type_label,
)


EDSM_SYSTEM_API_BASE = 'https://www.edsm.net/api-system-v1'
DEFAULT_TIMEOUT_SECONDS = 20.0
STATION_DISTANCE_CONFLICT_TOLERANCE_LS = DISTANCE_MATCH_TOLERANCE_LS
BODY_DISTANCE_MATCH_TOLERANCE_LS = DISTANCE_MATCH_TOLERANCE_LS

VALID_ECONOMIES = {
    'HighTech', 'Agriculture', 'Refinery', 'Industrial', 'Military',
    'Tourism', 'Extraction', 'Colony', 'Terraforming', 'Prison',
    'Damaged', 'Rescue', 'Repair', 'Carrier', 'None', 'Unknown',
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Dry-run targeted EDSM station/body enrichment for one system.',
    )
    parser.add_argument('--dsn', default=os.environ.get('DATABASE_URL'), help='Postgres DSN. Defaults to DATABASE_URL.')
    parser.add_argument('--system-name', default=None, help='System name to probe.')
    parser.add_argument('--system-id64', type=int, default=None, help='Local ED system address/id64, if known.')
    parser.add_argument('--dry-run', action='store_true', help='Accepted for clarity; dry-run is always enabled.')
    parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON report.')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_SECONDS, help='EDSM request timeout in seconds.')
    parser.add_argument('--no-network', action='store_true', help='Skip EDSM requests and report local-only unresolved matches.')
    parser.add_argument('--local-only', action='store_true', help='Alias for --no-network.')
    parser.add_argument('--apply', action='store_true', help='Not implemented. This probe never writes database changes.')
    return parser.parse_args(argv)


def fetch_local_payload(conn, *, system_name: str | None, system_id64: int | None) -> dict[str, Any]:
    """Load one local system and its station/body/link evidence."""
    if system_name is None and system_id64 is None:
        raise ValueError('--system-name or --system-id64 is required.')

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if system_id64 is not None:
            cur.execute("""
                SELECT id64, name, x, y, z
                FROM systems
                WHERE id64 = %s
            """, (system_id64,))
        else:
            cur.execute("""
                SELECT id64, name, x, y, z
                FROM systems
                WHERE lower(name) = lower(%s)
                ORDER BY name
                LIMIT 2
            """, (system_name,))
        system_rows = [dict(row) for row in cur.fetchall()]
        if not system_rows:
            raise LookupError('Local system not found.')
        if len(system_rows) > 1:
            raise LookupError(f'Local system name {system_name!r} matched multiple rows.')
        system = system_rows[0]

        if system_name is not None and _normalise_name(system['name']) != _normalise_name(system_name):
            raise LookupError(
                f'Local system id64 {system["id64"]} is {system["name"]!r}, not {system_name!r}.'
            )

        cur.execute("""
            SELECT id, system_id64, name, body_type::text AS body_type, subtype, distance_from_star
            FROM bodies
            WHERE system_id64 = %s
        """, (system['id64'],))
        bodies = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT id, id AS market_id, system_id64, name, station_type::text AS station_type,
                   distance_from_star, body_name AS station_body_name, body_name,
                   primary_economy::text AS primary_economy,
                   secondary_economy::text AS secondary_economy,
                   has_market, has_shipyard, has_outfitting,
                   has_refuel, has_repair, has_rearm
            FROM stations
            WHERE system_id64 = %s
        """, (system['id64'],))
        stations = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT to_regclass('public.station_body_links') IS NOT NULL AS exists")
        has_station_links = bool(cur.fetchone()['exists'])
        existing_links: dict[int, dict[str, Any]] = {}
        if has_station_links:
            cur.execute("""
                SELECT station_id, market_id, system_id64, body_id, body_name, lane,
                       association_status, association_confidence, association_source,
                       resolver_notes
                FROM station_body_links
                WHERE system_id64 = %s
            """, (system['id64'],))
            existing_links = {
                int(row['station_id']): dict(row)
                for row in cur.fetchall()
                if _read_int(row.get('station_id')) is not None
            }

    return {
        'system': system,
        'bodies': bodies,
        'stations': stations,
        'existing_links': existing_links,
    }


def fetch_edsm_system(system_name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Fetch EDSM station and body payloads for one named system."""
    return {
        'stations': _fetch_edsm_endpoint('stations', system_name, timeout=timeout),
        'bodies': _fetch_edsm_endpoint('bodies', system_name, timeout=timeout),
    }


def _fetch_edsm_endpoint(endpoint: str, system_name: str, *, timeout: float) -> Any:
    query = urlencode({'systemName': system_name})
    url = f'{EDSM_SYSTEM_API_BASE}/{endpoint}?{query}'
    request = Request(url, headers={'User-Agent': 'ed-finder-edsm-station-enrichment-probe/1.0'})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def build_enrichment_report(
    *,
    local_system: Mapping[str, Any],
    local_stations: Sequence[Mapping[str, Any]],
    local_bodies: Sequence[Mapping[str, Any]],
    existing_links: Mapping[int, Mapping[str, Any]] | None,
    edsm_stations_payload: Any,
    edsm_bodies_payload: Any,
    network_enabled: bool = True,
) -> dict[str, Any]:
    """Build a station-centric dry-run report from local and EDSM evidence."""
    edsm_stations = [_normalise_edsm_station(row) for row in _extract_edsm_stations(edsm_stations_payload)]
    edsm_bodies = [_normalise_edsm_body(row) for row in _extract_edsm_bodies(edsm_bodies_payload)]
    links = existing_links or {}
    local_name_counts = Counter(_normalise_name(station.get('name')) for station in local_stations)

    station_reports = []
    matched_edsm_indexes: set[int] = set()
    for station in local_stations:
        station_report, matched_index = _build_station_report(
            station,
            local_stations=local_stations,
            local_name_counts=local_name_counts,
            local_bodies=local_bodies,
            existing_link=links.get(_read_int(station.get('id')) or -1),
            edsm_stations=edsm_stations,
            edsm_bodies=edsm_bodies,
        )
        if matched_index is not None:
            matched_edsm_indexes.add(matched_index)
        station_reports.append(station_report)

    unmatched_edsm_stations = [
        _public_edsm_station(station)
        for index, station in enumerate(edsm_stations)
        if index not in matched_edsm_indexes
    ]
    station_metadata_changes = [
        change for station in station_reports
        if (change := _station_metadata_change_entry(station)) is not None
    ]
    association_changes = [
        change for station in station_reports
        if (change := _association_change_entry(station)) is not None
    ]
    conflicts = [
        _conflict_entry(station, conflict)
        for station in station_reports
        for conflict in station['conflicts']
    ]
    ignored_transient_non_slot = [
        ignored for station in station_reports
        if (ignored := _ignored_transient_entry(station)) is not None
    ]

    summary = Counter()
    for station in station_reports:
        proposed = station['proposed']
        summary[f"association:{proposed['association_status']}"] += 1
        summary[f"lane:{proposed['lane']}"] += 1
        summary[f"station_match:{station['station_match']['status']}"] += 1
        if station['fields_that_would_change']:
            summary['stations_with_changes'] += 1
        if station['conflicts']:
            summary['stations_with_conflicts'] += 1
        if station.get('association_would_change'):
            summary['stations_with_association_changes'] += 1
        if station.get('ignored_transient_non_slot'):
            summary['stations_ignored_transient_non_slot'] += 1

    return {
        'dry_run': True,
        'network_enabled': network_enabled,
        'source': 'edsm_system_api',
        'system': {
            'id64': _read_int(local_system.get('id64')),
            'name': _clean_text(local_system.get('name')),
        },
        'counts': {
            'local_stations': len(local_stations),
            'local_bodies': len(local_bodies),
            'edsm_stations': len(edsm_stations),
            'edsm_bodies': len(edsm_bodies),
            'unmatched_edsm_stations': len(unmatched_edsm_stations),
            'station_metadata_changes': len(station_metadata_changes),
            'association_changes': len(association_changes),
            'conflicts': len(conflicts),
            'ignored_transient_non_slot': len(ignored_transient_non_slot),
            **dict(sorted(summary.items())),
        },
        'matching_rules': {
            'station_identity': [
                'EDSM id/marketId is exact only when it also matches the local station name.',
                'A unique exact station name in the same local system is exact name evidence.',
                'distanceToArrival supports or conflicts with identity; it is not used by itself.',
            ],
            'body_association': [
                'EDSM bodyName/body.name must match exactly one local same-system body to confirm.',
                'EDSM station bodyId is mapped through the EDSM bodies payload name before local use.',
                f'distance-only body association is inferred only when exactly one body is within {BODY_DISTANCE_MATCH_TOLERANCE_LS:g} ls.',
            ],
        },
        'station_metadata_changes': station_metadata_changes,
        'association_changes': association_changes,
        'conflicts': conflicts,
        'ignored_transient_non_slot': ignored_transient_non_slot,
        'stations': station_reports,
        'unmatched_edsm_stations': unmatched_edsm_stations,
    }


def _build_station_report(
    local_station: Mapping[str, Any],
    *,
    local_stations: Sequence[Mapping[str, Any]],
    local_name_counts: Counter,
    local_bodies: Sequence[Mapping[str, Any]],
    existing_link: Mapping[str, Any] | None,
    edsm_stations: Sequence[Mapping[str, Any]],
    edsm_bodies: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], int | None]:
    station_match, matched_index, station_conflicts = _match_edsm_station(
        local_station,
        local_stations=local_stations,
        local_name_counts=local_name_counts,
        edsm_stations=edsm_stations,
    )
    conflicts = list(station_conflicts)
    fields_that_would_change: list[str] = []
    local_public = _public_local_station(local_station)
    existing_public = _public_existing_link(existing_link)

    if matched_index is None:
        proposed = _unresolved_proposal(
            station_type=normalise_station_type_label(local_station.get('station_type')) or 'Unknown',
            note=station_match['reason'],
        )
        return ({
            'local_station': local_public,
            'existing_link': existing_public,
            'station_match': station_match,
            'edsm_station': None,
            'proposed': proposed,
            'fields_that_would_change': fields_that_would_change,
            'association_would_change': False,
            'ignored_transient_non_slot': False,
            'station_type_evidence': {
                'local': local_public['station_type'],
                'edsm': None,
                'proposed': proposed['station_type'],
                'diagnostic_only': False,
            },
            'conflicts': conflicts,
        }, None)

    edsm_station = edsm_stations[matched_index]
    edsm_public = _public_edsm_station(edsm_station)
    local_type = normalise_station_type_label(local_station.get('station_type')) or 'Unknown'
    edsm_type = _clean_text(edsm_station.get('station_type')) or 'Unknown'
    station_type_fields_that_would_change: list[str] = []
    proposed_type = _proposed_station_type(local_type, edsm_type, conflicts, station_type_fields_that_would_change)
    lane, lane_note = classify_station_lane(proposed_type)
    station_type_evidence = {
        'local': local_type,
        'edsm': edsm_type,
        'proposed': proposed_type,
        'diagnostic_only': False,
    }
    is_transient_non_slot = (
        is_transient_non_slot_station_type(local_type)
        or is_transient_non_slot_station_type(edsm_type)
        or is_transient_non_slot_station_type(proposed_type)
    )
    if is_transient_non_slot:
        station_type_evidence['diagnostic_only'] = True
        body_proposal = _unresolved_proposal(
            station_type=proposed_type,
            lane=lane,
            note=_join_notes(
                lane_note,
                'Transient/mobile infrastructure is ignored for colony-planning station_body_links.',
            ),
        )
        return ({
            'local_station': local_public,
            'existing_link': existing_public,
            'station_match': station_match,
            'edsm_station': edsm_public,
            'proposed': body_proposal,
            'fields_that_would_change': [],
            'association_would_change': False,
            'ignored_transient_non_slot': True,
            'station_type_evidence': station_type_evidence,
            'conflicts': conflicts,
        }, matched_index)

    fields_that_would_change.extend(station_type_fields_that_would_change)
    _append_station_data_changes(
        local_station,
        edsm_station,
        proposed_type=proposed_type,
        fields_that_would_change=fields_that_would_change,
        conflicts=conflicts,
    )

    if is_permanent_colony_slot_station_type(proposed_type):
        body_proposal = _propose_body_association(
            edsm_station,
            local_bodies=local_bodies,
            edsm_bodies=edsm_bodies,
            lane=lane,
            lane_note=lane_note,
            station_match=station_match,
            conflicts=conflicts,
        )
    else:
        body_proposal = _unresolved_proposal(
            station_type=proposed_type,
            lane=lane,
            note=_join_notes(
                lane_note,
                'Station type is not a permanent colony-planning slot type; association evidence is diagnostic only.',
            ),
        )

    _preserve_confirmed_link(
        existing_link,
        proposed=body_proposal,
        fields_that_would_change=fields_that_would_change,
        conflicts=conflicts,
    )

    association_would_change = _association_would_change(
        local_station=local_station,
        existing_link=existing_link,
        proposed=body_proposal,
    )

    return ({
        'local_station': local_public,
        'existing_link': existing_public,
        'station_match': station_match,
        'edsm_station': edsm_public,
        'proposed': body_proposal,
        'fields_that_would_change': sorted(set(fields_that_would_change)),
        'association_would_change': association_would_change,
        'ignored_transient_non_slot': False,
        'station_type_evidence': station_type_evidence,
        'conflicts': conflicts,
    }, matched_index)


def _association_would_change(
    *,
    local_station: Mapping[str, Any],
    existing_link: Mapping[str, Any] | None,
    proposed: Mapping[str, Any],
) -> bool:
    proposed_status = _clean_text(proposed.get('association_status'))
    if proposed_status not in ('confirmed', 'inferred'):
        return False
    if not is_permanent_colony_slot_station_type(proposed.get('station_type')):
        return False
    if _read_int(proposed.get('body_id')) is None and _clean_text(proposed.get('body_name')) is None:
        return False
    if existing_link and existing_link.get('association_status') == 'confirmed':
        return False

    current_body_id = _read_int(existing_link.get('body_id')) if existing_link else None
    current_body_name = (
        _clean_text(existing_link.get('body_name'))
        if existing_link else _clean_text(local_station.get('body_name'))
    )
    current_lane = _clean_text(existing_link.get('lane')) if existing_link else None
    current_status = _clean_text(existing_link.get('association_status')) if existing_link else None
    current_confidence = _clean_text(existing_link.get('association_confidence')) if existing_link else None
    current_source = _clean_text(existing_link.get('association_source')) if existing_link else None

    return any((
        current_body_id != _read_int(proposed.get('body_id')),
        _normalise_name(current_body_name) != _normalise_name(proposed.get('body_name')),
        current_lane != _clean_text(proposed.get('lane')),
        current_status != proposed_status,
        current_confidence != _clean_text(proposed.get('association_confidence')),
        current_source != _clean_text(proposed.get('association_source')),
    ))


def _station_metadata_change_entry(station: Mapping[str, Any]) -> dict[str, Any] | None:
    fields = [
        field for field in station.get('fields_that_would_change', [])
        if field != 'station_body_links'
    ]
    if not fields:
        return None
    proposed = station['proposed']
    return {
        'local_station': station['local_station'],
        'edsm_station': station.get('edsm_station'),
        'station_match': station['station_match'],
        'fields_that_would_change': sorted(set(fields)),
        'station_type_evidence': station.get('station_type_evidence'),
        'proposed_station_type': proposed.get('station_type'),
    }


def _association_change_entry(station: Mapping[str, Any]) -> dict[str, Any] | None:
    if not station.get('association_would_change'):
        return None
    proposed = station['proposed']
    return {
        'local_station': station['local_station'],
        'existing_link': station.get('existing_link'),
        'edsm_station': station.get('edsm_station'),
        'station_match': station['station_match'],
        'proposed_link': {
            'body_id': _read_int(proposed.get('body_id')),
            'body_name': _clean_text(proposed.get('body_name')),
            'lane': _clean_text(proposed.get('lane')),
            'association_status': _clean_text(proposed.get('association_status')),
            'association_confidence': _clean_text(proposed.get('association_confidence')),
            'association_source': _clean_text(proposed.get('association_source')),
            'resolver_notes': _clean_text(proposed.get('resolver_notes')),
        },
    }


def _conflict_entry(station: Mapping[str, Any], conflict: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'local_station': station['local_station'],
        'edsm_station': station.get('edsm_station'),
        'station_match': station['station_match'],
        'conflict': dict(conflict),
    }


def _ignored_transient_entry(station: Mapping[str, Any]) -> dict[str, Any] | None:
    if not station.get('ignored_transient_non_slot'):
        return None
    edsm_station = station.get('edsm_station') or {}
    return {
        'local_station': station['local_station'],
        'edsm_station': station.get('edsm_station'),
        'station_match': station['station_match'],
        'station_type_evidence': station.get('station_type_evidence'),
        'body_evidence': {
            'body_id': _read_int(edsm_station.get('body_id')),
            'body_name': _clean_text(edsm_station.get('body_name')),
            'distance_to_arrival': _read_float(edsm_station.get('distance_to_arrival')),
        },
        'reason': _clean_text(station['proposed'].get('resolver_notes')),
        'conflicts': station.get('conflicts', []),
    }


def _match_edsm_station(
    local_station: Mapping[str, Any],
    *,
    local_stations: Sequence[Mapping[str, Any]],
    local_name_counts: Counter,
    edsm_stations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], int | None, list[dict[str, Any]]]:
    local_name = _normalise_name(local_station.get('name'))
    local_ids = _station_identity_values(local_station)
    conflicts: list[dict[str, Any]] = []

    id_matches: list[tuple[int, Mapping[str, Any]]] = []
    id_name_conflicts: list[Mapping[str, Any]] = []
    for index, station in enumerate(edsm_stations):
        if not local_ids.intersection(_station_identity_values(station)):
            continue
        if _normalise_name(station.get('name')) == local_name:
            id_matches.append((index, station))
        else:
            id_name_conflicts.append(station)

    if id_name_conflicts:
        conflicts.append({
            'field': 'station_identity',
            'type': 'id_name_mismatch',
            'message': 'Local station id matched an EDSM id/marketId with a different station name.',
            'edsm_candidates': [_public_edsm_station(station) for station in id_name_conflicts],
        })

    if len(id_matches) == 1:
        index, station = id_matches[0]
        confidence, distance_conflict = _station_distance_match(local_station, station)
        if distance_conflict is not None:
            conflicts.append(distance_conflict)
        return ({
            'status': 'matched',
            'confidence': 'exact',
            'source': 'id_name',
            'distance_support': confidence,
        }, index, conflicts)
    if len(id_matches) > 1:
        return ({
            'status': 'unresolved',
            'confidence': 'unresolved',
            'source': 'id_name',
            'reason': 'Multiple EDSM stations matched local id/name identity.',
        }, None, conflicts)

    name_matches = [
        (index, station)
        for index, station in enumerate(edsm_stations)
        if _normalise_name(station.get('name')) == local_name
    ]
    if len(name_matches) == 1 and local_name_counts[local_name] == 1:
        index, station = name_matches[0]
        distance_support, distance_conflict = _station_distance_match(local_station, station)
        if distance_conflict is not None:
            conflicts.append(distance_conflict)
        return ({
            'status': 'matched',
            'confidence': 'exact',
            'source': 'exact_name',
            'distance_support': distance_support,
        }, index, conflicts)
    if len(name_matches) > 1 or local_name_counts[local_name] > 1:
        return ({
            'status': 'unresolved',
            'confidence': 'unresolved',
            'source': 'exact_name',
            'reason': 'Station name matched multiple local or EDSM candidates.',
        }, None, conflicts)

    return ({
        'status': 'unresolved',
        'confidence': 'unresolved',
        'source': 'none',
        'reason': 'No exact EDSM station id/name or unique station name match.',
    }, None, conflicts)


def _station_distance_match(local_station: Mapping[str, Any], edsm_station: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    local_distance = _read_float(local_station.get('distance_from_star'))
    edsm_distance = _read_float(edsm_station.get('distance_to_arrival'))
    if local_distance is None or edsm_distance is None:
        return 'missing', None
    delta = abs(local_distance - edsm_distance)
    if delta <= STATION_DISTANCE_CONFLICT_TOLERANCE_LS:
        return 'matches', None
    return 'conflict', {
        'field': 'distance_from_star',
        'type': 'station_distance_mismatch',
        'local': local_distance,
        'edsm': edsm_distance,
        'delta_ls': delta,
        'tolerance_ls': STATION_DISTANCE_CONFLICT_TOLERANCE_LS,
    }


def _propose_body_association(
    edsm_station: Mapping[str, Any],
    *,
    local_bodies: Sequence[Mapping[str, Any]],
    edsm_bodies: Sequence[Mapping[str, Any]],
    lane: str,
    lane_note: str | None,
    station_match: Mapping[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    station_type = _clean_text(edsm_station.get('station_type')) or 'Unknown'
    base_notes = [lane_note]

    body_name = _clean_text(edsm_station.get('body_name'))
    if body_name is None:
        body_name = _body_name_from_edsm_station_body_id(edsm_station, edsm_bodies)
        if body_name is not None:
            base_notes.append('EDSM station bodyId was mapped through the EDSM bodies payload name.')

    if body_name is not None:
        name_matches = _local_bodies_by_name(local_bodies, body_name)
        if len(name_matches) == 1 and not _has_blocking_conflict(conflicts):
            body = name_matches[0]
            return _proposal(
                station_type=station_type,
                body=body,
                body_name=_clean_text(body.get('name')) or body_name,
                lane=lane,
                status='confirmed',
                confidence='exact',
                source='edsm_body_name',
                notes=_join_notes(*base_notes, 'Exact EDSM body name matched one local same-system body.'),
            )
        if len(name_matches) == 1:
            return _unresolved_proposal(
                station_type=station_type,
                lane=lane,
                note=_join_notes(*base_notes, 'EDSM body name matched, but station identity evidence has a blocking conflict.'),
            )
        if len(name_matches) > 1:
            conflicts.append({
                'field': 'body_name',
                'type': 'multiple_local_body_name_matches',
                'edsm': body_name,
                'message': 'EDSM body name matched multiple local bodies.',
            })
            return _unresolved_proposal(station_type=station_type, lane=lane, note=_join_notes(*base_notes, 'EDSM body name was ambiguous.'))
        conflicts.append({
            'field': 'body_name',
            'type': 'edsm_body_name_not_found_locally',
            'edsm': body_name,
            'message': 'EDSM body name did not match a local body in this system.',
        })
        return _unresolved_proposal(station_type=station_type, lane=lane, note=_join_notes(*base_notes, 'EDSM body name was not found locally.'))

    station_distance = _read_float(edsm_station.get('distance_to_arrival'))
    if station_distance is None:
        return _unresolved_proposal(
            station_type=station_type,
            lane=lane,
            note=_join_notes(*base_notes, 'EDSM station has no body name/body id or distanceToArrival evidence.'),
        )

    distance_matches = _unique_body_distance_candidates(station_distance, local_bodies=local_bodies, edsm_bodies=edsm_bodies)
    if len(distance_matches) == 1 and not _has_blocking_conflict(conflicts):
        body = distance_matches[0]
        return _proposal(
            station_type=station_type,
            body=body,
            body_name=_clean_text(body.get('name')),
            lane=lane,
            status='inferred',
            confidence='strong_inference',
            source='edsm_distance',
            notes=_join_notes(
                *base_notes,
                f'Unique EDSM/local body distance match within {BODY_DISTANCE_MATCH_TOLERANCE_LS:g} ls.',
            ),
        )
    if len(distance_matches) == 1:
        return _unresolved_proposal(
            station_type=station_type,
            lane=lane,
            note=_join_notes(*base_notes, 'EDSM distance matched one body, but station identity evidence has a blocking conflict.'),
        )
    if len(distance_matches) > 1:
        conflicts.append({
            'field': 'distance_to_arrival',
            'type': 'multiple_body_distance_matches',
            'edsm': station_distance,
            'candidate_body_ids': [_read_int(body.get('id')) for body in distance_matches],
            'tolerance_ls': BODY_DISTANCE_MATCH_TOLERANCE_LS,
        })
        return _unresolved_proposal(station_type=station_type, lane=lane, note=_join_notes(*base_notes, 'EDSM distance matched multiple bodies.'))

    return _unresolved_proposal(
        station_type=station_type,
        lane=lane,
        note=_join_notes(*base_notes, 'No exact body name/body id or unique distance match is available.'),
    )


def _proposed_station_type(
    local_type: str,
    edsm_type: str,
    conflicts: list[dict[str, Any]],
    fields_that_would_change: list[str],
) -> str:
    if edsm_type == 'Unknown':
        return local_type if local_type else 'Unknown'
    if local_type in (None, '', 'Unknown'):
        fields_that_would_change.append('station_type')
        return edsm_type
    if local_type != edsm_type:
        fields_that_would_change.append('station_type')
        conflicts.append({
            'field': 'station_type',
            'type': 'known_station_type_mismatch',
            'local': local_type,
            'edsm': edsm_type,
            'message': 'EDSM would change a known local station type.',
        })
    return edsm_type


def _append_station_data_changes(
    local_station: Mapping[str, Any],
    edsm_station: Mapping[str, Any],
    *,
    proposed_type: str,
    fields_that_would_change: list[str],
    conflicts: list[dict[str, Any]],
) -> None:
    local_type = normalise_station_type_label(local_station.get('station_type')) or 'Unknown'
    if local_type != proposed_type and 'station_type' not in fields_that_would_change:
        fields_that_would_change.append('station_type')

    local_distance = _read_float(local_station.get('distance_from_star'))
    edsm_distance = _read_float(edsm_station.get('distance_to_arrival'))
    if local_distance is None and edsm_distance is not None:
        fields_that_would_change.append('distance_from_star')

    _compare_economy(local_station, edsm_station, fields_that_would_change, conflicts)
    _compare_service_bool(local_station, edsm_station, 'has_market', 'have_market', fields_that_would_change, conflicts)
    _compare_service_bool(local_station, edsm_station, 'has_shipyard', 'have_shipyard', fields_that_would_change, conflicts)


def _preserve_confirmed_link(
    existing_link: Mapping[str, Any] | None,
    *,
    proposed: Mapping[str, Any],
    fields_that_would_change: list[str],
    conflicts: list[dict[str, Any]],
) -> None:
    if not existing_link or existing_link.get('association_status') != 'confirmed':
        return
    proposed_body_id = _read_int(proposed.get('body_id'))
    proposed_body_name = _clean_text(proposed.get('body_name'))
    existing_body_id = _read_int(existing_link.get('body_id'))
    existing_body_name = _clean_text(existing_link.get('body_name'))
    proposed_status = _clean_text(proposed.get('association_status'))
    proposed_lane = _clean_text(proposed.get('lane')) or 'unknown'
    existing_lane = _clean_text(existing_link.get('lane')) or 'unknown'
    same_body = (
        (proposed_body_id is not None and proposed_body_id == existing_body_id)
        or (
            proposed_body_name is not None
            and _normalise_name(proposed_body_name) == _normalise_name(existing_body_name)
        )
    )
    if proposed_status != 'confirmed' or not same_body or proposed_lane != existing_lane:
        conflicts.append({
            'field': 'station_body_links',
            'type': 'confirmed_link_preserved',
            'message': 'Existing confirmed station_body_links row is stronger than this EDSM proposal.',
            'existing': _public_existing_link(existing_link),
            'edsm_proposal': {
                'body_id': proposed_body_id,
                'body_name': proposed_body_name,
                'association_status': proposed_status,
                'association_confidence': proposed.get('association_confidence'),
                'association_source': proposed.get('association_source'),
                'lane': proposed_lane,
            },
        })
    while 'station_body_links' in fields_that_would_change:
        fields_that_would_change.remove('station_body_links')


def _compare_economy(
    local_station: Mapping[str, Any],
    edsm_station: Mapping[str, Any],
    fields_that_would_change: list[str],
    conflicts: list[dict[str, Any]],
) -> None:
    local = _normalise_economy(local_station.get('primary_economy'))
    edsm = _normalise_economy(edsm_station.get('economy'))
    if edsm == 'Unknown':
        return
    if local in ('Unknown', 'None'):
        fields_that_would_change.append('primary_economy')
    elif local != edsm:
        conflicts.append({
            'field': 'primary_economy',
            'type': 'station_economy_mismatch',
            'local': local,
            'edsm': edsm,
        })


def _compare_service_bool(
    local_station: Mapping[str, Any],
    edsm_station: Mapping[str, Any],
    local_key: str,
    edsm_key: str,
    fields_that_would_change: list[str],
    conflicts: list[dict[str, Any]],
) -> None:
    edsm_value = edsm_station.get(edsm_key)
    if edsm_value is None:
        return
    local_value = local_station.get(local_key)
    if local_value is None:
        fields_that_would_change.append(local_key)
    elif bool(edsm_value) and not bool(local_value):
        fields_that_would_change.append(local_key)
    elif bool(local_value) != bool(edsm_value):
        conflicts.append({
            'field': local_key,
            'type': 'station_service_mismatch',
            'local': bool(local_value),
            'edsm': bool(edsm_value),
        })


def _has_blocking_conflict(conflicts: Sequence[Mapping[str, Any]]) -> bool:
    return any(conflict.get('type') == 'station_distance_mismatch' for conflict in conflicts)


def _proposal(
    *,
    station_type: str,
    body: Mapping[str, Any],
    body_name: str | None,
    lane: str,
    status: str,
    confidence: str,
    source: str,
    notes: str | None,
) -> dict[str, Any]:
    return {
        'station_type': station_type,
        'body_id': _read_int(body.get('id')) or _read_int(body.get('body_id')),
        'body_name': body_name,
        'lane': lane,
        'occupies_colony_slot': lane in ('orbital', 'surface'),
        'association_status': status,
        'association_confidence': confidence,
        'association_source': source,
        'resolver_notes': notes,
    }


def _unresolved_proposal(*, station_type: str, note: str | None, lane: str | None = None) -> dict[str, Any]:
    resolved_lane, lane_note = classify_station_lane(station_type)
    if lane is not None:
        resolved_lane = lane
    return {
        'station_type': station_type,
        'body_id': None,
        'body_name': None,
        'lane': resolved_lane,
        'occupies_colony_slot': False,
        'association_status': 'unresolved',
        'association_confidence': 'unresolved',
        'association_source': 'edsm_station_probe',
        'resolver_notes': _join_notes(note, lane_note),
    }


def _normalise_edsm_station(station: Mapping[str, Any]) -> dict[str, Any]:
    raw_type = _first_text(station.get('type'), station.get('stationType'), station.get('station_type'))
    station_type = normalise_station_type_label(raw_type) or 'Unknown'
    return {
        'id': _read_int(station.get('id')),
        'market_id': _read_int(_first_present(station.get('marketId'), station.get('market_id'))),
        'name': _clean_text(station.get('name')),
        'type_raw': raw_type,
        'station_type': station_type,
        'distance_to_arrival': _first_float(
            station.get('distanceToArrival'),
            station.get('distanceFromArrival'),
            station.get('distanceFromArrivalLS'),
            station.get('distance_from_star'),
        ),
        'body_id': _read_int(_first_present(station.get('bodyId'), station.get('body_id'), station.get('bodyID'))),
        'body_name': _body_name_from_record(station),
        'economy': _station_economy_from_record(station),
        'have_market': _first_bool(station.get('haveMarket'), station.get('hasMarket'), station.get('has_market')),
        'have_shipyard': _first_bool(station.get('haveShipyard'), station.get('hasShipyard'), station.get('has_shipyard')),
        'raw': dict(station),
    }


def _normalise_edsm_body(body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'id': _read_int(body.get('id')),
        'body_id': _read_int(_first_present(body.get('bodyId'), body.get('body_id'), body.get('bodyID'))),
        'name': _first_text(body.get('name'), body.get('bodyName'), body.get('body_name')),
        'body_type': _first_text(body.get('type'), body.get('bodyType'), body.get('body_type')),
        'subtype': _first_text(body.get('subType'), body.get('subtype'), body.get('sub_type')),
        'distance_to_arrival': _first_float(
            body.get('distanceToArrival'),
            body.get('distanceFromArrival'),
            body.get('distanceFromArrivalLS'),
            body.get('distance_from_star'),
        ),
        'raw': dict(body),
    }


def _body_name_from_record(station: Mapping[str, Any]) -> str | None:
    return _first_text(
        station.get('bodyName'),
        station.get('body_name'),
        station.get('stationBodyName'),
        station.get('station_body_name'),
        station.get('body'),
    )


def _body_name_from_edsm_station_body_id(edsm_station: Mapping[str, Any], edsm_bodies: Sequence[Mapping[str, Any]]) -> str | None:
    station_body_id = _read_int(edsm_station.get('body_id'))
    if station_body_id is None:
        return None
    for body in edsm_bodies:
        body_ids = {_read_int(body.get('id')), _read_int(body.get('body_id'))}
        if station_body_id in body_ids:
            return _clean_text(body.get('name'))
    return None


def _unique_body_distance_candidates(
    station_distance: float,
    *,
    local_bodies: Sequence[Mapping[str, Any]],
    edsm_bodies: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    candidates: dict[int, Mapping[str, Any]] = {}
    for body in local_bodies:
        body_distance = _read_float(body.get('distance_from_star'))
        if body_distance is not None and abs(body_distance - station_distance) <= BODY_DISTANCE_MATCH_TOLERANCE_LS:
            body_id = _read_int(body.get('id'))
            if body_id is not None:
                candidates[body_id] = body

    for edsm_body in edsm_bodies:
        body_distance = _read_float(edsm_body.get('distance_to_arrival'))
        if body_distance is None or abs(body_distance - station_distance) > BODY_DISTANCE_MATCH_TOLERANCE_LS:
            continue
        local_matches = _local_bodies_by_name(local_bodies, _clean_text(edsm_body.get('name')))
        if len(local_matches) == 1:
            body_id = _read_int(local_matches[0].get('id'))
            if body_id is not None:
                candidates[body_id] = local_matches[0]
    return list(candidates.values())


def _local_bodies_by_name(local_bodies: Sequence[Mapping[str, Any]], body_name: str | None) -> list[Mapping[str, Any]]:
    normalised = _normalise_name(body_name)
    if not normalised:
        return []
    return [body for body in local_bodies if _normalise_name(body.get('name')) == normalised]


def _station_identity_values(station: Mapping[str, Any]) -> set[int]:
    return {
        value
        for value in (
            _read_int(station.get('id')),
            _read_int(station.get('market_id')),
            _read_int(station.get('marketId')),
        )
        if value is not None
    }


def _extract_edsm_stations(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ('stations', 'Stations'):
            stations = payload.get(key)
            if isinstance(stations, list):
                return [item for item in stations if isinstance(item, Mapping)]
    return []


def _extract_edsm_bodies(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ('bodies', 'Bodies'):
            bodies = payload.get(key)
            if isinstance(bodies, list):
                return [item for item in bodies if isinstance(item, Mapping)]
    return []


def _public_local_station(station: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'id': _read_int(station.get('id')),
        'market_id': _read_int(station.get('market_id')),
        'name': _clean_text(station.get('name')),
        'station_type': normalise_station_type_label(station.get('station_type')) or 'Unknown',
        'distance_from_star': _read_float(station.get('distance_from_star')),
        'body_name': _clean_text(station.get('body_name')),
        'primary_economy': _clean_text(station.get('primary_economy')),
        'has_market': station.get('has_market'),
        'has_shipyard': station.get('has_shipyard'),
    }


def _public_edsm_station(station: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'id': _read_int(station.get('id')),
        'market_id': _read_int(station.get('market_id')),
        'name': _clean_text(station.get('name')),
        'type_raw': _clean_text(station.get('type_raw')),
        'station_type': _clean_text(station.get('station_type')) or 'Unknown',
        'distance_to_arrival': _read_float(station.get('distance_to_arrival')),
        'body_id': _read_int(station.get('body_id')),
        'body_name': _clean_text(station.get('body_name')),
        'economy': _clean_text(station.get('economy')),
        'have_market': station.get('have_market'),
        'have_shipyard': station.get('have_shipyard'),
    }


def _public_existing_link(existing_link: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not existing_link:
        return None
    return {
        'station_id': _read_int(existing_link.get('station_id')),
        'market_id': _read_int(existing_link.get('market_id')),
        'body_id': _read_int(existing_link.get('body_id')),
        'body_name': _clean_text(existing_link.get('body_name')),
        'lane': _clean_text(existing_link.get('lane')),
        'association_status': _clean_text(existing_link.get('association_status')),
        'association_confidence': _clean_text(existing_link.get('association_confidence')),
        'association_source': _clean_text(existing_link.get('association_source')),
        'resolver_notes': _clean_text(existing_link.get('resolver_notes')),
    }


def _station_economy_from_record(station: Mapping[str, Any]) -> str | None:
    economy = _first_present(
        station.get('economy'),
        station.get('primaryEconomy'),
        station.get('primary_economy'),
    )
    if isinstance(economy, Mapping):
        return _first_text(economy.get('name'), economy.get('economy'), economy.get('value'))
    return _clean_text(economy)


def _normalise_economy(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return 'Unknown'
    token = text.replace(' ', '').replace('$economy_', '').replace(';', '').lower()
    mapping = {
        'hightech': 'HighTech',
        'high_tech': 'HighTech',
        'agriculture': 'Agriculture',
        'agri': 'Agriculture',
        'refinery': 'Refinery',
        'industrial': 'Industrial',
        'military': 'Military',
        'tourism': 'Tourism',
        'extraction': 'Extraction',
        'colony': 'Colony',
        'terraforming': 'Terraforming',
        'prison': 'Prison',
        'damaged': 'Damaged',
        'rescue': 'Rescue',
        'repair': 'Repair',
        'carrier': 'Carrier',
        'none': 'None',
        'unknown': 'Unknown',
    }
    normalised = mapping.get(token, text)
    return normalised if normalised in VALID_ECONOMIES else 'Unknown'


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            value = _first_text(value.get('name'), value.get('bodyName'), value.get('body_name'))
        text = _clean_text(value)
        if text:
            return text
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _read_float(value)
        if parsed is not None:
            return parsed
    return None


def _first_bool(*values: Any) -> bool | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            token = value.strip().lower()
            if token in ('true', 'yes', '1'):
                return True
            if token in ('false', 'no', '0'):
                return False
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


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalise_name(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.strip().lower().split())


def _join_notes(*notes: str | None) -> str | None:
    clean = [note.strip() for note in notes if isinstance(note, str) and note.strip()]
    return ' '.join(clean) if clean else None


def _json_default(value: Any) -> str:
    return str(value)


def render_text_report(report: Mapping[str, Any]) -> str:
    lines = [
        f"EDSM station enrichment dry-run: {report['system']['name']} ({report['system']['id64']})",
        f"network={'enabled' if report.get('network_enabled') else 'skipped'} source={report['source']}",
        'counts:',
    ]
    for key, value in sorted(report['counts'].items()):
        lines.append(f'  {key}: {value}')
    lines.append('station_metadata_changes:')
    if not report.get('station_metadata_changes'):
        lines.append('  none')
    for change in report.get('station_metadata_changes', []):
        local = change['local_station']
        fields = ', '.join(change['fields_that_would_change'])
        evidence = change.get('station_type_evidence') or {}
        lines.append(
            f"  - {local['name']} [{local['id']}]: fields={fields} "
            f"type={evidence.get('local')}->{evidence.get('proposed')}"
        )
    lines.append('association_changes:')
    if not report.get('association_changes'):
        lines.append('  none')
    for change in report.get('association_changes', []):
        local = change['local_station']
        proposed = change['proposed_link']
        lines.append(
            f"  - {local['name']} [{local['id']}]: body={proposed['body_name'] or 'unresolved'} "
            f"lane={proposed['lane']} assoc={proposed['association_status']}/{proposed['association_confidence']}"
        )
    lines.append('conflicts:')
    if not report.get('conflicts'):
        lines.append('  none')
    for entry in report.get('conflicts', []):
        local = entry['local_station']
        conflict = entry['conflict']
        lines.append(f"  - {local['name']} [{local['id']}]: {conflict.get('type')} field={conflict.get('field')}")
    lines.append('ignored_transient_non_slot:')
    if not report.get('ignored_transient_non_slot'):
        lines.append('  none')
    for entry in report.get('ignored_transient_non_slot', []):
        local = entry['local_station']
        evidence = entry.get('station_type_evidence') or {}
        body = entry.get('body_evidence') or {}
        lines.append(
            f"  - {local['name']} [{local['id']}]: type={evidence.get('local')}->{evidence.get('proposed')} "
            f"body_evidence={body.get('body_name') or body.get('body_id') or 'none'}"
        )
    return '\n'.join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply:
        print('--apply is not implemented for EDSM station enrichment; this tool is dry-run only.', file=sys.stderr)
        return 2
    if not args.dsn:
        print('DATABASE_URL or --dsn is required.', file=sys.stderr)
        return 2

    try:
        with psycopg2.connect(args.dsn) as conn:
            local = fetch_local_payload(conn, system_name=args.system_name, system_id64=args.system_id64)
            conn.rollback()
    except Exception as exc:
        print(f'Failed to load local system evidence: {exc}', file=sys.stderr)
        return 1

    system_name = args.system_name or _clean_text(local['system'].get('name'))
    if not system_name:
        print('System name is required for EDSM lookup.', file=sys.stderr)
        return 2

    network_enabled = not (args.no_network or args.local_only)
    if network_enabled:
        try:
            edsm_payload = fetch_edsm_system(system_name, timeout=args.timeout)
        except Exception as exc:
            print(f'Failed to fetch EDSM evidence: {exc}', file=sys.stderr)
            return 1
    else:
        edsm_payload = {'stations': {'stations': []}, 'bodies': {'bodies': []}}

    report = build_enrichment_report(
        local_system=local['system'],
        local_stations=local['stations'],
        local_bodies=local['bodies'],
        existing_links=local['existing_links'],
        edsm_stations_payload=edsm_payload['stations'],
        edsm_bodies_payload=edsm_payload['bodies'],
        network_enabled=network_enabled,
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=_json_default))
    else:
        print(render_text_report(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
