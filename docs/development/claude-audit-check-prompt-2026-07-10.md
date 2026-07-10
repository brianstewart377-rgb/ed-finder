Please perform a fresh adversarial audit of the current `ED-Finder` repository state.

Scope:
- Audit the current local workspace as it exists now, not an older checkpoint branch.
- Assume recent work focused on Stage 25 closeout follow-through, production deploy/promotion, audit-remediation cleanup, and live data-trust repair follow-through.

What to verify first:
- Current branch / commit state and whether the repo shape now matches the claimed integrated line.
- Whether the active docs were updated to reflect the real post-deploy state rather than the older Stage 25 checkpoint narrative.
- Whether the code and docs now support the claimed production-safe invariants / repair workflow.

Files worth special attention:
- `docs/ROADMAP.md`
- `docs/operations/audit-remediation-plan.md`
- `docs/operations/stage17n2c-data-trust-runbook.md`
- `docs/development/ratings-resume-handoff-2026-07-06.md`
- `scripts/run_data_invariants_receipted.sh`
- `scripts/deploy_main.sh`
- `scripts/repair_body_contract.py`
- `scripts/repair_body_ring_association_status.py`
- `scripts/reconcile_no_body_ratings.py`
- `tests/test_backup_restore_ops.py`
- `tests/test_data_trust_runtime.py`
- `tests/test_repo_hygiene_contract.py`
- `frontend/src/hooks/useHashRoute.ts`
- `frontend/src/components/NavBar.tsx`
- `frontend/src/features/journal-import/JournalImportPanel.tsx`
- `apps/api/src/journal_import/api_models.py`
- `apps/api/src/journal_import/store.py`
- `apps/api/src/routers/journal_import.py`

Important context to test against:
- Production deploy/promotion has already happened and the live app health was green.
- The huge no-body dirty tail and ring-status drift buckets were materially drained on production using the committed repair scripts.
- The remaining known residue is intentionally small:
  - persistent body-contract tail: `3` rows
  - no-body dirty rows: should now be a small live-churn band, not a bulk backlog
  - ring drift: expected `0`
- Recent repo-side follow-up fixes to verify:
  - journal import is now staging-only only; the previous `quarantined` mode should be gone from the active contract
  - repair scripts now use finite session timeouts instead of infinite lock/statement waits
  - the legacy `#optimizer` alias should no longer resolve to Development Tuning
  - Finder now exposes one explicit in-product link into Development Tuning
  - durable production evidence artifacts now exist under `artifacts/data-invariants/`
  - the invariants wrapper/deploy path now supports durable receipt copies under `/data/receipts/...`

Please be hostile and specific.

Priorities for findings:
1. Any claim in docs that still overstates closure or green-ness.
2. Any mismatch between what the code actually enforces and what the docs now say.
3. Any remaining branch topology, deployment, migration-ledger, or ops truth-gap.
4. Any place where the production-safe repair/invariants path is still fragile or misleading.
5. Any Stage 25 shell/product coherence issues that still contradict the “canonical surfaces” story.

Review style:
- Findings first, ordered by severity.
- Include file paths and line references.
- Focus on bugs, regressions, misleading claims, missing tests, and operational risk.
- Be explicit about what is fixed, what is improved but still incomplete, and what is still risky.

Specific questions to answer:
- Did we actually close the biggest Stage 25 checkpoint audit gaps, or only move them around?
- Are the current roadmap and audit-remediation docs now honest about the remaining residue?
- Is the production-safe invariants / bounded repair story credible and supportable from the repo?
- What are the top remaining issues, if any, before calling this lane genuinely tidy?
