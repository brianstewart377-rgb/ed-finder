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
AU_DOC_PATH = DOCS / 'stage-19au-readonly-asau-safety-gate.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19au_keeps_authority_paused_and_asau_recorded():
    authority = json.loads(_read(AUTHORITY_PATH))
    asau_checkpoint = authority['stage19as_au_completed_checkpoint']

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert authority['approved_stage19ar_baseline'] == {
        'source_run_key': 'stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034',
        'bridge_key': 'source_runs:stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034',
        'artifact': 'b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e',
        'rows': 25,
    }
    assert asau_checkpoint['status'] == 'completed'
    assert asau_checkpoint['source_run_key'] == 'stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
    assert asau_checkpoint['bridge_key'] == 'source_runs:stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
    assert asau_checkpoint['rows_read'] == 100
    assert asau_checkpoint['rows_staged'] == 100
    assert asau_checkpoint['rows_rejected'] == 0
    assert asau_checkpoint['rows_skipped'] == 0
    assert asau_checkpoint['canonical_writes_performed'] is False
    assert asau_checkpoint['approved_stage19ar_baseline_preserved'] is True
    assert asau_checkpoint['stage19_remains_paused'] is True


@pytest.mark.unit
def test_stage19au_records_as1_as2_at_and_readonly_gate():
    au_doc = _squash(_read(AU_DOC_PATH))
    as1_doc = _squash(_read(AS1_DOC_PATH))
    as2_doc = _squash(_read(AS2_DOC_PATH))
    at_doc = _squash(_read(AT_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    for fragment in (
        'Stage 19AU - Read-Only AS-AU Safety Gate',
        'Stage 19AS-AU is complete and recorded.',
        'Stage 19AS.1 is complete and recorded.',
        'Stage 19AS.2 is complete and recorded.',
        'Stage 19AT is complete and recorded.',
        'Stage 19 remains paused.',
        'Stage 19AU is read-only verification only.',
        'documentation and static/unit test coverage in this PR',
        'Any future write-capable lane requires a separate explicit operator decision.',
    ):
        assert fragment in au_doc

    assert 'Stage 19AS.1 adds the next safety-test checkpoint' in as1_doc
    assert 'Stage 19AS.2 - Operator Script Contract Formalization' in as2_doc
    assert 'Stage 19AT - Paused-State Next Operator Decision' in at_doc
    assert 'Stage 19AU is the read-only AS-AU safety-gate checkpoint after Stage 19AT.' in roadmap
    assert 'stage-19au-readonly-asau-safety-gate.md' in roadmap


@pytest.mark.unit
def test_stage19au_records_db_verification_not_run_without_safe_target():
    au_doc = _squash(_read(AU_DOC_PATH))

    for fragment in (
        'This PR did not run DB verification because no explicit safe local or disposable read-only DB target was supplied.',
        'db_verification: not_run',
        'No explicit safe local/disposable DB target was provided for this checkpoint.',
        'The repo changes are docs/static-test only.',
        'must stop on production- like DSNs or direct host `5432` targets',
    ):
        assert fragment in au_doc


@pytest.mark.unit
def test_stage19au_does_not_mark_canonical_apply_or_rebaseline_complete():
    au_doc = _squash(_read(AU_DOC_PATH))
    as2_doc = _squash(_read(AS2_DOC_PATH))
    at_doc = _squash(_read(AT_DOC_PATH))

    for source in (au_doc, as2_doc, at_doc):
        assert 'No canonical apply is complete.' in source
        assert 'No rebaseline is complete.' in source

    assert 'canonical apply is complete.' not in au_doc.replace('No canonical apply is complete.', '')
    assert 'rebaseline is complete.' not in au_doc.replace('No rebaseline is complete.', '')


@pytest.mark.unit
def test_stage19au_blocks_write_capable_lanes_and_forbidden_actions():
    au_doc = _squash(_read(AU_DOC_PATH))

    for fragment in (
        'No wider pilot is authorized by Stage 19AU.',
        'No DB mutation is authorized by Stage 19AU.',
        'No scheduler or service work is authorized by Stage 19AU.',
        'No canonical apply or rebaseline is authorized by Stage 19AU.',
        'Stage 19 operator commands',
        'Stage 19AR with `--commit`',
        'Stage 19AS-AU with `--commit`',
        'full source batch execution',
        'database mutation',
        'staging row writes',
        'canonical table writes',
        'scheduler, timer, or service-manager work',
        'production-like database targets',
        'host `5432` as a direct Stage 19 target',
        'secrets access or printing',
        'runtime source JSON or operator artifact JSON commits',
    ):
        assert fragment in au_doc


@pytest.mark.unit
def test_stage19au_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19au_readonly_asau_safety_gate.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity
