"""Stage 6C — predicted-vs-observed comparison engine + endpoint tests.

This file is NEW for Stage 6C. The legacy ``tests/test_observation_comparison.py``
covers the Stage 4D in-pipeline comparison and MUST NOT be touched.

Coverage:
  * Engine — service confirmed/contradicted/predicted_only/observed_only.
  * Engine — economy same/different.
  * Engine — CP scalar + dict match/mismatch.
  * Engine — unknown/unverified collapses to ``unverified``.
  * Engine — low-confidence observations cap contradiction severity.
  * Engine — notes never contradict (always observed_only/info).
  * Engine — prediction_match/prediction_mismatch elevation rules.
  * Engine — summary status for: no observations, all confirmed, mixed,
    needs_review, insufficient_evidence.
  * Engine — does not mutate prediction or observed_facts inputs.
  * Engine — JSON-safe round-trip via comparison_result_to_dict.
  * Endpoint — Mode A loads facts from store, Mode B uses supplied facts.
  * Endpoint — rejects negative system_id64 and non-object prediction.
  * Endpoint — passivity: no simulation/optimiser imports occur during a
    compare call (asserted via module import inspection at module-load time).
"""
from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deps import get_pool
from observations.comparison_engine import compare_prediction_to_observations
from observations.comparison_models import (
    ComparisonArea,
    ComparisonConfidenceImpact,
    ComparisonOverallStatus,
    ComparisonSeverity,
    ComparisonStatus,
    PredictionObservationComparisonResult,
    comparison_result_to_dict,
)
from observations.models import (
    ObservationSource,
    ObservedConfidence,
    ObservedFactType,
    ObservedStatus,
    ObservedSubjectType,
    PersistedObservedFact,
)
from routers import observations as observations_router


# ──────────────────────────────────────────────────────────────────────
# Fact builders
# ──────────────────────────────────────────────────────────────────────
def _fact(
    *,
    observation_id: str = 'obs_1',
    system_id64: int = 100,
    fact_type: ObservedFactType,
    subject_type: ObservedSubjectType,
    subject_id: str | None,
    status: ObservedStatus,
    observed_value: Any = None,
    expected_value: Any = None,
    confidence: ObservedConfidence = ObservedConfidence.HIGH,
    notes: str | None = None,
    service_id: str | None = None,
    economy: str | None = None,
    facility_template_id: str | None = None,
    target_archetype: str | None = None,
    created_at: str = '2026-05-15T10:00:00+00:00',
) -> PersistedObservedFact:
    return PersistedObservedFact(
        observation_id=observation_id,
        system_id64=system_id64,
        created_at=created_at,
        updated_at=None,
        source=ObservationSource.MANUAL.value,
        fact_type=fact_type.value,
        subject_type=subject_type.value,
        subject_id=subject_id,
        status=status.value,
        observed_value=observed_value,
        expected_value=expected_value,
        confidence=confidence.value,
        notes=notes,
        target_archetype=target_archetype,
        facility_template_id=facility_template_id,
        service_id=service_id,
        economy=economy,
    )


def _result_by_id(result: PredictionObservationComparisonResult, comparison_id: str):
    for c in result.comparisons:
        if c.comparison_id == comparison_id:
            return c
    raise AssertionError(f'comparison_id={comparison_id!r} not found; have {[c.comparison_id for c in result.comparisons]}')


# ──────────────────────────────────────────────────────────────────────
# Engine: service comparisons
# ──────────────────────────────────────────────────────────────────────
def test_service_confirmed_when_active_and_observed_present():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100,
        target_archetype=None,
        prediction=prediction,
        observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:refining')
    assert row.area == ComparisonArea.SERVICE.value
    assert row.status == ComparisonStatus.CONFIRMED.value
    assert row.severity == ComparisonSeverity.INFO.value
    assert len(row.evidence) == 1
    assert row.evidence[0].observation_id == 'obs_1'


def test_service_contradicted_when_active_but_observed_absent():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.OBSERVED_ABSENT,
        confidence=ObservedConfidence.HIGH,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:refining')
    assert row.status == ComparisonStatus.CONTRADICTED.value
    # High-confidence observation + base HIGH for active-but-absent => HIGH.
    assert row.severity == ComparisonSeverity.HIGH.value
    assert row.recommended_action is not None


def test_service_predicted_only_when_no_observation():
    prediction = {'services': {'shipyard': {'status': 'active'}}}
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[],
    )
    row = _result_by_id(result, 'service:shipyard')
    assert row.status == ComparisonStatus.PREDICTED_ONLY.value
    assert row.evidence == []
    assert row.observed_value is None


def test_service_observed_only_when_not_in_prediction():
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='tourism',
        service_id='tourism',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={'services': {}}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:tourism')
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value
    assert row.predicted_value is None


def test_service_unknown_observation_collapses_to_unverified():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.UNKNOWN,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:refining')
    assert row.status == ComparisonStatus.UNVERIFIED.value
    assert row.severity == ComparisonSeverity.INFO.value


def test_service_port_state_active_bucket_is_picked_up():
    prediction = {
        'services': {},
        'port_service_states': [
            {'active_services': {'market': {}}, 'locked_services': {}, 'unknown_services': {}},
        ],
    }
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='market',
        service_id='market',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:market')
    assert row.status == ComparisonStatus.CONFIRMED.value


def test_service_low_confidence_caps_contradiction_severity():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.OBSERVED_ABSENT,
        confidence=ObservedConfidence.LOW,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:refining')
    assert row.status == ComparisonStatus.CONTRADICTED.value
    # LOW confidence MUST clamp severity to LOW even though base was HIGH.
    assert row.severity == ComparisonSeverity.LOW.value


def test_service_medium_confidence_clamps_high_base_to_medium():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.OBSERVED_ABSENT,
        confidence=ObservedConfidence.MEDIUM,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'service:refining')
    assert row.status == ComparisonStatus.CONTRADICTED.value
    assert row.severity == ComparisonSeverity.MEDIUM.value


# ──────────────────────────────────────────────────────────────────────
# Engine: economy comparisons
# ──────────────────────────────────────────────────────────────────────
def test_economy_confirmed_when_predicted_and_observed_present():
    prediction = {'economy_composition': {'extraction': 0.7}, 'economy_order': ['extraction']}
    fact = _fact(
        fact_type=ObservedFactType.ECONOMY_PRESENCE,
        subject_type=ObservedSubjectType.ECONOMY,
        subject_id='extraction',
        economy='extraction',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'economy:extraction')
    assert row.status == ComparisonStatus.CONFIRMED.value
    assert row.predicted_value is True


def test_economy_contradicted_when_predicted_but_observed_absent():
    prediction = {'economy_composition': {'tourism': 0.5}}
    fact = _fact(
        fact_type=ObservedFactType.ECONOMY_PRESENCE,
        subject_type=ObservedSubjectType.ECONOMY,
        subject_id='tourism',
        economy='tourism',
        status=ObservedStatus.OBSERVED_ABSENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'economy:tourism')
    assert row.status == ComparisonStatus.CONTRADICTED.value


def test_economy_observed_only_when_not_in_prediction():
    fact = _fact(
        fact_type=ObservedFactType.ECONOMY_PRESENCE,
        subject_type=ObservedSubjectType.ECONOMY,
        subject_id='hightech',
        economy='hightech',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={'economy_composition': {}}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'economy:hightech')
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


def test_economy_zero_weight_is_not_predicted_present():
    """A composition weight of 0 should NOT count as predicted-present."""
    prediction = {'economy_composition': {'tourism': 0.0}}
    fact = _fact(
        fact_type=ObservedFactType.ECONOMY_PRESENCE,
        subject_type=ObservedSubjectType.ECONOMY,
        subject_id='tourism',
        economy='tourism',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'economy:tourism')
    # The economy with weight=0 is not in the prediction's predicted-present
    # set, so the observed fact becomes observed_only.
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


# ──────────────────────────────────────────────────────────────────────
# Engine: CP comparisons
# ──────────────────────────────────────────────────────────────────────
def test_cp_scalar_matches_yellow_cp_final():
    prediction = {'cp': {'yellow_cp_final': 12, 'green_cp_final': 4}}
    fact = _fact(
        fact_type=ObservedFactType.CP_VALUE,
        subject_type=ObservedSubjectType.CP,
        subject_id='yellow',
        status=ObservedStatus.OBSERVED_PRESENT,
        observed_value=12,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'cp:yellow')
    assert row.status == ComparisonStatus.CONFIRMED.value


def test_cp_scalar_mismatch_contradicted():
    prediction = {'cp': {'yellow_cp_final': 12}}
    fact = _fact(
        fact_type=ObservedFactType.CP_VALUE,
        subject_type=ObservedSubjectType.CP,
        subject_id='yellow',
        status=ObservedStatus.OBSERVED_PRESENT,
        observed_value=8,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'cp:yellow')
    assert row.status == ComparisonStatus.CONTRADICTED.value
    assert row.recommended_action is not None


def test_cp_dict_overlapping_keys_confirmed():
    prediction = {'cp': {'yellow_cp_final': 12, 'green_cp_final': 4}}
    fact = _fact(
        fact_type=ObservedFactType.CP_VALUE,
        subject_type=ObservedSubjectType.CP,
        subject_id='final',
        status=ObservedStatus.OBSERVED_PRESENT,
        observed_value={'yellow_cp_final': 12, 'green_cp_final': 4},
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'cp:final')
    assert row.status == ComparisonStatus.CONFIRMED.value


def test_cp_dict_partial_mismatch_contradicted():
    prediction = {'cp': {'yellow_cp_final': 12, 'green_cp_final': 4}}
    fact = _fact(
        fact_type=ObservedFactType.CP_VALUE,
        subject_type=ObservedSubjectType.CP,
        subject_id='final',
        status=ObservedStatus.OBSERVED_PRESENT,
        observed_value={'yellow_cp_final': 12, 'green_cp_final': 7},
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    row = _result_by_id(result, 'cp:final')
    assert row.status == ComparisonStatus.CONTRADICTED.value


def test_cp_observation_unverified_when_prediction_has_no_cp_block():
    fact = _fact(
        fact_type=ObservedFactType.CP_VALUE,
        subject_type=ObservedSubjectType.CP,
        subject_id='yellow',
        status=ObservedStatus.OBSERVED_PRESENT,
        observed_value=10,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'cp:yellow')
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


# ──────────────────────────────────────────────────────────────────────
# Engine: notes, facility, build outcome, prediction_match
# ──────────────────────────────────────────────────────────────────────
def test_note_is_always_observed_only_info():
    fact = _fact(
        observation_id='obs_note',
        fact_type=ObservedFactType.NOTE,
        subject_type=ObservedSubjectType.SYSTEM,
        subject_id=None,
        status=ObservedStatus.OBSERVED_PRESENT,
        notes='Free-form note',
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={'services': {'refining': {'status': 'active'}}}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'note:obs_note')
    assert row.area == ComparisonArea.NOTE.value
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value
    assert row.severity == ComparisonSeverity.INFO.value


def test_facility_state_is_observed_only_in_stage_6c():
    fact = _fact(
        observation_id='obs_fac',
        fact_type=ObservedFactType.FACILITY_STATE,
        subject_type=ObservedSubjectType.FACILITY,
        subject_id='installation_x',
        facility_template_id='installation_x',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'facility:installation_x')
    assert row.area == ComparisonArea.FACILITY.value
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


def test_prediction_mismatch_elevates_only_when_subject_in_prediction():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact_known = _fact(
        observation_id='obs_known',
        fact_type=ObservedFactType.PREDICTION_MISMATCH,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.CONTRADICTED,
    )
    fact_unknown = _fact(
        observation_id='obs_unknown',
        fact_type=ObservedFactType.PREDICTION_MISMATCH,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='ghost_service',
        service_id='ghost_service',
        status=ObservedStatus.CONTRADICTED,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact_known, fact_unknown],
    )
    row_known = _result_by_id(result, 'prediction_claim:obs_known')
    row_unknown = _result_by_id(result, 'prediction_claim:obs_unknown')
    assert row_known.status == ComparisonStatus.CONTRADICTED.value
    # Unknown subject — conservative, do NOT echo a contradiction claim.
    assert row_unknown.status == ComparisonStatus.UNVERIFIED.value


def test_prediction_match_observed_only_when_subject_not_in_prediction():
    fact = _fact(
        observation_id='obs_pm',
        fact_type=ObservedFactType.PREDICTION_MATCH,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='not_in_prediction',
        service_id='not_in_prediction',
        status=ObservedStatus.CONFIRMED,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'prediction_claim:obs_pm')
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


def test_build_outcome_observation_only_unless_user_marked_confirmed_or_contradicted():
    fact = _fact(
        observation_id='obs_build',
        fact_type=ObservedFactType.BUILD_OUTCOME,
        subject_type=ObservedSubjectType.BUILD,
        subject_id='build_1',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={'final_score': 80}, observed_facts=[fact],
    )
    row = _result_by_id(result, 'build_outcome:obs_build')
    assert row.area == ComparisonArea.BUILD_OUTCOME.value
    assert row.status == ComparisonStatus.OBSERVED_ONLY.value


# ──────────────────────────────────────────────────────────────────────
# Engine: summary status / confidence_impact
# ──────────────────────────────────────────────────────────────────────
def test_summary_no_observations_status():
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={'services': {'refining': {'status': 'active'}}},
        observed_facts=[],
    )
    assert result.summary.status == ComparisonOverallStatus.NO_OBSERVATIONS.value
    assert result.summary.confidence_impact == ComparisonConfidenceImpact.NONE.value
    assert result.summary.observed_facts_count == 0


def test_summary_confirmed_strengthens_when_all_confirmed():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining',
        service_id='refining',
        status=ObservedStatus.OBSERVED_PRESENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    assert result.summary.status == ComparisonOverallStatus.CONFIRMED.value
    assert result.summary.confidence_impact == ComparisonConfidenceImpact.STRENGTHENED.value


def test_summary_mixed_when_some_confirmed_and_some_contradicted():
    prediction = {
        'services': {
            'refining': {'status': 'active'},
            'shipyard': {'status': 'active'},
        },
    }
    facts = [
        _fact(observation_id='ok',
              fact_type=ObservedFactType.SERVICE_PRESENCE,
              subject_type=ObservedSubjectType.SERVICE,
              subject_id='refining', service_id='refining',
              status=ObservedStatus.OBSERVED_PRESENT),
        _fact(observation_id='bad',
              fact_type=ObservedFactType.SERVICE_PRESENCE,
              subject_type=ObservedSubjectType.SERVICE,
              subject_id='shipyard', service_id='shipyard',
              status=ObservedStatus.OBSERVED_ABSENT),
    ]
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=facts,
    )
    assert result.summary.status == ComparisonOverallStatus.MIXED.value
    assert result.summary.confidence_impact == ComparisonConfidenceImpact.MIXED.value


def test_summary_needs_review_when_only_contradictions():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining', service_id='refining',
        status=ObservedStatus.OBSERVED_ABSENT,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    assert result.summary.status == ComparisonOverallStatus.NEEDS_REVIEW.value
    assert result.summary.confidence_impact == ComparisonConfidenceImpact.WEAKENED.value


def test_summary_insufficient_evidence_when_only_unverified():
    prediction = {'services': {'refining': {'status': 'active'}}}
    fact = _fact(
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining', service_id='refining',
        status=ObservedStatus.UNKNOWN,
    )
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=[fact],
    )
    assert result.summary.status == ComparisonOverallStatus.INSUFFICIENT_EVIDENCE.value
    assert result.summary.confidence_impact == ComparisonConfidenceImpact.INSUFFICIENT_EVIDENCE.value


# ──────────────────────────────────────────────────────────────────────
# Engine: purity / passivity guarantees
# ──────────────────────────────────────────────────────────────────────
def test_engine_does_not_mutate_inputs():
    prediction = {
        'services': {'refining': {'status': 'active'}},
        'economy_composition': {'extraction': 0.7},
        'cp': {'yellow_cp_final': 5},
    }
    facts = [
        _fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='refining', service_id='refining',
            status=ObservedStatus.OBSERVED_PRESENT,
        ),
    ]
    prediction_snapshot = copy.deepcopy(prediction)
    facts_snapshot = copy.deepcopy(facts)
    compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=facts,
    )
    assert prediction == prediction_snapshot, 'engine mutated the prediction input'
    assert facts == facts_snapshot, 'engine mutated the observed_facts input'


def test_result_round_trips_through_json():
    prediction = {'services': {'refining': {'status': 'active'}}}
    facts = [
        _fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='refining', service_id='refining',
            status=ObservedStatus.OBSERVED_PRESENT,
        ),
    ]
    result = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction=prediction, observed_facts=facts,
    )
    payload = comparison_result_to_dict(result)
    # Must serialise without errors and recover the same top-level shape.
    blob = json.dumps(payload)
    reloaded = json.loads(blob)
    assert reloaded['system_id64'] == 100
    assert reloaded['summary']['status'] == ComparisonOverallStatus.CONFIRMED.value
    assert reloaded['comparisons'][0]['comparison_id'] == 'service:refining'


def test_engine_is_deterministic_with_injected_now():
    pinned = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    result1 = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={}, observed_facts=[], now=lambda: pinned,
    )
    result2 = compare_prediction_to_observations(
        system_id64=100, target_archetype=None,
        prediction={}, observed_facts=[], now=lambda: pinned,
    )
    assert result1.generated_at == result2.generated_at == pinned.isoformat()


# ──────────────────────────────────────────────────────────────────────
# Endpoint: Mode A (load from store) + Mode B (use supplied facts)
# ──────────────────────────────────────────────────────────────────────
class _FakeStore:
    """Minimal store double for the Stage 6C compare endpoint.

    Mirrors the contract used by the endpoint: ``list_observed_facts``
    must return ``(facts, total)``. We deliberately keep it smaller than
    the Stage 6A ``FakeObservedFactStore`` because the compare endpoint
    only calls ``list_observed_facts``.
    """

    def __init__(self) -> None:
        self.items: list[PersistedObservedFact] = []
        self.calls: list[dict[str, Any]] = []

    async def list_observed_facts(self, _pool: object, **filters: Any) -> tuple[list[PersistedObservedFact], int]:
        self.calls.append(filters)
        sysid = filters['system_id64']
        target = filters.get('target_archetype')
        out = [f for f in self.items if f.system_id64 == sysid]
        if target is not None:
            out = [f for f in out if f.target_archetype == target]
        return out, len(out)


@pytest.fixture
def fake_store(monkeypatch) -> _FakeStore:
    store = _FakeStore()
    monkeypatch.setattr(observations_router.store, 'list_observed_facts', store.list_observed_facts)
    return store


@pytest.fixture
def app(fake_store: _FakeStore) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(observations_router.router)
    test_app.dependency_overrides[get_pool] = lambda: object()
    return test_app


@pytest.mark.asyncio
async def test_compare_endpoint_mode_a_loads_facts_from_store(app: FastAPI, fake_store: _FakeStore):
    fake_store.items.append(_fact(
        observation_id='endpoint_a',
        fact_type=ObservedFactType.SERVICE_PRESENCE,
        subject_type=ObservedSubjectType.SERVICE,
        subject_id='refining', service_id='refining',
        status=ObservedStatus.OBSERVED_PRESENT,
    ))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': {'services': {'refining': {'status': 'active'}}},
        })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['summary']['status'] == ComparisonOverallStatus.CONFIRMED.value
    assert payload['comparisons'][0]['status'] == ComparisonStatus.CONFIRMED.value
    # Mode A: the store WAS called.
    assert len(fake_store.calls) == 1
    assert fake_store.calls[0]['system_id64'] == 100


@pytest.mark.asyncio
async def test_compare_endpoint_mode_b_uses_supplied_facts_and_skips_store(app: FastAPI, fake_store: _FakeStore):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': {'services': {'refining': {'status': 'active'}}},
            'observed_facts': [
                {
                    'observation_id': 'manual_1',
                    'system_id64': 100,
                    'created_at': '2026-05-15T10:00:00+00:00',
                    'source': 'manual',
                    'fact_type': 'service_presence',
                    'subject_type': 'service',
                    'subject_id': 'refining',
                    'service_id': 'refining',
                    'status': 'observed_present',
                    'confidence': 'high',
                },
            ],
        })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['summary']['status'] == ComparisonOverallStatus.CONFIRMED.value
    # Mode B: the store was NOT called.
    assert fake_store.calls == []


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_zero_system_id64(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 0,
            'prediction': {},
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_negative_system_id64(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': -7,
            'prediction': {},
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_non_object_prediction(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        # prediction as a list — must be rejected at validation time.
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': ['not', 'an', 'object'],
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_string_prediction(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': 'oops',
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_endpoint_returns_no_observations_summary_when_store_empty(app: FastAPI, fake_store: _FakeStore):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': {'services': {'refining': {'status': 'active'}}},
        })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['summary']['status'] == ComparisonOverallStatus.NO_OBSERVATIONS.value
    assert payload['summary']['confidence_impact'] == ComparisonConfidenceImpact.NONE.value
    # We should still see the prediction-only row for refining.
    statuses = {c['status'] for c in payload['comparisons']}
    assert ComparisonStatus.PREDICTED_ONLY.value in statuses


@pytest.mark.asyncio
async def test_compare_endpoint_does_not_import_simulation_or_optimiser_modules(app: FastAPI, fake_store: _FakeStore):
    """Passivity guard: running a compare call must not pull simulation/
    optimiser/ranking modules into ``sys.modules`` if they aren't there.

    This is a *dynamic* check — Stage 6C's static passivity test
    (separate file) scans imports in source. Here we observe runtime
    behaviour: any sim/optimiser module loaded *after* the call must
    have been loaded before it (i.e. not triggered by the compare).
    """
    before = {name for name in sys.modules if name.startswith(('simulation', 'optimiser'))}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/compare', json={
            'system_id64': 100,
            'prediction': {'services': {'refining': {'status': 'active'}}},
        })
    assert response.status_code == 200, response.text
    after = {name for name in sys.modules if name.startswith(('simulation', 'optimiser'))}
    newly_loaded = after - before
    assert newly_loaded == set(), (
        f'Stage 6C compare call must not import simulation/optimiser modules; '
        f'newly loaded: {sorted(newly_loaded)}'
    )
