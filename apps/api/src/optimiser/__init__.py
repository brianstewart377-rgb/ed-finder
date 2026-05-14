"""Stage 5A optimiser candidate generation package.

This package contains bounded deterministic candidate generation and optional
candidate ranking. It does not compare alternatives for the UI, apply candidates,
or alter simulation mechanics.
"""

from optimiser.candidate_generator import generate_candidates
from optimiser.models import CandidateGenerationRequest, CandidateGenerationResult, CandidateRankingResult
from optimiser.ranker import rank_candidates

__all__ = [
    'CandidateGenerationRequest',
    'CandidateGenerationResult',
    'CandidateRankingResult',
    'generate_candidates',
    'rank_candidates',
]
