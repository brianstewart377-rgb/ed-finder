"""Stage 6C deterministic predicted-vs-observed comparison engine.

This module compares a prediction (typically a Simulation Preview
response, but any prediction-shaped ``Mapping[str, Any]`` is accepted)
against a list of ``PersistedObservedFact`` records produced by the
Stage 6A evidence shelf, and returns a structured
``PredictionObservationComparisonResult``.

Design rules — DO NOT relax without an explicit stage decision:

1. **Pure / deterministic.** No database access, no network access,
   no global state, no time-dependent branching unless ``now`` is
   injected. The same inputs always produce the same output.
2. **No mutation.** Neither the ``prediction`` mapping nor the
   ``observed_facts`` list (or its members) is mutated.
3. **No scoring impact.** Nothing in this module is imported by
   simulation scoring, optimiser candidate generation, or optimiser
   ranking. A static passivity test enforces this.
4. **Conservative semantics.**
   * Missing observations do not contradict predictions.
   * Unknown/unverified observations do not confirm or contradict;
     they surface as ``unverified``.
   * Low-confidence observations cannot produce high-severity
     contradictions.
   * Notes never contradict — they are observed-only context.
   * One observation is evidence, not proof.

The matching rules and status decisions are documented inline next to
each helper so they are explicit, reviewable, and testable.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from observations.comparison_models import (
    ComparisonArea,
    ComparisonConfidence,
    ComparisonConfidenceImpact,
    ComparisonOverallStatus,
    ComparisonSeverity,
    ComparisonStatus,
    ObservationEvidenceMatch,
    PredictionObservationComparison,
    PredictionObservationComparisonResult,
    PredictionObservationComparisonSummary,
)
from observations.models import (
    ObservedConfidence,
    ObservedFactType,
    ObservedStatus,
    ObservedSubjectType,
    PersistedObservedFact,
)


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────
def compare_prediction_to_observations(
    *,
    system_id64: int,
    target_archetype: str | None,
    prediction: Mapping[str, Any],
    observed_facts: list[PersistedObservedFact],
    now: Callable[[], datetime] | None = None,
) -> PredictionObservationComparisonResult:
    """Compare a prediction against observed facts and return a result.

    ``now`` is injectable purely so tests can pin ``generated_at``. The
    default uses UTC ``datetime.now`` and serialises to ISO-8601.
    """
    if not isinstance(prediction, Mapping):
        # The router-level Pydantic model already enforces this, but the
        # engine is also called directly by tests/utilities, so guard
        # here too. We refuse to silently coerce.
        raise TypeError('prediction must be a Mapping[str, Any]')

    generated_at = (now() if now else datetime.now(timezone.utc)).isoformat()
    comparisons: list[PredictionObservationComparison] = []
    assumptions: list[str] = []
    warnings: list[str] = []

    # Index observations by (fact_type, subject_key) so prediction-side
    # walks can find counterpart observations in O(1).
    obs_index = _index_observations(observed_facts)

    # 1. Service comparisons — walk the prediction's predicted services
    #    first so predicted_only rows are emitted in a deterministic
    #    order, then process any observed services with no prediction.
    service_predictions = _extract_service_predictions(prediction)
    seen_service_subjects: set[str] = set()
    for service_id, predicted_status in sorted(service_predictions.items()):
        matched = obs_index.pop_service(service_id)
        seen_service_subjects.add(service_id)
        comparisons.append(_compare_service(service_id, predicted_status, matched))

    # Any service observations left unmatched are observed_only.
    for service_id, facts in sorted(obs_index.services_remaining().items()):
        for fact in facts:
            comparisons.append(_observed_only_service(fact))

    # 2. Economy comparisons — same pattern.
    economy_predictions = _extract_economy_predictions(prediction)
    for economy_name, predicted_present in sorted(economy_predictions.items()):
        matched = obs_index.pop_economy(economy_name)
        comparisons.append(_compare_economy(economy_name, predicted_present, matched))

    for economy_name, facts in sorted(obs_index.economies_remaining().items()):
        for fact in facts:
            comparisons.append(_observed_only_economy(fact))

    # 3. CP comparisons — observation-driven; we only emit a row per
    #    observation. We deliberately do not emit predicted_only rows
    #    for every CP sub-field to avoid noise (see status rules).
    for fact in obs_index.cp_facts():
        comparisons.append(_compare_cp(prediction, fact))

    # 4. Facility state — observation-driven. Predictions don't expose a
    #    structured per-facility state map yet in 6C, so these become
    #    observed_only.
    for fact in obs_index.facility_facts():
        comparisons.append(_observed_only_facility(fact))

    # 5. Build outcome — observation-driven, conservative summary-only.
    for fact in obs_index.build_outcome_facts():
        comparisons.append(_compare_build_outcome(prediction, fact))

    # 6. prediction_match / prediction_mismatch — user-supplied claims
    #    about a subject. Map to confirmed / contradicted only if the
    #    referenced subject is known to the prediction; otherwise leave
    #    as observed_only / unverified.
    for fact in obs_index.prediction_match_facts():
        comparisons.append(_compare_prediction_match(fact, service_predictions, economy_predictions, matched=True))
    for fact in obs_index.prediction_mismatch_facts():
        comparisons.append(_compare_prediction_match(fact, service_predictions, economy_predictions, matched=False))

    # 7. Notes — never contradict; always observed_only/info.
    for fact in obs_index.note_facts():
        comparisons.append(_observed_only_note(fact))

    if not service_predictions:
        assumptions.append('Prediction did not expose a `services` map; service comparisons rely on observed facts only.')
    if not economy_predictions:
        assumptions.append('Prediction did not expose `economy_composition` or `economy_order`; economy comparisons rely on observed facts only.')
    if 'cp' not in prediction:
        assumptions.append('Prediction did not expose a `cp` map; CP comparisons rely on observed facts only.')

    summary = _build_summary(
        observed_facts_count=len(observed_facts),
        comparisons=comparisons,
    )

    return PredictionObservationComparisonResult(
        system_id64=system_id64,
        target_archetype=target_archetype,
        generated_at=generated_at,
        summary=summary,
        comparisons=comparisons,
        warnings=warnings,
        assumptions=assumptions,
    )


# ──────────────────────────────────────────────────────────────────────
# Prediction extraction helpers
# ──────────────────────────────────────────────────────────────────────
def _extract_service_predictions(prediction: Mapping[str, Any]) -> dict[str, str | None]:
    """Pull predicted service IDs → status from the prediction.

    Reads two complementary fields:
      * ``services`` — top-level mapping of ``service_id -> {status,...}``
        produced by Simulation Preview.
      * ``port_service_states`` — per-port buckets (active/locked/unknown).
        Status precedence: ``active`` > ``locked`` > top-level value.

    The function is tolerant of partial shapes — anything that is not
    a dict-of-dicts is ignored rather than raising.
    """
    result: dict[str, str | None] = {}

    services_field = prediction.get('services')
    if isinstance(services_field, Mapping):
        for service_id, payload in services_field.items():
            if not isinstance(service_id, str):
                continue
            if isinstance(payload, Mapping):
                status = payload.get('status')
                result[service_id] = str(status) if status is not None else None
            else:
                # services map may carry simple presence values
                result[service_id] = str(payload) if payload is not None else None

    port_states = prediction.get('port_service_states')
    if isinstance(port_states, list):
        for state in port_states:
            if not isinstance(state, Mapping):
                continue
            for bucket, override_status in (
                ('active_services', 'active'),
                ('locked_services', 'locked'),
                ('unknown_services', 'unknown'),
            ):
                services = state.get(bucket)
                if not isinstance(services, Mapping):
                    continue
                for service_id in services.keys():
                    if not isinstance(service_id, str):
                        continue
                    # Active wins over locked wins over unknown wins
                    # over the (possibly null) top-level value.
                    if (
                        result.get(service_id) is None
                        or (override_status == 'active')
                        or (override_status == 'locked' and result.get(service_id) != 'active')
                    ):
                        result[service_id] = override_status

    return result


def _extract_economy_predictions(prediction: Mapping[str, Any]) -> dict[str, bool]:
    """Pull predicted economy names → present-bool from the prediction.

    Combines ``economy_composition`` (dict of economy → weight, present
    iff weight > 0) and ``economy_order`` (list, ordered most→least).
    A name appearing in either source is considered predicted-present.
    Anything that fails type checks is skipped, not raised.
    """
    result: dict[str, bool] = {}

    composition = prediction.get('economy_composition')
    if isinstance(composition, Mapping):
        for name, weight in composition.items():
            if not isinstance(name, str):
                continue
            try:
                w = float(weight) if weight is not None else 0.0
            except (TypeError, ValueError):
                w = 0.0
            if w > 0:
                result[name] = True

    order = prediction.get('economy_order')
    if isinstance(order, list):
        for name in order:
            if isinstance(name, str):
                result.setdefault(name, True)

    return result


# ──────────────────────────────────────────────────────────────────────
# Observation indexing
# ──────────────────────────────────────────────────────────────────────
class _ObservationIndex:
    """Bucket observations by fact_type/subject so prediction walks are O(1)."""

    def __init__(self, facts: Iterable[PersistedObservedFact]):
        self._services: dict[str, list[PersistedObservedFact]] = {}
        self._economies: dict[str, list[PersistedObservedFact]] = {}
        self._cp: list[PersistedObservedFact] = []
        self._facilities: list[PersistedObservedFact] = []
        self._build_outcomes: list[PersistedObservedFact] = []
        self._prediction_match: list[PersistedObservedFact] = []
        self._prediction_mismatch: list[PersistedObservedFact] = []
        self._notes: list[PersistedObservedFact] = []

        for fact in facts:
            self._classify(fact)

    def _classify(self, fact: PersistedObservedFact) -> None:
        ft = fact.fact_type
        if ft == ObservedFactType.SERVICE_PRESENCE.value:
            key = fact.service_id or fact.subject_id or ''
            self._services.setdefault(key, []).append(fact)
        elif ft == ObservedFactType.ECONOMY_PRESENCE.value:
            key = fact.economy or fact.subject_id or ''
            self._economies.setdefault(key, []).append(fact)
        elif ft == ObservedFactType.CP_VALUE.value:
            self._cp.append(fact)
        elif ft == ObservedFactType.FACILITY_STATE.value:
            self._facilities.append(fact)
        elif ft == ObservedFactType.BUILD_OUTCOME.value:
            self._build_outcomes.append(fact)
        elif ft == ObservedFactType.PREDICTION_MATCH.value:
            self._prediction_match.append(fact)
        elif ft == ObservedFactType.PREDICTION_MISMATCH.value:
            self._prediction_mismatch.append(fact)
        elif ft == ObservedFactType.NOTE.value:
            self._notes.append(fact)
        else:
            # Unknown fact_type: surface as note-style observed_only so we
            # never silently drop it. We bucket it into notes for
            # downstream rendering.
            self._notes.append(fact)

    def pop_service(self, service_id: str) -> list[PersistedObservedFact]:
        return self._services.pop(service_id, [])

    def services_remaining(self) -> dict[str, list[PersistedObservedFact]]:
        return self._services

    def pop_economy(self, name: str) -> list[PersistedObservedFact]:
        return self._economies.pop(name, [])

    def economies_remaining(self) -> dict[str, list[PersistedObservedFact]]:
        return self._economies

    def cp_facts(self) -> list[PersistedObservedFact]:
        return list(self._cp)

    def facility_facts(self) -> list[PersistedObservedFact]:
        return list(self._facilities)

    def build_outcome_facts(self) -> list[PersistedObservedFact]:
        return list(self._build_outcomes)

    def prediction_match_facts(self) -> list[PersistedObservedFact]:
        return list(self._prediction_match)

    def prediction_mismatch_facts(self) -> list[PersistedObservedFact]:
        return list(self._prediction_mismatch)

    def note_facts(self) -> list[PersistedObservedFact]:
        return list(self._notes)


def _index_observations(facts: Iterable[PersistedObservedFact]) -> _ObservationIndex:
    return _ObservationIndex(facts)


# ──────────────────────────────────────────────────────────────────────
# Service comparison
# ──────────────────────────────────────────────────────────────────────
def _service_present(predicted_status: str | None) -> bool:
    """Translate a predicted service status to a present-or-not boolean.

    'active' counts as present. 'locked' and 'unknown' do not.
    """
    if predicted_status is None:
        return False
    return predicted_status.lower() == 'active'


def _compare_service(
    service_id: str,
    predicted_status: str | None,
    observed_facts: list[PersistedObservedFact],
) -> PredictionObservationComparison:
    if not observed_facts:
        return PredictionObservationComparison(
            comparison_id=f'service:{service_id}',
            area=ComparisonArea.SERVICE.value,
            subject_type=ObservedSubjectType.SERVICE.value,
            subject_id=service_id,
            predicted_value=predicted_status,
            observed_value=None,
            status=ComparisonStatus.PREDICTED_ONLY.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=ComparisonConfidence.UNKNOWN.value,
            reason='Prediction includes this service but no observed evidence has been recorded yet.',
            recommended_action=None,
            evidence=[],
            prediction_source='services',
        )

    # Most-recent-first: observed_facts within a bucket retain their
    # insertion order which comes from the caller; we treat the first
    # one as primary for status decision while still attaching all.
    primary = observed_facts[0]
    predicted_present = _service_present(predicted_status)
    status, severity, reason, action = _service_status_decision(predicted_status, predicted_present, primary)
    return PredictionObservationComparison(
        comparison_id=f'service:{service_id}',
        area=ComparisonArea.SERVICE.value,
        subject_type=ObservedSubjectType.SERVICE.value,
        subject_id=service_id,
        predicted_value=predicted_status,
        observed_value=primary.observed_value,
        status=status,
        severity=severity,
        confidence=_comparison_confidence_for(primary),
        reason=reason,
        recommended_action=action,
        evidence=[_evidence_from_fact(fact) for fact in observed_facts],
        prediction_source='services',
    )


def _service_status_decision(
    predicted_status: str | None,
    predicted_present: bool,
    fact: PersistedObservedFact,
) -> tuple[str, str, str, str | None]:
    obs_status = fact.status
    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        return (
            ComparisonStatus.UNVERIFIED.value,
            ComparisonSeverity.INFO.value,
            'Observation marked as unknown or unverified — not used to confirm or contradict the prediction.',
            None,
        )

    observed_present = obs_status in (
        ObservedStatus.OBSERVED_PRESENT.value,
        ObservedStatus.CONFIRMED.value,
    )
    observed_absent = obs_status in (
        ObservedStatus.OBSERVED_ABSENT.value,
        ObservedStatus.CONTRADICTED.value,
    )

    if predicted_present and observed_present:
        return (
            ComparisonStatus.CONFIRMED.value,
            ComparisonSeverity.INFO.value,
            f'Predicted active and observed present (status={predicted_status}).',
            None,
        )
    if predicted_present and observed_absent:
        severity = _contradiction_severity(fact, base=ComparisonSeverity.HIGH)
        return (
            ComparisonStatus.CONTRADICTED.value,
            severity,
            f'Prediction expected this service to be active but the observation reports it as absent.',
            'Review service unlock rules and the observed port/facility combination.',
        )
    if not predicted_present and observed_present:
        severity = _contradiction_severity(fact, base=ComparisonSeverity.MEDIUM)
        return (
            ComparisonStatus.CONTRADICTED.value,
            severity,
            f'Prediction did not show this service as active but the observation reports it as present.',
            'Review service unlock rules for the observed facility mix.',
        )
    if not predicted_present and observed_absent:
        return (
            ComparisonStatus.CONFIRMED.value,
            ComparisonSeverity.INFO.value,
            'Prediction did not expect this service active and the observation confirms it is absent.',
            None,
        )
    # observed_present / observed_absent flags both False here means the
    # observation status is something unmapped — be conservative.
    return (
        ComparisonStatus.UNVERIFIED.value,
        ComparisonSeverity.INFO.value,
        'Observation status does not clearly indicate presence or absence — not used to confirm or contradict.',
        None,
    )


def _observed_only_service(fact: PersistedObservedFact) -> PredictionObservationComparison:
    service_id = fact.service_id or fact.subject_id or ''
    obs_status = fact.status
    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        status = ComparisonStatus.UNVERIFIED.value
        reason = 'Observation marked unknown/unverified and has no matching predicted service.'
    else:
        status = ComparisonStatus.OBSERVED_ONLY.value
        reason = 'Observed service has no matching entry in the current prediction.'
    return PredictionObservationComparison(
        comparison_id=f'service:{service_id}',
        area=ComparisonArea.SERVICE.value,
        subject_type=ObservedSubjectType.SERVICE.value,
        subject_id=service_id,
        predicted_value=None,
        observed_value=fact.observed_value,
        status=status,
        severity=ComparisonSeverity.INFO.value,
        confidence=_comparison_confidence_for(fact),
        reason=reason,
        recommended_action=None,
        evidence=[_evidence_from_fact(fact)],
        prediction_source=None,
    )


# ──────────────────────────────────────────────────────────────────────
# Economy comparison
# ──────────────────────────────────────────────────────────────────────
def _compare_economy(
    economy_name: str,
    predicted_present: bool,
    observed_facts: list[PersistedObservedFact],
) -> PredictionObservationComparison:
    if not observed_facts:
        return PredictionObservationComparison(
            comparison_id=f'economy:{economy_name}',
            area=ComparisonArea.ECONOMY.value,
            subject_type=ObservedSubjectType.ECONOMY.value,
            subject_id=economy_name,
            predicted_value=predicted_present,
            observed_value=None,
            status=ComparisonStatus.PREDICTED_ONLY.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=ComparisonConfidence.UNKNOWN.value,
            reason='Prediction includes this economy but no observed evidence has been recorded yet.',
            recommended_action=None,
            evidence=[],
            prediction_source='economy_composition/economy_order',
        )

    primary = observed_facts[0]
    obs_status = primary.status

    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        return PredictionObservationComparison(
            comparison_id=f'economy:{economy_name}',
            area=ComparisonArea.ECONOMY.value,
            subject_type=ObservedSubjectType.ECONOMY.value,
            subject_id=economy_name,
            predicted_value=predicted_present,
            observed_value=primary.observed_value,
            status=ComparisonStatus.UNVERIFIED.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_comparison_confidence_for(primary),
            reason='Observation marked unknown/unverified — not used to confirm or contradict the predicted economy.',
            recommended_action=None,
            evidence=[_evidence_from_fact(fact) for fact in observed_facts],
            prediction_source='economy_composition/economy_order',
        )

    observed_present = obs_status in (
        ObservedStatus.OBSERVED_PRESENT.value,
        ObservedStatus.CONFIRMED.value,
    )
    observed_absent = obs_status in (
        ObservedStatus.OBSERVED_ABSENT.value,
        ObservedStatus.CONTRADICTED.value,
    )

    if predicted_present and observed_present:
        status, severity, reason, action = (
            ComparisonStatus.CONFIRMED.value,
            ComparisonSeverity.INFO.value,
            'Predicted economy is also recorded as present in the observation.',
            None,
        )
    elif predicted_present and observed_absent:
        status, severity, reason, action = (
            ComparisonStatus.CONTRADICTED.value,
            _contradiction_severity(primary, base=ComparisonSeverity.MEDIUM),
            'Prediction expected this economy but the observation reports it as absent.',
            'Review economy inheritance and facility economy pressure for the observed body.',
        )
    elif not predicted_present and observed_present:
        status, severity, reason, action = (
            ComparisonStatus.CONTRADICTED.value,
            _contradiction_severity(primary, base=ComparisonSeverity.MEDIUM),
            'Prediction did not include this economy but the observation reports it as present.',
            'Review economy inheritance, facility economy pressure, and topology rules.',
        )
    elif not predicted_present and observed_absent:
        status, severity, reason, action = (
            ComparisonStatus.CONFIRMED.value,
            ComparisonSeverity.INFO.value,
            'Prediction did not include this economy and observation confirms it is absent.',
            None,
        )
    else:
        status, severity, reason, action = (
            ComparisonStatus.UNVERIFIED.value,
            ComparisonSeverity.INFO.value,
            'Observation status does not clearly indicate presence or absence — not used to confirm or contradict.',
            None,
        )

    return PredictionObservationComparison(
        comparison_id=f'economy:{economy_name}',
        area=ComparisonArea.ECONOMY.value,
        subject_type=ObservedSubjectType.ECONOMY.value,
        subject_id=economy_name,
        predicted_value=predicted_present,
        observed_value=primary.observed_value,
        status=status,
        severity=severity,
        confidence=_comparison_confidence_for(primary),
        reason=reason,
        recommended_action=action,
        evidence=[_evidence_from_fact(fact) for fact in observed_facts],
        prediction_source='economy_composition/economy_order',
    )


def _observed_only_economy(fact: PersistedObservedFact) -> PredictionObservationComparison:
    economy_name = fact.economy or fact.subject_id or ''
    obs_status = fact.status
    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        status = ComparisonStatus.UNVERIFIED.value
        reason = 'Observation marked unknown/unverified and has no matching predicted economy.'
    else:
        status = ComparisonStatus.OBSERVED_ONLY.value
        reason = 'Observed economy has no matching entry in the current prediction.'
    return PredictionObservationComparison(
        comparison_id=f'economy:{economy_name}',
        area=ComparisonArea.ECONOMY.value,
        subject_type=ObservedSubjectType.ECONOMY.value,
        subject_id=economy_name,
        predicted_value=None,
        observed_value=fact.observed_value,
        status=status,
        severity=ComparisonSeverity.INFO.value,
        confidence=_comparison_confidence_for(fact),
        reason=reason,
        recommended_action=None,
        evidence=[_evidence_from_fact(fact)],
        prediction_source=None,
    )


# ──────────────────────────────────────────────────────────────────────
# CP comparison
# ──────────────────────────────────────────────────────────────────────
def _compare_cp(prediction: Mapping[str, Any], fact: PersistedObservedFact) -> PredictionObservationComparison:
    cp = prediction.get('cp')
    subject_id = fact.subject_id or 'cp'

    if not isinstance(cp, Mapping):
        return PredictionObservationComparison(
            comparison_id=f'cp:{subject_id}',
            area=ComparisonArea.CP.value,
            subject_type=ObservedSubjectType.CP.value,
            subject_id=subject_id,
            predicted_value=None,
            observed_value=fact.observed_value,
            status=ComparisonStatus.OBSERVED_ONLY.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_comparison_confidence_for(fact),
            reason='Prediction did not include a `cp` block — observation kept as observed_only.',
            recommended_action=None,
            evidence=[_evidence_from_fact(fact)],
            prediction_source=None,
        )

    obs_status = fact.status
    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        return PredictionObservationComparison(
            comparison_id=f'cp:{subject_id}',
            area=ComparisonArea.CP.value,
            subject_type=ObservedSubjectType.CP.value,
            subject_id=subject_id,
            predicted_value=_cp_predicted_view(cp),
            observed_value=fact.observed_value,
            status=ComparisonStatus.UNVERIFIED.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_comparison_confidence_for(fact),
            reason='Observation marked unknown/unverified — not used to confirm or contradict CP prediction.',
            recommended_action=None,
            evidence=[_evidence_from_fact(fact)],
            prediction_source='cp',
        )

    matched, predicted_view, mismatch_keys = _cp_match(cp, fact.observed_value)
    if matched is None:
        # We could not compare — observed_value shape didn't make sense.
        return PredictionObservationComparison(
            comparison_id=f'cp:{subject_id}',
            area=ComparisonArea.CP.value,
            subject_type=ObservedSubjectType.CP.value,
            subject_id=subject_id,
            predicted_value=predicted_view,
            observed_value=fact.observed_value,
            status=ComparisonStatus.UNVERIFIED.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_comparison_confidence_for(fact),
            reason='Observed CP value shape could not be compared against the prediction (expected number or {yellow, green} object).',
            recommended_action=None,
            evidence=[_evidence_from_fact(fact)],
            prediction_source='cp',
        )

    if matched:
        return PredictionObservationComparison(
            comparison_id=f'cp:{subject_id}',
            area=ComparisonArea.CP.value,
            subject_type=ObservedSubjectType.CP.value,
            subject_id=subject_id,
            predicted_value=predicted_view,
            observed_value=fact.observed_value,
            status=ComparisonStatus.CONFIRMED.value,
            severity=ComparisonSeverity.INFO.value,
            confidence=_comparison_confidence_for(fact),
            reason='Observed CP balance matches the predicted CP balance.',
            recommended_action=None,
            evidence=[_evidence_from_fact(fact)],
            prediction_source='cp',
        )

    severity = _contradiction_severity(fact, base=ComparisonSeverity.MEDIUM)
    return PredictionObservationComparison(
        comparison_id=f'cp:{subject_id}',
        area=ComparisonArea.CP.value,
        subject_type=ObservedSubjectType.CP.value,
        subject_id=subject_id,
        predicted_value=predicted_view,
        observed_value=fact.observed_value,
        status=ComparisonStatus.CONTRADICTED.value,
        severity=severity,
        confidence=_comparison_confidence_for(fact),
        reason=(
            'Observed CP balance differs from predicted CP balance'
            + (f' on keys: {sorted(mismatch_keys)}.' if mismatch_keys else '.')
        ),
        recommended_action='Review CP rules, primary-port exemption, build order, and CP repair suggestions.',
        evidence=[_evidence_from_fact(fact)],
        prediction_source='cp',
    )


def _cp_predicted_view(cp: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the CP fields a comparison row typically cares about.

    Limiting the predicted view keeps the response compact and avoids
    repeating large nested CP timelines in every comparison row.
    """
    keys = ('yellow_cp_final', 'green_cp_final', 'yellow_cp_generated', 'green_cp_generated',
            'yellow_cp_spent', 'green_cp_spent', 't2_ports', 't3_ports')
    return {k: cp.get(k) for k in keys if k in cp}


def _cp_match(cp: Mapping[str, Any], observed: Any) -> tuple[bool | None, dict[str, Any], list[str]]:
    """Compare observed CP against the predicted ``cp`` block.

    Accepts two observed shapes:
      * a numeric value — compared against ``cp['yellow_cp_final']``
        (the most common case for "the final CP I saw").
      * a dict with any subset of ``yellow_cp_final`` / ``green_cp_final``
        / etc. — only overlapping keys are compared.

    Returns ``(matched, predicted_view, mismatch_keys)``. ``matched`` is
    ``None`` when the shape was unsupported.
    """
    predicted_view = _cp_predicted_view(cp)

    if isinstance(observed, (int, float)) and not isinstance(observed, bool):
        # Numeric scalar — interpret as final yellow CP (the prediction's
        # primary CP value). This is conservative: if the user wanted to
        # compare green CP, they should send a dict.
        target = cp.get('yellow_cp_final')
        if target is None:
            return None, predicted_view, []
        try:
            return (float(target) == float(observed)), predicted_view, [] if float(target) == float(observed) else ['yellow_cp_final']
        except (TypeError, ValueError):
            return None, predicted_view, []

    if isinstance(observed, Mapping):
        mismatch: list[str] = []
        any_compared = False
        for key, obs_value in observed.items():
            if not isinstance(key, str):
                continue
            if key not in cp:
                continue
            any_compared = True
            pred_value = cp.get(key)
            if _scalar_equal(pred_value, obs_value):
                continue
            mismatch.append(key)
        if not any_compared:
            return None, predicted_view, []
        return (not mismatch), predicted_view, mismatch

    return None, predicted_view, []


def _scalar_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


# ──────────────────────────────────────────────────────────────────────
# Facility / build outcome / notes / prediction_match
# ──────────────────────────────────────────────────────────────────────
def _observed_only_facility(fact: PersistedObservedFact) -> PredictionObservationComparison:
    subject = fact.facility_template_id or fact.subject_id or ''
    return PredictionObservationComparison(
        comparison_id=f'facility:{subject}' if subject else 'facility',
        area=ComparisonArea.FACILITY.value,
        subject_type=ObservedSubjectType.FACILITY.value,
        subject_id=subject or None,
        predicted_value=None,
        observed_value=fact.observed_value,
        status=ComparisonStatus.OBSERVED_ONLY.value,
        severity=ComparisonSeverity.INFO.value,
        confidence=_comparison_confidence_for(fact),
        reason='Prediction does not expose a comparable facility-state map; observation kept as observed_only.',
        recommended_action=None,
        evidence=[_evidence_from_fact(fact)],
        prediction_source=None,
    )


def _compare_build_outcome(prediction: Mapping[str, Any], fact: PersistedObservedFact) -> PredictionObservationComparison:
    # Stage 6C deliberately keeps build_outcome at a summary-only level
    # so we don't make claims about partial build sequences. We surface
    # the observed value and reference final_score/confidence from the
    # prediction without asserting confirmed/contradicted unless the
    # observation itself carries an explicit confirmed/contradicted
    # status.
    obs_status = fact.status
    final_score = prediction.get('final_score')
    confidence_view = prediction.get('confidence')
    predicted_view: dict[str, Any] = {}
    if final_score is not None:
        predicted_view['final_score'] = final_score
    if confidence_view is not None:
        predicted_view['confidence'] = confidence_view

    if obs_status == ObservedStatus.CONFIRMED.value:
        return _make_comparison(
            comparison_id=f'build_outcome:{fact.observation_id}',
            area=ComparisonArea.BUILD_OUTCOME,
            subject_type=ObservedSubjectType.BUILD,
            subject_id=fact.subject_id,
            predicted_value=predicted_view or None,
            fact=fact,
            status=ComparisonStatus.CONFIRMED,
            severity=ComparisonSeverity.INFO,
            reason='User-supplied build outcome marked confirmed against the prediction.',
            action=None,
            prediction_source='final_score/confidence',
        )
    if obs_status == ObservedStatus.CONTRADICTED.value:
        return _make_comparison(
            comparison_id=f'build_outcome:{fact.observation_id}',
            area=ComparisonArea.BUILD_OUTCOME,
            subject_type=ObservedSubjectType.BUILD,
            subject_id=fact.subject_id,
            predicted_value=predicted_view or None,
            fact=fact,
            status=ComparisonStatus.CONTRADICTED,
            severity=_severity_enum_from_value(_contradiction_severity(fact, base=ComparisonSeverity.MEDIUM)),
            reason='User-supplied build outcome marked contradicted against the prediction.',
            action='Review which prediction inputs differed from the observed build.',
            prediction_source='final_score/confidence',
        )
    # Default — observed_only/unverified, no strong claim.
    if obs_status in (ObservedStatus.UNKNOWN.value, ObservedStatus.UNVERIFIED.value):
        target_status = ComparisonStatus.UNVERIFIED
        reason = 'User-supplied build outcome is unknown/unverified — not used to confirm or contradict.'
    else:
        target_status = ComparisonStatus.OBSERVED_ONLY
        reason = 'User-supplied build outcome recorded; Stage 6C does not auto-classify build outcomes beyond user-supplied status.'
    return _make_comparison(
        comparison_id=f'build_outcome:{fact.observation_id}',
        area=ComparisonArea.BUILD_OUTCOME,
        subject_type=ObservedSubjectType.BUILD,
        subject_id=fact.subject_id,
        predicted_value=predicted_view or None,
        fact=fact,
        status=target_status,
        severity=ComparisonSeverity.INFO,
        reason=reason,
        action=None,
        prediction_source='final_score/confidence' if predicted_view else None,
    )


def _compare_prediction_match(
    fact: PersistedObservedFact,
    service_predictions: dict[str, str | None],
    economy_predictions: dict[str, bool],
    *,
    matched: bool,
) -> PredictionObservationComparison:
    """Map a prediction_match / prediction_mismatch fact.

    These are user claims: "I checked and the prediction was right" or
    "I checked and the prediction was wrong". We only elevate the claim
    to confirmed/contradicted when we can locate the referenced subject
    in the current prediction — otherwise we keep it observed_only
    (matched=True) or unverified (matched=False) so we don't echo a
    user claim as truth without supporting prediction context.
    """
    subject_type = fact.subject_type
    subject_id = fact.subject_id or fact.service_id or fact.economy or fact.facility_template_id

    predicted_value: Any | None = None
    prediction_source: str | None = None
    if subject_type == ObservedSubjectType.SERVICE.value and subject_id in service_predictions:
        predicted_value = service_predictions[subject_id]
        prediction_source = 'services'
    elif subject_type == ObservedSubjectType.ECONOMY.value and subject_id in economy_predictions:
        predicted_value = economy_predictions[subject_id]
        prediction_source = 'economy_composition/economy_order'

    if predicted_value is None:
        # We can't anchor the claim — keep it visible but conservative.
        target_status = ComparisonStatus.OBSERVED_ONLY if matched else ComparisonStatus.UNVERIFIED
        reason = (
            'User reported a prediction match but the referenced subject is not in the current prediction.'
            if matched
            else 'User reported a prediction mismatch but the referenced subject is not in the current prediction.'
        )
        severity_enum = ComparisonSeverity.INFO
        action: str | None = None
    else:
        if matched:
            target_status = ComparisonStatus.CONFIRMED
            severity_enum = ComparisonSeverity.INFO
            reason = 'User reported a prediction match for a known predicted subject.'
            action = None
        else:
            target_status = ComparisonStatus.CONTRADICTED
            severity_enum = _severity_enum_from_value(
                _contradiction_severity(fact, base=ComparisonSeverity.MEDIUM)
            )
            reason = 'User reported a prediction mismatch for a known predicted subject.'
            action = 'Review prediction rules for the reported subject and the user-provided notes.'

    area = ComparisonArea.SERVICE if subject_type == ObservedSubjectType.SERVICE.value else (
        ComparisonArea.ECONOMY if subject_type == ObservedSubjectType.ECONOMY.value else ComparisonArea.OTHER
    )

    return _make_comparison(
        comparison_id=f'prediction_claim:{fact.observation_id}',
        area=area,
        subject_type=ObservedSubjectType(subject_type) if subject_type in {e.value for e in ObservedSubjectType} else ObservedSubjectType.SYSTEM,
        subject_id=subject_id,
        predicted_value=predicted_value,
        fact=fact,
        status=target_status,
        severity=severity_enum,
        reason=reason,
        action=action,
        prediction_source=prediction_source,
    )


def _observed_only_note(fact: PersistedObservedFact) -> PredictionObservationComparison:
    return PredictionObservationComparison(
        comparison_id=f'note:{fact.observation_id}',
        area=ComparisonArea.NOTE.value,
        subject_type=fact.subject_type or ObservedSubjectType.SYSTEM.value,
        subject_id=fact.subject_id,
        predicted_value=None,
        observed_value=fact.observed_value,
        status=ComparisonStatus.OBSERVED_ONLY.value,
        severity=ComparisonSeverity.INFO.value,
        confidence=_comparison_confidence_for(fact),
        reason='Free-form note — recorded as observed-only context; Stage 6C does not interpret note bodies.',
        recommended_action=None,
        evidence=[_evidence_from_fact(fact)],
        prediction_source=None,
    )


# ──────────────────────────────────────────────────────────────────────
# Severity / confidence helpers
# ──────────────────────────────────────────────────────────────────────
def _contradiction_severity(fact: PersistedObservedFact, *, base: ComparisonSeverity) -> str:
    """Pick a contradiction severity, clamped by observation confidence.

    Rule: a LOW-confidence observation can never produce HIGH-severity
    contradictions. A MEDIUM-confidence observation caps at MEDIUM.
    """
    confidence = fact.confidence or ObservedConfidence.MEDIUM.value
    if confidence == ObservedConfidence.LOW.value:
        return ComparisonSeverity.LOW.value
    if confidence == ObservedConfidence.MEDIUM.value:
        if base == ComparisonSeverity.HIGH:
            return ComparisonSeverity.MEDIUM.value
        return base.value
    # high confidence — honour caller's base
    return base.value


def _comparison_confidence_for(fact: PersistedObservedFact) -> str:
    """Translate observation confidence into comparison confidence."""
    return fact.confidence if fact.confidence in {c.value for c in ObservedConfidence} else ComparisonConfidence.UNKNOWN.value


def _evidence_from_fact(fact: PersistedObservedFact) -> ObservationEvidenceMatch:
    return ObservationEvidenceMatch(
        observation_id=fact.observation_id,
        fact_type=fact.fact_type,
        subject_type=fact.subject_type,
        subject_id=fact.subject_id,
        status=fact.status,
        confidence=fact.confidence,
        observed_value=fact.observed_value,
        expected_value=fact.expected_value,
        notes=fact.notes,
    )


def _severity_enum_from_value(value: str) -> ComparisonSeverity:
    for member in ComparisonSeverity:
        if member.value == value:
            return member
    return ComparisonSeverity.INFO


def _make_comparison(
    *,
    comparison_id: str,
    area: ComparisonArea,
    subject_type: ObservedSubjectType,
    subject_id: str | None,
    predicted_value: Any | None,
    fact: PersistedObservedFact,
    status: ComparisonStatus,
    severity: ComparisonSeverity,
    reason: str,
    action: str | None,
    prediction_source: str | None,
) -> PredictionObservationComparison:
    return PredictionObservationComparison(
        comparison_id=comparison_id,
        area=area.value,
        subject_type=subject_type.value,
        subject_id=subject_id,
        predicted_value=predicted_value,
        observed_value=fact.observed_value,
        status=status.value,
        severity=severity.value,
        confidence=_comparison_confidence_for(fact),
        reason=reason,
        recommended_action=action,
        evidence=[_evidence_from_fact(fact)],
        prediction_source=prediction_source,
    )


# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
def _build_summary(
    *,
    observed_facts_count: int,
    comparisons: list[PredictionObservationComparison],
) -> PredictionObservationComparisonSummary:
    confirmed = sum(1 for c in comparisons if c.status == ComparisonStatus.CONFIRMED.value)
    contradicted = sum(1 for c in comparisons if c.status == ComparisonStatus.CONTRADICTED.value)
    observed_only = sum(1 for c in comparisons if c.status == ComparisonStatus.OBSERVED_ONLY.value)
    predicted_only = sum(1 for c in comparisons if c.status == ComparisonStatus.PREDICTED_ONLY.value)
    unknown = sum(1 for c in comparisons if c.status == ComparisonStatus.UNKNOWN.value)
    unverified = sum(1 for c in comparisons if c.status == ComparisonStatus.UNVERIFIED.value)

    # Overall status
    if observed_facts_count == 0:
        overall = ComparisonOverallStatus.NO_OBSERVATIONS
    elif contradicted > 0 and confirmed > 0:
        overall = ComparisonOverallStatus.MIXED
    elif contradicted > 0:
        overall = ComparisonOverallStatus.NEEDS_REVIEW
    elif confirmed > 0:
        overall = ComparisonOverallStatus.CONFIRMED
    else:
        overall = ComparisonOverallStatus.INSUFFICIENT_EVIDENCE

    # Confidence impact
    if observed_facts_count == 0:
        impact = ComparisonConfidenceImpact.NONE
    elif confirmed > 0 and contradicted == 0:
        impact = ComparisonConfidenceImpact.STRENGTHENED
    elif contradicted > 0 and confirmed == 0:
        impact = ComparisonConfidenceImpact.WEAKENED
    elif confirmed > 0 and contradicted > 0:
        impact = ComparisonConfidenceImpact.MIXED
    else:
        impact = ComparisonConfidenceImpact.INSUFFICIENT_EVIDENCE

    summary_text = _summary_text(
        overall=overall,
        confirmed=confirmed,
        contradicted=contradicted,
        observed_only=observed_only,
        predicted_only=predicted_only,
        unverified=unverified,
    )

    return PredictionObservationComparisonSummary(
        status=overall.value,
        observed_facts_count=observed_facts_count,
        compared_predictions_count=len(comparisons),
        confirmed_count=confirmed,
        contradicted_count=contradicted,
        observed_only_count=observed_only,
        predicted_only_count=predicted_only,
        unknown_count=unknown,
        unverified_count=unverified,
        confidence_impact=impact.value,
        summary=summary_text,
    )


def _summary_text(
    *,
    overall: ComparisonOverallStatus,
    confirmed: int,
    contradicted: int,
    observed_only: int,
    predicted_only: int,
    unverified: int,
) -> str:
    if overall == ComparisonOverallStatus.NO_OBSERVATIONS:
        return 'No observed evidence recorded for this system yet. Comparison shows prediction-only rows.'
    parts: list[str] = []
    if confirmed:
        parts.append(f'{confirmed} confirmed')
    if contradicted:
        parts.append(f'{contradicted} contradicted (review)')
    if observed_only:
        parts.append(f'{observed_only} observed-only')
    if predicted_only:
        parts.append(f'{predicted_only} predicted-only')
    if unverified:
        parts.append(f'{unverified} unverified')
    head = {
        ComparisonOverallStatus.CONFIRMED: 'Observations support the prediction',
        ComparisonOverallStatus.MIXED: 'Observations partially support the prediction — some entries need review',
        ComparisonOverallStatus.NEEDS_REVIEW: 'Observations contradict parts of the prediction — review recommended',
        ComparisonOverallStatus.INSUFFICIENT_EVIDENCE: 'Insufficient evidence to confirm or contradict the prediction',
    }.get(overall, 'Comparison complete')
    if parts:
        return f'{head}: {", ".join(parts)}.'
    return f'{head}.'


__all__ = ['compare_prediction_to_observations']
