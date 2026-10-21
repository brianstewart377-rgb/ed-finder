"""Alert rules and dashboard panels for the series PR #864 exported.

PR #864 made the EDDN simulation ingest and the EDDN→SSE bridge report their
failures on /api/metrics (`ed_finder_eddn_simulation_ingest_flush_failures_total`,
`..._consecutive_flush_failures`, `..._last_successful_flush_timestamp_seconds`,
`ed_finder_sse_bridge_state`, `ed_finder_sse_bridge_reconnects_total`) but
deliberately left `config/prometheus_rules.yml` alone. These tests pin the
rules that now consume them, the two small config gauges the rules need
(`..._enabled`, `..._max_consecutive_flush_failures`) and the matching
dashboard panels, so a later edit cannot quietly drop one.

The rules file is also checked with the real `promtool check rules` when a
`promtool` binary is on PATH (it is not in CI); the structural checks below
run everywhere.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

RULES_PATH = ROOT / 'config' / 'prometheus_rules.yml'
DASHBOARD_PATH = ROOT / 'config' / 'grafana' / 'dashboards' / 'ed-finder.json'

NEW_ALERTS = {
    'EddnSimulationIngestFlushFailing': {
        'metric': 'ed_finder_eddn_simulation_ingest_flush_failures_total',
        'for': '10m',
        'severity': 'warning',
        'expr_contains': ['rate(ed_finder_eddn_simulation_ingest_flush_failures_total[5m])', '> 0'],
    },
    'EddnSimulationIngestFlushBreakerNear': {
        'metric': 'ed_finder_eddn_simulation_ingest_consecutive_flush_failures',
        'for': '1m',
        'severity': 'warning',
        'expr_contains': [
            'ed_finder_eddn_simulation_ingest_consecutive_flush_failures > 0 and ',
            'ed_finder_eddn_simulation_ingest_consecutive_flush_failures >= '
            '(ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures - 1)',
        ],
    },
    'EddnSimulationIngestNoSuccessfulFlush': {
        'metric': 'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds',
        'for': '5m',
        'severity': 'critical',
        'expr_contains': [
            '(time() - ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds) > 1800',
            'ed_finder_eddn_simulation_ingest_last_flush_attempt_timestamp_seconds > '
            'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds',
            'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds > 0',
            'ed_finder_eddn_simulation_ingest_enabled == 1',
        ],
    },
    'SseBridgeUnhealthy': {
        'metric': 'ed_finder_sse_bridge_state',
        'for': '10m',
        'severity': 'warning',
        'expr_contains': ['ed_finder_sse_bridge_state != 2'],
    },
    'SseBridgeReconnecting': {
        'metric': 'ed_finder_sse_bridge_reconnects_total',
        'for': '15m',
        'severity': 'warning',
        'expr_contains': ['rate(ed_finder_sse_bridge_reconnects_total[15m])', '> 0'],
    },
}


def _rules_by_name() -> dict[str, dict]:
    doc = yaml.safe_load(RULES_PATH.read_text(encoding='utf-8'))
    rules = {}
    for group in doc['groups']:
        for rule in group['rules']:
            assert rule['alert'] not in rules, f"duplicate alert {rule['alert']}"
            rules[rule['alert']] = rule
    return rules


def _dashboard_expressions() -> str:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding='utf-8'))
    return '\n'.join(
        target['expr']
        for panel in dashboard['panels']
        for target in panel.get('targets', [])
    )


def test_rules_file_is_one_group_with_unique_alert_names():
    doc = yaml.safe_load(RULES_PATH.read_text(encoding='utf-8'))
    assert list(doc) == ['groups']
    assert [g['name'] for g in doc['groups']] == ['ed-finder-runtime']
    rules = _rules_by_name()
    assert len(rules) == len(doc['groups'][0]['rules'])


@pytest.mark.parametrize(('alert', 'spec'), sorted(NEW_ALERTS.items()))
def test_each_exported_series_has_an_alert(alert, spec):
    rule = _rules_by_name()[alert]
    expr = ' '.join(rule['expr'].split())
    assert spec['metric'] in expr
    for fragment in spec['expr_contains']:
        assert fragment in expr, f'{alert}: {fragment!r} not in {expr!r}'
    assert rule['for'] == spec['for']
    assert rule['labels'] == {'severity': spec['severity']}
    assert set(rule['annotations']) == {'summary', 'description'}
    assert rule['annotations']['summary'].strip()
    assert rule['annotations']['description'].strip()


def test_new_alerts_follow_the_existing_eddn_rules_in_file_order():
    names = list(_rules_by_name())
    stalled = names.index('EddnSimulationIngestFlushStalled')
    healthchecks = names.index('HealthchecksReportedDown')
    block = names[stalled + 1:healthchecks]
    assert block == [
        'EddnSimulationIngestFlushFailing',
        'EddnSimulationIngestFlushBreakerNear',
        'EddnSimulationIngestNoSuccessfulFlush',
        'SseBridgeUnhealthy',
        'SseBridgeReconnecting',
    ]


def test_no_successful_flush_alert_cannot_fire_on_a_fresh_or_disabled_process():
    """0 means "no successful flush since process start" (covered by
    EddnSimulationIngestFlushStalled instead) and a disabled ingest never
    flushes; both must be excluded or the alert is permanently red."""
    expr = ' '.join(_rules_by_name()['EddnSimulationIngestNoSuccessfulFlush']['expr'].split())
    assert ' and ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds > 0' in expr
    assert ' and ed_finder_eddn_simulation_ingest_enabled == 1' in expr


def test_no_successful_flush_alert_is_gated_on_an_attempt_since_the_last_success():
    """A healthy relay that carries no Scan/FSSBodySignals/SAASignalsFound
    events attempts no flush, so the success timestamp ages without any
    write having failed. The rule must require an attempt after the last
    success (attempt timestamp ahead of success timestamp)."""
    expr = ' '.join(_rules_by_name()['EddnSimulationIngestNoSuccessfulFlush']['expr'].split())
    assert (
        ' and ed_finder_eddn_simulation_ingest_last_flush_attempt_timestamp_seconds > '
        'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds'
    ) in expr


def test_breaker_alert_reads_the_threshold_from_the_api_not_a_literal():
    expr = _rules_by_name()['EddnSimulationIngestFlushBreakerNear']['expr']
    assert 'ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures' in expr
    assert '>= 4' not in expr


def test_breaker_alert_cannot_match_the_healthy_zero_at_threshold_one():
    """EDDN_SIMULATION_INGEST_MAX_CONSECUTIVE_FLUSH_FAILURES=1 is allowed
    (Field ge=1, MIN_CONSECUTIVE_FLUSH_FAILURES=1); threshold - 1 is then 0
    and the healthy gauge value is 0, so an explicit positive guard is
    required."""
    expr = ' '.join(_rules_by_name()['EddnSimulationIngestFlushBreakerNear']['expr'].split())
    assert expr.startswith('ed_finder_eddn_simulation_ingest_consecutive_flush_failures > 0 and ')


def test_metrics_endpoint_exports_the_two_config_gauges_the_rules_need():
    meta_source = (API_SRC / 'routers' / 'meta.py').read_text(encoding='utf-8')

    assert '# TYPE ed_finder_eddn_simulation_ingest_enabled gauge' in meta_source
    assert 'ed_finder_eddn_simulation_ingest_enabled {1 if settings.eddn_simulation_ingest_enabled else 0}' in meta_source
    assert '# TYPE ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures gauge' in meta_source
    assert (
        'ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures '
        '{eddn_simulation_ingest_max_consecutive_flush_failures()}'
    ) in meta_source


async def test_metrics_endpoint_renders_the_config_gauges(monkeypatch):
    from edfinder_api.ingest import eddn_client
    from edfinder_api.routers import meta

    monkeypatch.setattr(meta.settings, 'eddn_simulation_ingest_enabled', True)
    monkeypatch.setattr(eddn_client, 'max_consecutive_flush_failures', lambda: 7)
    # meta imported the function by name; patch that binding too.
    monkeypatch.setattr(meta, 'eddn_simulation_ingest_max_consecutive_flush_failures', lambda: 7)

    body = await meta.metrics_endpoint()

    assert 'ed_finder_eddn_simulation_ingest_enabled 1\n' in body
    assert 'ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures 7\n' in body

    monkeypatch.setattr(meta.settings, 'eddn_simulation_ingest_enabled', False)
    body = await meta.metrics_endpoint()
    assert 'ed_finder_eddn_simulation_ingest_enabled 0\n' in body


async def test_flush_attempt_timestamp_moves_on_attempt_not_only_on_success(monkeypatch):
    """The attempt gauge is what lets the NoSuccessfulFlush rule tell an idle
    relevant feed (no attempt) from a failing or hung write path (attempt
    after the last success)."""
    from edfinder_api.ingest import eddn_client
    from edfinder_api.routers import meta

    monkeypatch.setattr(eddn_client, '_last_flush_attempt_at', 0.0)
    monkeypatch.setattr(eddn_client, '_last_successful_flush_at', 0.0)
    monkeypatch.setattr(eddn_client, '_consecutive_flush_failures', 0)

    class _FailingPool:
        def acquire(self):
            raise RuntimeError('db down')

    # An empty batch is a no-op: no attempt recorded.
    assert await eddn_client._flush_batch(_FailingPool(), [], []) is True
    assert eddn_client.last_flush_attempt_timestamp() == 0.0

    before = eddn_client.time.time()
    assert await eddn_client._flush_batch(_FailingPool(), [{'x': 1}], []) is False
    attempt = eddn_client.last_flush_attempt_timestamp()
    assert attempt >= before
    assert eddn_client.last_successful_flush_timestamp() == 0.0
    assert attempt > eddn_client.last_successful_flush_timestamp()

    body = await meta.metrics_endpoint()
    assert f'ed_finder_eddn_simulation_ingest_last_flush_attempt_timestamp_seconds {attempt:.0f}\n' in body

    # After a success the attempt timestamp is never ahead of the success one.
    eddn_client._record_flush_success()
    assert eddn_client.last_flush_attempt_timestamp() <= eddn_client.last_successful_flush_timestamp()


def test_every_alerted_series_is_actually_exported_by_the_api():
    """A rule on a series the API never emits is permanently silent."""
    meta_source = (API_SRC / 'routers' / 'meta.py').read_text(encoding='utf-8')
    for spec in NEW_ALERTS.values():
        assert f"# TYPE {spec['metric']} " in meta_source, spec['metric']
    for extra in (
        'ed_finder_eddn_simulation_ingest_enabled',
        'ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures',
        'ed_finder_eddn_simulation_ingest_last_flush_attempt_timestamp_seconds',
    ):
        assert f'# TYPE {extra} gauge' in meta_source


def test_dashboard_has_panels_for_the_new_series():
    expressions = _dashboard_expressions()
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding='utf-8'))

    assert 'rate(ed_finder_eddn_simulation_ingest_flush_failures_total{job="ed-api"}[5m]) * 60' in expressions
    assert 'ed_finder_eddn_simulation_ingest_consecutive_flush_failures{job="ed-api"}' in expressions
    assert 'ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures{job="ed-api"}' in expressions
    assert 'ed_finder_eddn_simulation_ingest_last_successful_flush_timestamp_seconds{job="ed-api"}' in expressions
    assert 'ed_finder_sse_bridge_state{job="ed-api"}' in expressions
    assert 'rate(ed_finder_sse_bridge_reconnects_total{job="ed-api"}[15m]) * 60' in expressions

    ids = [panel['id'] for panel in dashboard['panels']]
    assert len(ids) == len(set(ids))
    titles = {panel['title'] for panel in dashboard['panels']}
    assert {
        'EDDN Simulation Ingest Flush Failures',
        'EDDN Simulation Ingest Last Successful Flush Age',
        'SSE Bridge State',
        'SSE Bridge Reconnects / min',
    } <= titles
    # Panels must not overlap on the 24-column grid.
    cells = set()
    for panel in dashboard['panels']:
        g = panel['gridPos']
        assert g['x'] + g['w'] <= 24
        for x in range(g['x'], g['x'] + g['w']):
            for y in range(g['y'], g['y'] + g['h']):
                assert (x, y) not in cells, f"panel {panel['id']} overlaps at {(x, y)}"
                cells.add((x, y))


@pytest.mark.skipif(shutil.which('promtool') is None, reason='promtool not installed')
def test_promtool_accepts_the_rules_file():
    result = subprocess.run(
        ['promtool', 'check', 'rules', str(RULES_PATH)],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
