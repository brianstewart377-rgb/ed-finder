import os
import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def _normalise_nginx_config_for_drift_check(text: str) -> str:
    replacements = {
        '/var/www/app': '/tmp/ngx/www',
        '/var/www/review': '/tmp/ngx/www',
        '/var/www/certbot': '/tmp/ngx/www',
        '/etc/nginx/snippets/security-headers.conf': '/tmp/ngx/snippets/security-headers.conf',
        '/var/log/nginx-review/review-access.log': '/tmp/ngx/logs/review-access.log',
        '/var/log/nginx-review/review-error.log': '/tmp/ngx/logs/review-error.log',
        'http://api:8000': 'http://127.0.0.1:8000',
        'http://review-api:8000': 'http://127.0.0.1:8000',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if ' # ' in line:
            line = line.split(' # ', 1)[0].rstrip()
        lines.append(line)
    return '\n'.join(lines)


def _production_nginx_http_and_review_slice(text: str) -> str:
    marker = '    # ── HTTPS main server ────────────────────────────────────────────────────'
    return text.split(marker, 1)[0].rstrip() + '\n}'


def test_frontend_package_manager_is_pinned_to_committed_yarn_version():
    package_json = _read('frontend', 'package.json')

    assert '"packageManager": "yarn@1.22.22"' in package_json


def test_package_frontend_bundle_script_builds_archive_and_checksum_from_real_dist():
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required for frontend bundle packaging runtime test')

    bash_probe = subprocess.run(
        [bash, '-lc', 'printf ready'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if bash_probe.returncode != 0 or bash_probe.stdout.strip() != 'ready':
        pytest.skip('usable bash is unavailable for frontend bundle packaging runtime test')

    script = ROOT / 'scripts' / 'package_frontend_bundle.sh'

    with TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        frontend_dir = tmp / 'frontend'
        dist_dir = frontend_dir / 'dist'
        dist_dir.mkdir(parents=True)
        (frontend_dir / 'yarn.lock').write_text('# runtime test lockfile\n', encoding='utf-8')
        (dist_dir / 'index.html').write_text('<!doctype html><title>bundle test</title>\n', encoding='utf-8')
        (dist_dir / 'assets.txt').write_text('bundle-asset\n', encoding='utf-8')

        archive_path = tmp / 'frontend-dist-runtime.tar.gz'
        env = {
            **os.environ,
            'FRONTEND_DIR': str(frontend_dir),
            'OUTPUT_DIR': str(tmp / 'artifacts'),
            'COMMIT_SHA': 'runtime-test',
        }

        result = subprocess.run(
            [bash, str(script), '--output', str(archive_path)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        assert archive_path.exists()
        checksum_path = archive_path.with_suffix(archive_path.suffix + '.sha256')
        assert checksum_path.exists()
        assert str(archive_path) in result.stdout

        with tarfile.open(archive_path, 'r:gz') as tar:
            names = tar.getnames()

        assert 'dist/index.html' in names
        assert 'dist/assets.txt' in names

        checksum_line = checksum_path.read_text(encoding='utf-8').strip().split()[0]
        actual_checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        assert checksum_line == actual_checksum

        check_result = subprocess.run(
            [
                bash,
                '-lc',
                'if command -v sha256sum >/dev/null 2>&1; then '
                'sha256sum -c "$1"; '
                'elif command -v shasum >/dev/null 2>&1; then '
                'shasum -a 256 -c "$1"; '
                'else exit 127; fi',
                'bash',
                str(checksum_path),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert check_result.returncode == 0, check_result.stderr or check_result.stdout


def test_frontend_packaging_remains_available_but_v2_deploy_path_is_retired():
    deploy = _read('scripts', 'deploy_main.sh')
    package = _read('scripts', 'package_frontend_bundle.sh')

    assert not (ROOT / 'scripts' / 'release-main-to-prod.ps1').exists()
    assert 'RETIRED — V2 single-host deployment entrypoint' in deploy
    assert 'intentionally performs no deployment or production mutation' in deploy
    assert 'exit 64' in deploy
    for retired_action in (
        'git pull --ff-only',
        'bash scripts/apply_migrations.sh',
        'docker compose up',
        'nginx -s reload',
        '--frontend-archive',
    ):
        assert retired_action not in deploy

    assert 'frontend/dist' in package
    assert 'frontend/yarn.lock' in package or '$FRONTEND_DIR/yarn.lock' in package
    assert 'cygpath -u' in package
    assert 'tar --force-local' not in package
    assert '.sha256' in package


def test_ci_workflow_uses_the_locked_svelte_web_toolchain_not_react_yarn():
    workflow = _read('.github', 'workflows', 'ci.yml')

    assert 'working-directory: apps/web' in workflow
    assert 'corepack prepare pnpm@11.25.0 --activate' in workflow
    assert 'pnpm install --frozen-lockfile' in workflow
    assert 'pnpm check' in workflow
    assert 'pnpm lint' in workflow
    assert 'pnpm test' in workflow
    assert 'pnpm build' in workflow
    assert 'frontend/yarn.lock' not in workflow
    assert 'yarn install --frozen-lockfile' not in workflow
    assert 'yarn test:ci' not in workflow


def test_nginx_ci_config_stays_structurally_aligned_with_production_http_and_review_blocks():
    production = _read('config', 'nginx.conf')
    ci = _read('config', 'nginx-ci.conf')

    normalised_production = _normalise_nginx_config_for_drift_check(
        _production_nginx_http_and_review_slice(production)
    )
    normalised_ci = _normalise_nginx_config_for_drift_check(ci)

    assert normalised_ci == normalised_production


def test_frontend_emits_release_identity_meta_for_the_deploy_smoke():
    """A promotion fails unless the served '/' HTML carries the exact single-line
    marker `name="edfinder-build-sha" content="<sha>"` exactly once
    (scripts/operator/v3_production_deploy.py smoke(); v3_checkpoint_public_smoke).
    ssr is disabled, so the tag must live in the static app.html, not a component
    <svelte:head>. This guards against silently dropping it (which blocks every
    deploy and leaves prod stale).
    """
    app_html = _read('apps', 'web', 'src', 'app.html')
    svelte_config = _read('apps', 'web', 'svelte.config.js')
    deploy = _read('scripts', 'operator', 'v3_production_deploy.py')

    # Exact byte prefix the smoke matches (single space between attributes).
    marker_prefix = 'name="edfinder-build-sha" content="'
    assert marker_prefix in deploy, (
        'deploy smoke no longer uses this marker — update app.html to match'
    )

    # The tag must be present AND on one physical line (smoke does a literal
    # substring byte count; a prettier-wrapped attribute would never match).
    marker_lines = [
        line for line in app_html.splitlines()
        if '<meta name="edfinder-build-sha"' in line
    ]
    assert len(marker_lines) == 1, 'exactly one edfinder-build-sha meta line expected'
    assert (
        f'{marker_prefix}%sveltekit.env.PUBLIC_BUILD_SHA%"' in marker_lines[0]
    ), 'meta tag must be single-line and use the PUBLIC_BUILD_SHA build env'

    # %sveltekit.env.X% only resolves for PUBLIC_-prefixed vars; svelte.config.js
    # derives PUBLIC_BUILD_SHA from the existing VITE_BUILD_SHA (one source).
    assert 'PUBLIC_BUILD_SHA' in svelte_config
    assert 'VITE_BUILD_SHA' in svelte_config
