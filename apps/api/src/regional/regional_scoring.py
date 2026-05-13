"""Archetype-aware regional fit scoring.

The scores here deliberately do not collapse into one universal "near is good"
metric.  Different colony designs want different regional positions.
"""
from __future__ import annotations

from typing import Any, Optional


ARCHETYPES = [
    'refinery_industrial',
    'extraction_refinery',
    'agriculture_terraforming',
    'hitech_tourism',
    'expansion_capital',
    'flexible_multirole',
]


def regional_scores(
    *,
    nearest_distance_ly: Optional[float],
    within_25: int,
    within_50: int,
    within_100: int,
    within_250: int,
) -> dict[str, float]:
    if nearest_distance_ly is None:
        return {'isolation': 0.0, 'density': 0.0, 'expansion': 0.0, 'competition': 0.0}
    isolation = _clamp((nearest_distance_ly / 180.0) * 100.0)
    density = _clamp((within_25 * 8) + (within_50 * 4) + (within_100 * 1.5) + (within_250 * 0.25))
    competition = _clamp((within_25 * 10) + (within_50 * 5) + max(0, within_100 - 10) * 2)
    expansion = _clamp(100.0 - abs(nearest_distance_ly - 90.0) * 0.65 - max(0, within_50 - 4) * 5)
    return {
        'isolation': round(isolation, 1),
        'density': round(density, 1),
        'expansion': round(expansion, 1),
        'competition': round(competition, 1),
    }


def archetype_regional_fit(
    *,
    regional_role: str,
    nearest_distance_ly: Optional[float],
    scores: dict[str, float],
    within_50: int,
    within_100: int,
) -> dict[str, float]:
    if nearest_distance_ly is None:
        return {key: 0.0 for key in ARCHETYPES}
    isolation = scores['isolation']
    density = scores['density']
    expansion = scores['expansion']
    competition = scores['competition']

    fit = {
        'expansion_capital': _clamp(expansion + _role_bonus(regional_role, {'frontier_hub': 12, 'bridge_system': 10, 'isolated_frontier': 4, 'oversaturated_region': -25})),
        'extraction_refinery': _clamp(isolation * 0.55 + (100 - competition) * 0.35 + _role_bonus(regional_role, {'isolated_frontier': 14, 'frontier_hub': 8, 'oversaturated_region': -24})),
        'refinery_industrial': _clamp(75 - abs(nearest_distance_ly - 70) * 0.35 + (100 - competition) * 0.15 + _role_bonus(regional_role, {'frontier_hub': 8, 'bridge_system': 7, 'oversaturated_region': -18})),
        'hitech_tourism': _clamp(density * 0.55 + (100 - isolation) * 0.25 + _role_bonus(regional_role, {'dense_developed_cluster': 14, 'emerging_cluster': 10, 'isolated_frontier': -24})),
        'agriculture_terraforming': _clamp(80 - abs(nearest_distance_ly - 80) * 0.3 - max(0, within_50 - 8) * 4 + _role_bonus(regional_role, {'frontier_hub': 8, 'emerging_cluster': 6, 'oversaturated_region': -14})),
        'flexible_multirole': _clamp(72 - abs(scores['density'] - 45) * 0.25 + _role_bonus(regional_role, {'bridge_system': 8, 'emerging_cluster': 7, 'unknown': -8})),
    }
    return {key: round(value, 1) for key, value in fit.items()}


def regional_rationale(
    *,
    regional_role: str,
    nearest_distance_ly: Optional[float],
    within_100: int,
    fit: dict[str, float],
) -> dict[str, Any]:
    if nearest_distance_ly is None:
        return {
            'summary': 'Regional position is unknown because system coordinates or colonised-neighbour data are missing.',
            'strengths': [],
            'warnings': ['Regional analysis could not be computed for this system.'],
            'archetype_notes': {},
        }
    best = max(fit, key=fit.get) if fit else 'flexible_multirole'
    strengths = [f'Regional role classified as {regional_role.replace("_", " ")}.']
    warnings: list[str] = []
    if regional_role == 'oversaturated_region':
        warnings.append('High nearby colony density may create competition for specialised expansion roles.')
    if regional_role == 'isolated_frontier':
        warnings.append('Extreme isolation helps frontier dominance but may hurt tourism and logistics access.')
    return {
        'summary': (
            f'Nearest colonised system is {nearest_distance_ly:.1f} LY away with {within_100} colonised systems '
            f'within 100 LY; strongest regional fit is {best.replace("_", " ")}.'
        ),
        'strengths': strengths,
        'warnings': warnings,
        'archetype_notes': {
            key: _fit_note(value)
            for key, value in fit.items()
        },
    }


def _fit_note(score: float) -> str:
    if score >= 85:
        return 'excellent regional fit'
    if score >= 70:
        return 'good regional fit'
    if score >= 50:
        return 'mixed regional fit'
    return 'weak regional fit'


def _role_bonus(role: str, values: dict[str, float]) -> float:
    return values.get(role, 0.0)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
