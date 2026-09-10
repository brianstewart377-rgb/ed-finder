"""Guards for the versioned V3 production private runtime health check.

The check named the legacy api and proxy containers. Retiring them turned it red
on every five-minute run with nothing alerting, so these assertions pin the
properties that broke: no legacy names, no fixed slot name, and no assumption
about which host port the api publishes.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEALTH = ROOT / "deploy/v3-production/health"
SCRIPT = HEALTH / "health-check.sh"
SERVICE = HEALTH / "edfinder-v3-health.service"
TIMER = HEALTH / "edfinder-v3-health.timer"


def test_health_check_never_names_a_retired_or_fixed_slot_container():
    source = SCRIPT.read_text(encoding="utf-8")

    # The legacy pair is gone, and any fixed slot name breaks on the next cutover.
    for forbidden in ("edfinder-v3-api'", "edfinder-v3-proxy'", "api-blue", "web-blue", "api-green", "web-green"):
        assert forbidden not in source


def test_health_check_finds_the_active_origin_by_project_label_and_port():
    source = SCRIPT.read_text(encoding="utf-8")

    # Topology-agnostic: exactly one project container owns the active origin.
    assert "label=com.docker.compose.project=$project" in source
    assert "127.0.0.1:58080" in source
    assert '-eq 1' in source
    # The former api host port and the legacy proxy endpoint are gone with them.
    assert "58095" not in source
    assert "_proxy-health" not in source


def test_health_check_still_covers_the_retained_support_services():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "edfinder-v3-phase4c-full-20260827_r5-postgres" in source
    assert "State.Health.Status" in source
    assert "redis-cli ping" in source
    assert "--jetstream" in source
    # Both application checks go through the active origin, covering the web slot
    # and the api slot it proxies to.
    assert "/api/health" in source
    assert "/api/v1/auth/session" in source


def test_health_timer_runs_every_five_minutes_and_catches_up():
    source = TIMER.read_text(encoding="utf-8")

    assert "OnUnitActiveSec=5min" in source
    assert "Persistent=true" in source
    assert "Unit=edfinder-v3-health.service" in source
    assert "WantedBy=timers.target" in source


def test_health_service_is_oneshot_and_targets_the_versioned_script():
    source = SERVICE.read_text(encoding="utf-8")

    assert "Type=oneshot" in source
    assert "ExecStart=/opt/ed-finder-v3-runtime/health-check.sh" in source
