# Code Quality Findings Register

Standing register for code-quality findings from audits and reviews.
Discipline mirrors docs/operations/known-issues.md: every finding carries
an ID, date raised, source, severity (Confirmed / Strongly supported /
Hypothesis / Unknown / Disproved), locations, close-when criteria, and
status. Findings close only with evidence (commit SHA plus verification
output), never by fiat. Nothing is deleted: closed findings move to
Resolved with date and closing commit. New audits append.

## Open

### CQ-002 — 8 orphaned frontend components (1,390 dead lines)
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed (zero references incl. tests)
- colony-planner/SelectedBodyPlannerCanvas.tsx (640),
  system-detail/BuildabilityPanel.tsx (228),
  system-detail/SlotPredictionPanel.tsx (223), news/EliteNewsBanner.tsx (106),
  preview/ChipPreview.tsx (84), system-detail/RecommendedBuildsPanel.tsx (76),
  colony-planner/SystemSlotMapPanel.tsx (27), colony-planner/WorkspaceGrid.tsx (6).
  Hypothesis on cause: superseded by the Stage 25D cockpit fold.
- Close when: each file deleted (or re-wired with stated reason); knip or
  equivalent unused-export check added to frontend CI.

### CQ-003 — orphaned one-shot script targeting retired column
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed
- scripts/repair_ratings_score_breakdown_null.py (391 lines), referenced by
  nothing; targets retired score_breakdown.
- Close when: moved to scripts/operator/archive/ with historical declaration
  per the operator-script contract.

### CQ-010 — CLAUDE.md stale on frontend/src/_redesign/
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed (directory no longer exists)
- Close when: CLAUDE.md frontend section updated; fold into the pending
  roadmap/docs drift update.

### CQ-011 — nightly_update.sh:66 cd without failure guard (SC2164)
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed, cosmetic (line 51 existence
  check mitigates; script deliberately runs set -uo pipefail without -e)
- Close when: `cd "$COMPOSE" || fatal "..."`; shellcheck -S warning clean.

### CQ-012 — oversized files (accepted split opportunities)
- Raised 2026-07-16 · audit @ 0a768a2 · improvement, not defect
- PlannerCanvasPreview.tsx 1,417 (continue plannerCanvasUtils extraction);
  MyWorkWorkspace.tsx 1,098 (extract ExpansionPlansSection while seam is
  fresh); NavBar.tsx 722 (feature logic out of nav);
  evidence_store/store.py 1,547; eddn_listener.py 1,445 (transport vs
  per-schema handlers); local_search.py 1,314 (candidate for edfinder_api/
  packaging). nightly_update.sh: collapse six VACUUM ANALYZE stanzas to a loop.
- Close when: each split lands, or is declined with rationale recorded here.

### CQ-013 — dependency refresh lane (deferred until CQ-005 closes)
- Raised 2026-07-16 · audit @ 0a768a2 · improvement, not defect
- pydantic 2.9.2 → 2.11.x (requires models.py audit + types:gen drift check
  per the documented 2.10+ Optional[dict] hazard); fastapi 0.115, asyncpg
  0.29 → 0.30, redis-py 5.0.8 → 6.x ride along.
- Close when: refresh PR lands with openapi-types job green, or deferred with
  rationale recorded here.
- CQ-005 closed 2026-07-18; this lane is unblocked but has not started.

### CQ-015 — data_invariants.py crash: unescaped % in ILIKE (RESOLVED, see below)
- Raised 2026-07-16 · surfaced by CI on PR #319 · Confirmed, contained
- scripts/checks/data_invariants.py crashed with IndexError (tuple index out
  of range) via shared_contracts/data_invariant_contracts.py: the
  ring_association_status_drift check contained ILIKE '% belt%' with a bare %
  that psycopg2 misreads as a format placeholder. Introduced in cac355b.
  Blast radius bounded: the LIVE admin invariants endpoint uses asyncpg
  fetchval(), which is unaffected — production-safe receipts were never
  corrupt; only the psycopg2 CI script hard-crashed. Surfaced under the
  misleadingly-named "OpenAPI types drift" job (crash is upstream of type-gen).
- Close when: % escaped to %% at source; openapi-types job green in CI.

### CQ-022 — backend-unit CI job: 64-failure triage (umbrella) (RESOLVED, see below)
- Raised 2026-07-16 · local repro of the job's exact selection @ 983a212 ·
  counts Confirmed (64 failed, 1348 passed, 15 collection errors); bucket
  severity varies
- Buckets: (a) ~25 DB-dependent tests unmarked and failing "Database pool
  not initialised" / 503-vs-422 in the no-DB job (test_stage6c_comparison,
  test_stage6e_review, parts of test_observations) — marker/mock ruling
  needed; (b) stale contract-pin tests asserting superseded text of
  scripts/checks/data_invariants.py, stage-22/23/25 docs, evidence
  fixtures, and one fetchval query shape; (c) POSSIBLE REAL BUGS, diagnose
  before touching: test_observation_comparison ×11 (TypeError: Unsupported
  observed fact value: ObservedFact), test_colony_layout_import ×4
  (partial-vs-success semantics), test_observations 403-vs-200/422,
  LivePlannerEvidenceResult missing 'coverage' arg; (d)
  test_local_review_test_environment Unknown in CI (docker-dependent).
- Close when: bucket (c) diagnosed and dispositioned as own findings;
  (a)/(b) ruled by owner and fixed; the job green. Met 2026-07-17; see below.

### CQ-026 — CI seed produced invariant-violating data (RESOLVED, see below)
- Raised 2026-07-16 · Confirmed · the seed (sql/seed_preview.sql) failed 3 of
  9 data-invariants (rating_version not uniform; body-data flags/counts drift;
  stale non-eligible systems carried ratings) plus both seed_check guards.
- Close when: seed satisfies all 9 invariants + seed_check; verified locally
  against postgres:16-alpine.

### CQ-027 — API fails to boot in CI (shared_contracts import) (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed · CI booted uvicorn from apps/api/src without
  repo root on sys.path → ModuleNotFoundError: shared_contracts. Prod Dockerfile
  co-locates both packages; CI did not. Pre-existing latent, unmasked by CQ-026.
- Close when: both Boot API steps set PYTHONPATH=repo root; API boots green.

### CQ-030 — SystemDetailRow under-declared its own response (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed · /api/system/{id64} returns archetype/
  buildability fields (LEFT JOIN mv_archetype_rankings) + ISO-string timestamps,
  but SystemDetailRow declared neither (archetype absent via extra='allow';
  timestamps Optional[Any]→unknown in TS). Frontend hand-augmented to compensate.
- Close when: model declares the fields honestly; frontend augmentation removed;
  typecheck green.

### CQ-031 — Windows CRLF line endings on shell scripts (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed · run_maintenance.sh, run_dirty_ratings.sh, an
  operator script carried \r\n, failing bash-syntax tests.
- Close when: scripts normalized to LF; .gitattributes guards recurrence.

### CQ-032 — evidence promote-canonical test data gap (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed · test_evidence_mutations_accept_admin_token
  asserted promoted_count>=1 but the first-by-id seed system lacked promotable
  canonical data.
- Close when: fixed so the promote path has promotable data; test green in CI.

### CQ-033 — two shipped-code bugs in systems endpoints (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed, shipping bugs · (1) POST /api/systems/batch
  omitted r.terraformable_count from its ratings SELECT while
  reconstruct_score_breakdown requires it → KeyError → 500 on any batch request.
  (2) GET /api/system/{id64} raised TypeError int<None at systems.py:68 —
  timestamp fields returned raw datetime objects.
- Close when: batch query complete; timestamps ::text-cast; both endpoints green.

### CQ-034 — data-trust runtime tests vs 034 hardening trigger (RESOLVED, see below)
- Raised 2026-07-17 · Confirmed, test-infra · 3 test_data_trust_runtime tests
  insert confirmed+lane='unknown' station_body_links to simulate drift, but
  migration 034's trigger rejects that write. The repair path they test is
  intentional defense-in-depth (shipped with 034 in 26a9a7d), not obsolete.
- Close when: fixtures create the legacy-drift row via trigger bypass
  (session_replication_role=replica); tests green.

## Resolved

### CQ-001 — 16 silently dead test functions — RESOLVED 2026-07-16
- Fixed in PR #318 (c9cff45): dead block tests/test_optimiser.py:655–835
  removed; collect-only name set unchanged; verified by independent replay.
- Recurrence is now gated by Ruff in CI (CQ-005, merged at b84d971).

### CQ-004 — zip() without strict= — RESOLVED 2026-07-18
- Fixed in PR #338 (cd89f1b; merged at f56c43d): all 11 audited pairings now
  use strict=True after confirming equal lengths are contractual at every
  site. Added mismatch regressions for the live slot-prediction endpoint and
  build_clusters cursor-row mapping.
- Ruff B905 is configured and gated across apps, tests, and scripts. Local
  verification passed 1450 backend unit tests plus 168 affected operator and
  importer tests; all nine protected checks and both post-merge main workflows
  passed.

### CQ-008 — computed-then-dropped locals — RESOLVED 2026-07-18
- The original fix commit dd9e5c1 never merged: PR #319 remained orphaned
  while CI restoration proceeded. Recovered as 670f1bf and merged through
  PR #334 at 57afee3. link_modifiers.py:58 was confirmed dead residue
  (modifier economies are consumed elsewhere); all other named locals were
  removed. The three owner-authored planned evidence-catalog sources carried
  by the original commit were retained as accepted inert metadata.

### CQ-009 — unused import / variable — RESOLVED 2026-07-18
- The original dd9e5c1 fix never merged with PR #319. Recovered as 670f1bf
  and merged through PR #334 at 57afee3: buildability.py's unused
  choose_location import was removed; topology_simulator.py's traits_row was
  retained as an intentional interface parameter. Recurrence is now covered
  by the Ruff gate merged at b84d971.

### CQ-015 — data_invariants.py unescaped % in ILIKE — RESOLVED 2026-07-16
- Fixed in PR #320: ILIKE '% belt%' → '%% belt%%' at
  shared_contracts/data_invariant_contracts.py:121–122; verified by
  byte-identical replay. Escape chosen over params-skip to preserve psycopg2
  placeholder safety for all other checks. Merged at 123e88d.

### CQ-007 — cluster-search endpoint typed — RESOLVED 2026-07-17
- Fixed in PR #328 (f5bdb6f): added ClusterResult + ClusterSearchResponse to
  models.py (extra='allow' result-model convention; schema-grounded nullability)
  + response_model on /api/search/cluster. Post-merge CI confirmed no
  ResponseValidationError on any path.

### CQ-018 — stale api.gen.ts — RESOLVED 2026-07-17
- Fixed in PR #329 (e2a0730): regenerated api.gen.ts (1,773-line catch-up of
  accumulated drift the perpetually-red drift job never forced). Diff verified
  benign (real admin routes, frontend-forward URL, no consumers of renamed
  fields). Determinism confirmed by re-run. Greened OpenAPI-drift.

### CQ-022 — backend-unit 64-failure triage — RESOLVED 2026-07-17
- Fixed across PR #331 (7e290ba) + #332 (395d618). Root cause of the bulk: a
  dual-import path (tests imported flat `from observations.models` while prod
  uses `edfinder_api.observations.models` → two ObservedFact classes → TypeError)
  — corrected to package path across 31 files, 62→5 failures. Colony-layout
  tests passed with the import fix alone (earlier "re-pin to stub" hypothesis was
  a misdiagnosis; they are mock-based endpoint tests). Remaining 5 were CQ-031
  (CRLF). 0 shipped-code bugs in this finding.

### CQ-023 — Container image parity workflow red — RESOLVED 2026-07-17
- Resolved as part of the green board (PR #332, a8b1c14). "Built image parity"
  confirmed green and is now a required status check under branch protection.

### CQ-026 — CI seed invariant violations — RESOLVED 2026-07-17
- Fixed across PR #325 (rating_version '3.4' + body-data reconciliation UPDATE)
  and #326 (A-rich: 111 synthetic bodies for the 34 body-less systems so all 40
  are eligible+rated, satisfying both seed_check guards). Owner chose A-rich over
  A-minimal because seed_check assumes every system populated+rated. Proven
  locally: seed_check + data_invariants both green.

### CQ-027 — API boot / shared_contracts import — RESOLVED 2026-07-17
- Fixed in PR #327 (8fa45ed): PYTHONPATH=${{ github.workspace }} added to both
  Boot API steps, matching prod Dockerfile's co-location of shared_contracts and
  edfinder_api. API boots green; unmasked CQ-018 at the type-gen step.

### CQ-030 — SystemDetailRow under-declaration — RESOLVED 2026-07-17
- Fixed in PR #330 (f679977): declared the 9 archetype fields (Optional, LEFT
  JOIN nullable) + changed body_data_updated_at/status_updated_at
  Optional[Any]→Optional[str] (matches jsonable_encoder's ISO-string output).
  Frontend SystemDetail augmentation collapsed to = Schemas['SystemDetailRow'].

### CQ-031 — CRLF on shell scripts — RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): scripts normalized to LF; recurrence guarded.

### CQ-032 — evidence promote test data gap — RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): promote path given promotable data; test green.

### CQ-033 — systems endpoint shipped bugs — RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): added r.terraformable_count to the batch ratings
  SELECT; ::text-cast the timestamp fields at query level (fixing the int<None at
  systems.py:68) + _value_or_zero hardening in reconstruct_score_breakdown. Both
  endpoints green; tests unchanged (not loosened).

### CQ-034 — data-trust tests vs 034 trigger — RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): fixtures seed legacy drift via SET LOCAL
  session_replication_role=replica to bypass the write-time trigger, faithfully
  modeling the historical/backfill drift the repair path targets. Repair path
  confirmed intentional defense-in-depth, not obsolete.

### CQ-005 — CI lint gate — RESOLVED 2026-07-18
- The orphaned F401/F541/F841 sweep was recovered in PR #334 (57afee3), with
  current-tree F401 findings and CQ-006 completed in 44c2ca2. PR #335
  (b84d971) pinned Ruff 0.15.22, committed the E4/E7/E9/F contract, added
  exact per-file E402 bootstrap exceptions, and ran Ruff inside the existing
  required backend job. E701/E702 are explicitly accepted legacy style rather
  than defect findings. Local Ruff and all nine protected checks passed.

### CQ-006 — undefined `Any` — RESOLVED 2026-07-18
- Fixed in PR #334 (44c2ca2; merged at 57afee3) by importing Any in
  test_local_review_test_environment.py. The helper is exercised by multiple
  collected review-environment tests; the exact backend-unit selection passed
  1446 tests before merge. F821 is now prevented by the CQ-005 Ruff gate.

### CQ-014 — frontend typecheck baseline — RESOLVED 2026-07-17
- Fixed in PR #324 (7427ac7; merged at 7c5e9e7): corrected nullable and
  TanStack Query mock-shape errors plus stale unused bindings. Frontend
  typecheck and the protected Frontend build job are green.

### CQ-016 — Expansion Plans push-sync — RESOLVED 2026-07-17
- Fixed in PR #324 (3ae1803; merged at 7c5e9e7): added
  ed_expansion_plans_v1 to ProfileBlob and gatherLocalBlob(), preserving the
  pull path, and removed the duplicate rehydratePinnedStore() call.

### CQ-017 — nullable My Work timestamps — RESOLVED 2026-07-17
- Fixed in PR #324 (d93e739; merged at 7c5e9e7): widened the My Work
  formatTimestamp helper to string | null and added the explicit null guard.
  Typecheck and frontend tests passed.

### CQ-019 — CLAUDE.md root allowlist — RESOLVED 2026-07-17
- Fixed in PR #323 (0a4284f; merged at a3a2efd): added CLAUDE.md to the
  intentional visible-root allowlist. Script contracts are green.

### CQ-020 — pyzmq CI dependency — RESOLVED 2026-07-17
- Fixed in PR #323 (38f2cfc; merged at a3a2efd): pinned pyzmq 26.2.0 in
  tests/requirements-ci.txt so the EDDN test modules collect and run in the
  backend job.

### CQ-021 — My Work middot encoding — RESOLVED 2026-07-17
- Fixed in PR #324 (fa9cbf8; merged at 7c5e9e7): replaced all six
  double-encoded sequences. Byte verification reached 0 mojibake / 15 clean
  U+00B7 middots.

### CQ-024 — shipped design-system redesign recorded — RESOLVED 2026-07-18
- The healthy redesign landed at be7b381 and is now explicitly acknowledged
  in ROADMAP as the shipped Finder visual baseline. No code remediation was
  required; subsequent protected frontend build and E2E checks remain green.

### CQ-025 — tool/session artifacts ignored — RESOLVED 2026-07-17
- Fixed in PR #323 (9207b82; merged at a3a2efd): .gitignore now covers
  .mcp.json, .playwright-mcp/, and the two root session screenshots, preventing
  accidental inclusion by broad staging commands.
