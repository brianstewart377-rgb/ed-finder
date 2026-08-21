"""Regression test for the EDDN simulation ingest freshness metric.

Requested after defaulting EDDN_SIMULATION_INGEST_ENABLED to on (2026-08-08):
a long-lived background consumer that silently stops cycling (ZMQ
disconnect, crash loop, upstream relay outage) looks identical to a
healthy one without a "how long since it last did something" signal.
Mirrors apps/eddn/src/eddn_listener.py's existing eddn_seconds_since_flush
gauge / EddnFlushStalled alert pattern exactly, rather than introducing a
second monitoring mechanism for what's architecturally the same kind of
thing (a long-lived EDDN consumer) — see config/prometheus_rules.yml's
EddnSimulationIngestFlushStalled alert and CLAUDE.md.
"""
import os
import sys
from importlib import reload
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', os.path.join(os.getcwd(), 'test-local.log'))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.ingest import eddn_client  # noqa: E402


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_seconds_since_last_flush_reflects_module_state(monkeypatch):
    monkeypatch.setattr(eddn_client, '_last_flush_at', eddn_client.time.time() - 42)

    elapsed = eddn_client.seconds_since_last_flush()

    assert 41 <= elapsed <= 43


def test_initialised_fresh_at_import_time():
    """Set at module import (process start), not left unset — a freshly
    started process must not immediately read as stalled before its first
    real flush cycle has had a chance to complete."""
    # The comprehensive coverage job may take several minutes between test
    # collection (when this module is first imported) and this assertion. A
    # reload exercises the process-start behaviour directly instead of making
    # the result depend on suite duration or test order.
    reloaded_client = reload(eddn_client)

    assert reloaded_client.seconds_since_last_flush() < 5


def test_metrics_endpoint_exposes_the_gauge():
    meta_source = _read('apps', 'api', 'src', 'routers', 'meta.py')

    assert 'seconds_since_last_flush as eddn_simulation_ingest_seconds_since_flush' in meta_source
    assert '# HELP ed_finder_eddn_simulation_ingest_seconds_since_flush' in meta_source
    assert '# TYPE ed_finder_eddn_simulation_ingest_seconds_since_flush gauge' in meta_source
    assert 'ed_finder_eddn_simulation_ingest_seconds_since_flush {eddn_simulation_ingest_seconds_since_flush():.1f}' in meta_source


def test_alert_mirrors_the_existing_eddn_flush_stalled_pattern():
    rules = _read('config', 'prometheus_rules.yml')

    eddn_alert_start = rules.index('- alert: EddnFlushStalled')
    sim_alert_start = rules.index('- alert: EddnSimulationIngestFlushStalled')
    assert eddn_alert_start < sim_alert_start

    sim_alert_end = rules.index('- alert: HealthchecksReportedDown')
    sim_alert = rules[sim_alert_start:sim_alert_end]

    assert 'expr: ed_finder_eddn_simulation_ingest_seconds_since_flush > 300' in sim_alert
    assert 'for: 5m' in sim_alert
    assert 'severity: warning' in sim_alert


def test_dashboard_has_a_matching_freshness_panel():
    import json

    dashboard = json.loads(_read('config', 'grafana', 'dashboards', 'ed-finder.json'))
    expressions = '\n'.join(
        target['expr']
        for panel in dashboard['panels']
        for target in panel.get('targets', [])
    )

    assert 'ed_finder_eddn_simulation_ingest_seconds_since_flush{job="ed-api"}' in expressions
