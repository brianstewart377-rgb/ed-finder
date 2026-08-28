"""V3 journal-intelligence performance test (Task 7).

Real-Postgres bulk-import throughput for the journal-events lane:

1. Generate the deterministic 100k-line synthetic journal
   (``tests/fixtures/journal_v3/generate_large_journal.py``).
2. Import it through ``edfinder_api.journal.store.import_journal_batch`` in
   10 batches of ~10k events; measure wall time per batch and assert a
   sustained >= 2,000 events/s.
3. Incrementally re-import a 1k-event slice; measure its wall time (semantic
   dedupe path — all rows are duplicates).

The database URL comes from the Task 1 rehearsal receipt
(``artifacts/v3-journal-intelligence-20260828/rehearsal/README.md``) or the
``EDFINDER_V3_DATABASE_URL`` env var. If neither exists, or the Task 2 store
module has not landed, the test skips honestly — no fake numbers.

Measured numbers are also appended to
``artifacts/v3-journal-intelligence-20260828/perf-results.jsonl`` for the
Task 10 artifacts bundle.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPO_ROOT / "tests" / "fixtures" / "journal_v3" / "generate_large_journal.py"
REHEARSAL_README = (
    REPO_ROOT / "artifacts" / "v3-journal-intelligence-20260828" / "rehearsal" / "README.md"
)
PERF_RESULTS_PATH = (
    REPO_ROOT / "artifacts" / "v3-journal-intelligence-20260828" / "perf-results.jsonl"
)

BATCH_SIZE = 10_000
INCREMENTAL_EVENTS = 1_000
MIN_EVENTS_PER_SECOND = 2_000


def _load_generator() -> object:
    spec = importlib.util.spec_from_file_location("generate_large_journal", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _database_url() -> str | None:
    env_url = os.environ.get("EDFINDER_V3_DATABASE_URL")
    if env_url:
        return env_url
    if REHEARSAL_README.exists():
        for raw_line in REHEARSAL_README.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


def _url_is_loopback(url: str) -> bool:
    """Fail-closed loopback guard mirroring tests/helpers/db_isolation.py."""
    parsed = urlparse(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1", None}:
        return False
    if parsed.port == 5432 and os.environ.get("EDFINDER_ALLOW_HOST_5432_TEST_DB") != "yes":
        return False
    return True


def _line_to_event(line: str, source_file: str, source_offset: int) -> dict:
    record = json.loads(line)
    payload = {key: value for key, value in record.items() if key not in ("event", "timestamp")}
    timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "event_type": record["event"],
        "event_timestamp": timestamp,
        "source_record_hash": hashlib.sha256(line.encode("utf-8")).hexdigest(),
        "source_file": source_file,
        "source_offset": source_offset,
        "payload": payload,
    }


def test_bulk_import_throughput_and_incremental() -> None:
    url = _database_url()
    if url is None:
        pytest.skip(
            "no V3 rehearsal DATABASE_URL (rehearsal README absent, "
            "EDFINDER_V3_DATABASE_URL unset) - Task 1 rehearsal not landed"
        )
    if not _url_is_loopback(url):
        pytest.skip(f"refusing non-loopback DB target (fail-closed): {urlparse(url).hostname}")
    try:
        from edfinder_api.journal.store import import_journal_batch
    except ImportError as exc:
        pytest.skip(f"edfinder_api.journal.store not importable (Task 2 not landed): {exc}")
    try:
        import asyncpg
    except ImportError as exc:
        pytest.skip(f"asyncpg not installed: {exc}")

    generator = _load_generator()
    lines = generator.generate_lines(100_000, seed=20260828)
    assert len(lines) == 100_000

    events = [
        _line_to_event(line, f"generated-batch-{index // BATCH_SIZE}.jsonl", index)
        for index, line in enumerate(lines)
    ]
    batches = [events[index : index + BATCH_SIZE] for index in range(0, len(events), BATCH_SIZE)]
    assert len(batches) == 10

    def file_ref(batch_events: list[dict], batch_index: int) -> dict:
        batch_lines = lines[batch_index * BATCH_SIZE : (batch_index + 1) * BATCH_SIZE]
        content = "\n".join(batch_lines).encode("utf-8")
        return {
            "name": f"generated-batch-{batch_index}.jsonl",
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "line_count": len(batch_lines),
            "event_count": len(batch_events),
            "first_event_at": batch_events[0]["event_timestamp"],
            "last_event_at": batch_events[-1]["event_timestamp"],
        }

    account_id = uuid.uuid4()

    async def init_conn(conn: asyncpg.Connection) -> None:
        # The store passes dicts to jsonb columns; asyncpg's default jsonb
        # codec takes pre-encoded JSON strings, so the pool must register the
        # jsonb/json codecs exactly as apps/api/src/main.py does for the API.
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )
        await conn.set_type_codec(
            "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    async def run() -> dict:
        pool = await asyncpg.create_pool(url, min_size=1, max_size=4, init=init_conn)
        try:
            # v3_private.private_import FKs to v3_identity.account; the store
            # expects an existing account (fixture account, never production).
            await pool.execute(
                "INSERT INTO v3_identity.account (account_id) VALUES ($1) "
                "ON CONFLICT (account_id) DO NOTHING",
                account_id,
            )
            per_batch: list[dict] = []
            inserted_total = 0
            received_total = 0
            duplicates_total = 0
            for index, batch in enumerate(batches):
                start = time.perf_counter()
                _, counts = await import_journal_batch(
                    pool,
                    account_id=account_id,
                    commander_id=None,
                    parser_version="fixture-generator-1",
                    files=[file_ref(batch, index)],
                    events=batch,
                )
                elapsed = time.perf_counter() - start
                received_total += counts.events_received
                inserted_total += counts.events_inserted
                duplicates_total += counts.duplicates_skipped
                per_batch.append(
                    {
                        "batch": index,
                        "events": counts.events_received,
                        "seconds": round(elapsed, 4),
                        "events_per_second": round(
                            counts.events_received / elapsed, 1
                        ),
                        "inserted": counts.events_inserted,
                        "duplicates_skipped": counts.duplicates_skipped,
                    }
                )

            # Incremental re-import of the first 1k events. The file gets a
            # NEW content identity (reversed line order -> different sha256) so
            # the file-level dedupe admits it and every event goes through the
            # level-2 semantic dedupe path (ON CONFLICT DO NOTHING).
            incremental_events = [
                {**event, "source_file": "generated-batch-0-reimport.jsonl"}
                for event in batches[0][:INCREMENTAL_EVENTS]
            ]
            incremental_lines = lines[:INCREMENTAL_EVENTS]
            incremental_content = "\n".join(reversed(incremental_lines)).encode("utf-8")
            incremental_file = {
                "name": "generated-batch-0-reimport.jsonl",
                "content_sha256": hashlib.sha256(incremental_content).hexdigest(),
                "size_bytes": len(incremental_content),
                "line_count": len(incremental_lines),
                "event_count": len(incremental_events),
                "first_event_at": incremental_events[0]["event_timestamp"],
                "last_event_at": incremental_events[-1]["event_timestamp"],
            }
            start = time.perf_counter()
            _, incremental_counts = await import_journal_batch(
                pool,
                account_id=account_id,
                commander_id=None,
                parser_version="fixture-generator-1",
                files=[incremental_file],
                events=incremental_events,
            )
            incremental_seconds = time.perf_counter() - start
            return {
                "per_batch": per_batch,
                "received_total": received_total,
                "inserted_total": inserted_total,
                "duplicates_total": duplicates_total,
                "incremental_seconds": round(incremental_seconds, 4),
                "incremental_received": incremental_counts.events_received,
                "incremental_inserted": incremental_counts.events_inserted,
                "incremental_duplicates": incremental_counts.duplicates_skipped,
            }
        finally:
            await pool.close()

    results = asyncio.run(run())

    total_seconds = sum(batch["seconds"] for batch in results["per_batch"])
    events_per_second = results["received_total"] / total_seconds

    perf_record = {
        "test": "test_bulk_import_throughput_and_incremental",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "account_id": str(account_id),
        "database_url_source": "env" if os.environ.get("EDFINDER_V3_DATABASE_URL") else "rehearsal README",
        "lines_generated": len(lines),
        "events_received_total": results["received_total"],
        "events_inserted_total": results["inserted_total"],
        "events_duplicates_skipped_total": results["duplicates_total"],
        "bulk_wall_seconds": round(total_seconds, 4),
        "events_per_second_sustained": round(events_per_second, 1),
        "per_batch": results["per_batch"],
        "incremental_wall_seconds": results["incremental_seconds"],
        "incremental_events_received": results["incremental_received"],
        "incremental_events_inserted": results["incremental_inserted"],
        "incremental_duplicates_skipped": results["incremental_duplicates"],
    }
    PERF_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PERF_RESULTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(perf_record, sort_keys=True) + "\n")

    assert results["received_total"] == 100_000
    # The generator repeats systems/bodies/species by design (200-system pool
    # over ~8.3k cycles), so the level-2 semantic dedupe collapses repeats:
    # every received event is either inserted once or skipped as a duplicate.
    assert results["inserted_total"] + results["duplicates_total"] == 100_000
    assert results["duplicates_total"] > 0
    assert results["inserted_total"] == 21_666  # deterministic corpus -> exact count
    assert results["incremental_received"] == INCREMENTAL_EVENTS
    assert results["incremental_inserted"] == 0
    assert results["incremental_duplicates"] == INCREMENTAL_EVENTS
    assert events_per_second >= MIN_EVENTS_PER_SECOND, (
        f"sustained throughput {events_per_second:.1f} events/s "
        f"below the {MIN_EVENTS_PER_SECOND} events/s floor"
    )

    print(
        f"bulk: {results['received_total']} events received, "
        f"{results['inserted_total']} inserted, "
        f"{results['duplicates_total']} duplicates skipped in {total_seconds:.2f}s "
        f"({events_per_second:.1f} events/s received); "
        f"incremental 1k re-import: {results['incremental_seconds']:.3f}s "
        f"({results['incremental_duplicates']} duplicates skipped); "
        f"recorded -> {PERF_RESULTS_PATH}"
    )
