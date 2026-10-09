import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_health_exposes_the_deployed_commit_sha_runtime_contract():
    config = _read("apps", "api", "src", "config.py")
    model = _read("apps", "api", "src", "models.py")
    route = _read("apps", "api", "src", "routers", "meta.py")
    compose = _read("docker-compose.yml")

    assert "build_sha:          str  = 'unknown'" in config
    assert "build_sha: str" in model
    assert "build_sha=settings.build_sha" in route
    assert "BUILD_SHA:" in compose
    assert "${EDFINDER_BUILD_SHA:-unknown}" in compose


def test_v2_deploy_entrypoint_is_retired():
    deploy = _read("scripts", "deploy_main.sh")

    assert "RETIRED — V2 single-host deployment entrypoint" in deploy
    assert "intentionally performs no deployment or production mutation" in deploy
    assert "exit 64" in deploy
    assert 'EDFINDER_BUILD_SHA="$(git rev-parse HEAD)"' not in deploy


def test_manual_drift_check_is_loud_and_never_deploys():
    check = _read("scripts", "check-production-drift.ps1")

    assert "git fetch --prune origin" in check
    assert "git rev-parse origin/main" in check
    assert 'git rev-list --count "$liveSha..origin/main"' in check
    assert "DEPLOY DRIFT:" in check
    assert "Do not use a retired V2/Hetzner release wrapper." in check
    assert "current V3 production runbook/operator path" in check
    assert "scripts/release-main-to-prod.ps1" not in check


def test_v2_release_wrapper_is_retired():
    assert not (ROOT / "scripts" / "release-main-to-prod.ps1").exists()


def test_production_drift_hold_and_manual_bypass_contract():
    hold = json.loads(_read("deploy", "v3-production", "promotion-hold.json"))
    workflow = _read(".github", "workflows", "prod-version-drift.yml")

    assert set(hold) == {
        "schema_version",
        "held_live_sha",
        "held_since",
        "expires_at",
        "reason",
        "review",
    }
    assert hold["schema_version"] == "ed-finder/production-promotion-hold/v1"
    assert hold["held_live_sha"] == "bed755b944eb6cb226e1726b2a51582ba9fa9bdb"
    assert hold["held_since"] == "2026-10-04"
    assert hold["expires_at"] == "2026-11-09T00:00:00Z"
    assert hold["review"] == "this PR"
    assert "ignore_hold:" in workflow
    assert "default: 'false'" in workflow
    assert '--hold-file "deploy/v3-production/promotion-hold.json"' in workflow
    assert "hold_args=(--ignore-hold)" in workflow
