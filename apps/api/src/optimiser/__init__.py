"""Stage 5A optimiser candidate generation package.

This package contains bounded deterministic candidate generation only. It does
not rank candidates, compare alternatives for the UI, or alter simulation
mechanics.
"""

from optimiser.candidate_generator import generate_candidates
from optimiser.models import CandidateGenerationRequest, CandidateGenerationResult

__all__ = [
    'CandidateGenerationRequest',
    'CandidateGenerationResult',
    'generate_candidates',
]
