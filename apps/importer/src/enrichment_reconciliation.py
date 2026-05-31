"""Report-only reconciliation candidate shaping for enrichment staging rows."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from enrichment_reconciliation_scoring import candidate_confidence
from enrichment_staging import canonicalise_json_payload


def station_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_station_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_station_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'market_id': first.get('market_id'),
            'edsm_station_id': first.get('edsm_station_id'),
            'station_name': first.get('station_name'),
        }
        warnings = volatile_warnings(
            first,
            staged_field='distance_to_arrival',
            canonical_field='canonical_distance_to_arrival',
            entity='station',
        )
        candidates.append(base_candidate(
            entity='station',
            source_identity=source_identity,
            canonical_matches=station_canonical_matches(group),
            insufficient=not has_system_identity(first) or _missing(first.get('station_name')),
            differences=diff_fields(
                first,
                (
                    ('station_type', 'canonical_station_type'),
                    ('body_name', 'canonical_body_name'),
                    ('controlling_faction', 'canonical_controlling_faction'),
                    ('allegiance', 'canonical_allegiance'),
                    ('government', 'canonical_government'),
                ),
            ),
            warnings=warnings,
        ))
    return candidates


def body_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_body_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_body_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'source_body_id': first.get('source_body_id'),
            'body_name': first.get('body_name'),
        }
        warnings = volatile_warnings(
            first,
            staged_field='distance_to_arrival',
            canonical_field='canonical_distance_to_arrival',
            entity='body',
        )
        candidates.append(base_candidate(
            entity='body',
            source_identity=source_identity,
            canonical_matches=body_canonical_matches(group),
            insufficient=not has_system_identity(first)
            or (_missing(first.get('source_body_id')) and _missing(first.get('body_name'))),
            differences=diff_fields(
                first,
                (
                    ('body_name', 'canonical_body_name'),
                    ('body_type', 'canonical_body_type'),
                    ('subtype', 'canonical_subtype'),
                    ('is_main_star', 'canonical_is_main_star'),
                    ('is_landable', 'canonical_is_landable'),
                    ('is_terraformable', 'canonical_is_terraformable'),
                    ('estimated_scan_value', 'canonical_estimated_scan_value'),
                    ('estimated_mapping_value', 'canonical_estimated_mapping_value'),
                ),
            ),
            warnings=warnings,
        ))
    return candidates


def ring_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_ring_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_ring_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'source_body_id': first.get('source_body_id'),
            'body_name': first.get('body_name'),
            'ring_name': first.get('ring_name'),
        }
        candidates.append(base_candidate(
            entity='ring',
            source_identity=source_identity,
            canonical_matches=ring_canonical_matches(group),
            insufficient=not has_system_identity(first)
            or _missing(first.get('ring_name'))
            or (_missing(first.get('source_body_id')) and _missing(first.get('body_name'))),
            differences=diff_fields(
                first,
                (
                    ('ring_name', 'canonical_ring_name'),
                    ('ring_type', 'canonical_ring_type'),
                    ('ring_class', 'canonical_ring_class'),
                    ('mass_mt', 'canonical_mass_mt'),
                    ('inner_radius', 'canonical_inner_radius'),
                    ('outer_radius', 'canonical_outer_radius'),
                ),
            ),
            warnings=[],
        ))
    return candidates


def base_candidate(
    *,
    entity: str,
    source_identity: Mapping[str, Any],
    canonical_matches: Sequence[Mapping[str, Any]],
    insufficient: bool,
    differences: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    canonical = list(canonical_matches)
    if insufficient:
        action = 'insufficient_evidence'
    elif len(canonical) > 1:
        action = 'ambiguous_match'
    elif not canonical:
        action = 'candidate_insert_missing_canonical'
    elif differences:
        action = 'candidate_update'
    else:
        action = 'no_change'
    scored = candidate_confidence(
        entity=entity,
        action=action,
        source_identity=source_identity,
        canonical_matches=canonical,
        differences=differences if len(canonical) == 1 else [],
        warnings=warnings,
    )
    return {
        'entity': entity,
        'candidate_action': action,
        'source': dict(source_identity),
        'canonical': canonical[0] if len(canonical) == 1 else None,
        'canonical_matches': canonical,
        'differences': list(differences) if len(canonical) == 1 else [],
        'warnings': list(warnings),
        **scored,
    }


def station_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_station_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'station_id': row.get('canonical_station_id'),
            'station_name': row.get('canonical_station_name'),
            'station_type': row.get('canonical_station_type'),
        }
        for row in rows
        if row.get('canonical_station_id') is not None
    }
    return sort_candidate_rows(matches.values())


def body_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_body_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'body_id': row.get('canonical_body_id'),
            'body_name': row.get('canonical_body_name'),
            'body_type': row.get('canonical_body_type'),
        }
        for row in rows
        if row.get('canonical_body_id') is not None
    }
    return sort_candidate_rows(matches.values())


def ring_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_ring_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'body_id': row.get('canonical_body_id'),
            'body_name': row.get('canonical_body_name'),
            'ring_id': row.get('canonical_ring_id'),
            'ring_name': row.get('canonical_ring_name'),
            'ring_type': row.get('canonical_ring_type'),
            'association_status': row.get('canonical_association_status'),
        }
        for row in rows
        if row.get('canonical_ring_id') is not None
    }
    return sort_candidate_rows(matches.values())


def diff_fields(row: Mapping[str, Any], field_pairs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for staged_field, canonical_field in field_pairs:
        staged_value = _normalise_compare_value(row.get(staged_field))
        canonical_value = _normalise_compare_value(row.get(canonical_field))
        if staged_value is None:
            continue
        if staged_value != canonical_value:
            differences.append({
                'field': staged_field,
                'staged': row.get(staged_field),
                'canonical': row.get(canonical_field),
            })
    return sorted(differences, key=canonicalise_json_payload)


def volatile_warnings(row: Mapping[str, Any], *, staged_field: str, canonical_field: str, entity: str) -> list[dict[str, Any]]:
    if row.get(staged_field) is None:
        return []
    if _normalise_compare_value(row.get(staged_field)) == _normalise_compare_value(row.get(canonical_field)):
        return []
    return [{
        'entity': entity,
        'field': staged_field,
        'reason': 'volatile_source_evidence_not_canonical_update',
        'source_record_hash': row.get('source_record_hash'),
    }]


def has_system_identity(row: Mapping[str, Any]) -> bool:
    return not _missing(row.get('system_id64')) or not _missing(row.get('system_name'))


def sort_candidate_rows(rows: Sequence[Mapping[str, Any]] | Any) -> list[dict[str, Any]]:
    return sorted((dict(row) for row in rows), key=canonicalise_json_payload)


def _group_rows(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = dict(row)
        grouped.setdefault(str(row_dict.get(key)), []).append(row_dict)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _normalise_compare_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value
