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
            'body_name': first.get('body_name'),
            'source': first.get('source'),
            'source_class': first.get('source_class'),
            'confidence': first.get('confidence'),
            'freshness_class': first.get('freshness_class'),
            'source_updated_at': first.get('source_updated_at'),
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
            'source': first.get('source'),
            'source_class': first.get('source_class'),
            'confidence': first.get('confidence'),
            'freshness_class': first.get('freshness_class'),
            'source_updated_at': first.get('source_updated_at'),
            **body_ring_array_source_fields(first),
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
            'association_status': first.get('association_status'),
            'source': first.get('source'),
            'source_class': first.get('source_class'),
            'confidence': first.get('confidence'),
            'freshness_class': first.get('freshness_class'),
            'source_updated_at': first.get('source_updated_at'),
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
            'body_name': row.get('canonical_body_name'),
            'station_body_link': station_body_link(row),
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
            'ring_scan_fact': body_ring_scan_fact(row),
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


def station_body_link(row: Mapping[str, Any]) -> dict[str, Any]:
    if (
        _missing(row.get('canonical_station_body_link_body_id'))
        and _missing(row.get('canonical_station_body_link_body_name'))
        and _missing(row.get('canonical_station_body_link_status'))
    ):
        return {}
    return {
        'body_id': row.get('canonical_station_body_link_body_id'),
        'body_name': row.get('canonical_station_body_link_body_name'),
        'lane': row.get('canonical_station_body_link_lane'),
        'association_status': row.get('canonical_station_body_link_status'),
        'association_confidence': row.get('canonical_station_body_link_confidence'),
        'association_source': row.get('canonical_station_body_link_source'),
    }


def body_ring_scan_fact(row: Mapping[str, Any]) -> dict[str, Any]:
    if (
        row.get('canonical_is_ringed') is None
        and row.get('canonical_ring_scan_confidence') is None
        and row.get('canonical_ring_scan_sources') is None
    ):
        return {}
    data_sources = row.get('canonical_ring_scan_sources')
    if isinstance(data_sources, str):
        sources = [data_sources]
    elif isinstance(data_sources, Sequence) and not isinstance(data_sources, (bytes, bytearray)):
        sources = list(data_sources)
    else:
        sources = []
    return {
        'is_ringed': row.get('canonical_is_ringed'),
        'confidence': row.get('canonical_ring_scan_confidence'),
        'data_sources': sources,
        'meaning': 'trusted_scan_fact_false' if row.get('canonical_is_ringed') is False else 'scan_fact_evidence',
    }


def body_ring_array_source_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    provenance = row.get('provenance')
    if not isinstance(provenance, Mapping):
        return {}
    return {
        'ring_array_state': provenance.get('ring_array_state'),
        'ring_array_meaning': provenance.get('ring_array_meaning'),
        'missing_ring_arrays_state': provenance.get('missing_ring_arrays_state'),
    }


def station_body_association_candidates(
    station_candidates: Sequence[Mapping[str, Any]],
    body_candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build report-only station/body association review candidates.

    This uses staged evidence already present in the reconciliation report. It
    does not create station_body_links or promote source body names to truth.
    """
    body_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for body_candidate in body_candidates:
        source = _source(body_candidate)
        key = _association_key(source)
        if key is not None:
            body_index.setdefault(key, []).append(dict(body_candidate))

    candidates = []
    for station_candidate in station_candidates:
        source = _source(station_candidate)
        base = {
            'entity': 'station_body_association',
            'source': {
                'source_record_hash': source.get('source_record_hash'),
                'system_id64': source.get('system_id64'),
                'system_name': source.get('system_name'),
                'station_name': source.get('station_name'),
                'body_name': source.get('body_name'),
            },
            'report_only': True,
            'canonical_link_writes_planned': 0,
        }
        if _missing(source.get('body_name')):
            candidates.append({
                **base,
                'candidate_action': 'station_body_name_missing',
                'confidence': 'low',
                'risk_flags': ['missing_station_body_name'],
                'confidence_explanations': [
                    'Station evidence has no body_name; association remains unknown.',
                    'Output is report-only; it is not a station-body link write plan.',
                ],
                'matched_body_evidence': [],
            })
            continue

        key = _association_key(source)
        body_matches = body_index.get(key, []) if key is not None else []
        if len(body_matches) == 1:
            body_source = _source(body_matches[0])
            candidates.append({
                **base,
                'candidate_action': 'station_body_supported_by_staged_body',
                'confidence': 'medium',
                'risk_flags': ['source_only_association'],
                'confidence_explanations': [
                    'Station body_name matches one staged body evidence row in the same system.',
                    'The association remains report-only until a separate trusted write design exists.',
                ],
                'matched_body_evidence': [{
                    'source_record_hash': body_source.get('source_record_hash'),
                    'source_body_id': body_source.get('source_body_id'),
                    'body_name': body_source.get('body_name'),
                    'candidate_action': body_matches[0].get('candidate_action'),
                    'confidence': body_matches[0].get('confidence'),
                }],
            })
        elif len(body_matches) > 1:
            candidates.append({
                **base,
                'candidate_action': 'station_body_ambiguous_staged_body',
                'confidence': 'low',
                'risk_flags': ['ambiguous_staged_body_evidence'],
                'confidence_explanations': [
                    'More than one staged body evidence row matched the station body_name.',
                    'Manual review is required before any future association design.',
                ],
                'matched_body_evidence': [
                    {
                        'source_record_hash': _source(match).get('source_record_hash'),
                        'source_body_id': _source(match).get('source_body_id'),
                        'body_name': _source(match).get('body_name'),
                        'candidate_action': match.get('candidate_action'),
                        'confidence': match.get('confidence'),
                    }
                    for match in body_matches
                ],
            })
        else:
            candidates.append({
                **base,
                'candidate_action': 'station_body_unresolved_staged_body',
                'confidence': 'low',
                'risk_flags': ['missing_staged_body_evidence'],
                'confidence_explanations': [
                    'No staged body evidence matched the station body_name in the same system.',
                    'The association stays unresolved and report-only.',
                ],
                'matched_body_evidence': [],
            })
    return sort_candidate_rows(candidates)


def source_coverage_summary(
    station_candidates: Sequence[Mapping[str, Any]],
    body_candidates: Sequence[Mapping[str, Any]],
    ring_candidates: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarise source coverage without coercing unknown evidence to false."""
    return {
        'schema_version': 'enrichment_source_coverage_summary/v1',
        'report_only': True,
        'canonical_writes_planned': 0,
        'entities': {
            'station': _entity_coverage(station_candidates),
            'body': _entity_coverage(body_candidates),
            'ring': _entity_coverage(ring_candidates),
        },
        'ring_evidence': {
            'staged_ring_candidates': len(ring_candidates),
            'trusted_local_matched_ring_candidates': sum(
                1 for candidate in ring_candidates
                if (candidate.get('canonical') or {}).get('association_status') == 'local_matched'
            ),
            'missing_ring_arrays_state': 'unknown_not_false' if not ring_candidates else 'ring_evidence_present',
            'ringed_truth_requires_trusted_body_rings': True,
        },
        'warnings': len(warnings),
    }


def confidence_risk_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        'schema_version': 'enrichment_confidence_risk_summary/v1',
        'report_only': True,
        'canonical_writes_planned': 0,
        'confidence_distribution': _distribution(candidates, 'confidence'),
        'evidence_quality_distribution': _distribution(candidates, 'evidence_quality'),
        'identifier_quality_distribution': _distribution(candidates, 'identifier_quality'),
        'risk_flag_distribution': _risk_distribution(candidates),
    }


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


def _source(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    source = candidate.get('source')
    return source if isinstance(source, Mapping) else {}


def _association_key(source: Mapping[str, Any]) -> tuple[str, str] | None:
    body_name = _normalise_key(source.get('body_name'))
    if body_name is None:
        return None
    system_key = _system_key(source)
    if system_key is None:
        return None
    return system_key, body_name


def _system_key(source: Mapping[str, Any]) -> str | None:
    if not _missing(source.get('system_id64')):
        return f"id64:{source.get('system_id64')}"
    system_name = _normalise_key(source.get('system_name'))
    if system_name is not None:
        return f'name:{system_name}'
    return None


def _normalise_key(value: Any) -> str | None:
    if _missing(value):
        return None
    return str(value).strip().lower()


def _entity_coverage(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        'candidates': len(candidates),
        'candidate_actions': _distribution(candidates, 'candidate_action'),
        'confidence': _distribution(candidates, 'confidence'),
        'source_runs': sorted({
            str(_source(candidate).get('source_run_key'))
            for candidate in candidates
            if not _missing(_source(candidate).get('source_run_key'))
        }),
        'source_files': sorted({
            str(_source(candidate).get('source_file_key'))
            for candidate in candidates
            if not _missing(_source(candidate).get('source_file_key'))
        }),
        'missing_system_identifiers': sum(1 for candidate in candidates if _system_key(_source(candidate)) is None),
        'volatile_warnings': sum(
            1 for candidate in candidates
            for warning in candidate.get('warnings', [])
            if isinstance(warning, Mapping)
            and warning.get('reason') == 'volatile_source_evidence_not_canonical_update'
        ),
    }


def _distribution(candidates: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        value = candidate.get(field_name)
        if value is None:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _risk_distribution(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        flags = candidate.get('risk_flags', [])
        if not isinstance(flags, Sequence) or isinstance(flags, (str, bytes, bytearray)):
            continue
        for flag in flags:
            key = str(flag)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
