from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_health_exposes_the_deployed_commit_sha():
    config = _read('apps', 'api', 'src', 'config.py')
    model = _read('apps', 'api', 'src', 'models.py')
    route = _read('apps', 'api', 'src', 'routers', 'meta.py')
    compose = _read('docker-compose.yml')
    deploy = _read('scripts', 'deploy_main.sh')

    assert "build_sha:          str  = 'unknown'" in config
    assert 'build_sha: str' in model
    assert 'build_sha=settings.build_sha' in route
    assert 'BUILD_SHA:            ${EDFINDER_BUILD_SHA:-unknown}' in compose
    assert 'EDFINDER_BUILD_SHA="$(git rev-parse HEAD)"' in deploy


def test_manual_drift_check_is_loud_and_never_deploys():
    check = _read('scripts', 'check-production-drift.ps1')

    assert 'git fetch --prune origin' in check
    assert 'git rev-parse origin/main' in check
    assert 'git rev-list --count "$liveSha..origin/main"' in check
    assert 'DEPLOY DRIFT:' in check
    assert 'Do not use a retired V2/Hetzner release wrapper.' in check
    assert 'current V3 production runbook/operator path' in check
    assert 'scripts/release-main-to-prod.ps1' not in check


def test_v2_release_wrapper_is_retired():
    assert not (ROOT / 'scripts' / 'release-main-to-prod.ps1').exists()
