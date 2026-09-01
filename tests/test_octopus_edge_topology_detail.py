import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/octopus-edge-topology-detail.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
DISPATCH = ROOT / "scripts/operator/actions/dispatch.sh"
OPERATION = "octopus-edge-topology-detail"
CONTAINERS = ("edfinder-v3-public-auth-edge", "edfinder-v3-proxy")


def _python_functions():
    source = ACTION.read_text(encoding="utf-8")
    program = source.split("exec python3 - <<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    namespace = {}
    exec(program.split("failures = []", 1)[0], namespace)
    return namespace


def test_workflow_and_fixed_dispatcher_allowlist_the_operation():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    dispatcher = DISPATCH.read_text(encoding="utf-8")
    assert workflow.count(f"          - {OPERATION}\n") == 1
    assert f"octopus-edge-status|{OPERATION}|recover-v3-runtime-contract" in workflow
    assert f"steps.request.outputs.operation == '{OPERATION}'" in workflow
    assert f"trusted-main/scripts/operator/actions/{OPERATION}.sh" in workflow
    assert "ref: main" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert f"{OPERATION})" in dispatcher
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in dispatcher


def test_action_has_no_parameters_and_uses_only_exact_container_names():
    source = ACTION.read_text(encoding="utf-8")
    assert 'if [ "$#" -ne 0 ]' in source
    assert f'CONTAINERS = ("{CONTAINERS[0]}", "{CONTAINERS[1]}")' in source
    assert '["docker", "inspect", "--type", "container", "--format", INSPECT_FORMAT, name]' in source
    assert '["docker", "exec", name, "nginx", "-T"]' in source
    assert "docker ps" not in source
    assert "docker container ls" not in source

    result = subprocess.run(["bash", str(ACTION), "unexpected"], capture_output=True, text=True)
    assert result.returncode == 64
    assert json.loads(result.stdout)["failures"] == ["caller_parameters_not_allowed"]


def test_docker_metadata_is_bounded_and_does_not_request_env_or_secrets():
    source = ACTION.read_text(encoding="utf-8")
    for required in (
        '"image": "{{.Config.Image}}"',
        '"network_mode": "{{.HostConfig.NetworkMode}}"',
        '"networks": "{{json .NetworkSettings.Networks}}"',
        '"ports": "{{json .NetworkSettings.Ports}}"',
        '"mounts": "{{json .Mounts}}"',
    ):
        assert required in source
    forbidden = (
        "Config.Env", ".env", "printenv", "/proc/", "docker cp", "docker volume",
        "psql", "postgres", "mysql", "sqlite", "redis-cli",
        "privkey", "docker restart", "docker start", "docker stop", "compose up",
        "compose down", "systemctl", "service restart", "chmod", "chown", "tee ",
    )
    lowered = source.lower()
    for value in forbidden:
        assert value.lower() not in lowered


def test_inspect_decoder_emits_required_structure_and_fails_closed():
    decode = _python_functions()["decode_inspect"]
    raw = {
        "name": "/edfinder-v3-proxy",
        "image": "nginx:1.27",
        "state": "running",
        "network_mode": "bridge",
        "networks": json.dumps({"edge": {"IPAddress": "172.20.0.2"}}),
        "ports": json.dumps({"443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]}),
        "mounts": json.dumps([
            {"Source": "/opt/ed-finder/nginx.conf", "Destination": "/etc/nginx/nginx.conf", "Type": "bind", "RW": False},
            {"Source": "cache", "Destination": "/cache", "Type": "volume", "RW": True},
            {"Source": "/tmp", "Destination": "/tmp", "Type": "tmpfs", "RW": True},
        ]),
    }
    result = decode(json.dumps(raw), "edfinder-v3-proxy")
    assert result == {
        "name": "edfinder-v3-proxy",
        "image": "nginx:1.27",
        "network_mode": "bridge",
        "network_names": ["edge"],
        "published_ports": {"443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]},
        "mounts": [
            {"source": "/opt/ed-finder/nginx.conf", "destination": "/etc/nginx/nginx.conf", "type": "bind", "rw": False},
            {"source": "cache", "destination": "/cache", "type": "volume", "rw": True},
        ],
    }
    raw["name"] = "/lookalike-proxy"
    try:
        decode(json.dumps(raw), "edfinder-v3-proxy")
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected container identity was accepted")
    raw["name"] = "/edfinder-v3-proxy"
    raw["state"] = "exited"
    try:
        decode(json.dumps(raw), "edfinder-v3-proxy")
    except ValueError:
        pass
    else:
        raise AssertionError("non-running container was accepted")


def test_nginx_output_is_reduced_to_origins_and_four_safe_directives():
    parse = _python_functions()["sanitized_nginx_metadata"]
    config = """
# configuration file /etc/nginx/nginx.conf:
include /etc/nginx/conf.d/*.conf;
# configuration file /etc/nginx/conf.d/octopus.conf:
server {
  listen 443 ssl;
  server_name octopus.ed-finder.app;
  proxy_pass http://127.0.0.1:43300;
  ssl_certificate_key /run/secrets/octopus.key;
  auth_basic_user_file /run/secrets/htpasswd;
}
"""
    result = parse(config)
    assert result["configuration_file_origins"] == [
        "/etc/nginx/nginx.conf", "/etc/nginx/conf.d/octopus.conf"
    ]
    assert [item["name"] for item in result["directives"]] == [
        "include", "listen", "server_name", "proxy_pass"
    ]
    serialized = json.dumps(result)
    assert "octopus.key" not in serialized
    assert "htpasswd" not in serialized


def test_exact_octopus_version_check_rejects_substrings_and_other_versions():
    exact = _python_functions()["exact_version"]
    assert exact('{"version":"1.0.122"}') is True
    assert exact('{"release":"v1.0.122"}') is True
    assert exact('"1.0.122"') is True
    assert exact('{"version":"1.0.122-build1"}') is False
    assert exact('{"version":"11.0.1220"}') is False
    assert exact('{"version":"1.0.121"}') is False


def test_host_workdir_fail_closed_and_receipt_safety_fields_are_present():
    source = ACTION.read_text(encoding="utf-8")
    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert 'EXPECTED_WORKDIR = "/opt/ed-finder"' in source
    assert 'failures.append("unexpected_host_identity")' in source
    assert 'failures.append("unexpected_working_directory")' in source
    assert 'failures.append(f"container_missing:{name}")' in source
    assert 'failures.append(f"container_unexpected:{name}")' in source
    for field in (
        '"db_access_performed": False', '"db_writes_performed": False',
        '"env_files_read": False', '"private_keys_read": False',
        '"service_changes_performed": False', '"filesystem_writes_performed": False',
    ):
        assert field in source
    syntax = subprocess.run(["bash", "-n", str(ACTION)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
