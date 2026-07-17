from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SQL_PATH = ROOT / 'sql' / '030_evidence_store_foundation.sql'
LIFECYCLE_SQL_PATH = ROOT / 'sql' / '036_evidence_record_lifecycle.sql'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

from evidence_store.api_models import (  # noqa: E402
    CanonicalEvidencePromotionRequest,
    EvidenceRecordCreateRequest,
    RuleDecisionRequest,
)
from evidence_store.models import DerivedFeature, EvidenceRecord, EvidenceSystemFocusArea, RuleProposal  # noqa: E402
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
            'id': 7,
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


class _EvidenceInsertConnection:
    def __init__(self, superseded_count: int = 0, existing_row: dict[str, object] | None = None):
        self.superseded_count = superseded_count
        self.existing_row = existing_row
        self.supersession_calls: list[tuple[str, tuple[object, ...]]] = []
        self.lookup_calls: list[tuple[str, tuple[object, ...]]] = []
        self.insert_calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchval(self, query: str, *args):
        self.supersession_calls.append((query, args))
        return self.superseded_count

    async def fetchrow(self, query: str, *args):
        if 'FROM evidence_records' in query and 'WHERE evidence_key = $1' in query:
            self.lookup_calls.append((query, args))
            return self.existing_row
        self.insert_calls.append((query, args))
        return {
            'evidence_key': args[0],
            'system_id64': args[1],
            'source_name': args[2],
            'origin': args[3],
            'subject_type': args[4],
            'subject_id': args[5],
            'evidence_type': args[6],
            'record_status': args[7],
            'freshness_status': args[8],
            'confidence': args[9],
            'summary': args[10],
            'source_record_id': args[11],
            'source_run_key': args[12],
            'observed_at': args[13],
            'collected_at': args[14],
            'expires_at': args[15],
            'value_json': json.loads(args[16]) if isinstance(args[16], str) else args[16],
            'provenance_json': json.loads(args[17]) if isinstance(args[17], str) else args[17],
            'tags_json': json.loads(args[18]) if isinstance(args[18], str) else args[18],
            'metadata_json': json.loads(args[19]) if isinstance(args[19], str) else args[19],
            'created_at': '2026-07-11T12:00:00+00:00',
            'updated_at': '2026-07-11T12:00:00+00:00',
        }


class _EvidenceInsertRetryConnection(_EvidenceInsertConnection):
    def __init__(self):
        super().__init__(superseded_count=1)
        self.insert_attempts = 0

    async def fetchrow(self, query: str, *args):
        if 'FROM evidence_records' in query and 'WHERE evidence_key = $1' in query:
            self.lookup_calls.append((query, args))
            return None
        self.insert_attempts += 1
        if self.insert_attempts == 1:
            raise store.asyncpg.exceptions.UniqueViolationError('duplicate active evidence subject')
        return await super().fetchrow(query, *args)


class _FreshnessSweepConnection:
    def __init__(self, results: list[int]):
        self.results = list(results)
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchval(self, query: str, *args):
        self.calls.append((query, args))
        if not self.results:
            raise AssertionError('Unexpected extra freshness sweep call')
        return self.results.pop(0)


class _FocusAreaConnection:
    async def fetchrow(self, query: str, *args):
        assert 'FROM systems' in query
        assert args == (42,)
        return {
            'id64': 42,
            'body_count': 15,
            'is_colonised': False,
            'is_being_colonised': True,
            'status_updated_at': '2026-07-11T10:15:00+00:00',
        }

    async def fetchval(self, query: str, *args):
        assert args == (42,)
        if 'FROM bodies' in query:
            return 12
        if 'FROM stations' in query:
            return 3
        if 'is_ringed = true' in query or 'ring_count > 0' in query:
            return 2
        if 'FROM body_scan_facts' in query:
            return 12
        if 'FROM body_rings' in query:
            return 2
        raise AssertionError(f'Unexpected focus-area query: {query}')


class _CanonicalPromotionConnection:
    async def fetchrow(self, query: str, *args):
        assert args == (42,)
        return {
            'id64': 42,
            'name': 'Test System',
            'body_count': 15,
            'is_colonised': False,
            'is_being_colonised': True,
            'updated_at': '2026-07-11T10:00:00+00:00',
        }

    async def fetchval(self, query: str, *args):
        if "to_regclass('public.station_body_links')" in query:
            return 'station_body_links'
        if 'COUNT(*)::int FROM bodies' in query:
            assert args == (42,)
            return 12
        if 'COUNT(*)::int FROM body_scan_facts WHERE system_address = $1 AND is_ringed IS TRUE' in query:
            assert args == (42,)
            return 4
        if 'COUNT(*)::int FROM body_scan_facts' in query and 'ring_count > 0' not in query:
            assert args == (42,)
            return 11
        if 'MAX(updated_at)::text FROM body_scan_facts' in query:
            assert args == (42,)
            return '2026-07-11T09:15:00+00:00'
        if 'COUNT(DISTINCT body_id)::int FROM body_rings' in query:
            assert args == (42,)
            return 3
        if 'MAX(updated_at)::text FROM body_rings' in query:
            assert args == (42,)
            return '2026-07-11T09:30:00+00:00'
        if 'COUNT(*)::int FROM stations' in query:
            assert args == (42,)
            return 3
        if 'COUNT(*)::int' in query and 'FROM station_body_links' in query:
            assert args == (42,)
            return 2
        if 'SELECT MAX(ts)::text' in query:
            assert args == (42,)
            return '2026-07-11T09:45:00+00:00'
        raise AssertionError(f'Unexpected canonical promotion query: {query}')


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
    record_list_calls: list[dict[str, object]] = []

    async def _observed_summary(_pool, _id64: int):
        return {'total_count': 3}

    async def _records(_pool, **kwargs):
        record_list_calls.append(kwargs)
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

    async def _focus_areas(_pool, *, system_id64: int, records):
        assert system_id64 == 42
        assert len(records) == 1
        return [
            EvidenceSystemFocusArea(
                key='station_set',
                label='Station set',
                posture='evidence_linked',
                summary='Latest station-set evidence is linked.',
                evidence_type='service_snapshot',
                evidence_key='evd_alpha',
            )
        ]

    monkeypatch.setattr(store, 'observed_fact_summary', _observed_summary)
    monkeypatch.setattr(store, 'list_evidence_records', _records)
    monkeypatch.setattr(store, 'list_derived_features', _features)
    monkeypatch.setattr(store, 'list_rule_proposals', _proposals)
    monkeypatch.setattr(store, '_build_evidence_focus_areas', _focus_areas)

    summary = await store.build_evidence_system_summary(object(), 42)

    assert summary.schema_version == 'evidence_store/v1'
    assert summary.system_id64 == 42
    assert summary.observed_fact_count == 3
    assert summary.imported_record_count == 1
    assert summary.derived_feature_count == 1
    assert summary.open_rule_proposal_count == 1
    assert summary.focus_areas[0].key == 'station_set'
    assert record_list_calls == [{
        'system_id64': 42,
        'record_status': 'active',
        'limit': 5,
        'offset': 0,
    }]
    assert summary.records[0].source_name == 'eddn'
    assert summary.derived_features[0].feature_name == 'mission_pressure'
    assert summary.open_rule_proposals[0].proposal_key == 'prop_alpha'


@pytest.mark.asyncio
async def test_build_evidence_focus_areas_prefers_active_evidence_then_falls_back_to_canonical_data():
    pool = _FakePool(_FocusAreaConnection())
    records = [
        EvidenceRecord(
            evidence_key='evd_col',
            system_id64=42,
            source_name='eddn',
            origin='imported',
            subject_type='system',
            subject_id='42',
            evidence_type='colonisation_status',
            record_status='active',
            freshness_status='current',
            confidence='high',
            summary='Colonisation state observed from the live relay.',
            source_record_id=None,
            source_run_key='run_eddn_1',
            observed_at='2026-07-11T10:15:00+00:00',
            collected_at='2026-07-11T10:15:30+00:00',
            expires_at=None,
            value={},
            provenance={},
        ),
    ]

    focus_areas = await store._build_evidence_focus_areas(
        pool,
        system_id64=42,
        records=records,
    )

    by_key = {focus.key: focus for focus in focus_areas}
    assert by_key['colonisation_status'].posture == 'evidence_linked'
    assert by_key['colonisation_status'].evidence_key == 'evd_col'
    assert by_key['station_set'].posture == 'canonical_present'
    assert '3 stations' in by_key['station_set'].summary
    assert by_key['body_completeness'].posture == 'canonical_present'
    assert '12/15 scanned bodies' in by_key['body_completeness'].summary
    assert by_key['ring_composition'].posture == 'canonical_present'
    assert '2/2 ring-bearing bodies' in by_key['ring_composition'].summary


@pytest.mark.asyncio
async def test_build_canonical_evidence_requests_returns_body_and_station_payloads():
    payloads, warnings = await store._build_canonical_evidence_requests(
        _CanonicalPromotionConnection(),
        system_id64=42,
        evidence_types=['body_completeness', 'station_set', 'colonisation_status', 'ring_composition'],
        source_run_key='run_demo',
        trigger_context='journal_promotion',
    )

    assert warnings == []
    assert [payload.evidence_type for payload in payloads] == [
        'body_completeness',
        'station_set',
        'colonisation_status',
        'ring_composition',
    ]
    body_payload, station_payload, colonisation_payload, ring_payload = payloads
    assert body_payload.source_name == 'canonical_app_data'
    assert body_payload.origin == 'derived'
    assert body_payload.source_run_key == 'run_demo'
    assert body_payload.observed_at == '2026-07-11T09:15:00+00:00'
    assert body_payload.value['total_body_count'] == 15
    assert body_payload.value['canonical_body_row_count'] == 12
    assert body_payload.value['scan_fact_count'] == 11
    assert body_payload.provenance['trigger_context'] == 'journal_promotion'
    assert station_payload.value['station_count'] == 3
    assert station_payload.value['linked_station_count'] == 2
    assert station_payload.observed_at == '2026-07-11T09:45:00+00:00'
    assert station_payload.provenance['source_run_key'] == 'run_demo'
    assert colonisation_payload.evidence_type == 'colonisation_status'
    assert colonisation_payload.value['status'] == 'being_colonised'
    assert colonisation_payload.observed_at == '2026-07-11T10:00:00+00:00'
    assert colonisation_payload.provenance['trigger_context'] == 'journal_promotion'
    assert ring_payload.evidence_type == 'ring_composition'
    assert ring_payload.value['ringed_body_count'] == 4
    assert ring_payload.value['ring_identity_count'] == 3
    assert ring_payload.observed_at == '2026-07-11T09:30:00+00:00'


@pytest.mark.unit
def test_canonical_evidence_promotion_request_rejects_unknown_types():
    request = CanonicalEvidencePromotionRequest()
    assert request.evidence_types == ['body_completeness', 'station_set']

    with pytest.raises(ValidationError):
        CanonicalEvidencePromotionRequest(evidence_types=['body_completeness', 'station_type_snapshot'])

    request = CanonicalEvidencePromotionRequest(
        evidence_types=['body_completeness', 'colonisation_status', 'ring_composition']
    )
    assert request.evidence_types == ['body_completeness', 'colonisation_status', 'ring_composition']


@pytest.mark.asyncio
async def test_promote_canonical_evidence_for_systems_dedupes_equivalent_active_records(monkeypatch: pytest.MonkeyPatch):
    body_request = EvidenceRecordCreateRequest(
        system_id64=42,
        source_name='canonical_app_data',
        origin='derived',
        subject_type='system',
        subject_id='42',
        evidence_type='body_completeness',
        freshness_status='current',
        confidence='high',
        summary='Body coverage already linked.',
        value={'total_body_count': 15, 'known_body_count': 15},
        provenance={},
        tags=['canonical_promotion'],
        metadata={},
    )
    station_request = EvidenceRecordCreateRequest(
        system_id64=42,
        source_name='canonical_app_data',
        origin='derived',
        subject_type='system',
        subject_id='42',
        evidence_type='station_set',
        freshness_status='current',
        confidence='medium',
        summary='Station set newly promoted.',
        value={'station_count': 3},
        provenance={},
        tags=['canonical_promotion'],
        metadata={},
    )

    async def _build_requests(_conn, *, system_id64: int, evidence_types, source_run_key=None, trigger_context=None):
        assert system_id64 == 42
        assert evidence_types == ['body_completeness', 'station_set']
        assert source_run_key == 'run_42'
        assert trigger_context == 'journal_promotion'
        return [body_request, station_request], ['builder-warning']

    async def _find_equivalent(_conn, payload):
        if payload['evidence_type'] == 'body_completeness':
            return EvidenceRecord(
                evidence_key='evd_existing_body',
                system_id64=42,
                source_name='canonical_app_data',
                origin='derived',
                subject_type='system',
                subject_id='42',
                evidence_type='body_completeness',
                record_status='active',
                freshness_status='current',
                confidence='high',
                summary='Body coverage already linked.',
                source_record_id=None,
                source_run_key=None,
                observed_at='2026-07-11T09:15:00+00:00',
                collected_at='2026-07-11T09:15:00+00:00',
                expires_at=None,
                value={'total_body_count': 15, 'known_body_count': 15},
                provenance={},
            )
        return None

    async def _create_with_conn(_conn, request: EvidenceRecordCreateRequest):
        return EvidenceRecord(
            evidence_key='evd_new_station',
            system_id64=request.system_id64,
            source_name=request.source_name,
            origin=request.origin,
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            evidence_type=request.evidence_type,
            record_status='active',
            freshness_status=request.freshness_status,
            confidence=request.confidence,
            summary=request.summary,
            source_record_id=request.source_record_id,
            source_run_key=request.source_run_key,
            observed_at=request.observed_at,
            collected_at=request.collected_at,
            expires_at=request.expires_at,
            value=request.value,
            provenance=request.provenance,
            tags=request.tags,
            metadata=request.metadata,
        )

    monkeypatch.setattr(store, '_build_canonical_evidence_requests', _build_requests)
    monkeypatch.setattr(store, '_find_equivalent_active_evidence_record', _find_equivalent)
    monkeypatch.setattr(store, '_create_evidence_record_with_conn', _create_with_conn)

    promotion = await store.promote_canonical_evidence_for_systems(
        object(),
        system_ids=[42],
        evidence_types=['body_completeness', 'station_set'],
        source_run_key='run_42',
        trigger_context='journal_promotion',
    )

    assert promotion['created_count'] == 1
    assert promotion['deduped_count'] == 1
    assert promotion['records'][0].evidence_type == 'station_set'
    assert promotion['warnings'][0] == 'builder-warning'
    assert any('already matches the active canonical evidence record' in warning for warning in promotion['warnings'])


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


@pytest.mark.asyncio
async def test_create_evidence_record_supersedes_prior_active_fact_and_stamps_lifecycle_metadata():
    pool = _FakePool(_EvidenceInsertConnection(superseded_count=2))

    record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=42,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id='42',
            evidence_type='operator_note',
            summary='New operator-confirmed note.',
            value={'note': 'latest'},
            metadata={'lane': 'operator'},
        ),
    )

    assert pool.conn.supersession_calls, 'Expected active evidence supersession pass'
    assert record.record_status == 'active'
    assert record.freshness_status == 'current'
    assert record.metadata['lane'] == 'operator'
    assert record.metadata['lifecycle']['superseded_record_count'] == 2
    assert record.evidence_key.startswith('evd_')


@pytest.mark.asyncio
async def test_create_evidence_record_does_not_supersede_existing_rows_when_new_record_is_quarantined():
    pool = _FakePool(_EvidenceInsertConnection(superseded_count=9))

    record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=42,
            source_name='frontier_journal',
            origin='imported',
            subject_type='body',
            subject_id='7',
            evidence_type='body_scan',
            record_status='quarantined',
            freshness_status='unknown',
            value={'planet_class': 'Rocky body'},
        ),
    )

    assert pool.conn.supersession_calls == []
    assert record.record_status == 'quarantined'
    assert record.metadata['lifecycle']['superseded_record_count'] == 0


@pytest.mark.asyncio
async def test_create_evidence_record_returns_existing_row_for_same_content_addressed_payload():
    existing_row = {
        'evidence_key': 'evd_existing',
        'system_id64': 42,
        'source_name': 'manual_operator_source',
        'origin': 'manual',
        'subject_type': 'system',
        'subject_id': '42',
        'evidence_type': 'operator_note',
        'record_status': 'active',
        'freshness_status': 'current',
        'confidence': 'medium',
        'summary': 'Existing evidence row.',
        'source_record_id': None,
        'source_run_key': None,
        'observed_at': None,
        'collected_at': '2026-07-11T12:00:00+00:00',
        'expires_at': None,
        'value_json': {'note': 'verified'},
        'provenance_json': {},
        'tags_json': [],
        'metadata_json': {},
        'created_at': '2026-07-11T12:00:00+00:00',
        'updated_at': '2026-07-11T12:00:00+00:00',
    }
    pool = _FakePool(_EvidenceInsertConnection(existing_row=existing_row))

    record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=42,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id='42',
            evidence_type='operator_note',
            value={'note': 'verified'},
        ),
    )

    assert pool.conn.lookup_calls, 'Expected deterministic-key lookup before insert'
    assert pool.conn.supersession_calls == []
    assert pool.conn.insert_calls == []
    assert record.evidence_key == 'evd_existing'


@pytest.mark.asyncio
async def test_create_evidence_record_retries_once_on_active_subject_unique_race():
    pool = _FakePool(_EvidenceInsertRetryConnection())

    record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=42,
            source_name='canonical_app_data',
            origin='derived',
            subject_type='system',
            subject_id='42',
            evidence_type='body_completeness',
            summary='Canonical body coverage updated.',
            value={'total_body_count': 15, 'known_body_count': 14},
            metadata={},
        ),
    )

    assert pool.conn.insert_attempts == 2
    assert len(pool.conn.supersession_calls) == 2
    assert record.evidence_type == 'body_completeness'


@pytest.mark.asyncio
async def test_sweep_evidence_record_freshness_summarises_expired_and_stale_updates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, '_EVIDENCE_FRESHNESS_POLICIES', {'operator_note': (10, 20)})
    pool = _FakePool(_FreshnessSweepConnection([1, 0, 2, 0, 3]))

    summary = await store.sweep_evidence_record_freshness(
        pool,
        now=store.datetime(2026, 7, 11, 12, 0, tzinfo=store.timezone.utc),
    )

    assert summary == {'expired': 3, 'stale': 3}
    assert len(pool.conn.calls) == 5


@pytest.mark.unit
def test_evidence_record_request_accepts_quarantined_and_rejects_inconsistent_superseded_states():
    record = EvidenceRecordCreateRequest(
        system_id64=42,
        source_name='frontier_journal',
        origin='imported',
        subject_type='body',
        subject_id='7',
        evidence_type='body_scan',
        record_status='quarantined',
        freshness_status='unknown',
    )
    assert record.record_status == 'quarantined'

    with pytest.raises(ValidationError):
        EvidenceRecordCreateRequest(
            system_id64=42,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id='42',
            evidence_type='operator_note',
            record_status='superseded',
            freshness_status='current',
        )


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


@pytest.mark.unit
def test_evidence_record_lifecycle_migration_adds_quarantine_and_active_subject_uniqueness():
    sql = LIFECYCLE_SQL_PATH.read_text(encoding='utf-8')

    assert "'quarantined'" in sql
    assert 'uq_evidence_records_active_subject_fact' in sql
    assert "WHERE record_status = 'active'" in sql
