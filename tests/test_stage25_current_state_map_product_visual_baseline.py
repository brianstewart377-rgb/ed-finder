import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
ROADMAP_PATH = DOCS / 'stage-25-roadmap.md'
BASELINE_PATH = DOCS / 'stage-25a-current-state-map-product-visual-baseline.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage25_docs_exist_and_define_primary_objective_and_recovery_state():
    roadmap = _read(ROADMAP_PATH)
    baseline = _read(BASELINE_PATH)
    combined = _squash(f'{roadmap} {baseline}')

    assert ROADMAP_PATH.exists()
    assert BASELINE_PATH.exists()
    assert combined.count('Stage 25 has exactly one primary objective:') == 2
    assert 'PR #257 fixed the Firefox map scroll/zoom crash.' in combined
    assert 'stable_after_pr257_manual_firefox_verification' in combined
    assert 'Stage 24 is closed.' in combined
    assert 'Stage 25 is a new explicit post-Stage-24 control.' in combined


@pytest.mark.unit
def test_stage25_docs_record_map_inventory_and_canonical_player_journey():
    combined = _squash(f'{_read(ROADMAP_PATH)} {_read(BASELINE_PATH)}')

    assert 'The map is retained as a secondary Explore surface only.' in combined
    assert 'retain_as_secondary_explore_surface' in combined
    assert 'Colony Planner: `canonical_live`' in combined
    assert 'simulation-preview: `reusable_but_unwired`' in combined
    assert 'map: `canonical_live` as a secondary Explore surface' in combined
    assert 'Explore → Inspect → Plan → Simulate/Sequence → Review Evidence → Export/Share' in combined
    assert 'Candidate Systems Map' in combined
    assert 'not authorized or implemented here' in combined


@pytest.mark.unit
def test_stage25_docs_define_visual_direction_and_reject_glass_for_dense_content():
    combined = _squash(f'{_read(ROADMAP_PATH)} {_read(BASELINE_PATH)}')

    assert 'restrained cockpit-oriented' in combined
    assert 'Glass or translucency is limited to workspace chrome only' in combined or (
        'glass or translucency is limited to workspace chrome only' in combined
    )
    assert 'Glass is not authorized on dense evidence cards, tables, planning canvases, map labels, or technical provenance surfaces.' in combined
    assert 'Glass is explicitly disallowed for dense evidence cards, tables, planning canvases, map labels, and technical provenance surfaces.' in combined
    assert 'evidence-language discipline' in combined
    assert 'evidence-language principles' in combined


@pytest.mark.unit
def test_stage25_docs_preserve_closed_and_deferred_boundaries():
    combined = _squash(f'{_read(ROADMAP_PATH)} {_read(BASELINE_PATH)}')

    assert 'Stage 19 remains separately gated.' in combined
    assert 'No database or operational write lane is authorized' in combined
    assert 'Stage 19 execution;' in combined
    assert 'database commands' in combined
    assert 'database writes' in combined
    assert 'canonical apply' in combined
    assert 'rebaseline' in combined
    assert 'scheduler, service, or timer activation' in combined
    assert 'Mission intelligence remains deferred and unauthorized' in combined
    assert 'Ring/mining work remains deferred and unauthorized' in combined
    assert 'Stage 25B remains unstarted.' in combined
    assert 'Stage 25C remains unstarted.' in combined
    assert 'Stage 25D remains unstarted.' in combined
    assert 'Stage 25E remains unstarted.' in combined
    assert 'Stage 25B through Stage 25E remain unstarted and unimplemented.' in combined
