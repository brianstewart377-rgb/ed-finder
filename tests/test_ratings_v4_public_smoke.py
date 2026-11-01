"""Public Ratings V4 smoke receipts, using only a disposable loopback server."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from scripts.checks import ratings_v4_public_smoke as smoke


ROOT = Path(__file__).resolve().parents[1]
BUILD_SHA = '0123456789abcdef0123456789abcdef01234567'
SYSTEM_IDS = (10477373803, 164098653, 1109989017963)
ECONOMIES = ('Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism', 'Extraction')
GENERATION = {
    'derived_generation_id': 'test-published-generation',
    'publication_sequence': 1,
    'published_at': '2026-10-31T12:34:56+00:00',
    'canonical_generation_id': 'test-canonical-generation',
    'canonical_publication_sequence': 2,
    'scorer_version': '4.0.0',
    'mechanics_version': 'v4-mechanics-2026-09',
    'validation_receipt': {'status': 'passed'},
}
IDENTITY_FIELDS = (
    'derived_generation_id', 'publication_sequence', 'canonical_generation_id',
    'canonical_publication_sequence', 'scorer_version', 'mechanics_version',
)
SUMMARY_PATH = f'/api/ratings/v4/systems/{SYSTEM_IDS[0]}'
EXPLANATION_PATH = SUMMARY_PATH + '/explanation'
REQUEST_PATHS = ['/api/health', '/api/ratings/v4/generation'] + [
    path
    for system_id in SYSTEM_IDS
    for path in (f'/api/ratings/v4/systems/{system_id}', f'/api/ratings/v4/systems/{system_id}/explanation')
]


def _payloads():
    summary = [{
        'economy': economy,
        'potential_score': 85 if index == 0 else 0,
        'specialisation_quality': 75 if index == 0 else None,
        'specialisation_quality_min': 75 if index == 0 else 0,
        'specialisation_quality_max': 75 if index == 0 else 100,
        'evidence_completeness': 0.6,
        'confidence': 0.7,
    } for index, economy in enumerate(ECONOMIES)]
    explanations = [{
        **rating,
        'best_candidate_id': 'body-1' if index == 0 else None,
        'local_scores': [85] if index == 0 else [],
        'explanation': ['Synthetic loopback fixture'],
        'mechanics_version': GENERATION['mechanics_version'],
        'scorer_version': GENERATION['scorer_version'],
        'contributions': [{
            'candidate_id': 'body-1', 'native': True, 'modifier': False,
            'base_score': 75, 'positive_rules': ['synthetic-positive'], 'negative_rules': [],
            'positive_adjustment': 10, 'negative_adjustment': 0, 'local_score': 85,
            'system_weight': 0.82, 'contributors': ['body-1'],
            'evidence': [{
                'feature_type': 'biologicals', 'known': True, 'weight': 1.0,
                'confidence': 0.7, 'provenance': None, 'value': True,
            }],
        }] if index == 0 else [],
        'best_specialisation_candidate_id': 'body-1' if index == 0 else None,
        'specialisation_candidates': [{
            'candidate_id': 'body-1', 'intrinsic_quality': 75, 'quality': 75,
            'minimum_quality': 75, 'maximum_quality': 75, 'competing_economies': [],
            'preferred_specialisation': True,
            'constraints': [{
                'rule_id': 'synthetic-constraint', 'satisfied': None,
                'feature_type': 'usable_ground_opportunity', 'confidence': 0.0,
                'provenance': None,
            }],
        }] if index == 0 else [],
    } for index, rating in enumerate(summary)]
    payloads = {
        '/api/health': {'status': 'ok', 'database': 'connected', 'version': '3.0.1', 'build_sha': BUILD_SHA},
        '/api/ratings/v4/generation': deepcopy(GENERATION),
    }
    identity = {field: GENERATION[field] for field in IDENTITY_FIELDS}
    for system_id in SYSTEM_IDS:
        payloads[f'/api/ratings/v4/systems/{system_id}'] = {
            **identity, 'system_id64': system_id, 'ratings': deepcopy(summary),
        }
        payloads[f'/api/ratings/v4/systems/{system_id}/explanation'] = {
            **identity, 'system_id64': system_id, 'ratings': deepcopy(explanations),
        }
    return payloads


@contextmanager
def _server(payloads, *, statuses=None, delays=None, redirects=None):
    statuses, delays, redirects = statuses or {}, delays or {}, redirects or {}
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.command, self.path, dict(self.headers)))
            time.sleep(delays.get(self.path, 0))
            payload = payloads.get(self.path, {'detail': 'Unexpected test route'})
            encoded = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
            try:
                self.send_response(statuses.get(self.path, 200 if self.path in payloads else 404))
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                if self.path in redirects:
                    self.send_header('Location', redirects[self.path])
                self.end_headers()
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                # Timed-out clients deliberately close before delayed responses.
                pass

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', seen
        finally:
            server.shutdown()
            thread.join(timeout=2)


def _run(base_url, tmp_path, *extra_args):
    receipt_path = tmp_path / 'evidence' / 'ratings-smoke.json'
    code = smoke.main(['--base-url', base_url, '--receipt', str(receipt_path), *extra_args])
    assert receipt_path.is_file(), 'HTTP and validation failures must retain a receipt'
    return code, json.loads(receipt_path.read_text(encoding='utf-8'))


def _failed_request(code, receipt, path):
    assert code != 0
    assert receipt['status'] == 'failed'
    request = next(item for item in receipt['requests'] if item['path'] == path)
    assert request['validation']['status'] == 'failed'
    assert request['validation']['errors']
    assert isinstance(request['latency_ms'], (int, float))
    assert request['latency_ms'] >= 0
    return request


def test_pass_records_all_eight_read_only_requests_and_release_identity(tmp_path, monkeypatch):
    for name in ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        monkeypatch.setenv(name, 'http://proxy-user:proxy-password@127.0.0.1:9')
    monkeypatch.setenv('no_proxy', '')
    monkeypatch.setenv('NO_PROXY', '')
    with _server(_payloads()) as (base_url, seen):
        code, receipt = _run(base_url, tmp_path)

    assert code == 0
    assert receipt['schema_version'] == 'ed-finder/ratings-v4-public-smoke/v1'
    assert receipt['status'] == 'passed'
    assert receipt['base_url'] == base_url
    assert datetime.fromisoformat(receipt['started_at']).utcoffset() is not None
    assert receipt['build_sha'] == BUILD_SHA
    assert receipt['database'] == 'connected'
    assert receipt['generation'] == GENERATION
    assert [item['path'] for item in receipt['requests']] == REQUEST_PATHS
    assert [(method, path) for method, path, _headers in seen] == [('GET', path) for path in REQUEST_PATHS]
    for item in receipt['requests']:
        assert item['method'] == 'GET'
        assert item['status'] == 200
        assert item['latency_ms'] >= 0
        assert item['validation'] == {'status': 'passed', 'errors': []}
    for _method, _path, headers in seen:
        assert not {'authorization', 'proxy-authorization', 'cookie'} & {name.lower() for name in headers}


@pytest.mark.parametrize('field', IDENTITY_FIELDS)
def test_wrong_generation_identity_fails_and_retains_receipt(tmp_path, field):
    payloads = _payloads()
    original = payloads[SUMMARY_PATH][field]
    payloads[SUMMARY_PATH][field] = original + 1 if isinstance(original, int) else original + '-wrong'
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    request = _failed_request(code, receipt, SUMMARY_PATH)
    assert field in ' '.join(request['validation']['errors'])


@pytest.mark.parametrize(('field', 'value'), [
    ('potential_score', -1), ('potential_score', 101),
    ('confidence', -0.01), ('confidence', 1.01),
    ('potential_score', True), ('confidence', '0.7'),
    ('confidence', float('nan')), ('confidence', float('inf')),
    ('confidence', 10**400),
])
def test_invalid_scores_fail_with_a_saved_receipt(tmp_path, field, value):
    payloads = _payloads()
    payloads[SUMMARY_PATH]['ratings'][0][field] = value
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    assert _failed_request(code, receipt, SUMMARY_PATH)['status'] == 200


def test_missing_nested_required_field_fails(tmp_path):
    payloads = _payloads()
    del payloads[EXPLANATION_PATH]['ratings'][0]['contributions'][0]['evidence'][0]['provenance']
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    request = _failed_request(code, receipt, EXPLANATION_PATH)
    assert 'provenance' in ' '.join(request['validation']['errors'])


def test_nested_type_mismatch_fails(tmp_path):
    payloads = _payloads()
    payloads[EXPLANATION_PATH]['ratings'][0]['specialisation_candidates'][0]['constraints'][0]['satisfied'] = 'yes'
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    request = _failed_request(code, receipt, EXPLANATION_PATH)
    assert 'satisfied' in ' '.join(request['validation']['errors'])


def test_duplicate_economy_cannot_replace_one_of_the_seven(tmp_path):
    payloads = _payloads()
    payloads[SUMMARY_PATH]['ratings'][-1]['economy'] = ECONOMIES[0]
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    _failed_request(code, receipt, SUMMARY_PATH)


def test_explanation_must_match_the_summary(tmp_path):
    payloads = _payloads()
    payloads[EXPLANATION_PATH]['ratings'][0]['potential_score'] = 84
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    _failed_request(code, receipt, EXPLANATION_PATH)


def test_non_200_fails_and_records_http_status(tmp_path):
    with _server(_payloads(), statuses={SUMMARY_PATH: 503}) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    assert _failed_request(code, receipt, SUMMARY_PATH)['status'] == 503


@pytest.mark.parametrize('body', [b'{', b'{"confidence":1e9999}', b'{"field":1,"field":2}'])
def test_invalid_json_retains_received_http_status(tmp_path, body):
    payloads = _payloads()
    payloads[SUMMARY_PATH] = body
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    request = _failed_request(code, receipt, SUMMARY_PATH)
    assert request['status'] == 200
    assert request['validation']['errors'] == ['invalid JSON response']


def test_redirect_fails_without_requesting_the_destination(tmp_path):
    with _server(_payloads(), statuses={SUMMARY_PATH: 302}, redirects={SUMMARY_PATH: '/must-not-follow'}) as (base_url, seen):
        code, receipt = _run(base_url, tmp_path)
    assert _failed_request(code, receipt, SUMMARY_PATH)['status'] == 302
    assert '/must-not-follow' not in [path for _method, path, _headers in seen]


def test_oversized_response_fails_with_a_saved_receipt(tmp_path):
    payloads = _payloads()
    payloads[SUMMARY_PATH]['extra'] = 'x' * (4 * 1024 * 1024)
    with _server(payloads) as (base_url, _seen):
        code, receipt = _run(base_url, tmp_path)
    request = _failed_request(code, receipt, SUMMARY_PATH)
    assert request['status'] == 200
    assert 'limit' in ' '.join(request['validation']['errors'])


def test_timeout_is_bounded_and_failure_receipt_is_persisted(tmp_path):
    with _server(_payloads(), delays={SUMMARY_PATH: 3}) as (base_url, _seen):
        started = time.monotonic()
        code, receipt = _run(base_url, tmp_path, '--timeout-seconds', '1')
        elapsed = time.monotonic() - started
    request = _failed_request(code, receipt, SUMMARY_PATH)
    assert request['status'] is None
    assert 'timeout' in ' '.join(request['validation']['errors']).lower() or 'deadline' in ' '.join(request['validation']['errors']).lower()
    assert request['latency_ms'] < 2500
    assert elapsed < 9, 'Each request must have a bounded wall-clock deadline'


@pytest.mark.parametrize('timeout', ['0', '-1', '31', 'nan', 'inf'])
def test_invalid_timeout_makes_no_requests(tmp_path, timeout):
    with _server(_payloads()) as (base_url, seen):
        try:
            code = smoke.main(['--base-url', base_url, '--receipt', str(tmp_path / 'unused.json'), '--timeout-seconds', timeout])
        except SystemExit as exc:
            code = exc.code
    assert code != 0
    assert seen == []


def test_url_credentials_are_rejected_before_any_request(tmp_path, capsys):
    with _server(_payloads()) as (base_url, seen):
        credential_url = base_url.replace('http://', 'http://example-user:example-secret@')
        try:
            code = smoke.main(['--base-url', credential_url, '--receipt', str(tmp_path / 'unused.json')])
        except SystemExit as exc:
            code = exc.code
    assert code != 0
    assert seen == []
    captured = capsys.readouterr()
    assert 'example-secret' not in captured.out + captured.err
    if (tmp_path / 'unused.json').exists():
        assert 'example-secret' not in (tmp_path / 'unused.json').read_text(encoding='utf-8')


def test_remote_http_origin_is_rejected_before_any_network_call(tmp_path, monkeypatch):
    def unexpected_run(*_args, **_kwargs):
        pytest.fail('Invalid base URL reached the network-capable smoke runner')

    monkeypatch.setattr(smoke, 'run_smoke', unexpected_run)
    with pytest.raises(SystemExit) as exc:
        smoke.main(['--base-url', 'http://ed-finder.app', '--receipt', str(tmp_path / 'unused.json')])
    assert exc.value.code == 2


def test_stdlib_contract_tracks_all_required_pydantic_response_fields():
    """Changing an API model must also update its standalone smoke validator."""
    def descriptor(annotation):
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Constant) and annotation.value is None:
            return 'None'
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            return f'{descriptor(annotation.left)} | {descriptor(annotation.right)}'
        if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
            if annotation.value.id == 'dict':
                return 'object'
            if annotation.value.id in ('tuple', 'list'):
                item = annotation.slice.elts[0] if isinstance(annotation.slice, ast.Tuple) else annotation.slice
                return f'list[{descriptor(item)}]'
        raise AssertionError(f'Update smoke contract for annotation {ast.unparse(annotation)}')

    tree = ast.parse((ROOT / 'apps/api/src/routers/ratings_v4.py').read_text(encoding='utf-8'))
    model_fields = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
        if 'BaseModel' not in bases and not any(base in model_fields for base in bases):
            continue
        required = {field: kind for base in bases for field, kind in model_fields.get(base, {}).items()}
        for field in node.body:
            if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name):
                if field.value is None:
                    required[field.target.id] = descriptor(field.annotation)
                else:
                    required.pop(field.target.id, None)
        model_fields[node.name] = required
    assert len(model_fields) == 9
    health_tree = ast.parse((ROOT / 'apps/api/src/models.py').read_text(encoding='utf-8'))
    health = next(node for node in health_tree.body if isinstance(node, ast.ClassDef) and node.name == 'HealthResponse')
    model_fields['HealthResponse'] = {
        field.target.id: descriptor(field.annotation)
        for field in health.body
        if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name) and field.value is None
    }
    assert set(smoke.MODEL_FIELDS) == set(model_fields)
    for name, required in model_fields.items():
        assert smoke.MODEL_FIELDS[name] == required, name


def test_smoke_script_imports_only_standard_library_modules():
    tree = ast.parse((ROOT / 'scripts/checks/ratings_v4_public_smoke.py').read_text(encoding='utf-8'))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, 'No repository-relative dependencies in the standalone smoke script'
            modules.add(node.module.split('.')[0])
    assert modules <= sys.stdlib_module_names
