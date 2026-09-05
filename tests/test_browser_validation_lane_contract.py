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

    # Until the re-base is complete, legacy overlap must be labelled as debt so
    # it cannot silently become the accepted V3 ownership model.
    assert 'TEMPORARY MIGRATION DEBT' in workflow
    assert 'a green legacy Lab run is not V3 acceptance' in workflow


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
