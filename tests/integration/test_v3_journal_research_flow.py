"""Integration flow tests: V3 journal research lane (consent + EDRE export).

Real Postgres fixture DB required (V3 baseline + 002 + 003 applied), plus
the parallel-task package ``edfinder_api.journal`` (Tasks 2/4). When either
is absent the suite skips with a clear reason — the orchestrator re-runs it
once the sibling modules land.

Flows covered (plan Task 3):
  7. Consent state machine: NONE -> GRANT (duplicate refused) -> export ->
     WITHDRAW -> batches superseded + supersede batch emitted -> export 403
     -> re-GRANT refused.
  8. Export determinism: two exports of unchanged data differ only in the
     receipt-pinned fields (export_batch_id, lineage_token, generated_at);
     byte identity holds after pinning from the receipts.
  9. Replay: GET rebuilds the payload; SHA-256 of the rebuilt bytes matches
     the receipt. Cross-account batch read -> 404.
  10. (3.1 regression) limit-truncated export replays byte-identically.
  11. (3.2 regression) same-instant superseded batches replay consistently.
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

# The trusted browser origin is whatever CORS_ORIGINS allows (conftest sets
# http://test; the Task 1 rehearsal README prescribes http://localhost:5173).
_ORIGIN = {"Origin": settings.cors_origins.split(",")[0].strip()}


@pytest.fixture(scope="session", autouse=True)
def _v2_table_shim(v3_fixture_db_ready, v3_v2_table_shim):
    """Session-scoped dependency (body lives in conftest): the V3-only fixture
    DB lacks the V2 tables conftest's ``clean_db`` TRUNCATEs; the shared
    ``v3_v2_table_shim`` fixture creates empty stand-ins. Autouse so the
    TRUNCATE always succeeds for these tests."""


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
    """Deterministic fixture restricted to events the export sanitizer can
    satisfy (system_name present via StarSystem, or SellOrganicData which
    deliberately omits system identity). CodexEntry/ScanOrganic/SAAScanComplete
    are deliberately absent here: Task 2's payload allowlists cannot carry
    SystemName/StarSystem for those types while Task 4's sanitizer requires it
    (cross-task gap, reported) — the import lane covers them separately in
    test_v3_journal_import_flow.py. Exported observation set = 6 (3 Scan +
    1 FSSBodySignals + 1 FSSDiscoveryScan + 1 SellOrganicData)."""
    events = [
        _ev("FSDJump", "2026-08-28T10:00:00Z", "01" * 32, "J_A.log", 10,
            {"SystemAddress": 1001, "StarSystem": "Alpha"}),
        _ev("Scan", "2026-08-28T10:02:00Z", "02" * 32, "J_A.log", 20,
            {"SystemAddress": 1001, "StarSystem": "Alpha", "BodyID": 5,
             "BodyName": "Alpha 1", "PlanetClass": "Rocky body"}),
        _ev("Scan", "2026-08-28T10:03:00Z", "03" * 32, "J_A.log", 30,
            {"SystemAddress": 1001, "StarSystem": "Alpha", "BodyID": 6,
             "BodyName": "Alpha 2"}),
        _ev("FSSBodySignals", "2026-08-28T10:02:30Z", "04" * 32, "J_A.log", 40,
            {"SystemAddress": 1001, "StarSystem": "Alpha", "BodyID": 5,
             "BodyName": "Alpha 1",
             "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 2}]}),
        _ev("FSSDiscoveryScan", "2026-08-28T10:03:30Z", "05" * 32, "J_A.log", 50,
            {"SystemAddress": 1001, "StarSystem": "Alpha", "Progress": 1.0,
             "BodyCount": 6, "NonBodyCount": 0}),
        _ev("FSDJump", "2026-08-28T10:05:00Z", "06" * 32, "J_B.log", 10,
            {"SystemAddress": 2002, "StarSystem": "Beta"}),
        _ev("Scan", "2026-08-28T10:06:00Z", "07" * 32, "J_B.log", 20,
            {"SystemAddress": 2002, "StarSystem": "Beta", "BodyID": 7,
             "BodyName": "Beta 1"}),
        _ev("FSDJump", "2026-08-28T11:00:00Z", "08" * 32, "J_B.log", 30,
            {"SystemAddress": 1001, "StarSystem": "Alpha"}),
        _ev("SellOrganicData", "2026-08-28T12:00:00Z", "09" * 32, "J_B.log", 40,
            {"MarketID": 999, "BioData": [
                {"Genus": "$Genus_Type1;", "Species": "$Species_Type1;",
                 "Variant": "V1", "Value": 5000}]}),
    ]
    return {
        "parser_version": "journal-import-worker-v3-test",
        "files": [
            {"name": "J_A.log", "content_sha256": "aa" * 32, "size_bytes": 1024,
             "line_count": 5, "event_count": 5,
             "first_event_at": "2026-08-28T10:00:00Z",
             "last_event_at": "2026-08-28T10:03:30Z"},
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
        headers=_ORIGIN, cookies=_cookie(token),
    )


async def _put_consent(client, token, decision: str):
    return await client.put(
        "/api/v1/journal/research-consent",
        json={"decision": decision},
        headers=_ORIGIN, cookies=_cookie(token),
    )


async def _export(client, token, limit=1000):
    return await client.post(
        "/api/v1/journal/research-exports",
        json={"limit": limit},
        headers=_ORIGIN, cookies=_cookie(token),
    )


async def test_consent_flow_and_supersede(client, pool):
    _, token = await _create_account(pool, f"consent-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200

    # NONE before any decision.
    resp = await client.get("/api/v1/journal/research-consent", cookies=_cookie(token))
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
    assert receipt["observation_count"] == 6
    assert receipt["batch_state"] == "CREATED"
    assert re.fullmatch(r"[0-9a-f]{64}", receipt["payload_sha256"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{16,64}", receipt["lineage_token"])
    batch_id = receipt["export_batch_id"]

    # WITHDRAW: batches superseded + supersede batch emitted.
    resp = await _put_consent(client, token, "WITHDRAW")
    assert resp.status_code == 200, resp.text
    assert resp.json()["decision"] == "WITHDRAW"

    resp = await client.get("/api/v1/journal/research-consent", cookies=_cookie(token))
    assert resp.status_code == 200
    assert resp.json()["decision"] == "WITHDRAW"

    # Export blocked again once withdrawn.
    resp = await _export(client, token)
    assert resp.status_code == 403, resp.text

    # Receipt list: original batch SUPERSEDED + a supersede batch emitted.
    # The supersede batch row itself is also SUPERSEDED (its payload is the
    # kind:"supersede" record), so distinguish it by replaying each batch.
    resp = await client.get("/api/v1/journal/research-exports", cookies=_cookie(token))
    assert resp.status_code == 200, resp.text
    batches = resp.json()
    by_id = {b["export_batch_id"]: b for b in batches}
    assert by_id.get(batch_id) is not None
    assert by_id[batch_id]["batch_state"] == "SUPERSEDED"
    assert len(batches) >= 2, "expected the original batch plus a supersede batch"
    supersede_batch_id = None
    for batch in batches:
        detail = await client.get(
            f"/api/v1/journal/research-exports/{batch['export_batch_id']}",
            cookies=_cookie(token),
        )
        assert detail.status_code == 200, detail.text
        if detail.json()["payload"].get("kind") == "supersede":
            supersede_batch_id = batch["export_batch_id"]
    assert supersede_batch_id is not None, "expected the supersede batch to be emitted"

    # Re-grant after withdrawal is refused by the state machine.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 409, resp.text


async def test_export_determinism_byte_identical(client, pool):
    """Binding replay contract: each build stamps export_batch_id,
    lineage_token and generated_at at build time, so two builds over
    unchanged data differ ONLY in those three receipt-pinned fields. The
    GET replay rebuild pins all three from the receipt — byte identity is
    asserted after pinning, and each rebuilt payload's SHA-256 matches its
    own receipt."""
    _, token = await _create_account(pool, f"det-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200

    r1 = (await _export(client, token)).json()
    r2 = (await _export(client, token)).json()
    assert r1["observation_count"] == r2["observation_count"] == 6

    body1 = (await client.get(
        f"/api/v1/journal/research-exports/{r1['export_batch_id']}",
        cookies=_cookie(token),
    )).json()
    body2 = (await client.get(
        f"/api/v1/journal/research-exports/{r2['export_batch_id']}",
        cookies=_cookie(token),
    )).json()
    assert body1["receipt"]["payload_sha256"] == r1["payload_sha256"]
    assert body2["receipt"]["payload_sha256"] == r2["payload_sha256"]
    p1, p2 = body1["payload"], body2["payload"]

    # Observations and every non-pinned field are byte-identical.
    assert p1["observations"] == p2["observations"]
    pinned = {"export_batch_id", "lineage_token", "generated_at"}
    for key in p1:
        if key not in pinned:
            assert p1[key] == p2[key], f"field {key!r} differs between deterministic builds"
    assert p1["export_batch_id"] == r1["export_batch_id"]
    assert p2["export_batch_id"] == r2["export_batch_id"]

    # Pinning the receipt values on either payload yields identical bytes.
    p1_pinned = {**p1, **{k: p2[k] for k in pinned}}
    def _bytes(payload: dict) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    assert _bytes(p1_pinned) == _bytes(p2)
    assert _bytes({**p2, **{k: p1[k] for k in pinned}}) == _bytes(p1)


async def test_export_replay_hash_matches_receipt(client, pool):
    _, token = await _create_account(pool, f"replay-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200
    receipt = (await _export(client, token)).json()

    resp = await client.get(
        f"/api/v1/journal/research-exports/{receipt['export_batch_id']}",
        cookies=_cookie(token),
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
        cookies=_cookie(other_token),
    )
    assert resp.status_code == 404


async def test_export_replay_limited_batch_matches_receipt(client, pool):
    """3.1 regression: a limit-truncated export replays byte-identically.

    The raw-row limit must be persisted in the receipt manifest
    (manifest.limit) at export time and read back by the GET rebuild, so a
    truncated export's rebuilt SHA matches its receipt. Fixture: 9 events,
    6 exportable; LIMIT 5 raw rows (SQL order: 3 FSDJump travel-excluded
    first, then FSSBodySignals + FSSDiscoveryScan) -> 2 sanitized
    observations — the truncation lands inside the excluded-event prefix,
    proving the limit applies to raw rows BEFORE sanitization.
    """
    _, token = await _create_account(pool, f"replay-lim-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200

    receipt = (await _export(client, token, limit=5)).json()
    assert receipt["observation_count"] == 2

    resp = await client.get(
        f"/api/v1/journal/research-exports/{receipt['export_batch_id']}",
        cookies=_cookie(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receipt"]["payload_sha256"] == receipt["payload_sha256"]
    rebuilt = json.dumps(body["payload"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(rebuilt).hexdigest() == receipt["payload_sha256"]


async def test_supersede_replay_same_second_batches(client, pool):
    """3.2 regression: supersede replay is consistent when superseded
    batches share one created_at instant.

    The superseded-batch ordering must match on BOTH sides (Task 4's
    supersede build and the router's rebuild): (created_at,
    export_batch_id). Two batches are forced to an identical created_at via
    UPDATE, then WITHDRAW; the emitted supersede batch must replay with a
    matching SHA and uuid-sorted batch ids. Without the export-side
    tiebreak this fails whenever creation order differs from uuid order
    (~50% of no-fix runs).
    """
    _, token = await _create_account(pool, f"ss-replay-{uuid.uuid4().hex[:8]}")
    assert (await _import(client, token)).status_code == 200
    assert (await _put_consent(client, token, "GRANT")).status_code == 200
    r1 = (await _export(client, token)).json()
    r2 = (await _export(client, token)).json()

    # Every export carries its OWN lineage token (per-export lineage), so
    # the two batches are pinned onto ONE token here — otherwise WITHDRAW
    # supersedes each token separately and emits two supersede batches.
    # Force one exact created_at instant for both receipts so the ordering
    # depends solely on the (created_at, export_batch_id) tiebreak.
    await pool.execute(
        "UPDATE v3_private.research_export_batch "
        "SET created_at = '2026-08-28T12:00:00.000000+00:00', "
        "    lineage_token = $1 "
        "WHERE export_batch_id = ANY($2::uuid[])",
        r1["lineage_token"],
        [uuid.UUID(r1["export_batch_id"]), uuid.UUID(r2["export_batch_id"])],
    )

    resp = await _put_consent(client, token, "WITHDRAW")
    assert resp.status_code == 200, resp.text

    # The supersede batch is the only receipt with observation_count == 0.
    batches = (await client.get(
        "/api/v1/journal/research-exports", cookies=_cookie(token)
    )).json()
    supersede_batches = [b for b in batches if b["observation_count"] == 0]
    assert len(supersede_batches) == 1, "expected exactly one supersede batch"
    detail = await client.get(
        f"/api/v1/journal/research-exports/{supersede_batches[0]['export_batch_id']}",
        cookies=_cookie(token),
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()["payload"]
    assert payload.get("kind") == "supersede"
    assert payload["superseded_export_batch_ids"] == sorted(
        [r1["export_batch_id"], r2["export_batch_id"]]
    )


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
        cookies=_cookie(token),
    )
    assert resp.status_code == 403, resp.text

    # With the trusted origin the write succeeds; oversize limit -> 422.
    resp = await _put_consent(client, token, "GRANT")
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/journal/research-exports",
        json={"limit": 10_001},
        headers=_ORIGIN, cookies=_cookie(token),
    )
    assert resp.status_code == 422, resp.text
