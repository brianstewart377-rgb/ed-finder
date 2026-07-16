# Code Quality Findings Register

Standing register for code-quality findings from audits and reviews.
Discipline mirrors docs/operations/known-issues.md: every finding carries
an ID, date raised, source, severity (Confirmed / Strongly supported /
Hypothesis / Unknown / Disproved), locations, close-when criteria, and
status. Findings close only with evidence (commit SHA plus verification
output), never by fiat. Nothing is deleted: closed findings move to
Resolved with date and closing commit. New audits append.

## Open

### CQ-001 — 16 silently dead test functions (name shadowing)
- Raised 2026-07-16 · full-codebase audit @ 0a768a2 · Confirmed
- tests/test_optimiser.py lines 655–835: helper `ranked_candidate` plus 16
  tests shadowed by identically named rewrites at 876–1039 (later-definition
  wins; first block never collected). Previously surfaced in the informal
  review; never remediated.
- Close when: dead block deleted; pytest --collect-only name list unchanged;
  ruff --select F811 clean on the file; F811 gated in CI (see CQ-005).

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

### CQ-004 — zip() without strict= (11 sites, 2 on hot paths)
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed
- Hot: apps/api/src/routers/simulation.py:179 (live slot-prediction endpoint;
  length mismatch silently truncates predictions — carried over unfixed from
  the earlier informal review); apps/importer/src/build_clusters.py:359.
  Others: canonical_evidence_promotion.py:288, enrichment_warehouse_sql.py:768,
  source_run_compatibility.py:307, station_type_canonical_pilot.py:835,
  scripts/dev/review_lab/process_registry.py:69 and :83, two stage-19 operator
  scripts, tests/test_stage17n2d_backfill_framework.py:289.
- Close when: strict=True at all 11 sites (if any site's lengths may
  legitimately differ, stop and escalate — never downgrade to strict=False
  silently); regression tests on both hot paths; B905 gated in CI.

### CQ-005 — CI runs no lint; ruff fails at 302 errors
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed
- Makefile:84 defines `ruff check apps tests`; .github/workflows/ci.yml never
  invokes it. 302 errors at both ruff 0.6.9 and 0.15.21 (87 E701, 77 F401,
  62 E402, 38 F541, 16 F811, 13 F841, 4 E401, 4 E702, 1 F821). Root cause of
  CQ-001 surviving the earlier review.
- Close when: [tool.ruff] config committed (per-file-ignores for deliberate
  sys.path-bootstrap E402; explicit decision recorded on E701/E702 style);
  F-class errors at zero; ruff wired into ci.yml and green.

### CQ-006 — undefined name `Any` (NameError if executed)
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed
- tests/test_local_review_test_environment.py:1587.
- Close when: import fixed AND the line demonstrably executes under pytest,
  or the dead path is removed.

### CQ-007 — cluster-search endpoint outside both type contracts
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed (both halves)
- frontend/src/features/cluster-search/useClusterSearch.ts:134 raw fetch
  bypasses lib/api.ts jsonFetch; apps/api/src/routers/search.py:228 declares
  no response_model on POST /api/search/cluster. Introduced with
  7224f87/fc96364.
- Close when: response_model declared in models.py and used on the route;
  yarn types:gen drift-free; api.ts helper added; hook migrated to it;
  openapi-types CI job green.

### CQ-008 — computed-then-dropped locals (10 sites)
- Raised 2026-07-16 · audit @ 0a768a2
- Strongly supported residue, delete: build_ratings.py:1217 secondary_eco and
  :1246 top_pair_meta (score_breakdown retirement residue; no ratings-side
  secondary/pair column exists); local_search.py:115 display_score plus its
  stale comment (legacy-score retirement residue; response dict carries
  archetype/buildability/purity scores only).
- Investigate first, Hypothesis: simulation/link_modifiers.py:58 `modifiers`
  parsed from modifier_economies and unused in the function — verify modifier
  economies are applied elsewhere in the simulation before deleting; if not,
  promote to its own feature-gap finding.
- Mechanical deletes: cp_simulator.py:268 cp_headroom, service_graph.py:113
  resolved_by_graph_key, build_archetype_scores.py:568, build_grid.py:557,
  build_topology.py:1032, enrichment_staging_db_loader.py:542.
- Close when: every site deleted with rationale in the commit, or promoted to
  its own finding here.

### CQ-009 — unused import / variable (vulture, high confidence)
- Raised 2026-07-16 · audit @ 0a768a2 · Confirmed
- simulation/buildability.py:34 unused import choose_location;
  simulation/topology_simulator.py:123 unused traits_row.
- Close when: removed; recurrence covered by the CQ-005 gate.

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

### CQ-014 — origin/main frontend typecheck red (pre-existing)
- Raised 2026-07-16 · surfaced by CI on PR #319 · Confirmed
- Frontend build job fails on 5 files, all pre-existing at 0a768a2 (Expansion
  Plans feature), none touched by #319 (which is Python-only):
  ClusterSearchForm.tsx (nullable-type), JournalImportPanel.test.tsx,
  MyWorkWorkspace.test.tsx + MyWorkWorkspace.tsx (TanStack Query v5
  UseQueryResult mock shape drift — missing isPending/isError/isLoadingError/
  isRefetchError +19), useProfileSync.ts (ed_expansion_plans_v1 missing from
  ProfileBlob), plus 2 unused-import and 2 nullable-type errors.
- Close when: frontend typecheck green in CI; fix PR merged.

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

### CQ-016 — Expansion Plans never push-sync to server
- Raised 2026-07-16 · found while diagnosing CQ-014 · Confirmed, shipping bug
- frontend/src/features/profile-sync/useProfileSync.ts: gatherLocalBlob()
  builds the push blob from six sibling keys but omits
  ed_expansion_plans_v1, while applyLocalBlob() DOES write it on pull and the
  ProfileBlob interface omits it entirely (the omission is what makes tsc
  flag line 108). Net effect: Expansion Plans (shipped 0a768a2) are restored
  on pull but never gathered on push, so cross-device sync for the feature is
  silently broken. Not cosmetic — the missing type field is a real
  persistence gap. Surfaced only because the frontend typecheck was not
  gating merges.
- Close when: ed_expansion_plans_v1 added to the ProfileBlob interface AND to
  gatherLocalBlob(); pull path unchanged; typecheck green; approach approved
  by owner before fix.

### CQ-017 — nullable timestamp passed to non-null formatter
- Raised 2026-07-16 · found while diagnosing CQ-014 · Confirmed, latent bug
- Two formatTimestamp functions exist: @/lib/format (nullable-safe, callers
  use ?? fallback) and my-work/myWorkWorkspaceUtils.ts:252 (param typed
  value: string, non-null). system-detail/systemDetailSections.tsx passes
  nullable API fields (sys.body_data_updated_at, sys.status_updated_at) to the
  non-null variant → TS2345. A null at runtime would format as the literal
  "null" or throw, depending on the body.
- Close when: the myWorkWorkspaceUtils formatTimestamp param widened to
  string | null with an explicit null guard (matching the @/lib/format twin),
  or call sites guarded; typecheck green; approach approved by owner before fix.

## Resolved

### CQ-001 — 16 silently dead test functions — RESOLVED 2026-07-16
- Fixed in PR #318 (c9cff45): dead block tests/test_optimiser.py:655–835
  removed; collect-only name set unchanged; verified by independent replay.
- Recurrence gate (F811 in CI) remains open under CQ-005.

### CQ-008 — computed-then-dropped locals — RESOLVED 2026-07-16
- Fixed in PR #319 (dd9e5c1). link_modifiers.py:58 confirmed dead residue
  (modifier_economies consumed elsewhere in optimiser/recommendations/
  candidate-gen); deleted. All other sites removed. Commit dd9e5c1 also
  carried 3 intended 'planned' evidence-catalog sources (ED Astrometrics,
  Elite BGS API, FDevIDs) added by the owner the prior night — reviewed as
  inert metadata, accepted. Merges on green CI.

### CQ-009 — unused import / variable — RESOLVED 2026-07-16
- Fixed in PR #319 (dd9e5c1): buildability.py:34 choose_location import
  removed. topology_simulator.py:123 traits_row reclassified Disproved —
  intentional unused parameter, not a defect; no change made.

### CQ-015 — data_invariants.py unescaped % in ILIKE — RESOLVED 2026-07-16
- Fixed in PR #320: ILIKE '% belt%' → '%% belt%%' at
  shared_contracts/data_invariant_contracts.py:121–122; verified by
  byte-identical replay. Escape chosen over params-skip to preserve psycopg2
  placeholder safety for all other checks. Merges on green CI.
