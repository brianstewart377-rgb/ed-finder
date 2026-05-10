"""
ED Finder — Ingest: Slot Prediction Engine
============================================
Predicts orbital and surface slot counts per body from scan facts.

Design rules:
  • Pure functions — no DB, no asyncio.
  • Every prediction carries confidence + reasons (explainability).
  • Predictions are ESTIMATES. ED does not expose slot counts via any API.
    All values are derived from observed colonisation behaviour.
  • Versionable: PREDICTION_VERSION bumped when logic changes.

Slot count heuristics (community-derived, confidence: observed):
  Surface slots:
    • Radius-based primary driver (larger body → more slots)
    • Landable required for any surface slots
    • High-metal / rocky bodies favour more slots
    • Terraformable gets a bonus

  Orbital slots:
    • Presence of body in system = 1 base orbital slot
    • Ringed body = +1 bonus orbital slot (ring anchor)
    • Large gas giants = +1 bonus (multiple orbital insertion points)
    • Binary pairs may share orbital budget — penalised slightly

IMPORTANT:
  These heuristics are derived from limited community observations.
  Real slot counts are only visible in-game when placing facilities.
  Treat all predictions as guidance, not authoritative values.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger('ed_finder')

PREDICTION_VERSION = '1.0.0'

# Radius thresholds for surface slot estimation (in km, converted from metres)
# Source: community colonisation spreadsheets — confidence: observed
_RADIUS_SURFACE_TIERS = [
    (8_000_000,  5),   # >8000 km → 5 surface slots
    (6_000_000,  4),   # >6000 km → 4 surface slots
    (4_000_000,  3),   # >4000 km → 3 surface slots
    (2_500_000,  2),   # >2500 km → 2 surface slots
    (1_000_000,  1),   # >1000 km → 1 surface slot
    (0,          0),   # tiny / very small → 0 surface slots
]

# Planet class bonuses/overrides for surface slots
_CLASS_SURFACE_MODIFIERS: dict[str, int] = {
    'High metal content body':     +1,
    'Metal rich body':             +1,
    'Rocky body':                   0,
    'Rocky ice body':              -1,
    'Icy body':                    -1,
    'Water world':                 +1,
    'Ammonia world':                0,
    'Earth-like world':            +2,   # ELWs are always prime real estate
    'Gas giant with water based life':  0,
    'Class I gas giant':            0,
    'Class II gas giant':           0,
    'Class III gas giant':          0,
    'Class IV gas giant':           0,
    'Class V gas giant':            0,
    'Helium rich gas giant':        0,
    'Helium gas giant':             0,
}

# Planet classes that cannot have surface slots (not landable)
_NON_LANDABLE_CLASSES = {
    'Class I gas giant', 'Class II gas giant', 'Class III gas giant',
    'Class IV gas giant', 'Class V gas giant', 'Helium rich gas giant',
    'Helium gas giant', 'Gas giant with water based life',
    'Gas giant with ammonia based life',
    'Sudarsky class I gas giant', 'Sudarsky class II gas giant',
    'Sudarsky class III gas giant', 'Sudarsky class IV gas giant',
    'Sudarsky class V gas giant',
}

_GAS_GIANT_CLASSES = _NON_LANDABLE_CLASSES


@dataclass
class SlotPrediction:
    """
    Slot prediction result for a single body.

    surface_slots:  estimated buildable surface slots
    orbital_slots:  estimated orbital slots this body contributes
    confidence:     0.0–1.0 prediction confidence
    slot_source:    'journal', 'predicted', 'estimated'
    reasons:        explainability chain
    """
    system_address:  int
    body_id:         int
    surface_slots:   int
    orbital_slots:   int
    confidence:      float
    slot_source:     str
    reasons:         list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'system_address':          self.system_address,
            'body_id':                 self.body_id,
            'estimated_surface_slots': self.surface_slots,
            'estimated_orbital_slots': self.orbital_slots,
            'slot_confidence':         round(self.confidence, 3),
            'slot_source':             self.slot_source,
            'reasons':                 self.reasons,
            'prediction_version':      PREDICTION_VERSION,
        }


def predict_body_slots(scan_fact: dict) -> SlotPrediction:
    """
    Predict surface and orbital slot counts for a single body
    from its body_scan_facts row.

    This is the primary prediction function. All other functions
    in this module are helpers called from here.
    """
    system_address = scan_fact['system_address']
    body_id        = scan_fact['body_id']
    planet_class   = (scan_fact.get('planet_class') or '').strip()
    radius         = scan_fact.get('radius')            # metres
    is_landable    = scan_fact.get('is_landable', False)
    is_terraformable = scan_fact.get('is_terraformable', False)
    is_ringed      = scan_fact.get('is_ringed', False)
    terraform_state = (scan_fact.get('terraform_state') or '').strip()
    data_sources   = scan_fact.get('data_sources', [])
    input_confidence = float(scan_fact.get('confidence', 0.4))

    reasons: list[dict] = []

    # ── Gas giants: no surface slots, 1-2 orbital slots ──────────────────
    is_gas_giant = planet_class in _GAS_GIANT_CLASSES
    if is_gas_giant:
        orbital = 1
        reasons.append({
            'factor': 'planet_class',
            'value':  planet_class,
            'contribution': '+1 orbital (gas giant)',
        })
        if is_ringed:
            orbital += 1
            reasons.append({
                'factor': 'ringed',
                'value':  True,
                'contribution': '+1 orbital (ringed body — orbital anchor)',
            })
        return SlotPrediction(
            system_address=system_address,
            body_id=body_id,
            surface_slots=0,
            orbital_slots=orbital,
            confidence=min(input_confidence, 0.80),
            slot_source=_source_from_data(data_sources),
            reasons=reasons,
        )

    # ── Non-landable rocky/icy bodies: orbital only ───────────────────────
    if not is_landable and planet_class not in ('', None):
        orbital = 1
        reasons.append({
            'factor': 'is_landable',
            'value':  False,
            'contribution': '0 surface slots (not landable), +1 orbital',
        })
        if is_ringed:
            orbital += 1
            reasons.append({
                'factor': 'ringed',
                'value':  True,
                'contribution': '+1 orbital (ring anchor)',
            })
        return SlotPrediction(
            system_address=system_address,
            body_id=body_id,
            surface_slots=0,
            orbital_slots=orbital,
            confidence=min(input_confidence, 0.75),
            slot_source=_source_from_data(data_sources),
            reasons=reasons,
        )

    # ── Landable bodies: radius-based surface slots ───────────────────────
    surface_slots = 0
    if radius is not None:
        for threshold, slots in _RADIUS_SURFACE_TIERS:
            if radius >= threshold:
                surface_slots = slots
                reasons.append({
                    'factor':       'radius',
                    'value':        round(radius / 1000, 1),
                    'unit':         'km',
                    'contribution': f'+{slots} surface slots (radius tier)',
                })
                break
    else:
        # No radius data — very low confidence estimate
        surface_slots = 1
        reasons.append({
            'factor':       'radius',
            'value':        None,
            'contribution': '+1 surface (no radius data — minimum estimate)',
        })

    # Planet class modifier
    class_mod = _CLASS_SURFACE_MODIFIERS.get(planet_class, 0)
    if class_mod != 0:
        surface_slots = max(0, surface_slots + class_mod)
        reasons.append({
            'factor':       'planet_class',
            'value':        planet_class,
            'contribution': f'{class_mod:+d} surface (class modifier)',
        })

    # Terraformable bonus
    if is_terraformable or terraform_state == 'Terraformable':
        surface_slots += 1
        reasons.append({
            'factor':       'terraformable',
            'value':        True,
            'contribution': '+1 surface (terraformable bonus)',
        })

    # Orbital slots for landable body: body itself + ring bonus
    orbital_slots = 1
    reasons.append({
        'factor':       'body_present',
        'value':        True,
        'contribution': '+1 orbital (body in system)',
    })
    if is_ringed:
        orbital_slots += 1
        reasons.append({
            'factor':       'ringed',
            'value':        True,
            'contribution': '+1 orbital (ring anchor point)',
        })

    # Confidence: journal scan data is higher confidence than estimates
    confidence = _calculate_confidence(input_confidence, radius, planet_class)

    return SlotPrediction(
        system_address=system_address,
        body_id=body_id,
        surface_slots=max(0, surface_slots),
        orbital_slots=max(0, orbital_slots),
        confidence=confidence,
        slot_source=_source_from_data(data_sources),
        reasons=reasons,
    )


def predict_system_slots(scan_facts: list[dict]) -> dict:
    """
    Aggregate slot predictions across all bodies in a system.

    Returns a dict suitable for upserting into buildability_analysis:
      {
        estimated_orbital_slots: int,
        estimated_ground_slots:  int,
        slot_confidence:         float,
        body_predictions:        list[SlotPrediction],
      }
    """
    if not scan_facts:
        return {
            'estimated_orbital_slots': 0,
            'estimated_ground_slots':  0,
            'slot_confidence':         0.0,
            'body_predictions':        [],
        }

    predictions = [predict_body_slots(f) for f in scan_facts]

    total_orbital  = sum(p.orbital_slots  for p in predictions)
    total_surface  = sum(p.surface_slots  for p in predictions)

    # System confidence = mean of body confidences, weighted by slot count
    total_slots = total_orbital + total_surface
    if total_slots > 0:
        weighted_conf = sum(
            p.confidence * (p.orbital_slots + p.surface_slots)
            for p in predictions
        ) / total_slots
    else:
        weighted_conf = 0.0

    return {
        'estimated_orbital_slots': total_orbital,
        'estimated_ground_slots':  total_surface,
        'slot_confidence':         round(weighted_conf, 3),
        'body_predictions':        predictions,
    }


def confidence_label(confidence: float) -> str:
    """Human-readable confidence label for UI display."""
    if confidence >= 0.90:
        return 'High'
    if confidence >= 0.70:
        return 'Moderate'
    if confidence >= 0.50:
        return 'Low'
    return 'Estimated'


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _source_from_data(data_sources: list[str]) -> str:
    """Map data sources to a slot_source label."""
    if 'eddn_saasignals' in data_sources:
        return 'journal'
    if 'eddn_scan' in data_sources:
        return 'journal'
    if 'eddn_fssbodysignals' in data_sources:
        return 'predicted'
    return 'estimated'


def _calculate_confidence(
    input_confidence: float,
    radius: Optional[float],
    planet_class: Optional[str],
) -> float:
    """
    Derive final slot prediction confidence.

    Higher input_confidence (from scan facts) propagates through.
    Missing radius or planet_class reduces confidence.
    """
    conf = input_confidence
    if radius is None:
        conf -= 0.15
    if not planet_class:
        conf -= 0.10
    return round(max(0.0, min(1.0, conf)), 3)
