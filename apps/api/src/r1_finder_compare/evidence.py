from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from math import prod
from typing import Mapping

from .types import BodyFact, CandidateEvidence

HMC = 'High metal content world'
METAL_RICH = 'Metal-rich body'
ROCKY = 'Rocky body'


def _normalise(value):
    if isinstance(value, dict):
        return {k: _normalise(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(_normalise(value), sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def sha256_id(value) -> str:
    return 'sha256:' + hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def evidence_snapshot_id(candidate: CandidateEvidence) -> str:
    payload = {
        'fixture_id': candidate.fixture_id,
        'fixture_revision': candidate.fixture_revision,
        'bodies': [asdict(b) for b in sorted(candidate.bodies, key=lambda b: b.body_id)],
        'physical_capacity': asdict(candidate.physical_capacity),
        'extraction_evidence': asdict(candidate.extraction_evidence),
        'refinery_evidence': asdict(candidate.refinery_evidence),
        'pair_stability': candidate.pair_stability,
        'logistics_no_carrier': candidate.logistics_no_carrier,
        'logistics_carrier': candidate.logistics_carrier,
        'evidence_disposition': candidate.evidence_disposition,
        'ambiguity_flags': sorted(candidate.ambiguity_flags),
        'conflict_flags': sorted(candidate.conflict_flags),
        'provenance_ids': sorted(candidate.provenance_ids),
    }
    return sha256_id(payload)


def body_is_hmc(body: BodyFact) -> bool:
    return body.base_identity == HMC


def body_is_metal_rich(body: BodyFact) -> bool:
    return body.base_identity == METAL_RICH


def extraction_source_units(
    bodies: tuple[BodyFact, ...],
    geological_signal_counts: Mapping[str, int] | None = None,
) -> float:
    """Return bounded fixture support units from composable Extraction sources.

    Raw geological signal counts are reduced to a per-body presence predicate.
    Ten signals on one body therefore do not become ten modifier credits.
    """
    counts = geological_signal_counts or {}
    units = 0.0
    for body in bodies:
        if body_is_hmc(body):
            units += 1.0
        elif body_is_metal_rich(body):
            units += 1.0
        if body.has_rings is True:
            units += 0.35
        geo_present = body.has_geologicals is True or counts.get(body.body_id, 0) > 0
        if geo_present:
            units += 0.35
    return round(units, 6)


def bounded_geometric(dimensions: tuple[tuple[str, float], ...]) -> int:
    if not dimensions:
        raise ValueError('at least one dimension is required')
    values = []
    for _, raw in dimensions:
        if raw < 0 or raw > 1:
            raise ValueError('fit dimensions must be within 0..1')
        values.append(raw)
    return round(100 * prod(values) ** (1 / len(values)))
