"""Research-export pause through FastAPI, without a database."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from edfinder_api.auth import AuthenticatedUser, settings
from edfinder_api.deps import get_pool
from edfinder_api.journal import consent, export
from edfinder_api.routers import v3_journal_research as research_router

ORIGIN = "http://testserver"
CONSENT_URL = "/api/v1/journal/research-consent"
EXPORT_URL = "/api/v1/journal/research-exports"
PAUSED_WRITES = [
    ("post", EXPORT_URL, {}),
    ("put", CONSENT_URL, {"decision": "GRANT"}),
]
GRANT = {
    "decision": "GRANT",
    "consent_version": "1.0",
    "sanitized_contract_version": "1.0.0",
    "purpose": "CRE_RESEARCH_EVIDENCE",
    "audience_code": "CRE",
    "decided_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
}

pytestmark = pytest.mark.unit


@pytest.fixture
async def research_client(monkeypatch):
    user = AuthenticatedUser(
        account_id=uuid.uuid4(), commander_name="Researcher", is_owner=False,
        recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4(),
    )
    authenticate = AsyncMock(return_value=user)
    consent_read = AsyncMock(return_value=None)
    record_consent = AsyncMock()
    build_export = AsyncMock()
    supersede = AsyncMock()
    monkeypatch.setattr(research_router, "get_request_user", authenticate)
    monkeypatch.setattr(settings, "cors_origins", ORIGIN)
    monkeypatch.setattr(consent, "effective_consent", consent_read)
    monkeypatch.setattr(consent, "record_consent", record_consent)
    monkeypatch.setattr(export, "build_export", build_export)
    monkeypatch.setattr(export, "supersede_lineage_batches", supersede)
    pool = AsyncMock()
    app = FastAPI()
    app.include_router(research_router.router)
    app.dependency_overrides[get_pool] = lambda: pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        yield SimpleNamespace(
            client=client, pool=pool, user=user, authenticate=authenticate,
            consent_read=consent_read, record_consent=record_consent,
            build_export=build_export, supersede=supersede,
        )


def assert_no_research_access(stubs):
    stubs.consent_read.assert_not_called()
    stubs.record_consent.assert_not_called()
    stubs.build_export.assert_not_called()
    stubs.supersede.assert_not_called()
    assert stubs.pool.mock_calls == []


@pytest.mark.parametrize("method,url,body", PAUSED_WRITES)
async def test_paused_writes_refuse_before_research_access(research_client, method, url, body):
    stubs = research_client
    assert research_router.RESEARCH_EXPORT_PAUSED is True
    response = await stubs.client.request(method, url, json=body, headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "type": "https://httpstatuses.com/503",
            "title": "Research exports paused",
            "status": 503,
            "detail": (
                "Research exports are paused because they cannot yet carry "
                "colonisation events the CRE can use."
            ),
            "reason": "research_export_paused",
        },
    }
    stubs.authenticate.assert_awaited_once()
    assert_no_research_access(stubs)


@pytest.mark.parametrize("method,url,body", PAUSED_WRITES)
@pytest.mark.parametrize("authenticated,origin,status,detail", [
    (False, "https://untrusted.example", 401, "Sign-in required"),
    (True, None, 403, "Trusted request origin required"),
    (True, "https://untrusted.example", 403, "Trusted request origin required"),
])
async def test_auth_and_origin_precede_pause(
    research_client, method, url, body, authenticated, origin, status, detail,
):
    stubs = research_client
    if not authenticated:
        stubs.authenticate.return_value = None
    headers = {"Origin": origin} if origin is not None else {}
    response = await stubs.client.request(method, url, json=body, headers=headers)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    stubs.authenticate.assert_awaited_once()
    assert_no_research_access(stubs)


async def test_withdraw_still_records_consent_and_supersedes_every_lineage(research_client):
    stubs = research_client
    stubs.consent_read.return_value = GRANT
    stubs.record_consent.return_value = {**GRANT, "decision": "WITHDRAW"}
    stubs.pool.fetch.return_value = [{"lineage_token": "first"}, {"lineage_token": "second"}]
    response = await stubs.client.put(
        CONSENT_URL, json={"decision": "WITHDRAW"}, headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        **GRANT, "decision": "WITHDRAW", "decided_at": GRANT["decided_at"].isoformat(),
        "withdrawable": False,
    }
    stubs.consent_read.assert_awaited_once_with(stubs.pool, stubs.user.account_id)
    assert stubs.supersede.await_args_list == [
        call(stubs.pool, stubs.user.account_id, "first"),
        call(stubs.pool, stubs.user.account_id, "second"),
    ]
    stubs.record_consent.assert_awaited_once_with(
        stubs.pool, stubs.user.account_id, decision="WITHDRAW",
    )
    stubs.build_export.assert_not_called()


async def test_withdraw_without_grant_keeps_consent_conflict(research_client):
    stubs = research_client
    response = await stubs.client.put(
        CONSENT_URL, json={"decision": "WITHDRAW"}, headers={"Origin": ORIGIN},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "No active GRANT to withdraw"}
    stubs.consent_read.assert_awaited_once_with(stubs.pool, stubs.user.account_id)
    stubs.record_consent.assert_not_called()
    stubs.supersede.assert_not_called()
    stubs.build_export.assert_not_called()
    assert stubs.pool.mock_calls == []
