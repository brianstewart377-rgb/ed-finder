"""Report-only confidence and risk scoring for enrichment reconciliation."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def candidate_confidence(
    *,
    entity: str,
    action: str,
    source_identity: Mapping[str, Any],
    canonical_matches: Sequence[Mapping[str, Any]],
    differences: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build transparent confidence metadata for a report-only candidate."""
    identifier_quality = identifier_quality_for_candidate(entity, source_identity, action)
    risk_flags = candidate_risk_flags(action, warnings)
    evidence_quality = evidence_quality_for_candidate(action, identifier_quality, canonical_matches, differences)

    if action in {'insufficient_evidence', 'ambiguous_match'}:
        confidence = 'low'
    elif action == 'no_change':
        confidence = 'high' if identifier_quality == 'stable' and not risk_flags else 'medium'
    elif action == 'candidate_update':
        confidence = 'medium' if identifier_quality in {'stable', 'partial'} else 'low'
    elif action == 'candidate_insert_missing_canonical':
        confidence = 'medium' if identifier_quality == 'stable' else 'low'
    else:
        confidence = 'low'

    return {
        'confidence': confidence,
        'confidence_reasons': confidence_reasons(
            action=action,
            identifier_quality=identifier_quality,
            evidence_quality=evidence_quality,
            risk_flags=risk_flags,
            differences=differences,
        ),
        'evidence_quality': evidence_quality,
        'identifier_quality': identifier_quality,
        'risk_flags': risk_flags,
    }


def identifier_quality_for_candidate(entity: str, source_identity: Mapping[str, Any], action: str) -> str:
    if action == 'insufficient_evidence':
        return 'missing'
    if action == 'ambiguous_match':
        return 'ambiguous'

    has_system_id = not _missing(source_identity.get('system_id64'))
    has_system_name = not _missing(source_identity.get('system_name'))
    if entity == 'station':
        has_stable_entity_id = (
            not _missing(source_identity.get('market_id'))
            or not _missing(source_identity.get('edsm_station_id'))
        )
        has_entity_name = not _missing(source_identity.get('station_name'))
    elif entity == 'body':
        has_stable_entity_id = not _missing(source_identity.get('source_body_id'))
        has_entity_name = not _missing(source_identity.get('body_name'))
    else:
        has_stable_entity_id = (
            not _missing(source_identity.get('source_body_id'))
            and not _missing(source_identity.get('ring_name'))
        )
        has_entity_name = (
            not _missing(source_identity.get('body_name'))
            and not _missing(source_identity.get('ring_name'))
        )

    if has_system_id and has_stable_entity_id:
        return 'stable'
    if (has_system_id or has_system_name) and (has_stable_entity_id or has_entity_name):
        return 'partial'
    return 'missing'


def candidate_risk_flags(action: str, warnings: Sequence[Mapping[str, Any]]) -> list[str]:
    flags: list[str] = []
    if action == 'ambiguous_match':
        flags.append('ambiguous_canonical_match')
    if action == 'insufficient_evidence':
        flags.append('insufficient_identifiers')
    if any(warning.get('reason') == 'volatile_source_evidence_not_canonical_update' for warning in warnings):
        flags.append('volatile_source_evidence')
    return sorted(flags)


def evidence_quality_for_candidate(
    action: str,
    identifier_quality: str,
    canonical_matches: Sequence[Mapping[str, Any]],
    differences: Sequence[Mapping[str, Any]],
) -> str:
    if action in {'insufficient_evidence', 'ambiguous_match'}:
        return 'weak'
    if identifier_quality == 'stable' and len(canonical_matches) == 1 and not differences:
        return 'strong'
    if identifier_quality in {'stable', 'partial'} and (canonical_matches or differences):
        return 'moderate'
    if identifier_quality == 'stable':
        return 'moderate'
    return 'weak'


def confidence_reasons(
    *,
    action: str,
    identifier_quality: str,
    evidence_quality: str,
    risk_flags: Sequence[str],
    differences: Sequence[Mapping[str, Any]],
) -> list[str]:
    reasons = [
        f'action:{action}',
        f'identifier_quality:{identifier_quality}',
        f'evidence_quality:{evidence_quality}',
    ]
    if differences:
        reasons.append('stable_field_differences_present')
    reasons.extend(f'risk:{flag}' for flag in risk_flags)
    return sorted(reasons)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False
