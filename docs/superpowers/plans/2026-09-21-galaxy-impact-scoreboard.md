# Galaxy Impact implementation plan

Written after [the design spec](../specs/2026-09-21-galaxy-impact-scoreboard-design.md)
and before implementation, 2026-09-21.

1. Establish safe validation: exact CPython 3.14, frozen API test dependencies,
   pnpm 11, and a new loopback-only disposable PostgreSQL 18 instance. Record any
   baseline failures separately from regressions.
2. Backend RED: add synthetic real-database tests through the journal importer
   for all seven counters, classification/identity handling, dedupe, ownership,
   import readiness and bounds; add endpoint authentication/contract tests.
   Run them before the implementation and record the expected failure.
3. Backend GREEN: implement bounded parameterized aggregation over verified own
   Scan events and the typed authenticated endpoint; run the targeted tests.
4. Frontend RED: add populated/new-commander panel tests plus asynchronous states
   and account-safe refresh behavior, run to establish failure.
5. Frontend GREEN: add generated-facade wrapper/query key and accessible Svelte 5
   scoreboard, integrate into journal account panel, preserve readable sharing
   management, invalidate after all committed import outcomes. Regenerate web
   SDK and shared API types from the local FastAPI schema without a running DB.
6. Review both boundaries and wording against the spec. Run API unit and feature
   PostgreSQL tests, web `pnpm check` and `pnpm test`; inspect the UI when feasible.
   Fix regressions, document unrelated failures or environment blockers.
7. Review diff, commit spec/plan and implementation locally on the requested
   branch, and report investigation, changes, validation and UX decisions.

Backend and frontend TDD may run independently once this contract is written.
Generated API files are regenerated only after the response model exists.
No production database, deployment, push or main-branch changes are authorized.
