"""Internal models for Stage 5A optimiser candidate generation.

These dataclasses are intentionally separate from the public Pydantic API
models in ``models.py``. They define the generator's clean internal contract and
can be serialized into the public response shape without importing FastAPI or
router code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from simulation.build_preview import PreviewPlacement


@dataclass(frozen=True)
class CandidatePlacement:
    facility_template_id: str
    local_body_id: Optional[str] = None
    is_primary_port: bool = False
    build_order: int = 1


@dataclass(frozen=True)
class CandidatePreviewSummary:
    final_score: Optional[float] = None
    composition_score: Optional[float] = None
    buildability_score: Optional[float] = None
    confidence: Optional[float] = None
    build_complexity: Optional[str] = None
    warnings_count: int = 0
    cp_negative: Optional[bool] = None
    top_two_alignment: Optional[str] = None


@dataclass(frozen=True)
class OptimiserCandidate:
    candidate_id: str
    label: str
    target_archetype: str
    strategy: str
    placements: list[CandidatePlacement]
    rationale: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    preview_summary: Optional[CandidatePreviewSummary] = None


@dataclass(frozen=True)
class CandidateGenerationRequest:
    system_id64: int
    target_archetype: str
    max_candidates: int = 5
    preferred_body_ids: list[str] = field(default_factory=list)
    allow_estimated_data: bool = True
    run_preview: bool = True


@dataclass(frozen=True)
class CandidateGenerationResult:
    system_id64: int
    target_archetype: str
    candidate_count: int
    candidates: list[OptimiserCandidate]
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def candidate_placement_to_preview_placement(placement: CandidatePlacement) -> PreviewPlacement:
    return PreviewPlacement(
        facility_template_id=placement.facility_template_id,
        local_body_id=placement.local_body_id,
        is_primary_port=placement.is_primary_port,
        build_order=placement.build_order,
    )


def candidate_placement_to_dict(placement: CandidatePlacement) -> dict[str, Any]:
    return {
        'facility_template_id': placement.facility_template_id,
        'local_body_id': placement.local_body_id,
        'is_primary_port': placement.is_primary_port,
        'build_order': placement.build_order,
    }


def preview_summary_to_dict(summary: Optional[CandidatePreviewSummary]) -> Optional[dict[str, Any]]:
    if summary is None:
        return None
    return {
        'final_score': summary.final_score,
        'composition_score': summary.composition_score,
        'buildability_score': summary.buildability_score,
        'confidence': summary.confidence,
        'build_complexity': summary.build_complexity,
        'warnings_count': summary.warnings_count,
        'cp_negative': summary.cp_negative,
        'top_two_alignment': summary.top_two_alignment,
    }


def candidate_to_dict(candidate: OptimiserCandidate) -> dict[str, Any]:
    return {
        'candidate_id': candidate.candidate_id,
        'label': candidate.label,
        'target_archetype': candidate.target_archetype,
        'strategy': candidate.strategy,
        'placements': [candidate_placement_to_dict(p) for p in candidate.placements],
        'rationale': list(candidate.rationale),
        'warnings': list(candidate.warnings),
        'assumptions': list(candidate.assumptions),
        'tags': list(candidate.tags),
        'preview_summary': preview_summary_to_dict(candidate.preview_summary),
    }


def candidate_result_to_dict(result: CandidateGenerationResult) -> dict[str, Any]:
    return {
        'system_id64': result.system_id64,
        'target_archetype': result.target_archetype,
        'candidate_count': result.candidate_count,
        'candidates': [candidate_to_dict(candidate) for candidate in result.candidates],
        'warnings': list(result.warnings),
        'assumptions': list(result.assumptions),
    }
