# RETIRED — V2 Stage 18/19 Enrichment Warehouse Runbook

> **Historical evidence only. Do not execute this document.** The former Hetzner/V2 operator environment and its `/opt/ed-finder` Stage 18J/19 shell-wrapper path are retired.

This filename is retained because historical Stage 17–19 architecture, evidence, and source-authority documents link to it. Keeping the filename preserves traceability; it does **not** preserve the old commands as an executable runbook.

## Current authority

For current work, use these sources in order:

1. `docs/operations/infrastructure-status.md` — current V3 infrastructure and recovery boundary;
2. `docs/ROADMAP.md` — current programme authorization;
3. `CLAUDE.md` — engineering/agent constraints;
4. `scripts/operator/README.md` and a specifically current V3 workflow/runbook when an operator action is explicitly authorized.

The surviving Stage 19 Python tools are historical/research tooling unless a current V3 runbook explicitly promotes a specific tool and target. Their presence in the repository is not production authority.

## Historical scope retained by reference

The old runbook covered offline enrichment snapshots, staging, reconciliation, Stage 18J identity review/apply preparation, and bounded Stage 19 staging activation. Historical design and closeout evidence remains under `docs/colonisation-redesign/`, `docs/archive/`, and `scripts/operator/archive/`.

Do not reconstruct deleted shell wrappers, Hetzner host checks, `/opt/ed-finder` commands, cron entries, or production database targets from Git history. If a future V3 enrichment/warehouse operator lane is authorized, create a new reviewed V3 runbook with explicit target identity, read/write scope, credentials, rollback, and receipt requirements.
