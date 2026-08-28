"""Integration flow tests: V3 journal research lane (consent + CRE export).

Real Postgres fixture DB required (V3 baseline + 002 + 003 applied), plus
the parallel-task package ``edfinder_api.journal`` (Tasks 2/4). When either
is absent the suite skips with a clear reason — the orchestrator re-runs it
once the sibling modules land.

Flows covered (plan Task 3):
  7. Consent state machine: NONE -> GRANT (duplicate refused) -> export ->
     WITHDRAW -> batches superseded + supersede batch emitted -> export 403
     -> re-GRANT refused.
  8. Export determinism: two exports of unchanged data -> identical
     payload_sha256 and identical observation payloads.
  9. Replay: GET rebuilds the payload; SHA-256 of the rebuilt bytes matches
     the receipt. Cross-account batch read -> 404.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import uuid

import pytest

from edfinder_api.config import settings
from edfinder_api.routers import auth as auth_router

pytestmark = pytest.mark.skipif(
    not all(
        importlib.util.find_spec(f"edfinder_api.journal.{name}") is not None
        for name in ("event_contract", "identity", "store", "projections",
                     "consent", "sanitize", "export")
    ),
    reason="pending sibling modules: edfinder_api.journal (Tasks 2/4)",
)

_ORIGIN = {"Origin": "http://test"}


def _cookie(token: str) -> dict[str, str]:
    return {settings.auth_session_cookie_name: token}


async def _create_account(pool, subject: str) -> tuple[uuid.UUID, str]:
    identity = auth_router.FrontierIdentity(
        issuer=auth_router.FRONTIER_ISSUER,
        subject=subject,
        commander_name=f"CMDR {subject}",
    )
    user, raw_token, _ = await auth_router._upsert_account_and_session(pool, identity)
    return user.account_id, raw_token


def _ev(event_type, ts, h, file, offset, payload):
    return {
        "event_type": event_type,
        "event_timestamp": ts,
        "source_record_hash": h,
        "source_file": file,
        "source_offset": offset,
        "payload": payload,
    }


def _import_body() -> dict:
    """Same deterministic fixture as test_v3_journal_import_flow.py; the
    exported observation set is 8 (3 Scan + 1 FSSBodySignals + 1 CodexEntry +
    2 ScanOrganic + 1 SellOrganicData; FSDJump is travel-excluded)."""
    events = [
        _ev("FSDJump", "2026-08-28T10:00:00Z", "01" * 32, "J_A.log", 10,
            {"SystemAddress": 1001, "StarSystem": "Alpha"}),
        _ev("Scan", "2026-08-28T10:02:00Z", "02" * 32, "J_A.log", 20,
            {"SystemAddress": 1001, "BodyID": 5, "BodyName": "Alpha 1",
             "PlanetClass": "Rocky body"}),
        _ev("Scan", "2026-08-28T10:03:00Z", "03" * 32, "J_A.log", 30,
            {"SystemAddress": 1001, "BodyID": 6, "BodyName": "Alpha 2"}),
        _ev("FSSBodySignals", "2026-08-28T10:02:30Z", "04" * 32, "J_A.log", 40,
            {"SystemAddress": 1001, "BodyID": 5, "BodyName": "Alpha 1",
             "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 2}]}),
        _ev("CodexEntry", "2026-08-28T10:04:00Z", "05" * 32, "J_A.log", 50,
            {"EntryID": "C1", "Name": "Alpha Planet Discovered",
             "Category": "$Codex_Category_Geology;",
             "SubCategory": "$Codex_SubCategory_Planet;",
             "Region": "Inner Orion Spur", "System": "Alpha",
             "SystemAddress": 1001, "BodyID": 5}),
        _ev("ScanOrganic", "2026-08-28T10:04:30Z", "06" * 32, "J_A.log", 60,
            {"SystemAddress": 1001, "Body": 5, "BodyID": 5, "BodyName": "Alpha 1",
             "Genus": "$Genus_Type1;", "Species": "$Species_Type1;",
             "Variant": "V1", "ScanType": "Log"}),
        _ev("ScanOrganic", "2026-08-28T10:04:45Z", "07" * 32, "J_A.log", 70,
            {"SystemAddress": 1001, "Body": 5, "BodyID": 5, "BodyName": "Alpha 1",
             "Genus": "$Genus_Type1;", "Species": "$Species_Type1;",
             "Variant": "V1", "ScanType": "Sample"}),
        _ev("FSDJump", "2026-08-28T10:05:00Z", "08" * 32, "J_B.log", 10,
            {"SystemAddress": 2002, "StarSystem": "Beta"}),
        _ev("Scan", "2026-08-28T10:06:00Z", "09" * 32, "J_B.log", 20,
            {"SystemAddress": 2002, "BodyID": 7, "BodyName": "Beta 1"}),
        _ev("FSDJump", "2026-08-28T11:00:00Z", "10" * 32, "J_B.log", 30,
            {"SystemAddress": 1001, "StarSystem": "Alpha"}),
        _ev("SellOrganicData", "2026-08-28T12:00:00Z", "11" * 32, "J_B.log", 40,
            {"MarketID": 999, "BioData": [
                {"Genus": "$Genus_Type1;", "Species": "$Species_Type1;",
                 "Variant": "V1", "Value": 5000}]}),
    ]
    return {
        "parser_version": "journal-import-worker-v3-test",
        "files": [
            {"name": "J_A.log", "content_sha256": "aa" * 32, "size_bytes": 1024,
             "line_count": 7, "event_count": 7,
             "first_event_at": "2026-08-28T10:00:00Z",
             "last_event_at": "2026-08-28T10:04:45Z"},
            {"name": "J_B.log", "content_sha256": "bb" * 32, "size_bytes": 512,
             "line_count": 4, "event_count": 4,
             "first_event_at": "2026-08-28T10:05:00Z",
             "last_event_at": "2026-08-28T12:00:00Z"},
        ],
        "events": events,
    }


async def _import(client, token):
    return await client.post(
        "/api/v1/journal/imports",
        json=_import_body(),
        headers={**_ORIGIN, **_cookie(token)},
    )


async def _put_consent(client, token, decision: str):
    return await client.put(
        "/api/v1/journal/research-consent",
        json={"decision": decision},
        headers={**_ORIGIN, **_cookie(token)},
    )


async def _export(client, token, limit=1000):
    return await client.post(
        "/api/v1/journal/research-exports",
        json={"limit": limit},
        headers={**_ORIGIN, **_cookie(token)},
    )


async def test_consent_flow_and_supersede(client, pool):
    _, token = await _create_account(pool, f"consent-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200

    # NONE before any decision.
    resp = await client.get("/api/v1/journal/research-consent", headers=_cookie(token))
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["decision"] == "NONE"
    assert state["withdrawable"] is False

    # Export without an effective GRANT is blocked.
    resp = await _export(client, token)
    assert resp.status_code == 403, resp.text

    # GRANT.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["decision"] == "GRANT"
    assert state["consent_version"] == "1.0"
    assert state["sanitized_contract_version"] == "1.0.0"
    assert state["purpose"] == "CRE_RESEARCH_EVIDENCE"
    assert state["audience_code"] == "CRE"
    assert state["withdrawable"] is True

    # Duplicate GRANT is refused.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 409, resp.text

    # Export now succeeds with an exact receipt.
    resp = await _export(client, token)
    assert resp.status_code == 200, resp.text
    receipt = resp.json()
    assert receipt["observation_count"] == 8
    assert receipt["batch_state"] == "CREATED"
    assert re.fullmatch(r"[0-9a-f]{64}", receipt["payload_sha256"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{16,64}", receipt["lineage_token"])
    batch_id = receipt["export_batch_id"]

    # WITHDRAW: batches superseded + supersede batch emitted.
    resp = await _put_consent(client, token, "WITHDRAW")
    assert resp.status_code == 200, resp.text
    assert resp.json()["decision"] == "WITHDRAW"

    resp = await client.get("/api/v1/journal/research-consent", headers=_cookie(token))
    assert resp.status_code == 200
    assert resp.json()["decision"] == "WITHDRAW"

    # Export blocked again once withdrawn.
    resp = await _export(client, token)
    assert resp.status_code == 403, resp.text

    # Receipt list: original batch SUPERSEDED + a supersede batch emitted.
    resp = await client.get("/api/v1/journal/research-exports", headers=_cookie(token))
    assert resp.status_code == 200, resp.text
    batches = resp.json()
    by_id = {b["export_batch_id"]: b for b in batches}
    assert by_id.get(batch_id) is not None
    assert by_id[batch_id]["batch_state"] == "SUPERSEDED"
    supersede_batches = [b for b in batches if b["batch_state"] == "CREATED"]
    assert supersede_batches, "expected the supersede batch to be emitted"
    detail = await client.get(
        f"/api/v1/journal/research-exports/{supersede_batches[0]['export_batch_id']}",
        headers=_cookie(token),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["payload"].get("kind") == "supersede"

    # Re-grant after withdrawal is refused by the state machine.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 409, resp.text


async def test_export_determinism_byte_identical(client, pool):
    _, token = await _create_account(pool, f"det-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200

    r1 = (await _export(client, token)).json()
    r2 = (await _export(client, token)).json()
    assert r1["observation_count"] == r2["observation_count"] == 8
    assert r1["payload_sha256"] == r2["payload_sha256"]

    p1 = (await client.get(
        f"/api/v1/journal/research-exports/{r1['export_batch_id']}",
        headers=_cookie(token),
    )).json()["payload"]
    p2 = (await client.get(
        f"/api/v1/journal/research-exports/{r2['export_batch_id']}",
        headers=_cookie(token),
    )).json()["payload"]
    assert p1["observations"] == p2["observations"]
    assert json.dumps(p1["observations"], sort_keys=True) == json.dumps(
        p2["observations"], sort_keys=True
    )


async def test_export_replay_hash_matches_receipt(client, pool):
    _, token = await _create_account(pool, f"replay-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200
    receipt = (await _export(client, token)).json()

    resp = await client.get(
        f"/api/v1/journal/research-exports/{receipt['export_batch_id']}",
        headers=_cookie(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receipt"]["payload_sha256"] == receipt["payload_sha256"]
    rebuilt = json.dumps(body["payload"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(rebuilt).hexdigest() == receipt["payload_sha256"]

    # Cross-account read of a batch -> 404.
    _other_id, other_token = await _create_account(pool, f"replay-other-{uuid.uuid4().hex[:8]}")
    resp = await client.get(
        f"/api/v1/journal/research-exports/{receipt['export_batch_id']}",
        headers=_cookie(other_token),
    )
    assert resp.status_code == 404


async def test_research_lane_auth_and_origin(client, pool):
    # Unauthenticated -> 401.
    resp = await client.get("/api/v1/journal/research-consent")
    assert resp.status_code == 401
    resp = await client.put("/api/v1/journal/research-consent", json={"decision": "GRANT"})
    assert resp.status_code == 401
    resp = await client.post("/api/v1/journal/research-exports", json={})
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/research-exports")
    assert resp.status_code == 401

    # Authenticated but no trusted Origin -> 403 on writes.
    _, token = await _create_account(pool, f"origin-{uuid.uuid4().hex[:8]}")
    resp = await client.put(
        "/api/v1/journal/research-consent",
        json={"decision": "GRANT"},
        headers=_cookie(token),
    )
    assert resp.status_code == 403, resp.text

    # With the trusted origin the write succeeds; oversize limit -> 422.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/journal/research-exports",
        json={"limit": 10_001},
        headers={**_ORIGIN, **_cookie(token)},
    )
    assert resp.status_code == 422, resp.text
