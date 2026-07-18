import pytest
from pydantic import ValidationError

from edfinder_api.models import ClusterSearchRequest, SlotRequirement


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
