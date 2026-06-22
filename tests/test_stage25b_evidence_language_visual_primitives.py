import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
ROADMAP_PATH = DOCS / 'stage-25-roadmap.md'
STAGE25B_PATH = DOCS / 'stage-25b-evidence-language-visual-primitives.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage25b_docs_exist_and_mark_pending_review_without_false_completion():
    roadmap = _read(ROADMAP_PATH)
    stage25b = _read(STAGE25B_PATH)
    combined = _squash(f'{roadmap} {stage25b}')

    assert STAGE25B_PATH.exists()
    # The frozen Stage 25B implementation doc retains its original pending-review
    # wording, while the roadmap reset records the corrected merged status.
    assert 'Stage 25B is `implemented_in_this_pr_pending_review`.' in combined
    assert 'It does not claim Stage 25B is complete until the implementing PR is reviewed and merged.' in combined
    assert 'Stage 25B is complete and merged' in combined


@pytest.mark.unit
def test_stage25b_docs_record_touched_surfaces_primitives_and_evidence_language_rule():
    stage25b = _squash(_read(STAGE25B_PATH))

    assert 'SystemDetailModal.tsx' in stage25b
    assert 'WorkspaceHeader.tsx' in stage25b
    assert 'ColonyPlannerWorkspace.tsx' in stage25b
    assert 'WarehouseEvidenceCard.tsx' in stage25b
    assert 'SemanticStatusBadge.tsx' in stage25b
    assert 'WorkspaceContextHeader.tsx' in stage25b
    assert 'EvidencePostureSummary.tsx' in stage25b
    assert 'evidence must be player-facing first' in stage25b
    assert 'technically honest' in stage25b
    assert 'apparent canonical truth' in stage25b
    assert 'Available' in stage25b
    assert 'Unavailable' in stage25b
    assert 'Not evaluated' in stage25b
    assert 'Unknown' in stage25b


@pytest.mark.unit
def test_stage25b_docs_require_progressive_disclosure_and_preserved_truth_boundaries():
    stage25b = _squash(_read(STAGE25B_PATH))

    assert 'accessible progressive-disclosure control' in stage25b
    assert 'freshness' in stage25b
    assert 'source class' in stage25b
    assert 'provenance and source run' in stage25b
    assert 'report-only status' in stage25b
    assert 'selected-system-only scope' in stage25b
    assert 'bounded or incomplete coverage' in stage25b
    assert 'source-posture fallback' in stage25b
    assert 'manual-review requirement' in stage25b
    assert 'canonical planner truth remains visibly separate from evidence' in stage25b
    assert 'available evidence remains report-only where the contract requires it' in stage25b
    assert 'dedicated contract preference remains in place' in stage25b
    assert 'provenance fallback remains in place only when the dedicated endpoint cannot be read' in stage25b


@pytest.mark.unit
def test_stage25b_docs_preserve_accessibility_visual_and_scope_safety_boundaries():
    stage25b = _squash(_read(STAGE25B_PATH))

    assert 'visible focus rings' in stage25b
    assert 'reduced motion remains respected' in stage25b
    assert 'dense evidence surfaces avoid added blur or decorative glass' in stage25b
    assert 'does not redesign the map' in stage25b
    assert 'does not alter `GalacticMap`' in stage25b
    assert 'does not wire `simulation-preview` into live routes' in stage25b
    assert 'Stage 25C, Stage 25D, or Stage 25E implementation' in stage25b
    assert 'does not authorize or run Stage 19 commands' in stage25b
    assert 'database commands' in stage25b
    assert 'database writes' in stage25b
    assert 'canonical apply' in stage25b
    assert 'rebaseline' in stage25b
    assert 'scheduler, service, or timer work' in stage25b
    assert 'source acquisition' in stage25b
