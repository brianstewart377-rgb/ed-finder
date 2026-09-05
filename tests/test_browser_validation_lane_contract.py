from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_E2E_WORKFLOW = ROOT / '.github' / 'workflows' / 'cypress-parity.yml'
REVIEW_LAB_WORKFLOW = ROOT / '.github' / 'workflows' / 'review-lab.yml'
AUTHORITY_DOC = ROOT / 'docs' / 'development' / 'v3-browser-validation-lanes.md'


@pytest.mark.unit
def test_product_e2e_lane_does_not_invoke_review_lab_runtime():
    workflow = PRODUCT_E2E_WORKFLOW.read_text(encoding='utf-8')

    # Normal product E2E may use a seeded CI database, but it must never boot or
    # invoke the isolated Review Lab runtime/handshake as a shortcut.
    for forbidden in (
        'scripts/dev/review_environment.py',
        'EDFINDER_REVIEW_LAB_RUN',
        'review_main.py',
        '--confirm-local-review-environment',
        'com.docker.compose.project=edfinder-review',
    ):
        assert forbidden not in workflow

    # During migration the workflow may still carry retained React evidence,
    # but the V3 lane itself must remain present and execute apps/web Cypress.
    assert 'This workflow owns normal Product E2E / Visual Acceptance.' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'pnpm exec cypress run' in workflow
    assert 'Run V3 Svelte Product E2E / Visual Acceptance' in workflow
    assert 'Preserve normal Product E2E evidence' in workflow


@pytest.mark.unit
def test_review_lab_lane_uses_wrapper_authority_not_normal_product_e2e_specs():
    workflow = REVIEW_LAB_WORKFLOW.read_text(encoding='utf-8')

    assert 'This workflow owns the isolated deterministic Review Lab only.' in workflow
    assert 'scripts/dev/review_environment.py verify' in workflow
    assert '--confirm-local-review-environment' in workflow

    # Review Lab owns a dedicated collector invoked by its Python wrapper. It
    # must not substitute the normal product E2E command or release-gate specs.
    for forbidden in (
        'pnpm test:e2e',
        'yarn e2e',
        'cypress/e2e/auth-owner-access.cy.js',
        'cypress/e2e/release-gate.cy.js',
    ):
        assert forbidden not in workflow

    # The synthetic lane must use the same V3 frontend/renderer while keeping a
    # dedicated collector and wrapper-owned environment.
    assert 'Node 24 for V3 Review Lab collector' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'pnpm install --frozen-lockfile' in workflow
    assert 'tests/test_review_lab_v3.py' in workflow
    assert 'working-directory: frontend' not in workflow
    assert 'resolve_project_state.py' not in workflow
    assert 'Review Lab Cypress diagnostic artifacts' in workflow


@pytest.mark.unit
def test_authority_doc_keeps_visual_baseline_ownership_out_of_review_lab():
    authority = AUTHORITY_DOC.read_text(encoding='utf-8')

    assert 'V3 Product E2E / Visual Acceptance' in authority
    assert 'Review Lab' in authority
    assert 'Review Lab screenshots are diagnostic evidence, not approved product visual baselines.' in authority
    assert 'Approved visual baselines belong only to the V3 Product E2E / Visual Acceptance lane.' in authority
    assert 'Normal code-quality CI is outside both browser lanes.' in authority
    assert 'A lane re-base is complete only when **both** browser workflows target their intended V3 responsibilities independently' in authority
    assert 'Contabo is the **live-checkpoint environment**, not the production server.' in authority


@pytest.mark.unit
def test_v3_map_validation_uses_fresh_babylon_stack_in_both_browser_lanes():
    authority = AUTHORITY_DOC.read_text(encoding='utf-8')

    assert 'The V3 map is a **fresh design** in `apps/web/` using **Babylon.js**' in authority
    assert 'the old React map is not the visual oracle for the new product' in authority
    assert 'Both browser-validation lanes must exercise the **same V3 frontend and renderer stack**' in authority
    assert 'Review Lab may change the **data and environment**' in authority
    assert 'It must not substitute a different frontend framework or renderer.' in authority
    assert 'A React/R3F Review Lab therefore cannot gate a Babylon V3 map checkpoint.' in authority
    assert 'For the first meaningful Finder/Inspect/Babylon live checkpoint' in authority


@pytest.mark.unit
def test_review_lab_rebase_removed_retained_react_collector():
    assert not (ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js').exists()
    runner = (ROOT / 'scripts' / 'dev' / 'review_lab' / 'browser_runner.py').read_text(encoding='utf-8')
    assert "FRONTEND_DIR" in runner
    assert "'cypress/e2e/review-lab.cy.ts'" in runner
    assert "'pnpm', 'build'" in runner


@pytest.mark.unit
def test_product_e2e_covers_the_non_product_spatial_foundation_lifecycle():
    workflow = PRODUCT_E2E_WORKFLOW.read_text(encoding='utf-8')
    spec = (
        ROOT / 'apps' / 'web' / 'cypress' / 'e2e' / 'spatial-foundation.cy.ts'
    ).read_text(encoding='utf-8')

    assert 'browser: [chrome, firefox]' in workflow
    assert "cy.visit('/spatial-foundation'" in spec
    assert 'data-renderer-state="ready"' in spec
    assert 'WEBGPU|WEBGL2' in spec
    assert 'cy.viewport(' in spec
    assert "cy.go('back')" in spec
    assert '__spatialRuntimeFailures' in spec
    assert 'cy.screenshot(' in spec
