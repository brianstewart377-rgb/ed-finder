from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SQL_PATH = ROOT / 'sql' / '030_evidence_store_foundation.sql'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

from evidence_store.api_models import RuleDecisionRequest  # noqa: E402
from evidence_store.models import DerivedFeature, EvidenceRecord, RuleProposal  # noqa: E402
from evidence_store.source_catalog import list_evidence_sources  # noqa: E402
from evidence_store import store  # noqa: E402


class _FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


class _DecisionConnection:
    def __init__(self):
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchval(self, query: str, *args):
        assert 'SELECT 1 FROM rule_proposals' in query
        assert args == ('prop_demo',)
        return 1

    async def fetchrow(self, query: str, *args):
        assert 'INSERT INTO rule_decisions' in query
        return {
            'decision_id': 7,
            'proposal_key': args[0],
            'decision': args[1],
            'decided_by': args[2],
            'reason': args[3],
            'metadata_json': {'reason_code': 'safe-low-risk'},
            'created_at': '2026-07-06T19:10:00+00:00',
        }

    async def execute(self, query: str, *args):
        self.executed.append((query, args))
        return 'UPDATE 1'


@pytest.mark.unit
def test_evidence_source_catalog_prioritises_live_foundations_and_missing_high_value_targets():
    sources = list_evidence_sources()

    assert [row['source_name'] for row in sources[:3]] == ['spansh', 'eddn', 'edsm']
    assert sources[0]['implementation_status'] == 'live'
    assert sources[1]['implementation_status'] == 'live'
    assert sources[2]['implementation_status'] == 'bounded_live'
    assert any(row['source_name'] == 'inara' and row['recommended_priority'] == 4 for row in sources)
    assert any(row['source_name'] == 'frontier_journal' and row['recommended_priority'] == 5 for row in sources)
    assert any('station_services' in row['domains'] for row in sources if row['source_name'] == 'inara')


@pytest.mark.asyncio
async def test_evidence_system_summary_combines_existing_and_new_evidence_layers(monkeypatch: pytest.MonkeyPatch):
    async def _observed_summary(_pool, _id64: int):
        return {'total_count': 3}

    async def _records(_pool, **_kwargs):
        return (
            [
                EvidenceRecord(
                    evidence_key='evd_alpha',
                    system_id64=42,
                    source_name='eddn',
                    origin='imported',
                    subject_type='station',
                    subject_id='Jameson Memorial',
                    evidence_type='service_snapshot',
                    record_status='active',
                    freshness_status='current',
                    confidence='high',
                    summary='Latest EDDN station-service snapshot.',
                    source_record_id=None,
                    source_run_key='run_eddn_1',
                    observed_at='2026-07-06T18:00:00+00:00',
                    collected_at='2026-07-06T18:01:00+00:00',
                    expires_at=None,
                    value={'services': ['market']},
                    provenance={'relay': 'eddn'},
                )
            ],
            1,
        )

    async def _features(_pool, **_kwargs):
        return (
            [
                DerivedFeature(
                    feature_key='feat_alpha',
                    system_id64=42,
                    feature_name='mission_pressure',
                    feature_version='v1',
                    feature_status='active',
                    confidence='medium',
                    summary='Mission pressure rising.',
                    derived_from_run_key='run_inara_1',
                    derived_at='2026-07-06T18:05:00+00:00',
                    expires_at=None,
                    value={'score': 0.71},
                    evidence_refs=['evd_alpha'],
                )
            ],
            1,
        )

    async def _proposals(_pool, **_kwargs):
        return (
            [
                RuleProposal(
                    proposal_key='prop_alpha',
                    proposal_type='threshold_tweak',
                    domain='mission_intelligence',
                    scope_type='system',
                    scope_key='42',
                    status='pending_review',
                    priority='medium',
                    risk_level='low',
                    auto_approval_eligible=False,
                    summary='Increase mission pressure alert threshold.',
                    proposed_by='evidence-pipeline',
                    decided_by=None,
                    decision_notes=None,
                    proposed_change={'threshold': 0.75},
                    evidence_refs=['evd_alpha'],
                    impact_summary={'delta_systems': 12},
                )
            ],
            1,
        )

    monkeypatch.setattr(store, 'observed_fact_summary', _observed_summary)
    monkeypatch.setattr(store, 'list_evidence_records', _records)
    monkeypatch.setattr(store, 'list_derived_features', _features)
    monkeypatch.setattr(store, 'list_rule_proposals', _proposals)

    summary = await store.build_evidence_system_summary(object(), 42)

    assert summary.schema_version == 'evidence_store/v1'
    assert summary.system_id64 == 42
    assert summary.observed_fact_count == 3
    assert summary.imported_record_count == 1
    assert summary.derived_feature_count == 1
    assert summary.open_rule_proposal_count == 1
    assert summary.records[0].source_name == 'eddn'
    assert summary.derived_features[0].feature_name == 'mission_pressure'
    assert summary.open_rule_proposals[0].proposal_key == 'prop_alpha'


@pytest.mark.asyncio
async def test_create_rule_decision_updates_proposal_status_and_records_audit():
    pool = _FakePool(_DecisionConnection())

    decision = await store.create_rule_decision(
        pool,
        'prop_demo',
        RuleDecisionRequest(
            decision='approved',
            decided_by='admin-user',
            reason='Strong evidence and low projected impact.',
            metadata={'reason_code': 'safe-low-risk'},
        ),
    )

    assert decision is not None
    assert decision.decision_id == 7
    assert decision.proposal_key == 'prop_demo'
    assert decision.decision == 'approved'
    assert decision.decided_by == 'admin-user'
    assert pool.conn.executed, 'Expected proposal status update'
    _, args = pool.conn.executed[0]
    assert args[0] == 'prop_demo'
    assert args[1] == 'approved'
    assert args[2] == 'admin-user'


@pytest.mark.unit
def test_evidence_store_migration_creates_foundational_tables_and_governance_audit():
    sql = SQL_PATH.read_text(encoding='utf-8')

    assert 'CREATE TABLE IF NOT EXISTS evidence_records' in sql
    assert 'CREATE TABLE IF NOT EXISTS derived_features' in sql
    assert 'CREATE TABLE IF NOT EXISTS rule_proposals' in sql
    assert 'CREATE TABLE IF NOT EXISTS rule_decisions' in sql
    assert 'FOREIGN KEY (source_run_key)' in sql
    assert "CHECK (origin IN ('manual', 'imported', 'inferred', 'derived', 'test_fixture'))" in sql
    assert "CHECK (status IN ('pending_review', 'approved', 'rejected', 'auto_approved', 'implemented', 'superseded'))" in sql
