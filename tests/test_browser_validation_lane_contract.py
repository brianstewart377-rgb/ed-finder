from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_E2E_WORKFLOW = ROOT / '.github' / 'workflows' / 'cypress-parity.yml'
REVIEW_LAB_WORKFLOW = ROOT / '.github' / 'workflows' / 'review-lab.yml'
AUTHORITY_DOC = ROOT / 'docs' / 'development' / 'v3-browser-validation-lanes.md'
PRODUCT_SPEC = ROOT / 'apps' / 'web' / 'cypress' / 'e2e' / 'product-journey.cy.ts'
REVIEW_SPEC = ROOT / 'apps' / 'web' / 'cypress' / 'e2e' / 'review-lab.cy.ts'
REVIEW_SCENARIOS = ROOT / 'scripts' / 'dev' / 'review_lab' / 'scenarios.py'


@pytest.mark.unit
def test_product_e2e_lane_does_not_invoke_review_lab_runtime():
    workflow = PRODUCT_E2E_WORKFLOW.read_text(encoding='utf-8')
    for forbidden in (
        'scripts/dev/review_environment.py',
        'EDFINDER_REVIEW_LAB_RUN',
        'review_main.py',
        '--confirm-local-review-environment',
        'com.docker.compose.project=edfinder-review',
        '/api/review/scenario/',
    ):
        assert forbidden not in workflow
    assert 'This workflow owns normal Product E2E / Visual Acceptance.' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'pnpm exec cypress run' in workflow
    assert 'Run V3 Svelte Product E2E / Visual Acceptance' in workflow


@pytest.mark.unit
def test_review_lab_lane_uses_wrapper_authority_not_normal_product_e2e_specs():
    workflow = REVIEW_LAB_WORKFLOW.read_text(encoding='utf-8')
    assert 'This workflow owns the isolated deterministic Review Lab only.' in workflow
    assert 'scripts/dev/review_environment.py verify' in workflow
    assert '--confirm-local-review-environment' in workflow
    for forbidden in (
        'pnpm test:e2e',
        'yarn e2e',
        'cypress/e2e/auth-owner-access.cy.js',
        'cypress/e2e/release-gate.cy.js',
        'product-journey.cy.ts',
    ):
        assert forbidden not in workflow
    assert 'Node 24 for V3 Review Lab collector' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'tests/test_review_lab_v3.py' in workflow
    assert 'working-directory: frontend' not in workflow


@pytest.mark.unit
def test_review_lab_collector_does_not_duplicate_normal_product_acceptance():
    product = PRODUCT_SPEC.read_text(encoding='utf-8')
    review = REVIEW_SPEC.read_text(encoding='utf-8')
    scenarios = REVIEW_SCENARIOS.read_text(encoding='utf-8')

    for marker in ('.inspect-link', '{downArrow}{enter}', 'cy.checkA11y', 'cy.screenshot('):
        assert marker in product
        assert marker not in review

    assert 'explore_inspect' not in scenarios
    assert 'navigation_containment' not in scenarios
    assert 'synthetic_wiring' in scenarios
    assert 'api_failure' in scenarios
    assert 'empty_results' in scenarios
    assert 'renderer_recovery' in scenarios


@pytest.mark.unit
def test_review_lab_uses_backend_owned_synthetic_conditions_not_cypress_stubs():
    review = REVIEW_SPEC.read_text(encoding='utf-8')
    review_main = (ROOT / 'apps' / 'api' / 'src' / 'review_main.py').read_text(encoding='utf-8')
    assert '/api/review/scenario/' in review
    assert 'statusCode: 503' not in review
    assert 'review_lab_synthetic_empty' not in review
    assert "mode == 'api_failure'" in review_main
    assert "mode == 'empty_results'" in review_main


@pytest.mark.unit
def test_authority_doc_keeps_visual_baseline_ownership_out_of_review_lab():
    authority = AUTHORITY_DOC.read_text(encoding='utf-8')
    assert 'V3 Product E2E / Visual Acceptance' in authority
    assert 'Review Lab' in authority
    assert 'Review Lab screenshots are diagnostic evidence, not approved product visual baselines.' in authority
    assert 'Approved visual baselines belong only to the V3 Product E2E / Visual Acceptance lane.' in authority
    assert 'Normal code-quality CI is outside both browser lanes.' in authority


@pytest.mark.unit
def test_v3_map_validation_uses_fresh_babylon_stack_in_both_browser_lanes():
    authority = AUTHORITY_DOC.read_text(encoding='utf-8')
    assert 'The V3 map is a **fresh design** in `apps/web/` using **Babylon.js**' in authority
    assert 'the old React map is not the visual oracle for the new product' in authority
    assert 'Both browser-validation lanes must exercise the **same V3 frontend and renderer stack**' in authority
    assert 'Review Lab may change the **data and environment**' in authority
    assert 'It must not substitute a different frontend framework or renderer.' in authority


@pytest.mark.unit
def test_review_lab_rebase_removed_retained_react_collector():
    assert not (ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js').exists()
    runner = (ROOT / 'scripts' / 'dev' / 'review_lab' / 'browser_runner.py').read_text(encoding='utf-8')
    assert 'FRONTEND_DIR' in runner
    assert "'cypress/e2e/review-lab.cy.ts'" in runner
    assert "'pnpm', 'build'" in runner
    assert "'--host'" in runner


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
