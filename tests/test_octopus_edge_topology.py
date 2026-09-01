import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/octopus-edge-topology.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
DISPATCH = ROOT / "scripts/operator/actions/dispatch.sh"
OPERATION = "octopus-edge-topology"


def test_workflow_and_dispatch_allowlist_topology_inventory():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    dispatch = DISPATCH.read_text(encoding="utf-8")
    assert workflow.count(f"          - {OPERATION}\n") == 1
    assert f"octopus-edge-status|{OPERATION}|recover-v3-runtime-contract" in workflow
    assert f"steps.request.outputs.operation == '{OPERATION}'" in workflow
    assert f"trusted-main/scripts/operator/actions/{OPERATION}.sh" in workflow
    assert f"{OPERATION})" in dispatch
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in dispatch


def test_missing_python_emits_structured_stopped_receipt():
    result = subprocess.run(
        ["/bin/bash", str(ACTION)],
        capture_output=True,
        text=True,
        env={"PATH": "/definitely-missing"},
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["operation"] == OPERATION
    assert payload["status"] == "stopped"
    assert payload["read_only"] is True
    assert payload["failures"] == ["python3_unavailable"]


def test_topology_inventory_is_metadata_only_and_secret_safe():
    source = ACTION.read_text(encoding="utf-8")
    assert '"docker", "inspect", "--format"' in source
    assert '"{{json .Mounts}}"' in source
    assert '"{{json .NetworkSettings.Networks}}"' in source
    assert '"{{json .NetworkSettings.Ports}}"' in source
    assert '"{{.HostConfig.NetworkMode}}"' in source
    assert 'com.docker.compose.project.config_files' in source
    assert 'Path("/opt/octopus/ui.htpasswd")' in source
    assert ".stat()" in source

    forbidden = (
        "Config.Env",
        ".env",
        "read_text(",
        "read_bytes(",
        "open('/opt/octopus/ui.htpasswd",
        'open("/opt/octopus/ui.htpasswd',
        "cat /opt/octopus/ui.htpasswd",
        "POSTGRES_PASSWORD",
        "BETTER_AUTH_SECRET",
        "GITHUB_APP_PRIVATE_KEY",
        "docker restart",
        "docker stop",
        "docker rm",
        "docker network connect",
        "compose up",
        "compose down",
        "systemctl",
    )
    for value in forbidden:
        assert value not in source

    for safety_field in (
        '"db_access_performed": False',
        '"db_writes_performed": False',
        '"env_files_read": False',
        '"private_keys_read": False',
        '"service_changes_performed": False',
        '"filesystem_writes_performed": False',
    ):
        assert safety_field in source


def test_http_summary_never_emits_cookie_headers_or_body():
    source = ACTION.read_text(encoding="utf-8")
    header_allowlist = source.split('if key in {', 1)[1].split('}:', 1)[0]
    assert "set-cookie" not in header_allowlist.lower()
    assert "cookie" not in header_allowlist.lower()
    assert '"body_sha256"' in source
    assert '"title"' in source
    assert '"body": body' not in source


def test_nginx_inventory_is_directive_allowlisted_and_excludes_key_directive():
    source = ACTION.read_text(encoding="utf-8")
    assert "allowed_semicolon = re.compile" in source
    assert "auth_request" in source
    assert "auth_basic_user_file" in source
    assert "proxy_pass" in source
    assert "server_name" in source
    assert "ssl_certificate_key" not in source


def test_action_shell_syntax():
    result = subprocess.run(["bash", "-n", str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
