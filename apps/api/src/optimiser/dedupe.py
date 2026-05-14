"""Placement fingerprinting and candidate deduplication for Stage 5A."""
from __future__ import annotations

from optimiser.models import CandidatePlacement, OptimiserCandidate


def placement_fingerprint(placements: list[CandidatePlacement]) -> tuple[tuple[str, str | None, bool, int], ...]:
    """Return a deterministic fingerprint for a complete placement plan."""
    return tuple(
        (placement.facility_template_id, placement.local_body_id, placement.is_primary_port, placement.build_order)
        for placement in sorted(placements, key=lambda p: (p.build_order, p.facility_template_id, p.local_body_id or ''))
    )


def dedupe_candidates(candidates: list[OptimiserCandidate]) -> list[OptimiserCandidate]:
    seen: set[tuple[tuple[str, str | None, bool, int], ...]] = set()
    result: list[OptimiserCandidate] = []
    for candidate in candidates:
        fingerprint = placement_fingerprint(candidate.placements)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(candidate)
    return result
