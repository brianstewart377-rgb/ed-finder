import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
AS1_DOC_PATH = DOCS / 'stage-19as1-disposable-postgres-constraint-tests.md'
AS2_DOC_PATH = DOCS / 'stage-19as2-operator-script-contract.md'
AT_DOC_PATH = DOCS / 'stage-19at-paused-state-next-operator-decision.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19at_keeps_active_authority_paused_and_asau_recorded():
    authority = json.loads(_read(AUTHORITY_PATH))
    asau_checkpoint = authority['stage19as_au_completed_checkpoint']

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert asau_checkpoint['status'] == 'completed'
    assert asau_checkpoint['rows_read'] == 100
    assert asau_checkpoint['rows_staged'] == 100
    assert asau_checkpoint['canonical_writes_performed'] is False
    assert asau_checkpoint['approved_stage19ar_baseline_preserved'] is True
    assert asau_checkpoint['stage19_remains_paused'] is True


@pytest.mark.unit
def test_stage19at_records_as1_as2_and_paused_decision_gate():
    at_doc = _squash(_read(AT_DOC_PATH))
    as1_doc = _squash(_read(AS1_DOC_PATH))
    as2_doc = _squash(_read(AS2_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    for fragment in (
        'Stage 19AT - Paused-State Next Operator Decision',
        'Stage 19AS-AU is complete and recorded.',
        'Stage 19AS.1 is complete and recorded.',
        'Stage 19AS.2 is complete and recorded.',
        'Stage 19 remains paused.',
        'Stage 19AT is a decision checkpoint, not an execution checkpoint.',
        'The next operational lane still requires explicit operator approval.',
        'documentation and static-test checkpoint only',
    ):
        assert fragment in at_doc

    assert 'Stage 19AS.1 adds the next safety-test checkpoint' in as1_doc
    assert 'Stage 19AS.2 - Operator Script Contract Formalization' in as2_doc
    assert 'Stage 19AT is the current paused-state decision gate after Stage 19AS.2' in roadmap
    assert 'stage-19at-paused-state-next-operator-decision.md' in roadmap


@pytest.mark.unit
def test_stage19at_does_not_mark_canonical_apply_or_rebaseline_complete():
    at_doc = _squash(_read(AT_DOC_PATH))
    as2_doc = _squash(_read(AS2_DOC_PATH))

    for source in (at_doc, as2_doc):
        assert 'No canonical apply is complete.' in source
        assert 'No rebaseline is complete.' in source

    assert 'canonical apply is complete.' not in at_doc.replace('No canonical apply is complete.', '')
    assert 'rebaseline is complete.' not in at_doc.replace('No rebaseline is complete.', '')


@pytest.mark.unit
def test_stage19at_blocks_wider_pilot_db_execution_and_forbidden_actions():
    at_doc = _read(AT_DOC_PATH)
    compact_at_doc = _squash(at_doc)

    for fragment in (
        'wider pilot execution',
        'Stage 19 operator commands',
        'Stage 19AR with `--commit`',
        'Stage 19AS-AU with `--commit`',
        'full source batch execution',
        'database mutation',
        'staging row writes',
        'canonical table writes',
        'canonical apply',
        'rebaseline',
        'scheduler, timer, or service-manager work',
        'production-like database targets',
        'host `5432` as a direct Stage 19 target',
        'secrets access or printing',
        'runtime source JSON or operator artifact JSON commits',
        'No Stage 19 operator command is authorized by this checkpoint.',
        'No DB mutation is authorized by this checkpoint.',
    ):
        assert fragment in compact_at_doc


@pytest.mark.unit
def test_stage19at_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19at_paused_state_next_operator_decision.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity
