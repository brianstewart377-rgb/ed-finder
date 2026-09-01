from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
DISPATCH = ROOT / "scripts/operator/actions/dispatch.sh"
ACTION = ROOT / "scripts/operator/actions/octopus-edge-status.sh"
OPERATION = "octopus-edge-status"


def test_ed_new_workflow_allowlists_and_uses_pinned_trusted_action():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(f"          - {OPERATION}\n") == 1
    assert f"host-status|{OPERATION}|recover-v3-runtime-contract" in source
    block = source.split("- name: Inspect Octopus edge status (read only)", 1)[1].split("- name:", 1)[0]
    assert "StrictHostKeyChecking=yes" in block
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in block
    assert "trusted-main/scripts/operator/actions/octopus-edge-status.sh" in block
    assert "git pull" not in block


def test_dispatcher_is_fail_closed_and_routes_only_the_named_action():
    source = DISPATCH.read_text(encoding="utf-8")
    assert f"  {OPERATION})" in source
    assert f"exec bash scripts/operator/actions/{OPERATION}.sh" in source
    assert 'STOP: unsupported operator stage: $stage' in source


def test_edge_action_is_read_only_secret_safe_and_host_pinned():
    source = ACTION.read_text(encoding="utf-8")
    for required in (
        'EXPECTED_HOST="ed-finder-prod"',
        'EXPECTED_FQDN="nb79a3d.mevnode.com"',
        'OCTOPUS_UPSTREAM="127.0.0.1:43300"',
        'docker ps --no-trunc --format',
        'Config.Env',
        'nginx -T',
        'server_name|proxy_pass',
        '--resolve "$OCTOPUS_HOST:443:127.0.0.1"',
        'openssl x509 -noout -subject -ext subjectAltName',
        '-name fullchain.pem -o -name cert.pem',
        '"db_access_performed": False',
        '"service_restarts_performed": False',
    ):
        assert required in source

    forbidden = (
        "docker compose up",
        "docker restart",
        "systemctl restart",
        "service restart",
        "psql",
        "DATABASE_URL",
        "private_key",
        "BEGIN PRIVATE KEY",
        "cat .env",
        "source .env",
    )
    lowered = source.lower()
    for token in forbidden:
        assert token.lower() not in lowered


def test_receipt_contains_required_machine_readable_conclusions():
    source = ACTION.read_text(encoding="utf-8")
    for field in (
        '"dns_present"',
        '"listener_80"',
        '"listener_443"',
        '"listener_43300"',
        '"octopus_internal_healthy"',
        '"route_present"',
        '"certificate_present"',
        '"needed"',
    ):
        assert field in source
