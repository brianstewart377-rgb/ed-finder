from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / 'scripts' / 'operator' / 'actions' / 'v3-app-status.sh'
WORKFLOW = ROOT / '.github' / 'workflows' / 'chatgpt-ed-new-ops.yml'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_v3_app_status_is_allowlisted_through_trusted_main_operator_path():
    workflow = _read(WORKFLOW)

    assert '          - v3-app-status\n' in workflow
    assert 'v3-app-status)' in workflow
    assert "steps.request.outputs.operation == 'v3-app-status'" in workflow
    assert 'trusted-main/scripts/operator/actions/v3-app-status.sh' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'UserKnownHostsFile=~/.ssh/known_hosts' in workflow


def test_v3_app_status_has_fixed_read_only_runtime_targets():
    source = _read(ACTION)

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert 'ORIGIN = "http://127.0.0.1:58080"' in source
    assert 'PUBLIC = "https://ed-finder.app"' in source
    assert 'API_CONTAINER = "edfinder-v3-api"' in source
    assert 'HOST_FRONTEND_INDEX = Path("/opt/ed-finder/frontend/dist/index.html")' in source
    assert '"direct_db_access_performed": False' in source
    assert '"application_health_may_read_db": True' in source
    assert '"db_writes_performed": False' in source
    assert '"oauth_login_started": False' in source
    assert '"env_files_read": False' in source
    assert '"private_keys_read": False' in source
    assert '"service_changes_performed": False' in source
    assert '"filesystem_writes_performed": False' in source

    for forbidden in (
        '.env',
        'Config.Env',
        'docker restart',
        'docker compose up',
        'docker compose down',
        'systemctl',
        'pg_dump',
        'pg_restore',
        'FRONTIER_CLIENT_SECRET',
        'ADMIN_TOKEN',
        '/root/.ssh',
    ):
        assert forbidden not in source


def test_v3_app_status_checks_frontend_health_and_oauth_without_starting_login():
    source = _read(ACTION)

    assert 'get(ORIGIN + "/api/health", follow_redirects=False)' in source
    assert 'get(ORIGIN + "/api/auth/session", follow_redirects=False)' in source
    assert 'ORIGIN + "/openapi.json"' in source
    assert 'max_body=MAX_OPENAPI_BODY' in source
    assert 'get(PUBLIC + "/api/health", follow_redirects=False)' in source
    assert 'get(PUBLIC + "/api/auth/session", follow_redirects=False)' in source
    assert 'parse_health_response(public_health_body)' in source
    assert 'parse_anonymous_session(public_session_body)' in source
    assert 'public_health_shape_invalid' in source
    assert 'public_session_shape_invalid' in source
    assert 'replacement ED-Finder backend is online' in source
    assert 'oauth_paths_missing' in source
    assert 'get(ORIGIN + "/api/auth/frontier/login")' not in source
    assert 'get(PUBLIC + "/api/auth/frontier/login")' not in source

    for path in (
        '/api/auth/frontier/login',
        '/api/auth/frontier/callback',
        '/api/auth/session',
        '/api/auth/logout',
        '/api/auth/owner/claim',
    ):
        assert path in source


def test_v3_app_status_does_not_mask_origin_with_public_redirects():
    source = _read(ACTION)

    assert 'def get(url, *, body=True, follow_redirects=False' in source
    assert 'if follow_redirects:\n        argv.append("--location")' in source
    assert 'origin_root, _ = get(ORIGIN + "/", body=False, follow_redirects=False)' in source
    assert 'get(ORIGIN + "/api/health", follow_redirects=False)' in source
    assert 'get(ORIGIN + "/api/auth/session", follow_redirects=False)' in source
    assert 'public_root, _ = get(PUBLIC + "/", body=False, follow_redirects=True)' in source
    assert '200 <= code < 300' in source


def test_v3_app_status_compares_host_bundle_to_running_api_without_mutation():
    source = _read(ACTION)

    assert '["git", "rev-parse", "HEAD"]' in source
    assert '["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=no"]' in source
    assert 'receipt["host_frontend"]' in source
    assert '"host_bundle_available"' in source
    assert '"host_matches_running"' in source
    assert 'Path("/opt/ed-finder/frontend/dist/index.html")' in source
    assert '/app/frontend/index.html' in source
    assert 'git reset' not in source
    assert 'git checkout' not in source
    assert 'git pull' not in source


def test_v3_app_status_rejects_unhealthy_required_containers():
    source = _read(ACTION)

    assert '"(unhealthy)" in item["status"].lower()' in source
    assert 'not item["status"].lower().startswith("up ")' in source
    assert 'required_v3_container_unhealthy' in source
    assert 'receipt["containers"]["unhealthy"] = unhealthy' in source


def test_v3_app_status_shell_syntax_is_valid():
    result = subprocess.run(['bash', '-n', str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
