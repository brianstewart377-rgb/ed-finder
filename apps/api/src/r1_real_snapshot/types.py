from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from r1_evidence_bridge.types import CanonicalBodyRow,CanonicalRingRow,CanonicalSystemRow,ProjectedSystemEvidence
from r1_finder_compare.types import CandidateEvidence
SelectorKind=Literal['id64','name']
@dataclass(frozen=True)
class SnapshotSelector:
    kind:SelectorKind; value:str
@dataclass(frozen=True)
class SnapshotBundle:
    system:CanonicalSystemRow; bodies:tuple[CanonicalBodyRow,...]; rings:tuple[CanonicalRingRow,...]; projected_system:ProjectedSystemEvidence; candidate:CandidateEvidence; snapshot_digest:str
@dataclass(frozen=True)
class SnapshotReport:
    system_id64:str; system_name:str; body_data_completeness:str; declared_body_count:int; supplied_body_count:int; availability_counts:tuple[tuple[str,int],...]; surface_slots_known:int; surface_slots_unknown:int; gas_giant_orbital_predictions:tuple[tuple[str,int],...]; extraction_satisfied:bool|None; extraction_disposition:str; refinery_satisfied:bool|None; refinery_disposition:str; snapshot_digest:str; caveats:tuple[str,...]
