from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from edfinder_api.monitoring import data_invariants_receipt_metrics  # noqa: E402


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_latest_valid_invariant_receipt_becomes_metrics(tmp_path: Path):
    older = tmp_path / 'weekly.json'
    newer = tmp_path / 'post-deploy.json'
    malformed = tmp_path / 'malformed.json'
    older.write_text(
        json.dumps({
            'completed_at_utc': '2026-08-01T10:00:00Z',
            'status': 'failed',
        }),
        encoding='utf-8',
    )
    newer.write_text(
        json.dumps({
            'completed_at_utc': '2026-08-02T11:30:00Z',
            'status': 'passed',
        }),
        encoding='utf-8',
    )
    malformed.write_text('{', encoding='utf-8')

    status, age = data_invariants_receipt_metrics(
        [older, malformed, tmp_path / 'missing.json', newer],
        now=datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
    )

    assert status == 1
    assert age == 30 * 60


def test_missing_invariant_receipts_are_explicitly_unknown(tmp_path: Path):
    status, age = data_invariants_receipt_metrics([tmp_path / 'missing.json'])

    assert status == -1
    assert age != age  # Prometheus text format represents this float as NaN.


def test_api_exports_histogram_and_receipt_contracts_without_counting_scrapes():
    main = _read('apps', 'api', 'src', 'main.py')
    state = _read('apps', 'api', 'src', 'state.py')
    meta = _read('apps', 'api', 'src', 'routers', 'meta.py')
    compose = _read('docker-compose.yml')

    assert "request.url.path == '/api/metrics'" in main
    assert 'observe_request_duration(duration_seconds)' in main
    assert "'request_duration_seconds_buckets'" in state
    assert 'ed_finder_http_request_duration_seconds_bucket' in meta
    assert 'ed_finder_http_request_duration_seconds_sum' in meta
    assert 'ed_finder_http_request_duration_seconds_count' in meta
    assert 'ed_finder_data_invariants_success' in meta
    assert 'ed_finder_data_invariants_age_seconds' in meta
    assert "invariant_age_text = 'NaN'" in meta
    assert '- /data/receipts:/data/receipts:ro' in compose


def test_dashboard_queries_only_metrics_the_services_export():
    dashboard = json.loads(
        _read('config', 'grafana', 'dashboards', 'ed-finder.json')
    )
    serialized = json.dumps(dashboard)
    target_expressions = [
        target['expr']
        for panel in dashboard['panels']
        for target in panel.get('targets', [])
    ]
    expressions = '\n'.join(target_expressions)

    assert dashboard['title'] == 'ED Finder — Production Overview'
    assert sum(panel['type'] == 'timeseries' for panel in dashboard['panels']) >= 10
    assert all(
        target.get('refId')
        for panel in dashboard['panels']
        for target in panel.get('targets', [])
    )
    assert 'ed_finder_requests_total' in expressions
    assert 'ed_finder_http_request_duration_seconds_bucket' in expressions
    assert 'ed_finder_dirty_counts_rating_dirty' in expressions
    assert 'ed_finder_dirty_counts_cluster_dirty' in expressions
    assert 'eddn_events_received_total' in expressions
    assert 'hc_checks_down_total' in expressions
    assert 'hc_check_up' in expressions

    for nonexistent_metric in (
        'http_requests_total',
        'ed_finder_rating_dirty_count',
        'ed_finder_cluster_dirty_count',
        'ed_finder_eddn_events_total',
    ):
        assert nonexistent_metric not in serialized
    assert 'rate(http_request_duration_seconds_bucket' not in serialized


def test_dirty_backlog_export_uses_partial_index_predicates_and_cache():
    queries = _read('config', 'sql_exporter_ed_finder.collector.yml')
    exporter = _read('config', 'sql_exporter.yml')

    assert 'COUNT(*) FILTER' not in queries
    assert queries.count('FROM systems') == 2
    assert 'WHERE rating_dirty = TRUE' in queries
    assert 'WHERE cluster_dirty = TRUE' in queries
    assert 'AND has_body_data = TRUE' in queries
    assert 'AND macro_grid_id IS NOT NULL' in queries
    assert 'min_interval: 5m' in exporter


def test_custom_queries_use_supported_sql_exporter_contract():
    compose = _read('docker-compose.yml')
    prometheus = _read('config', 'prometheus.yml')
    postgres_config = _read('config', 'postgres_exporter.yml')
    sql_config = _read('config', 'sql_exporter.yml')
    collector = _read('config', 'sql_exporter_ed_finder.collector.yml')
    sql_guard = _read('config', 'sql_exporter_start.sh')

    assert 'burningalchemist/sql_exporter:0.24.4' in compose
    assert 'PG_EXPORTER_EXTEND_QUERY_PATH' not in compose
    assert 'postgres_exporter_queries.yaml' not in compose
    assert '--config.file=/etc/postgres_exporter/postgres_exporter.yml' in compose
    assert postgres_config.strip().endswith('auth_modules: {}')
    assert "job_name: 'postgres-custom'" in prometheus
    assert 'postgres_custom_exporter:9399' in prometheus
    assert 'SQLEXPORTER_TARGET_DSN' not in compose
    assert 'sql_exporter_start.sh:/etc/sql_exporter/start.sh:ro' in compose
    assert "sed 's/../%&/g'" in sql_guard
    assert 'unset POSTGRES_PASSWORD' in sql_guard
    assert 'disabled:disabled' in sql_config
    assert 'ed_finder_dirty_counts_rating_dirty' in collector
    assert 'ed_finder_dirty_counts_cluster_dirty' in collector


def test_healthchecks_is_optional_and_uses_a_read_only_secret_file():
    prometheus = _read('config', 'prometheus.yml')
    empty_targets = _read('config', 'healthchecks_targets.empty.yml')
    example_targets = _read('config', 'healthchecks_targets.example.yml')
    compose = _read('docker-compose.yml')

    assert "job_name: 'healthchecks'" in prometheus
    assert 'credentials_file: /run/secrets/healthchecks_readonly_api_key' in prometheus
    assert '/projects/${1}/metrics/' in prometheus
    assert 'file_sd_configs:' in prometheus
    assert empty_targets.strip() == '[]'
    assert 'healthchecks.io' in example_targets
    assert 'healthchecks_readonly_api_key.disabled' in compose
    assert 'api_key' not in example_targets.lower()


def test_monitoring_images_are_pinned_and_grafana_fails_closed():
    compose = _read('docker-compose.yml')
    guard = _read('config', 'grafana', 'start-with-secret.sh')

    assert 'prom/prometheus:v3.13.2' in compose
    assert 'grafana/grafana:13.1.1' in compose
    assert 'prometheuscommunity/postgres-exporter:v0.20.1' in compose
    assert 'burningalchemist/sql_exporter:0.24.4' in compose
    assert 'oliver006/redis_exporter:v1.88.0' in compose
    monitoring_section = compose[compose.index('  prometheus:'):]
    assert ':latest' not in monitoring_section
    assert 'GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}' not in compose
    assert 'grafana-piechart-panel' not in compose
    assert 'grafana_admin_password.disabled' in compose
    assert "''|admin|change-me|not-configured)" in guard
    assert 'exec /run.sh' in guard


def test_pr1_does_not_activate_monitoring_in_the_deploy_path():
    deploy = _read('scripts', 'deploy_main.sh')

    assert '--profile monitoring' not in deploy
    assert 'config/prometheus_rules.yml' in _read('docker-compose.yml')
    assert 'DataInvariantsFailed' in _read('config', 'prometheus_rules.yml')


def test_gate2_permission_helper_is_explicit_and_monitoring_stays_opt_in():
    helper = _read('scripts', 'prepare_monitoring.sh')
    deploy = _read('scripts', 'deploy_main.sh')

    assert "chown 472:0 \"$grafana_password\"" in helper
    assert "chmod 0400 \"$grafana_password\"" in helper
    assert "chown 65534:65534 \"$healthchecks_token\"" in helper
    assert "chmod 0400 \"$healthchecks_token\"" in helper
    assert "chmod 0644 \"$healthchecks_targets\"" in helper
    assert '--check' in helper
    assert '--profile monitoring' not in deploy
