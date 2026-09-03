from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_REVIEW_COMPOSE = ROOT / 'docker-compose.review.yml'
RETIRED_HOSTED_REVIEW_COMPOSE = ROOT / 'docker-compose.review-hosted.yml'
RETIRED_DEPLOY_SCRIPT = ROOT / 'scripts' / 'ops' / 'deploy_hosted_review.sh'
RETIRED_AUTH_SCRIPT = ROOT / 'scripts' / 'ops' / 'create_review_auth_file.sh'
RETIRED_HOSTED_DOC = ROOT / 'docs' / 'operations' / 'hosted-review-environment.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f'  {service_name}:':
            start = index
            break
    assert start is not None, f'missing service {service_name}'
    collected: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith('  ') and not line.startswith('    '):
            break
        if line and not line.startswith(' '):
            break
        collected.append(line)
    return '\n'.join(collected)


def _top_level_block(compose_text: str, key: str) -> str:
    lines = compose_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f'{key}:':
            start = index
            break
    assert start is not None, f'missing top-level {key}'
    collected: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line.startswith(' '):
            break
        collected.append(line)
    return '\n'.join(collected)


def _child_block(block: str, child_name: str) -> str:
    lines = block.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f'  {child_name}:':
            start = index
            break
    assert start is not None, f'missing child {child_name}'
    collected: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith('  ') and not line.startswith('    '):
            break
        if line and not line.startswith(' '):
            break
        collected.append(line)
    return '\n'.join(collected)


def _named_resource_name(compose_text: str, section: str, resource: str) -> str:
    block = _child_block(_top_level_block(compose_text, section), resource)
    for line in block.splitlines():
        if line.strip().startswith('name:'):
            return line.split(':', 1)[1].strip()
    raise AssertionError(f'missing name for {section}.{resource}')


def _list_values(block: str, key: str) -> list[str]:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f'{key}:':
            indent = len(line) - len(line.lstrip(' '))
            values: list[str] = []
            for child in lines[index + 1:]:
                if child.strip() == '':
                    continue
                child_indent = len(child) - len(child.lstrip(' '))
                if child_indent <= indent:
                    break
                stripped = child.strip()
                if stripped.startswith('- '):
                    values.append(stripped[2:].split(' #', 1)[0])
            return values
    return []


def test_local_review_compose_remains_disposable_local_only():
    compose_text = _read(LOCAL_REVIEW_COMPOSE)

    assert 'docker-compose.review-hosted.yml' not in compose_text
    assert 'edfinder-review-edge' not in compose_text
    assert 'external:' not in compose_text
    assert 'env_file:' not in compose_text
    assert 'ed-finder.app' not in compose_text
    assert '127.0.0.1:8001:8000' in compose_text

    assert 'ports:' not in _service_block(compose_text, 'review-postgres')
    assert 'ports:' not in _service_block(compose_text, 'review-redis')
    assert _list_values(_service_block(compose_text, 'review-postgres'), 'networks') == ['review']
    assert _list_values(_service_block(compose_text, 'review-redis'), 'networks') == ['review']
    assert _list_values(_service_block(compose_text, 'review-api'), 'networks') == ['review']


def test_local_review_compose_resolves_existing_local_resource_names():
    compose_text = _read(LOCAL_REVIEW_COMPOSE)

    assert _named_resource_name(compose_text, 'networks', 'review') == 'edfinder-review-network'
    assert _named_resource_name(compose_text, 'volumes', 'review_postgres_data') == 'edfinder_review_postgres_data'
    assert _named_resource_name(compose_text, 'volumes', 'review_redis_data') == 'edfinder_review_redis_data'


def test_local_review_uses_only_synthetic_local_credentials_and_targets():
    compose_text = _read(LOCAL_REVIEW_COMPOSE)
    api_block = _service_block(compose_text, 'review-api')

    assert 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review' in api_block
    assert 'redis://review-redis:6379/0' in api_block
    assert 'review-environment-admin-token' in api_block
    assert 'postgresql://edfinder:' not in compose_text
    assert '@postgres:5432/edfinder' not in compose_text
    assert 'redis://redis:6379' not in compose_text
    assert 'ed-postgres' not in compose_text
    assert 'ed-redis' not in compose_text


def test_hetzner_hosted_review_surface_is_retired():
    for path in (
        RETIRED_HOSTED_REVIEW_COMPOSE,
        RETIRED_DEPLOY_SCRIPT,
        RETIRED_AUTH_SCRIPT,
        RETIRED_HOSTED_DOC,
    ):
        assert not path.exists(), f'retired Hetzner hosted-review artifact returned: {path}'


def test_local_review_contract_does_not_depend_on_retired_hosted_paths():
    compose_text = _read(LOCAL_REVIEW_COMPOSE)
    forbidden = (
        '/opt/ed-finder-review',
        'review.ed-finder.app',
        'review.htpasswd',
        'edfinder-review-edge',
        'deploy_hosted_review.sh',
        'create_review_auth_file.sh',
    )
    for value in forbidden:
        assert value not in compose_text

    # Keep this structural rather than text-only: local Review Lab has exactly
    # the three services it needs and no hidden hosted edge/proxy service.
    service_names = re.findall(r'^  ([A-Za-z0-9_-]+):$', _top_level_block(compose_text, 'services'), re.MULTILINE)
    assert service_names == ['review-postgres', 'review-redis', 'review-api']
