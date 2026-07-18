# Code Quality Findings Register

Standing register for code-quality findings from audits and reviews.
Discipline mirrors docs/operations/known-issues.md: every finding carries
an ID, date raised, source, severity (Confirmed / Strongly supported /
Hypothesis / Unknown / Disproved), locations, close-when criteria, and
status. Findings close only with evidence (commit SHA plus verification
output), never by fiat. Nothing is deleted: closed findings move to
Resolved with date and closing commit. New audits append.

## Open

### CQ-012 — oversized files (accepted split opportunities)
- Raised 2026-07-16 · audit @ 0a768a2 · improvement, not defect
- PlannerCanvasPreview.tsx 1,417 (continue plannerCanvasUtils extraction);
  MyWorkWorkspace.tsx 1,098 (extract ExpansionPlansSection while seam is
  fresh); NavBar.tsx 722 (feature logic out of nav);
  evidence_store/store.py 1,547; eddn_listener.py 1,445 (transport vs
  per-schema handlers); local_search.py 1,314 (candidate for edfinder_api/
  packaging). nightly_update.sh: collapse six VACUUM ANALYZE stanzas to a loop.
- Close when: each split lands, or is declined with rationale recorded here.
- CQ-012 ruling (2026-07-18): accepted as a sequenced split lane, not
  declined. S1 nightly_update.sh VACUUM loop, S2 MyWorkWorkspace
  ExpansionPlansSection extraction, S3 PlannerCanvasPreview
  plannerCanvasUtils continuation, and S4 local_search.py edfinder_api/
  packaging are scheduled as individual mechanical-extraction PRs after
  this docs pass. NavBar closes as overtaken: the be7b381 redesign
  already reduced it 722 → 379 lines. evidence_store/store.py and
  eddn_listener.py are deferred with rationale, not declined: both sit
  on the evidence layer / live ingest and will be split at their next
  feature contact (the CRE confidence-vocabulary integration opens
  store.py naturally), where real work validates the refactor. Original
  "6 VACUUM stanzas" count re-verified accurate at 51fe2d8.

### CQ-013 — dependency refresh lane (deferred until CQ-005 closes)
- Raised 2026-07-16 · audit @ 0a768a2 · improvement, not defect
- pydantic 2.9.2 → 2.11.x (requires models.py audit + types:gen drift check
  per the documented 2.10+ Optional[dict] hazard); fastapi 0.115, asyncpg
  0.29 → 0.30, redis-py 5.0.8 → 6.x ride along.
- Close when: refresh PR lands with openapi-types job green, or deferred with
  rationale recorded here.
- CQ-005 closed 2026-07-18; this lane is unblocked but has not started.

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

### CQ-002 — 8 orphaned frontend components (1,390 dead lines) — RESOLVED 2026-07-18
- Resolved in H1 frontend pruning (PR #334 ff4b26e; H2 merged at 51fe2d8).
  8 files deleted: SelectedBodyPlannerCanvas.tsx, BuildabilityPanel.tsx,
  SlotPredictionPanel.tsx, EliteNewsBanner.tsx, ChipPreview.tsx,
  RecommendedBuildsPanel.tsx, SystemSlotMapPanel.tsx, WorkspaceGrid.tsx.
  Total dead-line reduction: 1,390 lines (zero references, incl. tests).
  Knip unused-export check added to frontend CI (H1).

### CQ-003 — orphaned one-shot script targeting retired column — RESOLVED 2026-07-18
- Resolved in H1 (PR #334 ff4b26e; H2 merged at 51fe2d8).
  scripts/repair_ratings_score_breakdown_null.py (391 lines) moved to
  scripts/operator/archive/ per operator-script contract. Zero references
  confirmed.

### CQ-010 — CLAUDE.md stale on frontend/src/_redesign/ — RESOLVED 2026-07-18
- Resolved in H2 docs pass (this PR; codex/hygiene-pass-docs).
  CLAUDE.md line 163: sentence replaced with archival pointer; directory
  reference no longer claims a non-existent runtime path.

### CQ-011 — nightly_update.sh:66 cd without failure guard (SC2164) — RESOLVED 2026-07-18
- Resolved in H1 (PR #335; H2 merged at 51fe2d8).
  nightly_update.sh:66 changed to `cd "$COMPOSE" || fatal "..."`; line 51
  existence check confirmed mitigating. shellcheck -S warning clean.
