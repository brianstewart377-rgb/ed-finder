import pytest
from pydantic import ValidationError

from edfinder_api.models import (
    ClusterSearchRequest,
    LocalSearchRequest,
    SlotRequirement,
)


def test_slot_requirement_resolves_archetype_economies_and_labels():
    combined = SlotRequirement(economies=['Refinery', 'Industrial'])
    assert combined.label == 'Refinery + Industrial'
    assert combined.min_score == 65

    archetype = SlotRequirement(archetype_key='refinery_industrial')
    assert archetype.economies == ['Refinery', 'Industrial']
    assert archetype.label == 'Refinery Industrial'

    extraction = SlotRequirement(archetype_key='extraction_refinery')
    assert extraction.economies == ['Refinery']


def test_slot_requirement_preserves_explicit_values():
    slot = SlotRequirement(
        archetype_key='refinery_industrial',
        economies=['Agriculture'],
        label='Custom',
    )

    assert slot.economies == ['Agriculture']
    assert slot.label == 'Custom'


@pytest.mark.parametrize('economies', [[], ['A', 'B', 'C']])
def test_slot_requirement_rejects_invalid_economy_counts(economies):
    with pytest.raises(ValidationError):
        SlotRequirement(economies=economies)


def test_cluster_search_accepts_slots_or_legacy_requirements_but_not_both():
    slots = ClusterSearchRequest(
        slots=[SlotRequirement(archetype_key='refinery_industrial')],
    )
    assert len(slots.slots) == 1

    legacy = ClusterSearchRequest(
        requirements=[{'economy': 'Agriculture', 'min_count': 1}],
    )
    assert len(legacy.requirements) == 1

    with pytest.raises(ValidationError):
        ClusterSearchRequest(
            requirements=[{'economy': 'Agriculture'}],
            slots=[SlotRequirement(economies=['Refinery'])],
        )


def test_cluster_search_accepts_only_named_galactic_region_ids():
    request = ClusterSearchRequest(
        slots=[SlotRequirement(archetype_key='refinery_industrial')],
        galaxy_region_id=31,
    )
    assert request.galaxy_region_id == 31

    for invalid_id in (0, 43):
        with pytest.raises(ValidationError):
            ClusterSearchRequest(
                slots=[SlotRequirement(archetype_key='refinery_industrial')],
                galaxy_region_id=invalid_id,
            )


def test_local_search_bounds_min_development_score_to_score_domain():
    """min_development_score is the 0..100 development-score domain. An
    out-of-domain value must fail validation (422) rather than reach the SQL
    bind and overflow best_colony_potential's smallint (previously a 503)."""
    assert LocalSearchRequest(min_development_score=0).min_development_score == 0
    assert LocalSearchRequest(min_development_score=100).min_development_score == 100
    for invalid in (-1, 101, 40_000):
        with pytest.raises(ValidationError):
            LocalSearchRequest(min_development_score=invalid)


def test_local_search_exposes_named_galaxy_region_id():
    """galaxy_region_id must be an accepted request field (so the router can
    forward it to the V3 region predicate) and bounded to named regions."""
    assert LocalSearchRequest(galaxy_region_id=31).galaxy_region_id == 31
    assert LocalSearchRequest().galaxy_region_id is None
    for invalid in (0, 43):
        with pytest.raises(ValidationError):
            LocalSearchRequest(galaxy_region_id=invalid)
