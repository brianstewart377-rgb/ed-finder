"""Integration flow tests: account-scoped V3 journal personal lane.

Real Postgres fixture DB required (V3 baseline + 002 + 003 applied; see the
Task 1 rehearsal DSN), plus the parallel-task package ``edfinder_api.journal``
(Tasks 2/4). When either is absent the suite skips with a clear reason — the
orchestrator re-runs it once the sibling modules land.

Flows covered (plan Task 3):
  1. A imports -> receipt counts exact (and GET receipt reconstructs).
  2. A re-imports the same request -> files_skipped, zero new rows.
  3. B imports the same events -> full counts for B, A's rows untouched,
     B cannot read A's import (404), summaries are account-scoped.
  4. Unknown event_type / oversized events list / bad hash -> 422.
  5. Daily-event quota -> 429 (after seeding rows past the cap).
  6. Summary counters match hand-computed values.
"""

from __future__ import annotations

import importlib.util
import uuid

import pytest

from edfinder_api.config import settings
from edfinder_api.routers import auth as auth_router

pytestmark = pytest.mark.skipif(
    not all(
        importlib.util.find_spec(f"edfinder_api.journal.{name}") is not None
        for name in ("event_contract", "identity", "store", "projections")
    ),
    reason="pending sibling modules: edfinder_api.journal (Task 2)",
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
    """Deterministic 2-file / 11-event fixture.

    Hand-computed summary values: events_stored=11, unique_bodies=3,
    unique_bio_observations=1, systems_observed=2; export observation set = 8
    (3 Scan + 1 FSSBodySignals + 1 CodexEntry + 2 ScanOrganic +
    1 SellOrganicData).
    """
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


async def _import(client, token, body=None):
    return await client.post(
        "/api/v1/journal/imports",
        json=body or _import_body(),
        headers={**_ORIGIN, **_cookie(token)},
    )


async def test_import_receipt_counts_exact(client, pool):
    account_id, token = await _create_account(pool, f"import-a-{uuid.uuid4().hex[:8]}")
    resp = await _import(client, token)
    assert resp.status_code == 200, resp.text
    receipt = resp.json()
    assert receipt["status"] == "READY"
    assert receipt["files_received"] == 2
    assert receipt["files_admitted"] == 2
    assert receipt["files_skipped"] == 0
    assert receipt["events_received"] == 11
    assert receipt["events_inserted"] == 11
    assert receipt["duplicates_skipped"] == 0
    assert receipt["privacy_stripped_fields"] == 0
    assert receipt["event_counts"] == {
        "FSDJump": 3, "Scan": 3, "FSSBodySignals": 1,
        "CodexEntry": 1, "ScanOrganic": 2, "SellOrganicData": 1,
    }
    assert uuid.UUID(receipt["import_id"])
    assert receipt["started_at"] and receipt["finished_at"]

    # GET the same import: persisted subset of the receipt shape.
    resp = await client.get(
        f"/api/v1/journal/imports/{receipt['import_id']}",
        headers=_cookie(token),
    )
    assert resp.status_code == 200, resp.text
    fetched = resp.json()
    assert fetched["import_id"] == receipt["import_id"]
    assert fetched["status"] == "READY"
    assert fetched["files_admitted"] == 2
    assert fetched["events_inserted"] == 11

    # Rows really persisted for this account.
    stored = await pool.fetchval(
        "SELECT count(*) FROM v3_private.journal_event WHERE owner_account_id = $1",
        account_id,
    )
    assert stored == 11


async def test_reimport_is_idempotent(client, pool):
    account_id, token = await _create_account(pool, f"import-b-{uuid.uuid4().hex[:8]}")
    first = await _import(client, token)
    assert first.status_code == 200, first.text
    second = await _import(client, token)
    assert second.status_code == 200, second.text
    receipt = second.json()
    assert receipt["files_received"] == 2
    assert receipt["files_skipped"] == 2
    assert receipt["files_admitted"] == 0
    assert receipt["events_received"] == 11
    assert receipt["events_inserted"] == 0
    stored = await pool.fetchval(
        "SELECT count(*) FROM v3_private.journal_event WHERE owner_account_id = $1",
        account_id,
    )
    assert stored == 11


async def test_account_isolation_same_events(client, pool):
    account_a, token_a = await _create_account(pool, f"iso-a-{uuid.uuid4().hex[:8]}")
    account_b, token_b = await _create_account(pool, f"iso-b-{uuid.uuid4().hex[:8]}")
    body = _import_body()

    resp_a = await _import(client, token_a, body=body)
    assert resp_a.status_code == 200, resp_a.text
    import_id_a = resp_a.json()["import_id"]

    resp_b = await _import(client, token_b, body=body)
    assert resp_b.status_code == 200, resp_b.text
    receipt_b = resp_b.json()
    assert receipt_b["files_admitted"] == 2
    assert receipt_b["events_inserted"] == 11

    # Both accounts hold exactly their own 11 rows.
    for account_id in (account_a, account_b):
        n = await pool.fetchval(
            "SELECT count(*) FROM v3_private.journal_event WHERE owner_account_id = $1",
            account_id,
        )
        assert n == 11

    # B cannot read A's import.
    resp = await client.get(
        f"/api/v1/journal/imports/{import_id_a}",
        headers=_cookie(token_b),
    )
    assert resp.status_code == 404

    # Summaries are account-scoped and never bleed.
    summary_a = await client.get("/api/v1/journal/summary", headers=_cookie(token_a))
    summary_b = await client.get("/api/v1/journal/summary", headers=_cookie(token_b))
    assert summary_a.status_code == 200 and summary_b.status_code == 200
    assert summary_a.json()["events_stored"] == 11
    assert summary_b.json()["events_stored"] == 11
    assert summary_a.json()["events_stored"] + summary_b.json()["events_stored"] == 22


async def test_request_validation_422s(client, pool):
    _, token = await _create_account(pool, f"val-{uuid.uuid4().hex[:8]}")
    base = _import_body()

    # Unknown event_type -> 422 (allowlist-validated before any store call).
    bad_type = {**base, "events": [
        _ev("TotallyFakeEvent", "2026-08-28T10:00:00Z", "ff" * 32, "J.log", 0, {})]}
    resp = await _import(client, token, body=bad_type)
    assert resp.status_code == 422, resp.text

    # Bad content hash -> 422.
    bad_hash = {**base, "events": [
        _ev("FSDJump", "2026-08-28T10:00:00Z", "xyz", "J.log", 0,
            {"SystemAddress": 1})]}
    resp = await _import(client, token, body=bad_hash)
    assert resp.status_code == 422, resp.text

    # Oversized events list (50_001 > 50_000) -> 422.
    oversized = {**base, "events": [
        _ev("FSDJump", "2026-08-28T10:00:00Z", ("%02x" % (i % 256)) * 32, "J.log",
            i, {"SystemAddress": i})
        for i in range(50_001)
    ]}
    resp = await _import(client, token, body=oversized)
    assert resp.status_code == 422, resp.text

    # Empty files list -> 422.
    no_files = {**base, "files": []}
    resp = await _import(client, token, body=no_files)
    assert resp.status_code == 422, resp.text

    # Event count above the per-file cap -> 422.
    big_file = {**base, "files": [{**base["files"][0], "event_count": 1_000_001}]}
    resp = await _import(client, token, body=big_file)
    assert resp.status_code == 422, resp.text

    # Cookie without the trusted origin -> 403 on the write.
    resp = await client.post(
        "/api/v1/journal/imports",
        json=_import_body(),
        headers=_cookie(token),
    )
    assert resp.status_code == 403, resp.text


async def _seed_event_rows(pool, account_id, n: int) -> None:
    """Seed ``n`` journal_event rows for the account through a minimal
    acquisition chain (mirrors the store's bootstrap), bypassing the API."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO v3_source.source
                       (source_code, display_name, authority_class)
                   VALUES ('frontier_journal', 'Frontier Journal', 'FRONTIER_DIRECT')
                   ON CONFLICT (source_code) DO NOTHING"""
            )
            source_id = await conn.fetchval(
                "SELECT source_id FROM v3_source.source WHERE source_code = 'frontier_journal'"
            )
            await conn.execute(
                """INSERT INTO v3_source.source_rights_policy
                       (source_id, policy_version, rights_class, retention_class,
                        distribution_allowed, effective_at)
                   VALUES ($1, '1.0', 'PRIVATE_ONLY', 'PRIVATE_USER_CONTENT',
                           false, now())
                   ON CONFLICT (source_id, policy_version) DO NOTHING""",
                source_id,
            )
            rights_policy_id = await conn.fetchval(
                """SELECT rights_policy_id FROM v3_source.source_rights_policy
                    WHERE source_id = $1 AND policy_version = '1.0'""",
                source_id,
            )
            artifact_id = uuid.uuid4()
            await conn.execute(
                """INSERT INTO v3_source.source_artifact
                       (artifact_id, source_id, rights_policy_id, artifact_kind,
                        content_sha256, size_bytes, media_type, retrieved_at,
                        retention_class)
                   VALUES ($1, $2, $3, 'JOURNAL', $4, 1, 'text/plain', now(),
                           'PRIVATE_USER_CONTENT')
                   ON CONFLICT (source_id, content_sha256) DO NOTHING""",
                artifact_id, source_id, rights_policy_id, b"\x55" * 32,
            )
            run_id = uuid.uuid4()
            await conn.execute(
                """INSERT INTO v3_source.source_run
                       (source_run_id, source_id, rights_policy_id, artifact_id,
                        acquisition_kind, trust_zone, run_state, idempotency_key,
                        started_at, completed_at, importer_version,
                        importer_code_sha256, importer_config_sha256,
                        normalizer_version, normalizer_sha256)
                   VALUES ($1, $2, $3, $4, 'JOURNAL_IMPORT', 'PRIVATE', 'SUCCEEDED',
                           $5, now(), now(), 'test', $6, $6, 'test', $6)""",
                run_id, source_id, rights_policy_id, artifact_id,
                f"seed-{uuid.uuid4().hex}", b"\x00" * 32,
            )
            import_id = uuid.uuid4()
            await conn.execute(
                """INSERT INTO v3_private.private_import
                       (private_import_id, owner_account_id, source_run_id,
                        import_kind, import_state)
                   VALUES ($1, $2, $3, 'journal_upload_v1', 'READY')""",
                import_id, account_id, run_id,
            )
            file_id = uuid.uuid4()
            await conn.execute(
                """INSERT INTO v3_private.journal_import_file
                       (journal_file_id, private_import_id, owner_account_id,
                        file_name, content_sha256, size_bytes, line_count,
                        event_count)
                   VALUES ($1, $2, $3, 'seed.log', $4, 1, 1, $5)""",
                file_id, import_id, account_id, b"\x66" * 32, n,
            )
            await conn.execute(
                """INSERT INTO v3_private.journal_event
                       (journal_event_id, owner_account_id, private_import_id,
                        journal_file_id, source_run_id, event_type, event_key,
                        event_payload, event_timestamp, source_record_hash,
                        source_offset)
                   SELECT gen_random_uuid(), $1, $2, $3, $4, 'FSDJump',
                          jsonb_build_object('SystemAddress', (1000000000 + i)::text),
                          jsonb_build_object('StarSystem', 'Seed ' || i,
                                              'SystemAddress', 1000000000 + i),
                          now(), $5, i
                     FROM generate_series(1, $6) AS i""",
                account_id, import_id, file_id, run_id, b"\x11" * 32, n,
            )


async def test_daily_quota_429(client, pool):
    from edfinder_api.journal.event_contract import MAX_DAILY_EVENTS_PER_ACCOUNT

    account_id, token = await _create_account(pool, f"quota-{uuid.uuid4().hex[:8]}")
    await _seed_event_rows(pool, account_id, MAX_DAILY_EVENTS_PER_ACCOUNT)

    # One more event pushes received + stored past the daily cap.
    body = _import_body()
    body["events"] = body["events"][:1]
    resp = await _import(client, token, body=body)
    assert resp.status_code == 429, resp.text

    # The rejected import persisted nothing.
    stored = await pool.fetchval(
        "SELECT count(*) FROM v3_private.journal_event WHERE owner_account_id = $1",
        account_id,
    )
    assert stored == MAX_DAILY_EVENTS_PER_ACCOUNT


async def test_summary_counters_hand_computed(client, pool):
    _, token = await _create_account(pool, f"sum-{uuid.uuid4().hex[:8]}")
    resp = await _import(client, token)
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/journal/summary", headers=_cookie(token))
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["events_stored"] == 11
    assert summary["unique_bodies"] == 3
    assert summary["unique_bio_observations"] == 1
    assert summary["systems_observed"] == 2
    assert summary["last_imported_at"] is not None
    assert summary["event_counts"]["FSDJump"] == 3
    assert summary["event_counts"]["Scan"] == 3
    assert summary["imported_files"] == 2


async def test_unauthenticated_401(client):
    resp = await client.post("/api/v1/journal/imports", json=_import_body())
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/summary")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/systems")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/bodies")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/codex")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/organics")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/journal/sales")
    assert resp.status_code == 401
