from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_REVIEW_COMPOSE = ROOT / 'docker-compose.review.yml'
HOSTED_REVIEW_COMPOSE = ROOT / 'docker-compose.review-hosted.yml'
PRODUCTION_COMPOSE = ROOT / 'docker-compose.yml'
NGINX_CONFIG = ROOT / 'config' / 'nginx.conf'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
DEPLOY_SCRIPT = ROOT / 'scripts' / 'ops' / 'deploy_hosted_review.sh'
AUTH_SCRIPT = ROOT / 'scripts' / 'ops' / 'create_review_auth_file.sh'
HOSTED_DOC = ROOT / 'docs' / 'operations' / 'hosted-review-environment.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _service_names(compose_text: str) -> list[str]:
    names: list[str] = []
    in_services = False
    for line in compose_text.splitlines():
        if line == 'services:':
            in_services = True
            continue
        if in_services and line and not line.startswith(' '):
            break
        if in_services:
            match = re.match(r'^  ([A-Za-z0-9_-]+):$', line)
            if match:
                names.append(match.group(1))
    return names


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


def _merged_named_resource_name(base_text: str, overlay_text: str, section: str, resource: str) -> str:
    try:
        return _named_resource_name(overlay_text, section, resource)
    except AssertionError:
        return _named_resource_name(base_text, section, resource)


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


def _mapping_value(block: str, key: str, name: str) -> str | None:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f'{key}:':
            indent = len(line) - len(line.lstrip(' '))
            for child in lines[index + 1:]:
                if child.strip() == '':
                    continue
                child_indent = len(child) - len(child.lstrip(' '))
                if child_indent <= indent:
                    break
                stripped = child.strip()
                if stripped.startswith(f'{name}:'):
                    return stripped.split(':', 1)[1].strip()
    return None


def _server_blocks(nginx_text: str) -> list[str]:
    blocks: list[str] = []
    collecting = False
    depth = 0
    current: list[str] = []
    for line in nginx_text.splitlines():
        if not collecting and re.match(r'^\s*server\s+\{', line):
            collecting = True
        if collecting:
            current.append(line)
            depth += line.count('{') - line.count('}')
            if depth == 0:
                blocks.append('\n'.join(current))
                current = []
                collecting = False
    return blocks


def _server_for_name(nginx_text: str, server_name: str) -> str:
    for block in _server_blocks(nginx_text):
        if f'server_name {server_name};' in block:
            return block
    raise AssertionError(f'missing nginx server block for {server_name}')


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


def test_hosted_review_overlay_adds_only_review_api_to_edge_network():
    compose_text = _read(HOSTED_REVIEW_COMPOSE)

    assert _list_values(_service_block(compose_text, 'review-api'), 'networks') == ['review', 'review-edge']
    assert 'review-edge' not in _service_block(compose_text, 'review-postgres')
    assert 'review-edge' not in _service_block(compose_text, 'review-redis')
    assert _named_resource_name(compose_text, 'networks', 'review-edge') == 'edfinder-review-edge'
    assert 'external: true' in _child_block(_top_level_block(compose_text, 'networks'), 'review-edge')


def test_hosted_review_compose_merges_to_hosted_private_resource_names():
    local_text = _read(LOCAL_REVIEW_COMPOSE)
    hosted_text = _read(HOSTED_REVIEW_COMPOSE)

    assert (
        _merged_named_resource_name(local_text, hosted_text, 'networks', 'review')
        == 'edfinder-review-hosted-network'
    )
    assert (
        _merged_named_resource_name(local_text, hosted_text, 'volumes', 'review_postgres_data')
        == 'edfinder_review_hosted_postgres_data'
    )
    assert (
        _merged_named_resource_name(local_text, hosted_text, 'volumes', 'review_redis_data')
        == 'edfinder_review_hosted_redis_data'
    )


def test_hosted_review_overlay_constrains_targets_cors_and_resources():
    compose_text = _read(HOSTED_REVIEW_COMPOSE)
    api_block = _service_block(compose_text, 'review-api')

    assert 'env_file:' not in compose_text
    assert '.env' not in compose_text
    for forbidden in (
        'postgresql://edfinder:',
        '@postgres:5432/edfinder',
        'redis://redis:6379',
        'ed-postgres',
        'ed-redis',
    ):
        assert forbidden not in compose_text

    assert _mapping_value(api_block, 'environment', 'CORS_ORIGINS') == 'https://review.ed-finder.app'
    assert 'mem_limit: 2g' in _service_block(compose_text, 'review-postgres')
    assert 'cpus: 2.0' in _service_block(compose_text, 'review-postgres')
    assert 'mem_limit: 256m' in _service_block(compose_text, 'review-redis')
    assert 'cpus: 0.5' in _service_block(compose_text, 'review-redis')
    assert 'mem_limit: 1g' in api_block
    assert 'cpus: 1.0' in api_block


def test_production_compose_attaches_only_nginx_to_review_edge():
    compose_text = _read(PRODUCTION_COMPOSE)
    nginx_block = _service_block(compose_text, 'nginx')

    assert _list_values(nginx_block, 'networks') == ['default', 'review-edge']
    for service_name in _service_names(compose_text):
        if service_name != 'nginx':
            assert 'review-edge' not in _service_block(compose_text, service_name)

    volumes = _list_values(nginx_block, 'volumes')
    assert '/opt/ed-finder-review/frontend/dist:/var/www/review:ro' in volumes
    assert '/opt/ed-finder-review/.secrets/review.htpasswd:/etc/nginx/review.htpasswd:ro' in volumes
    assert '/opt/ed-finder-review/.review/nginx-logs:/var/log/nginx-review' in volumes
    assert 'name: edfinder-review-edge' in compose_text
    assert 'external: true' in compose_text


def test_review_nginx_host_is_auth_protected_and_uses_review_static_root_api_logs_and_rate_limit():
    nginx_text = _read(NGINX_CONFIG)
    review_block = _server_for_name(nginx_text, 'review.ed-finder.app')

    assert 'limit_req_zone $binary_remote_addr zone=review_api:10m rate=30r/s;' in nginx_text
    assert 'auth_basic "ED Finder hosted review";' in review_block
    assert 'auth_basic_user_file /etc/nginx/review.htpasswd;' in review_block
    assert 'access_log /var/log/nginx-review/review-access.log main buffer=32k flush=5s;' in review_block
    assert 'error_log  /var/log/nginx-review/review-error.log warn;' in review_block
    assert 'root /var/www/review;' in review_block
    assert 'try_files $uri /index.html;' in review_block
    assert 'resolver 127.0.0.11 valid=10s ipv6=off;' in review_block
    assert 'set $review_api_origin http://review-api:8000;' in review_block
    assert 'proxy_pass         $review_api_origin;' in review_block
    assert 'limit_req zone=review_api burst=60 nodelay;' in review_block
    assert 'limit_req zone=api' not in review_block
    assert 'api_backend' not in review_block
    assert 'location ^~ /api/admin/' in review_block
    assert 'location = /api/cache/clear' in review_block
    assert 'return 403;' in review_block


def test_production_nginx_hosts_remain_intact():
    nginx_text = _read(NGINX_CONFIG)
    production_blocks = [
        block for block in _server_blocks(nginx_text)
        if 'server_name ed-finder.app www.ed-finder.app;' in block
    ]

    assert len(production_blocks) == 2
    assert 'limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;' in nginx_text
    assert 'limit_req_zone $binary_remote_addr zone=search:10m rate=10r/s;' in nginx_text
    assert any('listen 80;' in block and 'location /api/' in block for block in production_blocks)
    assert any('listen 443 ssl;' in block and 'location = /api/events/live' in block for block in production_blocks)
    assert all('review-api:8000' not in block for block in production_blocks)
    assert all('zone=review_api' not in block for block in production_blocks)
    assert any('proxy_pass         $api_origin;' in block for block in production_blocks)
    assert any('limit_req zone=api burst=60 nodelay;' in block for block in production_blocks)
    assert any('limit_req zone=search burst=20 nodelay;' in block for block in production_blocks)


def test_ci_nginx_syntax_sandbox_maps_review_log_directory():
    workflow = _read(CI_WORKFLOW)

    assert 'Nginx config syntax' in workflow
    assert 'mkdir -p /tmp/ngx/snippets /tmp/ngx/www /tmp/ngx/v2 /tmp/ngx/logs' in workflow
    assert "sed -i 's|/var/log/nginx-review/|/tmp/ngx/logs/|g' /tmp/ngx/nginx.conf" in workflow


def test_hosted_review_deploy_tool_has_required_safety_guards():
    script = _read(DEPLOY_SCRIPT)

    assert '--confirm-hosted-review' in script
    assert 'mutating hosted review commands require --confirm-hosted-review' in script
    assert 'missing review auth file' in script
    assert 'must not be world-readable' in script
    assert 'status --porcelain=v1 --untracked-files=all' in script
    assert '/opt/ed-finder-review' in script
    assert 'git -C "$PRODUCTION_REPO_DIR" checkout' not in script
    assert 'git -C "$PRODUCTION_REPO_DIR" switch' not in script
    assert 'VITE_PUBLIC_BASE=/ corepack yarn build' in script
    assert 'docker compose "${compose_args[@]}"' in script
    assert 'docker compose down' not in script
    assert 'reset_hosted_review_project' in script
    assert 'run_review_compose down -v --remove-orphans' in script
    assert 'local down_args=(down --remove-orphans)' in script
    assert 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review' in script
    assert 'redis://review-redis:6379/0' in script
    assert 'postgresql://edfinder:' in script
    assert 'redis://redis:6379' in script
    assert 'capture_production_container_state' in script
    assert 'verify_edge_network_membership' in script
    assert 'ed-nginx|"$REVIEW_PROJECT"-review-api-*' in script
    assert 'REVIEW_NGINX_LOG_DIR="${REVIEW_NGINX_LOG_DIR:-$REVIEW_REPO_DIR/.review/nginx-logs}"' in script
    assert 'ensure_review_nginx_log_dir' in script
    reset_call = script.index('say "Reset hosted review project to clean synthetic volumes"')
    assert script.index('VITE_PUBLIC_BASE=/ corepack yarn build') < reset_call
    assert script.index('say "Validate hosted review compose targets"') < reset_call
    assert reset_call < script.index('run_review_compose up -d review-postgres review-redis')
    assert script.index('production_before="$(capture_production_container_state)"') < reset_call
    verify_call = script.index('  verify_edge_network_membership\n\n  production_after=')
    assert script.index('write_deployment_metadata "$DEPLOY_REF" "$resolved_commit"') > verify_call


def test_hosted_review_deploy_ref_guard_runs_after_checkout_before_mutations():
    script = _read(DEPLOY_SCRIPT)
    deploy_section = script[script.index('deploy_review() {'):script.index('\nteardown_review() {')]

    assert 'require_hosted_review_infrastructure' in script
    assert 'docker-compose.review.yml' in script
    assert 'docker-compose.review-hosted.yml' in script
    assert 'scripts/dev/review_environment_seed.py' in script
    assert 'Selected review ref does not contain hosted review infrastructure.' in script
    assert (
        'Rebase this branch onto current main after the hosted review environment has been merged, '
        'then deploy it again.'
    ) in script

    checkout_call = deploy_section.index('git -C "$REVIEW_REPO_DIR" checkout --detach "$resolved_commit"')
    guard_call = deploy_section.index('  require_hosted_review_infrastructure')
    build_call = deploy_section.index('VITE_PUBLIC_BASE=/ corepack yarn build')
    compose_validation_call = deploy_section.index('  verify_compose_targets')
    reset_call = deploy_section.index('  reset_hosted_review_project')
    data_start_call = deploy_section.index('  run_review_compose up -d review-postgres review-redis')
    bootstrap_call = deploy_section.index('  bootstrap_schema')
    api_build_call = deploy_section.index('  run_review_compose build review-api')
    seed_call = deploy_section.index(
        '  run_review_compose run --rm review-api python /workspace/scripts/dev/review_environment_seed.py'
    )
    api_start_call = deploy_section.index('  run_review_compose up -d review-api')

    assert checkout_call < guard_call
    assert guard_call < build_call
    assert guard_call < compose_validation_call
    assert guard_call < reset_call
    assert guard_call < data_start_call
    assert guard_call < bootstrap_call
    assert guard_call < api_build_call
    assert guard_call < seed_call
    assert guard_call < api_start_call


def test_review_auth_helper_prompts_without_echo_and_uses_bcrypt_htpasswd():
    script = _read(AUTH_SCRIPT)
    file_modes = re.findall(r'-m\s+([0-7]{3})', script)

    assert 'read -r -s -p' in script
    assert 'htpasswd -B -C 12 -i -c' in script
    assert '.secrets/review.htpasswd' in script
    assert 'docker compose exec -T nginx' in script
    assert 'id -g nginx' in script
    assert 'getent group nginx' not in script
    assert '[[ ! "$gid" =~ ^[0-9]+$ ]]' in script
    assert 'NGINX_GROUP_ID="$(resolve_nginx_group_id)"' in script
    assert 'install -o root -g "$NGINX_GROUP_ID" -m 640 "$TMP_FILE" "$AUTH_FILE"' in script
    assert 'install -m 600' not in script
    assert '640' in file_modes
    assert '600' not in file_modes
    assert all(mode[-1] == '0' for mode in file_modes)
    assert 'mode 640' in script
    assert 'root:%s' in script
    assert 'already exists; pass --force to replace it intentionally' in script
    assert 'PASSWORD' not in re.sub(r'PASSWORD(_CONFIRM)?', '', script)


def test_hosted_review_operations_doc_covers_activation_and_boundaries():
    doc = _read(HOSTED_DOC)

    for expected in (
        'review.ed-finder.app',
        'Cloudflare/proxied Flexible SSL',
        'docker network create edfinder-review-edge',
        'scripts/ops/create_review_auth_file.sh --user review',
        'Merge PR #272',
        'Update Hetzner `main` with the merged hosted-review infrastructure',
        'Rebase PR #271 onto the updated `main`',
        'Push the rebased PR #271 branch',
        'Deploy that rebased branch into `review.ed-finder.app`',
        'scripts/ops/deploy_hosted_review.sh deploy',
        '--ref stage-25d-a2-planner-clarity',
        'docker compose config -q',
        'docker compose run --rm --no-deps nginx nginx -t',
        'docker compose up -d nginx',
        'scripts/ops/deploy_hosted_review.sh teardown',
        'review hostname remains configured',
        'Do not stop production Nginx as a review rollback step',
        '.review/nginx-logs',
        'Review data is synthetic',
        'Review drafts live in browser storage',
        'Review cannot alter Elite Dangerous',
    ):
        assert expected in doc
    assert 'docker compose stop nginx' not in doc
