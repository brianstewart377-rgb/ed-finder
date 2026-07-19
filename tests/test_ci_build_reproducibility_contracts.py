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
            [bash, '-lc', 'sha256sum -c "$1"', 'bash', str(checksum_path)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert check_result.returncode == 0, check_result.stderr or check_result.stdout


def test_deploy_and_release_paths_support_prebuilt_frontend_artifacts():
    deploy = _read('scripts', 'deploy_main.sh')
    release = _read('scripts', 'release-main-to-prod.ps1')
    package = _read('scripts', 'package_frontend_bundle.sh')

    assert '--frontend-archive' in deploy
    assert 'tar -xzf "$FRONTEND_ARCHIVE"' in deploy
    assert 'yarn install --frozen-lockfile --no-progress --non-interactive' in deploy
    assert 'scripts/package_frontend_bundle.sh' in release
    assert 'scp' in release
    assert '--frontend-archive' in release
    assert 'frontend-dist-$head.tar.gz' in release
    assert 'frontend/dist' in package
    assert 'frontend/yarn.lock' in package or '$FRONTEND_DIR/yarn.lock' in package
    assert 'cygpath -u' in package
    assert 'tar --force-local' not in package
    assert '.sha256' in package


def test_ci_workflow_uses_pinned_yarn_lock_and_packages_frontend_bundle():
    workflow = _read('.github', 'workflows', 'ci.yml')

    assert 'cache: yarn' in workflow
    assert 'cache-dependency-path: frontend/yarn.lock' in workflow
    assert 'corepack enable' in workflow
    assert 'yarn install --frozen-lockfile --no-progress --non-interactive' in workflow
    assert 'yarn test:ci' in workflow
    assert 'bash scripts/package_frontend_bundle.sh --output artifacts/frontend-bundles/frontend-dist-ci.tar.gz' in workflow
    assert 'artifacts/frontend-bundles/frontend-dist-ci.tar.gz.sha256' in workflow


def test_nginx_ci_config_stays_structurally_aligned_with_production_http_and_review_blocks():
    production = _read('config', 'nginx.conf')
    ci = _read('config', 'nginx-ci.conf')

    normalised_production = _normalise_nginx_config_for_drift_check(
        _production_nginx_http_and_review_slice(production)
    )
    normalised_ci = _normalise_nginx_config_for_drift_check(ci)

    assert normalised_ci == normalised_production
