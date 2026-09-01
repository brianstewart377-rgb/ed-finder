import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/octopus-edge-status.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
DISPATCH = ROOT / "scripts/operator/actions/dispatch.sh"
OPERATION = "octopus-edge-status"


def _python_functions():
    source = ACTION.read_text(encoding="utf-8")
    program = source.split("exec python3 - <<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    namespace = {}
    exec(program.split("receipt = {", 1)[0], namespace)
    return namespace


def test_ed_new_workflow_and_dispatch_allowlist_dedicated_action():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    dispatch = DISPATCH.read_text(encoding="utf-8")
    assert workflow.count(f"          - {OPERATION}\n") == 1
    assert f"host-status|{OPERATION}|recover-v3-runtime-contract" in workflow
    assert f"steps.request.outputs.operation == '{OPERATION}'" in workflow
    assert f"trusted-main/scripts/operator/actions/{OPERATION}.sh" in workflow
    assert f"{OPERATION})" in dispatch
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in dispatch


def test_variable_docker_network_proxy_route_is_correlated_in_same_server():
    functions = _python_functions()
    config = """
server {
  listen 443 ssl;
  server_name octopus.ed-finder.app;
  set $octopus_upstream http://octopus-web:3000;
  location / { proxy_pass $octopus_upstream; }
  proxy_pass $octopus_upstream;
  ssl_certificate_key /do/not/report/privkey.pem;
}
"""
    servers = functions["parse_proxy_servers"](config)
    present, resolved, emitted = functions["route_present"](servers)
    assert present is True
    assert resolved == ["http://octopus-web:3000"]
    assert "43300" not in " ".join(emitted)
    assert all(item.startswith(("set ", "server_name ", "proxy_pass ")) for item in emitted)
    assert "privkey" not in " ".join(emitted)


def test_proxy_variable_cannot_be_defined_in_an_unrelated_server():
    functions = _python_functions()
    config = """
server {
  server_name unrelated.example;
  set $octopus_upstream http://octopus-web:3000;
}
server {
  server_name octopus.ed-finder.app;
  proxy_pass $octopus_upstream;
}
"""
    present, _, _ = functions["route_present"](functions["parse_proxy_servers"](config))
    assert present is False


def test_version_requires_exact_expected_release_not_http_success_or_substring():
    matches = _python_functions()["version_matches"]
    assert matches('{"version":"1.0.122"}') is True
    assert matches('{"release":"v1.0.122"}') is True
    assert matches('{"version":"1.0.121"}') is False
    assert matches('{"version":"11.0.1220"}') is False
    assert matches("x" * 4097 + "1.0.122") is False


def test_proxy_inspection_failure_is_explicit_and_fail_closed():
    source = ACTION.read_text(encoding="utf-8")
    inspection = source.split('nginx_result = run(["docker", "exec"', 1)[1].split(
        'receipt["proxy"] = proxy', 1
    )[0]
    assert 'proxy["inspection_succeeded"] = nginx_result.returncode == 0' in inspection
    assert 'failures.append("proxy_inspection_failed")' in inspection
    assert "if nginx_result.returncode:" in inspection
    assert "else:" in inspection
    assert "|| true" not in inspection
    assert "2>/dev/null" not in inspection


def test_served_certificate_is_independent_from_https_and_installed_certs():
    source = ACTION.read_text(encoding="utf-8")
    assert '"tls_verification_bypassed_for_response_only"] = True' in source
    assert '"installed_certificate_availability": "not_inspected"' in source
    assert '"-servername", PUBLIC_NAME' in source
    assert '"-verify_hostname", PUBLIC_NAME, "-verify_return_error"' in source
    served_block = source.split('served = {', 1)[1].split('receipt["served_certificate"]', 1)[0]
    assert "/etc/letsencrypt" not in served_block
    assert "installed_certificate" not in served_block.replace(
        '"installed_certificate_availability": "not_inspected"', ""
    )
    assert 'served["certificate_present"] = metadata.returncode == 0' in served_block
    assert 'served["hostname_valid"] = hostname_check.returncode == 0' in served_block
    assert 'served["currently_valid"] = validity_check.returncode == 0' in served_block


def test_action_command_surface_is_read_only_secret_safe_and_bounded():
    source = ACTION.read_text(encoding="utf-8")
    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert "MAX_RESPONSE = 4096" in source
    forbidden = (
        ".env", "Config.Env", "POSTGRES", "psql", "mysql", "sqlite", "/root/.ssh",
        "id_rsa", "privkey.pem", "docker restart", "compose up", "compose down",
        "systemctl", "service restart", "shred", "chmod", "chown",
    )
    for value in forbidden:
        assert value not in source
    for safety_field in (
        '"db_access_performed": False', '"db_writes_performed": False',
        '"env_files_read": False', '"private_keys_read": False',
        '"service_changes_performed": False', '"filesystem_writes_performed": False',
    ):
        assert safety_field in source
    syntax = subprocess.run(["bash", "-n", str(ACTION)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
