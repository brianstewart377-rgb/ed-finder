"""Regression test for the opt-in EDDN simulation ingest configuration.

Emergent adversarial-review recurrence check (2026-08-07), item A3/B3.
See tests/integration/test_eddn_simulation_ingest_wiring.py for the real
lifespan-behavior tests (those need DB/Redis); this file covers the plain
file-content wiring that doesn't need a live service.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_flag_is_documented_in_env_example_and_compose():
    env_example = (ROOT / 'env.example').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')

    assert 'EDDN_SIMULATION_INGEST_ENABLED=false' in env_example.splitlines()
    assert 'EDDN_SIMULATION_INGEST_ENABLED: ${EDDN_SIMULATION_INGEST_ENABLED:-false}' in compose


def test_pyzmq_is_a_declared_api_dependency():
    """Without this, the task starts (flag on) but its own ImportError
    fallback silently no-ops it — see eddn_client.py's _run_ingest_loop."""
    requirements = (ROOT / 'apps' / 'api' / 'requirements.txt').read_text(encoding='utf-8')

    assert 'pyzmq==' in requirements


def test_config_defaults_the_flag_off():
    config = (ROOT / 'apps' / 'api' / 'src' / 'config.py').read_text(encoding='utf-8')

    assert 'eddn_simulation_ingest_enabled: bool = False' in config
