from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / 'docs' / 'development' / 'v3-coordination-control-plane.md'
BROWSER_LANES = ROOT / 'docs' / 'development' / 'v3-browser-validation-lanes.md'
HISTORICAL_OPS_DESIGN = ROOT / 'docs' / 'development' / 'chatgpt-ops-control-plane.md'
CODEX_DISPATCH = ROOT / '.github' / 'workflows' / 'codex-dispatch.yml'
CODEX_WORKER = ROOT / '.github' / 'workflows' / 'codex-laptop.yml'
OPS_WORKFLOW = ROOT / '.github' / 'workflows' / 'chatgpt-ed-new-ops.yml'


@pytest.mark.unit
def test_v3_coordination_control_plane_is_not_an_application_runtime_bus():
    text = CONTROL_PLANE.read_text(encoding='utf-8')

    assert 'coordination and evidence' in text
    assert 'not a new application runtime service' in text
    assert 'Svelte / SvelteKit' in text
    assert 'renderer-neutral spatial contracts' in text
    assert 'Babylon runtime adapter' in text
    assert 'Domain/feature code must not import Babylon types.' in text
    assert 'Typed API contracts are the liaison between browser application and backend' in text


@pytest.mark.unit
def test_control_plane_preserves_separate_validation_authorities():
    control = CONTROL_PLANE.read_text(encoding='utf-8')
    browser = BROWSER_LANES.read_text(encoding='utf-8')

    assert 'Product E2E / Visual Acceptance' in control
    assert 'Review Lab' in control
    assert 'A green Review Lab does not replace Product E2E.' in control
    assert 'same `apps/web` + Babylon frontend/renderer' in control
    assert 'Review Lab screenshots are diagnostic evidence, not approved product visual baselines.' in browser


@pytest.mark.unit
def test_live_checkpoint_path_is_main_immutable_and_receipted():
    text = CONTROL_PLANE.read_text(encoding='utf-8')

    assert 'After a checkpoint merges, `main` is the only source from which a live checkpoint release may be built.' in text
    assert '`main` SHA' in text
    assert 'digest-pinned release' in text
    assert 'Contabo' in text
    assert 'deployment receipt' in text
    assert 'No worker branch deploy' in text
    assert 'no `git pull`' in text


@pytest.mark.unit
def test_historical_ops_design_cannot_be_mistaken_for_current_authority():
    historical = HISTORICAL_OPS_DESIGN.read_text(encoding='utf-8')
    current = CONTROL_PLANE.read_text(encoding='utf-8')

    assert 'DESIGN/HISTORICAL DOCUMENT — NOT AN OPERATOR RUNBOOK' in historical
    assert 'older `chatgpt-ops-control-plane.md` contains useful design history but is not the current authority' in current


@pytest.mark.unit
def test_codex_and_operator_control_surfaces_remain_narrow():
    dispatch = CODEX_DISPATCH.read_text(encoding='utf-8')
    worker = CODEX_WORKER.read_text(encoding='utf-8')
    ops = OPS_WORKFLOW.read_text(encoding='utf-8')

    assert 'codex-task-requests' in dispatch
    assert 'target_branch is protected/control-plane state and cannot be updated by Codex' in worker
    assert 'contents: read' in worker
    assert 'Allowlisted ed-new operation' in ops
    assert 'Unsupported operation' in ops
