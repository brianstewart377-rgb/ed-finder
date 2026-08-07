"""Regression test for the opt-in EDDN simulation ingest lifespan wiring.

Emergent adversarial-review recurrence check (2026-08-07), item A3/B3:
run_eddn_simulation_ingest existed but was never wired into the FastAPI
lifespan — its only "call" was inside its own docstring. Wired up behind
EDDN_SIMULATION_INGEST_ENABLED (default off, per docs/ROADMAP.md's "no
scheduler/service/timer activation for import automation by default").

Patches main.run_eddn_simulation_ingest to a tracking no-op rather than
letting the real lifespan attempt a live EDDN ZMQ connection — these tests
must not depend on network access to tcp://eddn.edcd.io:9500.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_ingest_task_not_started_when_disabled(monkeypatch):
    import main

    assert main.settings.eddn_simulation_ingest_enabled is False, (
        'default must stay off — this test assumes the untouched default'
    )

    started = asyncio.Event()

    async def _tracking_noop(pool):
        started.set()
        await asyncio.Event().wait()  # never returns on its own

    monkeypatch.setattr(main, 'run_eddn_simulation_ingest', _tracking_noop)

    async with main.app.router.lifespan_context(main.app):
        await asyncio.sleep(0)  # let any startup tasks get a chance to run
        assert not started.is_set()
        assert main._eddn_simulation_ingest_task is None


@pytest.mark.asyncio
async def test_ingest_task_started_and_cleanly_cancelled_when_enabled(monkeypatch):
    import main

    monkeypatch.setattr(main.settings, 'eddn_simulation_ingest_enabled', True)

    started = asyncio.Event()

    async def _tracking_noop(pool):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(main, 'run_eddn_simulation_ingest', _tracking_noop)

    async with main.app.router.lifespan_context(main.app):
        await asyncio.wait_for(started.wait(), timeout=5)
        task = main._eddn_simulation_ingest_task
        assert task is not None
        assert not task.done()

    # Lifespan shutdown must have cancelled it cleanly, not left it running
    # or leaked an unhandled exception.
    assert task.done()
    assert task.cancelled()
