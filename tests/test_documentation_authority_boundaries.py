from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_migration_ledger_plan_is_explicitly_superseded_and_names_retired_paths():
    plan = _read("docs/operations/migration-ledger-implementation-plan.md")

    assert "SUPERSEDED / NON-AUTHORITATIVE PLAN" in plan
    assert "`scripts/release-main-to-prod.ps1`" in plan
    assert "have been deleted" in plan
    assert "`scripts/deploy_main.sh` is a retired V2 entrypoint" in plan
    assert "[`infrastructure-status.md`](./infrastructure-status.md)" in plan


def test_ops_control_plane_marks_unimplemented_mutations_as_design_only():
    design = _read("docs/development/chatgpt-ops-control-plane.md")

    assert "DESIGN DOCUMENT — PROPOSED MUTATIONS ARE NOT IMPLEMENTED" in design
    for operation in (
        "restart-api",
        "restart-worker",
        "deploy-commit",
        "run-governed-migrations",
    ):
        assert f"`{operation}`" in design
    assert "are not implemented in the current V3 allowlist" in design
    assert "../../.github/workflows/chatgpt-ed-new-ops.yml" in design


def test_historical_ops_docs_link_to_existing_current_authority():
    remediation = _read("docs/operations/audit-remediation-plan.md")
    incident = _read("docs/operations/database-bloat-incident-2026-08-20.md")

    assert "[migration-ledger implementation plan](./migration-ledger-implementation-plan.md)" in remediation
    assert "[PostgreSQL backup and restore contract](./postgres-backup-and-restore.md)" in remediation
    assert "[Infrastructure Status](./infrastructure-status.md)" in incident
    assert "[infrastructure-status.md](./infrastructure-status.md)" in incident
    assert "docs/operations/monitoring.md" not in incident
