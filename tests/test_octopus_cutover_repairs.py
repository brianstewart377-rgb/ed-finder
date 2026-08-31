from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME = ROOT / "scripts/operator/octopus_runtime.sh"
OLD_WORKFLOW = ROOT / ".github/workflows/octopus-legacy-handoff.yml"
NEW_WORKFLOW = ROOT / ".github/workflows/octopus-new-ops.yml"


def test_legacy_control_plane_executes_real_preflight_and_has_restore() -> None:
    workflow = OLD_WORKFLOW.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert "if: inputs.operation != 'preflight'" not in workflow
    assert "legacy-preflight" in workflow
    assert "legacy-status" in workflow
    assert "legacy-env-path" in workflow
    assert "restore-old" in workflow
    assert "/tmp/octopus_handoff.sh export '$RECIPIENT' /opt/octopus/octopus.env" not in workflow

    assert '"$DIR/octopus.env" "$DIR/.env"' in runtime
    assert "no supported legacy env file found" in runtime
    assert "multiple supported legacy env files found" in runtime
    preflight = runtime[runtime.index("legacy-preflight)") : runtime.index("legacy-status)")]
    assert "octopus_credentials.py\" check --source" in preflight
    assert "legacy_dc config --quiet" in preflight

    restore = runtime[runtime.index("restore-old)") : runtime.index("enable-worker)")]
    assert "set_workers_file \"$env_file\" true" in restore
    assert "legacy_worker_state) == true" in restore
    assert 'rm -f "$DIR/receipts/old-quiesced"' in restore


def test_cutover_verify_is_pinned_to_new_local_origin_before_external_webhook_proof() -> None:
    workflow = NEW_WORKFLOW.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert "private-install|private-verify|cutover-verify" in workflow
    assert "https://octopus.ed-finder.app/api/health" not in workflow

    verify = runtime[runtime.index("cutover-verify)") : runtime.index("legacy-env-path)")]
    assert "receipt private-proof" in verify
    assert "receipt public-edge-proof" in verify
    assert "ENABLE_REVIEW_WORKERS) == true" in verify
    assert "http://127.0.0.1:43300/api/health" in verify
    assert "--resolve octopus.ed-finder.app:443:127.0.0.1" in verify
    assert "local_edge_tls_routes_to_new_octopus: true" in verify
    assert "external_dns_webhook_proof_pending: true" in verify
