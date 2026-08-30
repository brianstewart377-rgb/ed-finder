from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "v3" / "compose.yml"


def _compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_v3_runtime_has_no_postgres_service_or_dependency():
    services = _compose()["services"]
    assert set(services) == {"redis", "api", "eddn", "proxy", "maintenance"}
    assert "postgres" not in services
    assert "nats" not in services
    assert not any(
        name.startswith("postgres") or "postgres:" in str(service.get("image", ""))
        for name, service in services.items()
    )
    for service in services.values():
        assert "postgres" not in service.get("depends_on", {})
        assert "/var/lib/postgresql/data" not in str(service.get("volumes", []))
        assert "docker-entrypoint-initdb.d" not in str(service.get("volumes", []))


def test_v3_default_runtime_is_private_and_uses_external_role_urls():
    services = _compose()["services"]
    assert services["proxy"]["ports"] == ["${V3_BIND_ADDRESS:-127.0.0.1}:${V3_HTTP_PORT:-8080}:8080"]
    assert services["api"]["environment"]["DATABASE_URL"].startswith("${V3_DATABASE_APP_URL:?")
    assert services["api"]["environment"]["DATABASE_READONLY_URL"].startswith("${V3_DATABASE_READONLY_URL:?")
    assert services["eddn"]["environment"]["DATABASE_URL"].startswith("${V3_DATABASE_EDDN_URL:?")
    assert services["api"]["environment"]["FRONTIER_CLIENT_ID"] == ""
    assert services["maintenance"]["profiles"] == ["maintenance"]


def test_v3_maintenance_url_has_compose_safe_disabled_fallback():
    maintenance_url = _compose()["services"]["maintenance"]["environment"]["DATABASE_URL"]
    assert maintenance_url == "${V3_DATABASE_MAINTENANCE_URL:-disabled}"
    assert ";" not in maintenance_url


def test_v3_services_have_operational_guards():
    for name in ("redis", "api", "eddn", "proxy", "maintenance"):
        service = _compose()["services"][name]
        assert service["restart"] == "unless-stopped"
        assert service["healthcheck"]
        assert service["mem_limit"]
        assert service["cpus"]
        assert service["logging"]["driver"] == "local"


def test_v3_operator_script_never_starts_maintenance_or_postgres_by_default():
    script = (ROOT / "scripts" / "operator" / "v3-runtime.sh").read_text(encoding="utf-8")
    assert "up -d --build redis api eddn proxy" in script
    assert "up -d --build postgres" not in script
    assert '"postgres", "ed-postgres"' in script
    assert "source \"$ENV_FILE\"" not in script
