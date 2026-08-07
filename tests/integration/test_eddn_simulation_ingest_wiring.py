"""Regression test for the EDDN simulation ingest lifespan wiring.

Emergent adversarial-review recurrence check (2026-08-07), item A3/B3:
run_eddn_simulation_ingest existed but was never wired into the FastAPI
lifespan — its only "call" was inside its own docstring. Wired up behind
EDDN_SIMULATION_INGEST_ENABLED, which defaults ON as of 2026-08-07 (see
config.py and CLAUDE.md's roadmap boundaries section for why this is
deliberately distinct from the still-deferred "journal-import canonical
promotion" work). Kept as a flag, not unconditional, so it stays testable
in both states and switchable off via env var without a redeploy.

conftest.py forces EDDN_SIMULATION_INGEST_ENABLED=false for every other
test in this directory (so the shared `app`/`client` fixtures don't try a
real network connection on every test run) — that's why both tests here
explicitly monkeypatch the setting rather than relying on config.py's
Python-level default, which is verified separately (as a plain string
check, unaffected by this directory's env override) in
tests/test_eddn_simulation_ingest_config.py::test_config_defaults_the_flag_on.

Patches main.run_eddn_simulation_ingest to a tracking no-op rather than
letting the real lifespan attempt a live EDDN ZMQ connection — these tests
must not depend on network access to tcp://eddn.edcd.io:9500.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_ingest_task_started_when_enabled(monkeypatch):
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


@pytest.mark.asyncio
async def test_ingest_task_not_started_when_disabled(monkeypatch):
    import main

    # _eddn_simulation_ingest_task is a module-level global that persists
    # across tests within the same process (main is imported once, not
    # per-test) — an earlier test's finished/cancelled Task object would
    # otherwise still be sitting there, making an `is None` assertion
    # below fail for a reason unrelated to this test's own behavior.
    monkeypatch.setattr(main, '_eddn_simulation_ingest_task', None)
    monkeypatch.setattr(main.settings, 'eddn_simulation_ingest_enabled', False)

    started = asyncio.Event()

    async def _tracking_noop(pool):
        started.set()
        await asyncio.Event().wait()  # never returns on its own

    monkeypatch.setattr(main, 'run_eddn_simulation_ingest', _tracking_noop)

    async with main.app.router.lifespan_context(main.app):
        await asyncio.sleep(0)  # let any startup tasks get a chance to run
        assert not started.is_set()
        assert main._eddn_simulation_ingest_task is None
