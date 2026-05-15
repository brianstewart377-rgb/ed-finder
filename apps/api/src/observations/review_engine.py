"""Stage 6E deterministic review guidance engine.

The engine consumes a Stage 6C ``PredictionObservationComparisonResult``
and emits advisory review guidance. It is intentionally pure: no DB
access, no API calls, no simulation or optimiser imports, and no
mutation of the comparison result.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from observations.comparison_models import (
    ComparisonArea,
    ComparisonConfidence,
    ComparisonSeverity,
    ComparisonStatus,
    PredictionObservationComparison,
    PredictionObservationComparisonResult,
)
from observations.review_models import (
    EvidenceStrength,
    ReviewArea,
    ReviewStatus,
    ValidationReviewResult,
    ValidationReviewSignal,
    ValidationReviewSummary,
)

_SEVERITY_RANK = {
    'none': 0,
    ComparisonSeverity.INFO.value: 1,
    ComparisonSeverity.LOW.value: 2,
    ComparisonSeverity.MEDIUM.value: 3,
    ComparisonSeverity.HIGH.value: 4,
}
_AREA_ORDER = [
    ReviewArea.SERVICE_RULES.value,
    ReviewArea.ECONOMY_RULES.value,
    ReviewArea.CP_RULES.value,
    ReviewArea.FACILITY_RULES.value,
    ReviewArea.BUILD_OUTCOME.value,
    ReviewArea.PREDICTION_CLAIMS.value,
    ReviewArea.EVIDENCE_QUALITY.value,
    ReviewArea.GENERAL.value,
]
_NON_ACTION_STATUSES = {
    ReviewStatus.REVIEW_HIGH_PRIORITY.value,
    ReviewStatus.REVIEW_RECOMMENDED.value,
    ReviewStatus.MIXED_EVIDENCE.value,
    ReviewStatus.MONITOR.value,
    ReviewStatus.INSUFFICIENT_EVIDENCE.value,
}


def build_validation_review(
    *,
    comparison_result: PredictionObservationComparisonResult,
) -> ValidationReviewResult:
    """Build conservative review guidance from a Stage 6C comparison.

    The returned guidance describes areas that may need investigation.
    It never declares a rule wrong and never feeds anything back into
    mechanics, predictions, scoring, or confidence weights.
    """
    comparisons = list(comparison_result.comparisons)
    signals: list[ValidationReviewSignal] = []

    contradictions = [
        comparison for comparison in comparisons
        if comparison.status == ComparisonStatus.CONTRADICTED.value
    ]
    low_confidence_contradictions = [
        comparison for comparison in contradictions
        if _is_low_confidence(comparison)
    ]
    actionable_contradictions = [
        comparison for comparison in contradictions
        if not _is_low_confidence(comparison)
    ]
    confirmed = [
        comparison for comparison in comparisons
        if comparison.status == ComparisonStatus.CONFIRMED.value
    ]
    observed_only = [
        comparison for comparison in comparisons
        if comparison.status == ComparisonStatus.OBSERVED_ONLY.value
    ]
    predicted_only = [
        comparison for comparison in comparisons
        if comparison.status == ComparisonStatus.PREDICTED_ONLY.value
    ]

    if comparison_result.summary.observed_facts_count == 0:
        signals.append(_signal(
            signal_id='evidence:none',
            area=ReviewArea.EVIDENCE_QUALITY.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=ComparisonConfidence.UNKNOWN.value,
            status=ReviewStatus.INSUFFICIENT_EVIDENCE.value,
            title='No observed evidence recorded',
            message='No observed evidence has been recorded yet. Record evidence before reviewing prediction quality.',
            recommended_action='Record observed services, economies, CP, or notes.',
        ))

    if low_confidence_contradictions:
        signals.append(_signal(
            signal_id='evidence:low_confidence_contradictions',
            area=ReviewArea.EVIDENCE_QUALITY.value,
            severity=_highest_severity(low_confidence_contradictions),
            confidence=ComparisonConfidence.LOW.value,
            status=ReviewStatus.MONITOR.value,
            title='Contradiction is based on low-confidence evidence',
            message='Some needs-review rows are based on low-confidence evidence. Treat them as leads to confirm, not as high-priority review items.',
            recommended_action='Confirm in-game before changing assumptions.',
            comparison_ids=_ids(low_confidence_contradictions),
        ))

    for area, grouped in _group_actionable_contradictions(actionable_contradictions).items():
        signals.append(_contradiction_signal(area, grouped))

    facility_observed_only = [
        comparison for comparison in observed_only
        if comparison.area == ComparisonArea.FACILITY.value
    ]
    if facility_observed_only:
        signals.append(_signal(
            signal_id='facility_rules:observed_only',
            area=ReviewArea.FACILITY_RULES.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_highest_confidence(facility_observed_only),
            status=ReviewStatus.MONITOR.value,
            title='Facility evidence is not yet matched to prediction',
            message='Facility observations are present, but Stage 6C does not yet match them to structured facility predictions.',
            recommended_action='Add facility prediction extraction in a later validation stage if needed.',
            comparison_ids=_ids(facility_observed_only),
        ))

    if _predicted_only_heavy(comparison_result, predicted_only, confirmed, contradictions):
        signals.append(_signal(
            signal_id='evidence:predicted_only_heavy',
            area=ReviewArea.EVIDENCE_QUALITY.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=ComparisonConfidence.UNKNOWN.value,
            status=ReviewStatus.INSUFFICIENT_EVIDENCE.value,
            title='Many predictions have no matching observations',
            message='Many predictions have not been checked by matching observations. This is missing evidence, not a failure signal.',
            recommended_action='Record observed evidence before judging prediction quality.',
            comparison_ids=_ids(predicted_only[:20]),
        ))

    if _observed_only_heavy(observed_only, confirmed, contradictions):
        signals.append(_signal(
            signal_id='general:observed_only_heavy',
            area=ReviewArea.GENERAL.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_highest_confidence(observed_only),
            status=ReviewStatus.MONITOR.value,
            title='Observed evidence is not yet represented in prediction',
            message='Observed-only evidence is present without matching prediction rows. This is a coverage lead, not proof that a prediction is wrong.',
            recommended_action='Review whether prediction extraction covers this evidence type.',
            comparison_ids=_ids(observed_only[:20]),
        ))

    if confirmed and contradictions:
        signals.append(_signal(
            signal_id='general:mixed_evidence',
            area=ReviewArea.GENERAL.value,
            severity=_highest_severity(contradictions),
            confidence=_highest_confidence(confirmed + contradictions),
            status=ReviewStatus.MIXED_EVIDENCE.value,
            title='Validation evidence is mixed',
            message='Some predictions are supported while others may need review.',
            recommended_action='Review high-confidence needs-review rows first.',
            comparison_ids=_ids((confirmed + contradictions)[:20]),
        ))

    if confirmed and not contradictions and not signals:
        signals.append(_signal(
            signal_id='general:confirmed_only',
            area=ReviewArea.GENERAL.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_highest_confidence(confirmed),
            status=ReviewStatus.NO_ACTION.value,
            title='Evidence currently supports the prediction',
            message='Current observed evidence mostly supports the prediction. Continue gathering observations.',
            recommended_action='Continue gathering observations.',
            comparison_ids=_ids(confirmed[:20]),
        ))

    if not signals:
        signals.append(_signal(
            signal_id='general:no_review_action',
            area=ReviewArea.GENERAL.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=ComparisonConfidence.UNKNOWN.value,
            status=ReviewStatus.NO_ACTION.value,
            title='No review action yet',
            message='There is not enough matched evidence to suggest a review area yet.',
            recommended_action='Record more observations before changing assumptions.',
        ))

    summary = _build_summary(
        comparison_result=comparison_result,
        comparisons=comparisons,
        signals=signals,
        confirmed=confirmed,
        contradictions=contradictions,
        observed_only=observed_only,
    )
    return ValidationReviewResult(
        system_id64=comparison_result.system_id64,
        target_archetype=comparison_result.target_archetype,
        generated_at=comparison_result.generated_at,
        summary=summary,
        signals=signals,
        warnings=list(comparison_result.warnings),
        assumptions=list(comparison_result.assumptions),
    )


def _build_summary(
    *,
    comparison_result: PredictionObservationComparisonResult,
    comparisons: list[PredictionObservationComparison],
    signals: list[ValidationReviewSignal],
    confirmed: list[PredictionObservationComparison],
    contradictions: list[PredictionObservationComparison],
    observed_only: list[PredictionObservationComparison],
) -> ValidationReviewSummary:
    highest_severity = _highest_severity(comparisons) if comparisons else 'none'
    review_needed_count = sum(
        1 for signal in signals
        if signal.status in {
            ReviewStatus.REVIEW_RECOMMENDED.value,
            ReviewStatus.REVIEW_HIGH_PRIORITY.value,
        }
    )
    primary_review_areas = _primary_areas(signals)

    if comparison_result.summary.observed_facts_count == 0:
        overall = ReviewStatus.INSUFFICIENT_EVIDENCE.value
        strength = EvidenceStrength.NONE.value
        summary_text = 'No observed evidence has been recorded yet. Record evidence before reviewing prediction quality.'
    elif confirmed and contradictions:
        overall = ReviewStatus.MIXED_EVIDENCE.value
        strength = EvidenceStrength.MIXED.value
        summary_text = 'Evidence is mixed: some predictions are confirmed while others need review.'
    elif any(signal.status == ReviewStatus.REVIEW_HIGH_PRIORITY.value for signal in signals):
        overall = ReviewStatus.REVIEW_HIGH_PRIORITY.value
        strength = EvidenceStrength.STRONG.value
        area_text = _area_phrase(primary_review_areas)
        summary_text = f'Validation includes high-confidence needs-review rows. Review {area_text} first.'
    elif any(signal.status == ReviewStatus.REVIEW_RECOMMENDED.value for signal in signals):
        overall = ReviewStatus.REVIEW_RECOMMENDED.value
        strength = EvidenceStrength.MODERATE.value
        area_text = _area_phrase(primary_review_areas)
        summary_text = f'Validation includes needs-review rows. Review {area_text} next.'
    elif confirmed and not contradictions:
        overall = ReviewStatus.NO_ACTION.value
        strength = EvidenceStrength.STRONG.value if len(confirmed) >= 3 else EvidenceStrength.MODERATE.value
        summary_text = 'Current observed evidence mostly supports the prediction. Continue gathering observations.'
    elif observed_only:
        overall = ReviewStatus.MONITOR.value
        strength = EvidenceStrength.WEAK.value
        summary_text = 'Observed evidence is present but not yet matched to prediction rows. Review coverage before changing assumptions.'
    elif comparison_result.summary.predicted_only_count > 0:
        overall = ReviewStatus.INSUFFICIENT_EVIDENCE.value
        strength = EvidenceStrength.WEAK.value
        summary_text = 'No matching observations yet. Record evidence before judging predictions.'
    else:
        overall = ReviewStatus.NO_ACTION.value
        strength = EvidenceStrength.NONE.value
        summary_text = 'No review action yet. Record more observations before changing assumptions.'

    return ValidationReviewSummary(
        overall_review_status=overall,
        confidence_impact=comparison_result.summary.confidence_impact,
        highest_severity=highest_severity,
        review_needed_count=review_needed_count,
        evidence_strength=strength,
        primary_review_areas=primary_review_areas,
        summary=summary_text,
    )


def _group_actionable_contradictions(
    contradictions: Iterable[PredictionObservationComparison],
) -> dict[str, list[PredictionObservationComparison]]:
    grouped: dict[str, list[PredictionObservationComparison]] = defaultdict(list)
    for comparison in contradictions:
        grouped[_review_area_for_comparison(comparison)].append(comparison)
    return {area: grouped[area] for area in _AREA_ORDER if grouped.get(area)}


def _contradiction_signal(
    area: str,
    comparisons: list[PredictionObservationComparison],
) -> ValidationReviewSignal:
    high_priority = any(
        comparison.severity == ComparisonSeverity.HIGH.value
        and comparison.confidence in {ComparisonConfidence.HIGH.value, ComparisonConfidence.MEDIUM.value}
        for comparison in comparisons
    )
    status = (
        ReviewStatus.REVIEW_HIGH_PRIORITY.value
        if high_priority
        else ReviewStatus.REVIEW_RECOMMENDED.value
    )
    title, action = _area_title_action(area)
    return _signal(
        signal_id=f'{area}:contradicted',
        area=area,
        severity=_highest_severity(comparisons),
        confidence=_highest_confidence(comparisons),
        status=status,
        title=title,
        message=f'{len(comparisons)} needs-review comparison row(s) point to this area. This is a review lead, not proof of a rule failure.',
        recommended_action=action,
        comparison_ids=_ids(comparisons),
    )


def _area_title_action(area: str) -> tuple[str, str]:
    if area == ReviewArea.SERVICE_RULES.value:
        return (
            'Service prediction rules may need review',
            'Review service unlock assumptions and facility/service mapping.',
        )
    if area == ReviewArea.ECONOMY_RULES.value:
        return (
            'Economy prediction rules may need review',
            'Review economy inheritance, facility pressure, and economy composition assumptions.',
        )
    if area == ReviewArea.CP_RULES.value:
        return (
            'CP calculation may need review',
            'Review CP source values and final CP calculation.',
        )
    if area == ReviewArea.BUILD_OUTCOME.value:
        return (
            'Build outcome interpretation may need review',
            'Review build outcome assumptions and the observed outcome notes.',
        )
    if area == ReviewArea.PREDICTION_CLAIMS.value:
        return (
            'Prediction claim evidence may need review',
            'Review the recorded prediction-match or prediction-mismatch claim.',
        )
    return (
        'Validation area may need review',
        'Review high-confidence needs-review rows first.',
    )


def _review_area_for_comparison(comparison: PredictionObservationComparison) -> str:
    if comparison.area == ComparisonArea.SERVICE.value:
        return ReviewArea.SERVICE_RULES.value
    if comparison.area == ComparisonArea.ECONOMY.value:
        return ReviewArea.ECONOMY_RULES.value
    if comparison.area == ComparisonArea.CP.value:
        return ReviewArea.CP_RULES.value
    if comparison.area == ComparisonArea.FACILITY.value:
        return ReviewArea.FACILITY_RULES.value
    if comparison.area == ComparisonArea.BUILD_OUTCOME.value:
        return ReviewArea.BUILD_OUTCOME.value
    if comparison.subject_type == 'prediction':
        return ReviewArea.PREDICTION_CLAIMS.value
    return ReviewArea.GENERAL.value


def _signal(
    *,
    signal_id: str,
    area: str,
    severity: str,
    confidence: str,
    status: str,
    title: str,
    message: str,
    recommended_action: str | None = None,
    comparison_ids: list[str] | None = None,
) -> ValidationReviewSignal:
    return ValidationReviewSignal(
        signal_id=signal_id,
        area=area,
        severity=severity,
        confidence=confidence,
        status=status,
        title=title,
        message=message,
        recommended_action=recommended_action,
        comparison_ids=comparison_ids or [],
    )


def _highest_severity(comparisons: Iterable[PredictionObservationComparison]) -> str:
    highest = 'none'
    for comparison in comparisons:
        if _SEVERITY_RANK.get(comparison.severity, 0) > _SEVERITY_RANK[highest]:
            highest = comparison.severity
    return highest


def _highest_confidence(comparisons: Iterable[PredictionObservationComparison]) -> str:
    rank = {
        ComparisonConfidence.UNKNOWN.value: 0,
        ComparisonConfidence.LOW.value: 1,
        ComparisonConfidence.MEDIUM.value: 2,
        ComparisonConfidence.HIGH.value: 3,
    }
    highest = ComparisonConfidence.UNKNOWN.value
    for comparison in comparisons:
        if rank.get(comparison.confidence, 0) > rank[highest]:
            highest = comparison.confidence
    return highest


def _is_low_confidence(comparison: PredictionObservationComparison) -> bool:
    return comparison.confidence == ComparisonConfidence.LOW.value


def _ids(comparisons: Iterable[PredictionObservationComparison]) -> list[str]:
    return [comparison.comparison_id for comparison in comparisons]


def _predicted_only_heavy(
    comparison_result: PredictionObservationComparisonResult,
    predicted_only: list[PredictionObservationComparison],
    confirmed: list[PredictionObservationComparison],
    contradictions: list[PredictionObservationComparison],
) -> bool:
    if not predicted_only:
        return False
    if comparison_result.summary.observed_facts_count == 0:
        return True
    checked = len(confirmed) + len(contradictions)
    return len(predicted_only) >= 3 and len(predicted_only) > checked


def _observed_only_heavy(
    observed_only: list[PredictionObservationComparison],
    confirmed: list[PredictionObservationComparison],
    contradictions: list[PredictionObservationComparison],
) -> bool:
    if not observed_only:
        return False
    checked = len(confirmed) + len(contradictions)
    return len(observed_only) >= 3 and len(observed_only) >= checked


def _primary_areas(signals: list[ValidationReviewSignal]) -> list[str]:
    areas = {
        signal.area for signal in signals
        if signal.status in _NON_ACTION_STATUSES
        and signal.area != ReviewArea.GENERAL.value
    }
    if not areas:
        areas = {
            signal.area for signal in signals
            if signal.status in _NON_ACTION_STATUSES
        }
    if not areas:
        areas = {signal.area for signal in signals}
    return [area for area in _AREA_ORDER if area in areas]


def _area_phrase(areas: list[str]) -> str:
    labels = {
        ReviewArea.SERVICE_RULES.value: 'service assumptions',
        ReviewArea.ECONOMY_RULES.value: 'economy assumptions',
        ReviewArea.CP_RULES.value: 'CP assumptions',
        ReviewArea.FACILITY_RULES.value: 'facility coverage',
        ReviewArea.BUILD_OUTCOME.value: 'build outcome assumptions',
        ReviewArea.PREDICTION_CLAIMS.value: 'prediction claim evidence',
        ReviewArea.EVIDENCE_QUALITY.value: 'evidence quality',
        ReviewArea.GENERAL.value: 'validation evidence',
    }
    picked = [labels.get(area, area) for area in areas[:2]]
    if not picked:
        return 'validation evidence'
    if len(picked) == 1:
        return picked[0]
    return f'{picked[0]} and {picked[1]}'


__all__ = ['build_validation_review']
