from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from r1_finder_compare.types import BodyFact
FactAvailability=Literal['known','unknown','ambiguous','conflicting','not_applicable']
BodyDataCompleteness=Literal['known_present','unknown','conflicting']
@dataclass(frozen=True)
class CanonicalSystemRow:
    id64:str; name:str; has_body_data:bool; body_count:int; updated_at:str|None
@dataclass(frozen=True)
class CanonicalBodyRow:
    id:str; system_id64:str; name:str; body_type:str; subtype:str|None; distance_from_star:float|None; is_tidal_lock:bool|None; radius:float|None; gravity:float|None; surface_temp:float|None; atmosphere_type:str|None; volcanism:str|None; terraforming_state:str|None; is_terraformable:bool; is_landable:bool; bio_signal_count:int; geo_signal_count:int; updated_at:str|None; is_ammonia_world:bool=False
@dataclass(frozen=True)
class CanonicalRingRow:
    body_id:str|None; source_body_id:str|None; body_name:str|None; ring_name:str|None; source:str; confidence:str; association_status:str; updated_at:str|None
@dataclass(frozen=True)
class BodyEvidenceHints:
    body_id:str; landable_negative_confirmed:bool=False; terraformable_negative_confirmed:bool=False; bio_signal_scan_complete:bool=False; geo_signal_scan_complete:bool=False; provenance_ids:tuple[str,...]=()
@dataclass(frozen=True)
class FactStatus:
    availability:FactAvailability; provenance_ids:tuple[str,...]; reason:str
@dataclass(frozen=True)
class ProjectedBodyEvidence:
    body:BodyFact; field_status:tuple[tuple[str,FactStatus],...]; true_ammonia_world:bool|None; raw_bio_signal_count:int; raw_geo_signal_count:int; provenance_ids:tuple[str,...]
    def status(self,name:str)->FactStatus: return dict(self.field_status)[name]
@dataclass(frozen=True)
class ProjectedSystemEvidence:
    system_id64:str; system_name:str; body_data_completeness:BodyDataCompleteness; bodies:tuple[ProjectedBodyEvidence,...]; provenance_ids:tuple[str,...]; projection_revision:str
@dataclass(frozen=True)
class SlotPrediction:
    availability:Literal['known_prediction','unknown']; slots:int|None; model_id:str; model_revision:str; evidence_class:Literal['prediction']; input_status:tuple[tuple[str,FactAvailability],...]; caveats:tuple[str,...]
@dataclass(frozen=True)
class OrbitalCapacityPrediction:
    availability:Literal['known_prediction','unknown']; slots:int|None; model_id:str; model_revision:str; evidence_class:Literal['prediction']; caveats:tuple[str,...]
