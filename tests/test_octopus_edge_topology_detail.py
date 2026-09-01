import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/octopus-edge-topology-detail.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
DISPATCH = ROOT / "scripts/operator/actions/dispatch.sh"
OPERATION = "octopus-edge-topology-detail"


def _python_functions():
    source = ACTION.read_text(encoding="utf-8")
    program = source.split("exec python3 - <<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    namespace = {}
    exec(program.split("receipt = {", 1)[0], namespace)
    return namespace


def test_workflow_and_dispatch_exactly_allowlist_dedicated_action():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    dispatch = DISPATCH.read_text(encoding="utf-8")
    assert workflow.count(f"          - {OPERATION}\n") == 1
    assert f"octopus-edge-status|{OPERATION}|recover-v3-runtime-contract" in workflow
    assert f"steps.request.outputs.operation == '{OPERATION}'" in workflow
    assert f"trusted-main/scripts/operator/actions/{OPERATION}.sh" in workflow
    assert f"{OPERATION})" in dispatch
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in dispatch
    assert f"{OPERATION}.sh \"$" not in dispatch


def test_action_rejects_parameters_with_one_structured_receipt():
    result = subprocess.run(["bash", str(ACTION), "unexpected"], capture_output=True, text=True)
    assert result.returncode == 1
    assert len(result.stdout.splitlines()) == 1
    payload = json.loads(result.stdout)
    assert payload["operation"] == OPERATION
    assert payload["status"] == "stopped"
    assert payload["read_only"] is True
    assert payload["failures"] == ["caller_parameters_forbidden"]


def test_missing_python_has_structured_stopped_receipt():
    result = subprocess.run(
        ["/bin/bash", str(ACTION)], capture_output=True, text=True,
        env={"PATH": "/definitely-missing"},
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["operation"] == OPERATION
    assert payload["failures"] == ["python3_unavailable"]


def test_exact_host_directory_containers_and_read_only_command_surface():
    source = ACTION.read_text(encoding="utf-8")
    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert 'EXPECTED_DIRECTORY = "/opt/ed-finder"' in source
    assert 'EXPECTED_CONTAINERS = ("edfinder-v3-public-auth-edge", "edfinder-v3-proxy")' in source
    assert 'run(["docker", "exec", name, "nginx", "-T"])' in source
    assert '["docker", "inspect", "--type", "container", "--format", template, container]' in source
    assert '"name=^/" + name + "$"' in source
    assert ".Config.Image" in source
    assert ".HostConfig.NetworkMode" in source
    assert ".NetworkSettings.Networks" in source
    assert ".NetworkSettings.Ports" in source
    assert ".Mounts" in source
    assert ".Config.Env" not in source
    for field in (
        '"read_only": True', '"db_access_performed": False', '"db_writes_performed": False',
        '"env_files_read": False', '"private_keys_read": False',
        '"service_changes_performed": False', '"filesystem_writes_performed": False',
    ):
        assert field in source
    forbidden = (
        ".env", "/proc/", "POSTGRES", "psql", "mysql", "sqlite", "/root/.ssh",
        "id_rsa", "privkey.pem", "docker restart", "docker start", "docker stop",
        "docker rm", "compose up", "compose down", "network connect", "network disconnect",
        "systemctl", "service restart", "nginx -s", "nginx -t &&",
    )
    for item in forbidden:
        assert item not in source
    syntax = subprocess.run(["bash", "-n", str(ACTION)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_nginx_output_is_origin_correlated_sanitized_and_bounded():
    parse = _python_functions()["parse_nginx_config"]
    config = """
# configuration file /etc/nginx/nginx.conf:
include /etc/nginx/conf.d/*.conf;
# configuration file /etc/nginx/conf.d/app.conf:
server {
  listen 443 ssl;
  server_name example.test;
  proxy_pass http://user:password@upstream.internal/path?token=secret;
  ssl_certificate_key /private/do-not-emit.pem;
  auth_basic_user_file /private/do-not-emit.htpasswd;
}
"""
    origins, directives = parse(config)
    assert origins == ["/etc/nginx/nginx.conf", "/etc/nginx/conf.d/app.conf"]
    assert {item["directive"] for item in directives} == {
        "include", "listen", "server_name", "proxy_pass"
    }
    proxy = next(item for item in directives if item["directive"] == "proxy_pass")
    assert proxy == {
        "origin": "/etc/nginx/conf.d/app.conf",
        "directive": "proxy_pass",
        "value": "http://redacted@upstream.internal/path",
    }
    emitted = json.dumps(directives)
    assert "password" not in emitted
    assert "token" not in emitted
    assert "ssl_certificate_key" not in emitted
    assert "auth_basic_user_file" not in emitted


def test_version_requires_exact_release_and_only_two_expected_containers_are_emitted():
    functions = _python_functions()
    matches = functions["exact_version"]
    assert matches('{"version":"1.0.122"}') is True
    assert matches('{"release":"v1.0.122"}') is True
    assert matches('{"version":"1.0.122-hotfix"}') is False
    assert matches('{"version":"1.0.121"}') is False
    source = ACTION.read_text(encoding="utf-8")
    loop = source.split("containers = []", 1)[1].split('receipt["containers"]', 1)[0]
    assert "for name in EXPECTED_CONTAINERS:" in loop
    assert 'containers.append({"name": name' in loop
    assert "docker ps --format" not in source


def test_receipt_is_compact_structured_and_fails_closed():
    source = ACTION.read_text(encoding="utf-8")
    assert '"image": image' in source
    assert '"network_mode": network_mode' in source
    assert '"network_names": sorted(network_names)' in source
    assert '"published_ports": published_ports' in source
    assert '"container_port": container_port' in source
    assert '"host_ip": binding.get("HostIp")' in source
    assert '"host_port": binding.get("HostPort")' in source
    assert '"mounts": mounts' in source
    assert '"nginx_config_origins": origins' in source
    assert '"nginx_directives": directives' in source
    assert '"source": item.get("Source")' in source
    assert '"destination": item.get("Destination")' in source
    assert '"type": item.get("Type")' in source
    assert '"rw": bool(item.get("RW"))' in source
    assert 'failures.append("missing_or_unexpected_container:" + name)' in source
    assert 'raise RuntimeError("nginx_inspection_failed")' in source
    assert '"success": health_success' in source
    assert '"exact_version_match": version_exact' in source
    assert 'separators=(",", ":")' in source
    assert 'receipt["status"] = "success" if not failures else "stopped"' in source
