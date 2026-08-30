from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'chatgpt-ed-new-ops.yml'
RUNBOOK_PATH = ROOT / 'docs' / 'operations' / 'production-pg18-candidate-promotion.md'


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def test_ed_new_workflow_narrowly_allowlists_readiness_audit():
    workflow = _workflow_text()

    assert '- production-candidate-readiness' in workflow
    assert 'host-status|production-candidate-readiness)' in workflow
    assert 'scripts/operator/audit_production_candidate.py --json-output' in workflow
    assert 'run-governed-migrations' not in workflow


def test_ed_new_readiness_operation_keeps_database_url_off_argv_and_receipt():
    workflow = _workflow_text()

    assert 'printf \'%s\\n\' "$CANDIDATE_DATABASE_URL" | ssh' in workflow
    assert 'IFS= read -r DATABASE_URL' in workflow
    assert '--database-url "$CANDIDATE_DATABASE_URL"' not in workflow
    assert 'secret in raw' in workflow
    assert 'json.loads(raw)' in workflow


def test_ed_new_readiness_operation_retains_receipt_and_preserves_exit_meaning():
    workflow = _workflow_text()

    assert 'production-candidate-readiness.json' in workflow
    assert 'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a' in workflow
    assert 'AUDIT_STATUS' in workflow
    assert '1) echo "Production candidate has readiness blockers' in workflow
    assert '2) echo "Production-candidate audit failed closed' in workflow
    yaml.safe_load(workflow)


def test_pg18_runbook_defines_order_completion_and_non_goals():
    runbook = RUNBOOK_PATH.read_text(encoding='utf-8')
    normalized = ' '.join(runbook.split())

    ordered_terms = (
        '**Snapshot/backup.**',
        '**Schema and migration audit.**',
        '**Base-data validation/import gaps.**',
        '**Grid.**',
        '**Ratings v3.4.**',
        '**Topology and economy-pair synergy.**',
        '**Archetypes.**',
        '**Regional analysis.**',
        '**Station/body links and canonical backfills.**',
        '**Full clusters.**',
        '**Materialized views and maintenance refresh.**',
        '**Strict invariant audit.**',
        '**Application smoke/release gate.**',
    )
    positions = [runbook.index(term) for term in ordered_terms]
    assert positions == sorted(positions)
    assert 'bounded nightly run' in runbook
    assert '100% eligible coverage' in runbook
    assert 'restore V2 into V3' in normalized
    assert 'does not run a migration or backfill' in runbook
