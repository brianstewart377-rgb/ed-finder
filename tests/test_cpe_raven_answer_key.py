"""Compare only the hand-recorded Raven answer key already on this branch."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.cpe import Plan, Site, evaluate_plan  # noqa: E402


FIXTURE = ROOT / 'tests' / 'fixtures' / 'cpe' / 'raven_answer_key_praea_euq_rev174.json'


def test_raven_praea_euq_revision_174_answer_key() -> None:
    answer = json.loads(FIXTURE.read_text(encoding='utf-8'))
    plan = Plan(
        system_id64=answer['source']['system_id64'],
        bodies=(),
        sites=tuple(
            Site(**{key: row[key] for key in (
                'site_id', 'facility_id', 'body_ref', 'slot_kind', 'status', 'name'
            )})
            for row in answer['sites_in_raven_order']
        ),
    )
    result = evaluate_plan(plan)
    expected_now = answer['expected']['completed_sites_only']
    expected_after = answer['expected']['all_sites']
    assert (result.now.t2, result.now.t3) == (expected_now['t2'], expected_now['t3']) == (1, -17)
    assert (result.after_plan.t2, result.after_plan.t3) == (expected_after['t2'], expected_after['t3']) == (5, -16)
    assert any(
        item['what'] == 'Sixth counted Tier 2 port'
        and item['raven'] == '12 Tier 2 points'
        and item['ed_finder'] == '11 Tier 2 points'
        and 'RB-0003' in item['reason']
        for item in answer['known_differences']
    )
