from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'deploy' / 'octopus'
COMPOSE_PATH = BUNDLE / 'docker-compose.yml'
ENV_PATH = BUNDLE / 'env.example'
HELPER_PATH = BUNDLE / 'octopusctl.sh'
RUNBOOK_PATH = ROOT / 'docs' / 'operations' / 'octopus-fresh-self-hosted-deployment.md'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _compose() -> dict:
    return yaml.safe_load(_text(COMPOSE_PATH))


def _prose(path: Path) -> str:
    return ' '.join(_text(path).split())


def test_images_and_matching_migration_toolchain_are_immutable():
    compose = _compose()
    images = [service['image'] for service in compose['services'].values()]

    assert images == [
        'ghcr.io/octopusreview/octopus-selfhost:1.0.122@sha256:7a65a6009136376a74ff0a4dd58fae26c10f610879bed7f9c97adb0530c7eb78',
        'postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73',
        'qdrant/qdrant:v1.17.0@sha256:f1c7272cdac52b38c1a0e89313922d940ba50afd90d593a1605dbbc214e66ffb',
    ]
    all_bundle_text = '\n'.join(_text(path) for path in BUNDLE.iterdir() if path.is_file()).lower()
    assert ':latest' not in all_bundle_text

    helper = _text(HELPER_PATH)
    assert 'RELEASE=1.0.122' in helper
    assert 'UPSTREAM_COMMIT=55583ac832472ad8b535f1f678f9c11837f7cfdb' in helper
    assert 'oven/bun:1.3.4-alpine@sha256:' in helper
    assert 'bun install --frozen-lockfile' in helper
    assert 'bunx prisma migrate deploy' in helper
    assert 'migration-source-commit.txt' in helper


def test_network_ports_names_and_worker_default_are_isolated():
    compose = _compose()
    services = compose['services']

    assert compose['name'] == 'edfinder_octopus_fresh_10122'
    assert services['web']['ports'] == ['127.0.0.1:43300:3000']
    assert 'ports' not in services['postgres']
    assert 'ports' not in services['qdrant']
    assert services['web']['environment']['ENABLE_REVIEW_WORKERS'] == '${ENABLE_REVIEW_WORKERS:-false}'
    assert all(service['networks'] == ['octopus_fresh'] for service in services.values())

    assert compose['networks']['octopus_fresh'] == {
        'name': 'edfinder-octopus-fresh-10122-network',
        'driver': 'bridge',
        'external': False,
    }
    volume_names = {value['name'] for value in compose['volumes'].values()}
    assert volume_names == {
        'edfinder-octopus-fresh-10122-postgres-data',
        'edfinder-octopus-fresh-10122-qdrant-data',
    }
    assert len({service['container_name'] for service in services.values()}) == 3


def test_secret_template_has_only_invalid_placeholders_and_safe_defaults():
    env = _text(ENV_PATH)
    required = {
        'OCTOPUS_POSTGRES_PASSWORD',
        'OCTOPUS_DATABASE_URL',
        'BETTER_AUTH_SECRET',
        'OCTOPUS_DATA_KEY',
        'GITHUB_APP_ID',
        'GITHUB_APP_PRIVATE_KEY',
        'GITHUB_WEBHOOK_SECRET',
        'GITHUB_APP_CLIENT_ID',
        'GITHUB_APP_CLIENT_SECRET',
        'GITHUB_STATE_SECRET',
        'OCTOPUS_ADMIN_EMAIL',
        'OCTOPUS_ADMIN_PASSWORD',
    }
    values = dict(
        line.split('=', 1)
        for line in env.splitlines()
        if line and not line.startswith('#') and '=' in line
    )

    assert required <= values.keys()
    assert all(values[name].startswith('__REQUIRED_') for name in required)
    assert values['ENABLE_REVIEW_WORKERS'] == 'false'
    assert values['OCTOPUS_EMBED_MODEL'] == 'text-embedding-3-large'
    assert not re.search(r'(?i)(password|secret|data_key)=octopus(?:$|\s)', env, re.MULTILINE)
    assert 'sk-ant-' not in env and 'sk-proj-' not in env and 'BEGIN PRIVATE KEY' not in env


def test_helper_is_bounded_fail_closed_and_non_destructive():
    helper = _text(HELPER_PATH)
    lower = helper.lower()

    for required in [
        'TARGET=/opt/octopus',
        'assert_absent_docker_objects',
        'assert_port_free',
        'assert_owned_stack',
        'com.docker.compose.project',
        'TCP port 43300 is already listening',
        'compose stop',
    ]:
        assert required in helper
    for forbidden in [
        'down -v',
        'docker system prune',
        'docker container prune',
        'docker network prune',
        'docker volume prune',
        'docker volume rm',
        'docker rm',
        'rm -rf',
    ]:
        assert forbidden not in lower
    assert "grep -qx 'ENABLE_REVIEW_WORKERS=false'" in helper
    assert "sed 's/^ENABLE_REVIEW_WORKERS=false$/ENABLE_REVIEW_WORKERS=true/'" in helper
    assert 'activation changed more than the worker setting' in helper


def test_health_version_and_exact_image_receipts_are_required():
    helper = _text(HELPER_PATH)
    runbook = _prose(RUNBOOK_PATH)

    for requirement in [
        '/api/health',
        '/api/version',
        'pg_isready',
        '/readyz',
        'container-health.txt',
        'image-version-health.txt',
        'api-version.json',
    ]:
        assert requirement in helper
    assert 'version `1.0.122` with `selfHosted: true`' in runbook
    assert 'retains both fresh volumes' in runbook
    assert 'stops only project `edfinder_octopus_fresh_10122`' in runbook


def test_runbook_enforces_fresh_install_cutover_and_org_byok():
    runbook = _prose(RUNBOOK_PATH)

    for requirement in [
        'It is not a migration.',
        'Do not read, copy, export, mount',
        'Use fresh auth and data-encryption secrets',
        'old `OCTOPUS_DATA_KEY`',
        'organization-level Anthropic BYOK',
        'organization-level OpenAI BYOK',
        '`text-embedding-3-large`',
        'internal credit gate',
        'classifies the provider call as BYOK',
        'no platform-credit debit',
        'old Octopus worker and webhook delivery must be stopped',
        'controlled exact-HEAD test review',
        'Destroy the old server only after',
        'DNS, TLS, reverse proxy',
        'Octopus-unavailable reviewer waiver',
    ]:
        assert requirement in runbook


def test_bundle_does_not_claim_existing_deployment_authority():
    bundle_and_runbook = '\n'.join(
        [_text(COMPOSE_PATH), _text(ENV_PATH), _text(HELPER_PATH), _text(RUNBOOK_PATH)]
    )

    assert 'review-edge' not in _text(COMPOSE_PATH)
    assert 'edfinder-v3-phase4c-full-20260827_r5-postgres' not in bundle_and_runbook
    assert '.github/workflows/chatgpt-ed-new-ops.yml' not in bundle_and_runbook
    assert 'config/nginx.conf' not in bundle_and_runbook
    assert 'docker-compose.yml' not in _text(RUNBOOK_PATH)
