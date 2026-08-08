"""Regression test for the EDDN simulation ingest configuration.

Emergent adversarial-review recurrence check (2026-08-07), item A3/B3.
Defaults ON (decided 2026-08-07, after initially shipping opt-in/default-off
— see config.py's comment and CLAUDE.md's roadmap boundaries section for why
this is deliberately not the same thing as the still-deferred "journal-import
canonical promotion" work). Kept as a flag so it can still be switched off
via env var without a redeploy.

See tests/integration/test_eddn_simulation_ingest_wiring.py for the real
lifespan-behavior tests (those need DB/Redis); this file covers the plain
file-content wiring that doesn't need a live service.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_flag_is_documented_in_env_example_and_compose():
    env_example = (ROOT / 'env.example').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')

    assert 'EDDN_SIMULATION_INGEST_ENABLED=true' in env_example.splitlines()
    assert 'EDDN_SIMULATION_INGEST_ENABLED: ${EDDN_SIMULATION_INGEST_ENABLED:-true}' in compose


def test_pyzmq_is_a_declared_api_dependency():
    """Without this, the task starts (flag on) but its own ImportError
    fallback silently no-ops it — see eddn_client.py's _run_ingest_loop."""
    requirements = (ROOT / 'apps' / 'api' / 'requirements.txt').read_text(encoding='utf-8')

    assert 'pyzmq==' in requirements


def test_tornado_is_a_declared_api_dependency():
    """Root-caused 2026-08-08: on Windows, asyncio's default ProactorEventLoop
    doesn't implement add_reader, which pyzmq needs. Without tornado, the
    first zmq socket recv() raises RuntimeError, and because zmq's own
    Socket._get_loop() marks the loop as registered *before* attempting that
    registration, the subsequent close() cleanup hits the identical
    RuntimeError before it can call the real native close — leaking the
    socket. A later Context.term() on that leaked socket then blocks the
    entire asyncio event loop indefinitely (verified directly: a concurrent
    heartbeat coroutine stops being scheduled and never resumes), taking
    down request handling for the whole API process, not just this task.
    pyzmq detects tornado automatically at runtime and uses its
    AddThreadSelectorEventLoop shim instead of raising — no application code
    changes needed. A no-op on Linux (production): this path only runs when
    the event loop is an instance of asyncio.ProactorEventLoop, which is
    Windows-only."""
    requirements = (ROOT / 'apps' / 'api' / 'requirements.txt').read_text(encoding='utf-8')

    assert 'tornado==' in requirements


def test_config_defaults_the_flag_on():
    config = (ROOT / 'apps' / 'api' / 'src' / 'config.py').read_text(encoding='utf-8')

    assert 'eddn_simulation_ingest_enabled: bool = True' in config


def test_claude_md_distinguishes_this_from_deferred_journal_import_work():
    """The roadmap boundary this feature runs alongside ("No scheduler/
    service/timer activation for import automation by default") predates
    this feature and would otherwise read as contradicted by an always-on
    background task — CLAUDE.md must explain why this one is a deliberate,
    named exception rather than leaving that self-contradiction unexplained."""
    claude_md = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')

    assert 'EDDN_SIMULATION_INGEST_ENABLED' in claude_md
    assert 'journal-import canonical promotion' in claude_md
