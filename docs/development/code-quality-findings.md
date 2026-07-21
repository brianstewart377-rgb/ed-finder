# Code Quality Findings Register

Standing register for code-quality findings from audits and reviews.
Discipline mirrors docs/operations/known-issues.md: every finding carries
an ID, date raised, source, severity (Confirmed / Strongly supported /
Hypothesis / Unknown / Disproved), locations, close-when criteria, and
status. Findings close only with evidence (commit SHA plus verification
output), never by fiat. Nothing is deleted: closed findings move to
Resolved with date and closing commit. New audits append.

## Open

### CQ-012 â€” oversized files (accepted split opportunities)
- Raised 2026-07-16 Â· audit @ 0a768a2 Â· improvement, not defect
- PlannerCanvasPreview.tsx 1,417 (continue plannerCanvasUtils extraction);
  MyWorkWorkspace.tsx 1,098 (extract ExpansionPlansSection while seam is
  fresh); NavBar.tsx 722 (feature logic out of nav);
  evidence_store/store.py 1,547; eddn_listener.py 1,445 (transport vs
  per-schema handlers); local_search.py 1,314 (candidate for edfinder_api/
  packaging). nightly_update.sh: collapse six VACUUM ANALYZE stanzas to a loop.
CQ-012 ruling (2026-07-18, recorded 2026-07-20): accepted as a sequenced split lane, not declined. S1 nightly_update.sh VACUUM loop, S2 MyWorkWorkspace ExpansionPlansSection extraction, S3 PlannerCanvasPreview plannerCanvasUtils continuation, and S4 local_search.py edfinder_api/ packaging are scheduled as individual mechanical-extraction PRs. NavBar sub-item closes as overtaken: the be7b381 redesign already reduced it 722 -> 379 lines. evidence_store/store.py and eddn_listener.py are deferred with rationale, not declined: both sit on the evidence layer / live ingest and will be split at their next feature contact (the CRE confidence-vocabulary integration opens store.py naturally), where real work validates the refactor. Original "6 VACUUM stanzas" count re-verified accurate at 51fe2d8.
- Close when: each split lands, or is declined with rationale recorded here.

### CQ-013 â€” dependency refresh lane (deferred until CQ-005 closes)
- Raised 2026-07-16 Â· audit @ 0a768a2 Â· improvement, not defect
- pydantic 2.9.2 â†’ 2.11.x (requires models.py audit + types:gen drift check
  per the documented 2.10+ Optional[dict] hazard); fastapi 0.115, asyncpg
  0.29 â†’ 0.30, redis-py 5.0.8 â†’ 6.x ride along.
- Close when: refresh PR lands with openapi-types job green, or deferred with
  rationale recorded here.
- CQ-005 closed 2026-07-18; this lane is unblocked but has not started.
## Resolved

### CQ-046 - Windows release wrapper treated SSH alias as an SCP source - RESOLVED 2026-07-19
- Raised 2026-07-19 during the production release retry for `649e9c1`.
  Confirmed operational defect: `Resolve-SshTarget` mixed SCP options with the
  remote host, then the upload builder appended that mixed array before the
  local archive. OpenSSH therefore tried to stat a local file named after the
  `ed-finder-prod` alias.
- The release failed closed before artifact upload, remote command execution, or
  any production service change. Local typecheck, build, frontend tests,
  archive creation, and checksum creation had passed.
- Fixed in `71abc8e`: resolved targets now expose `ScpOptions` and `Destination`
  separately. Alias mode has no extra SCP flags; direct-host mode contributes
  only `-P <port>`; both append exactly one local source and one remote target.
- Closed with PowerShell syntax parsing, five focused reproducibility tests,
  Ruff, and native `make test-unit` at 1490 passed, 13 skipped, and 125
  deselected. The release-path contract rejects the former mixed `ScpArgs`
  representation and pins the destination order.

### CQ-045 - Windows release wrapper split frontend packaging arguments - RESOLVED 2026-07-19
- Raised 2026-07-19 during the canonical production release of merge commit
  `cd5c753`. Confirmed operational defect: `release-main-to-prod.ps1` launched
  `run-bash.ps1` through nested Windows PowerShell `-File` argument binding, so
  the `string[]` archive arguments spilled into `-Command` and `-Script` at once.
- The release failed closed before artifact upload or any production change;
  typecheck, build, and frontend tests had already passed.
- Fixed in `2f58d74`: the release wrapper invokes the Git Bash adapter directly
  and passes `@('--output', $frontendArchiveLocal)` as a real PowerShell array.
- Closed with a release-path regression contract, PowerShell syntax parsing,
  five focused reproducibility tests, native `make test-unit` at 1490 passed,
  13 skipped, and 125 deselected, plus a clean-clone packaging rehearsal that
  produced both the frontend archive and checksum with deploy disabled.

### CQ-044 - Windows Make and frontend packaging paths were not portable - RESOLVED 2026-07-19
- Raised 2026-07-19 during installation and first use of GNU Make 4.4.1 on the
  documented Windows development path. Confirmed developer-workflow and release
  reproducibility defect: `make test-unit` sent POSIX inline environment syntax
  to `cmd.exe`, and forcing Git Bash instead consumed backslashes in the Windows
  virtualenv path.
- The resulting full test run exposed a second Windows path defect in
  `package_frontend_bundle.sh`: GNU tar interpreted `C:` as a remote host, then
  `sha256sum` escaped a drive-letter filename by prefixing the digest with `\`.
- The first fix in `981a6c9` moved environment defaults into Make, selected a
  cross-shell virtualenv path, and attempted to make drive-letter archive paths
  explicit to tar and the checksum writer.
- Review Lab on `286fcce` found four portability edge cases in that first fix:
  dollar signs in caller-supplied environment values, checksum mode-marker
  preservation, BSD tar compatibility, and valid global-Python fallback when a
  Windows repo venv is absent. Fixed in `78faa28` with direct regressions.
- An exact-head review found that the archive regression itself still required
  GNU `sha256sum` even though the release script supports BSD/macOS `shasum`.
  The regression now mirrors the production verifier selection.
- A second exact-head review found that Make's raw-value-preserving defaults
  treated explicitly empty test variables as intentional values. The final
  defaults use Make's unexpanded `value` function, preserving literal dollar
  signs while restoring the previous empty-means-missing behavior.
- A third exact-head review found that an empty Make command-line assignment
  could still outrank the target default. Target-specific `override export`
  semantics now apply the same contract to environment and command-line input.
- Closed with focused Make/reproducibility tests, Ruff, Bash syntax checking, a
  passing native `make state-check`, a clean Windows drive-path archive and
  checksum rehearsal, and native `make test-unit` at 1490 passed, 13 skipped,
  and 125 deselected.

### CQ-041 â€” sync_password.sh exposed credentials in process arguments â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed Â· high operational
  risk. The same unsafe password URI and SQL interpolation had also drifted into
  `run_import.sh`, while loopback trust meant the old verification did not
  actually authenticate the supplied password.
- Fixed in `587e477`: password verification now creates a mode-0600 passfile
  inside the database container from escaped stdin, connects through the
  container's SCRAM-authenticated address, and deletes the file on exit.
  Password updates use psql's quoting-safe `\password`; output is fully
  redacted, and `run_import.sh` delegates to the single hardened utility.
- Closed with static forbidden-pattern contracts, a mocked special-character
  secret-channel rehearsal, and a real `postgres:16-alpine` mismatch, update,
  authenticated verification, and verify-only run. The disposable container
  was removed after the rehearsal.

### CQ-042 â€” migration runner defaulted to unbounded database timeouts â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed Â· operational
  hardening. Both the canonical applier and one-time baseline helper disabled
  statement and lock timeouts.
- Fixed in `587e477`: both scripts default to a one-hour per-statement timeout
  and 30-second per-lock-acquisition timeout. Valid finite durations are
  operator-overridable; zero is rejected unless the reviewed run explicitly
  sets `EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS=yes`. Values are syntax
  validated before interpolation into the container shell.
- Closed with policy/unsafe-input regressions and a fresh disposable PostgreSQL
  16 database rehearsal: 39 automatic migrations applied, the manual migration
  remained skipped, and the second run reported `applied=0, skipped=40`. The
  rehearsal database was dropped afterward.

### CQ-043 â€” Review Lab browser verification was persistently red â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· CI forensic comparison of PR #344 and PR #345 Â·
  Confirmed Â· pre-existing on `main`. The isolated API omitted current app-shell
  and System Detail read routes, while the browser journey still modeled an
  older Finder-to-planner interaction.
- Fixed in `d1a9c6a`: added bounded review-only news, archetype, and evidence
  summary contracts; synchronized the browser journey with the current UI;
  preserved the deliberate Delta `503` provenance fallback; and hardened
  Windows executable resolution, UTF-8 capture, and review-owned process-tree
  cleanup. Contract tests also require the workflow to run on every pull
  request, allowing `Review Lab` to become the tenth protected context.
- Full local verification passed all scenarios, accessibility checks,
  console/network policy, Delta fallback correlation, product acceptance, and
  Docker/process teardown in run `20260718T155912Z-32900-429f62aa`.
- Closed when: the universal `Review Lab` workflow passed on its protected PR
  and its exact check context was added to `main` branch protection.

### CQ-010 â€” CLAUDE.md stale on frontend/src/_redesign/ â€” RESOLVED 2026-07-18
- Raised 2026-07-16 Â· audit @ 0a768a2 Â· Confirmed.
- Closed by the H2 trust/hygiene documentation reconciliation: `CLAUDE.md` and
  `README.md` now identify the prototype as archived historical material under
  `docs/archive/frontend-redesign-prototype/`, not a runtime source or wiring
  target. ROADMAP foundation state was reconciled at the same time.

### CQ-035 â€” Ruff scope and shell EOL policy gaps â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed. CI omitted
  `scripts` and `shared_contracts` from its primary Ruff command, while Windows
  checkout behavior had no repository-owned LF policy for shell scripts.
- Fixed in `0d80f4c`: Ruff now covers `apps`, `tests`, `scripts`, and
  `shared_contracts`; all nine newly exposed findings were corrected or given
  one narrow bootstrap exception; `.gitattributes` pins `*.sh` to LF.
- Review Lab exposed a Linux direct-entry import regression after the cleanup;
  `7394580` added the explicit repo-root entrypoint bootstrap and a subprocess
  regression that runs without `PYTHONPATH` from outside the checkout.
- Local expanded Ruff and focused backend/Review Lab contract tests passed.

### CQ-036 â€” Cluster Search bypassed the shared API client â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed.
- Fixed in `0d80f4c`: added typed Cluster Search request/response contracts to
  `frontend/src/lib/api.ts`, routed the hook through the shared client, and
  added direct success/error hook tests.

### CQ-037 â€” uncollected slot smoke test and expansion-store gap â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed test-trust gaps.
- Fixed in `0d80f4c`: replaced the uncollected `tests/smoke_test_slots.py` with
  collected model tests and added expansion-plan store coverage for lifecycle,
  slot replacement, project-link clearing, and plan isolation.

### CQ-038 â€” admin cache clear masked Redis failure â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed behavioral defect.
- Fixed in `0d80f4c`: database cache clearing remains attempted, Redis failure
  is logged, and the endpoint truthfully returns `ok=false`, `partial=true`,
  and `redis_cleared=false`. Direct backend regressions cover partial and full
  success.

### CQ-039 â€” shell localStorage access could throw â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed resilience gap.
- Fixed in `0d80f4c`: guarded storage helpers now contain read/write/remove
  exceptions and the app shell uses them. Tests cover normal behavior and
  browser `SecurityError` failures.

### CQ-040 â€” Fleet Carrier input label was not associated â€” RESOLVED 2026-07-18
- Raised 2026-07-18 Â· forensic audit @ a447222 Â· Confirmed accessibility gap.
- Fixed in `0d80f4c`: the label/input now share `htmlFor`/`id`, with a direct
  accessible-name regression test.

### CQ-002 â€” 8 orphaned frontend components â€” RESOLVED 2026-07-18
- Fixed in PR #344 (implementation commits 203ccd9 and d0fb52e): deleted all eight
  zero-reference components and renamed the surviving EliteNewsBar test to
  match the live component.
- Added Knip's unused-file check to the required Frontend build job. Local
  `yarn knip --files` completed cleanly; the existing typecheck, frontend test,
  build, and protected CI gates cover the resulting import graph.

### CQ-003 â€” orphaned one-shot script targeting retired column â€” RESOLVED 2026-07-18
- Fixed in PR #344 (implementation commit 203ccd9): moved
  `scripts/repair_ratings_score_breakdown_null.py` to
  `scripts/operator/archive/stage-h1-cq003/` with an explicit historical-only
  declaration. No active tests, scripts, or Makefile targets referenced it.

### CQ-011 â€” nightly_update.sh unguarded cd â€” RESOLVED 2026-07-18
- Fixed in PR #344 (implementation commit 203ccd9): the compose-directory
  change now fails through the script's existing `fatal` path when `cd` fails.
- Ruff and the script-contract CI job are green; ShellCheck remains enforced by
  CI because it is not installed in the current Windows workspace.

### CQ-001 â€” 16 silently dead test functions â€” RESOLVED 2026-07-16
- Fixed in PR #318 (c9cff45): dead block tests/test_optimiser.py:655â€“835
  removed; collect-only name set unchanged; verified by independent replay.
- Recurrence is now gated by Ruff in CI (CQ-005, merged at b84d971).

### CQ-004 â€” zip() without strict= â€” RESOLVED 2026-07-18
- Fixed in PR #338 (cd89f1b; merged at f56c43d): all 11 audited pairings now
  use strict=True after confirming equal lengths are contractual at every
  site. Added mismatch regressions for the live slot-prediction endpoint and
  build_clusters cursor-row mapping.
- Ruff B905 is configured and gated across apps, tests, and scripts. Local
  verification passed 1450 backend unit tests plus 168 affected operator and
  importer tests; all nine protected checks and both post-merge main workflows
  passed.

### CQ-008 â€” computed-then-dropped locals â€” RESOLVED 2026-07-18
- The original fix commit dd9e5c1 never merged: PR #319 remained orphaned
  while CI restoration proceeded. Recovered as 670f1bf and merged through
  PR #334 at 57afee3. link_modifiers.py:58 was confirmed dead residue
  (modifier economies are consumed elsewhere); all other named locals were
  removed. The three owner-authored planned evidence-catalog sources carried
  by the original commit were retained as accepted inert metadata.

### CQ-009 â€” unused import / variable â€” RESOLVED 2026-07-18
- The original dd9e5c1 fix never merged with PR #319. Recovered as 670f1bf
  and merged through PR #334 at 57afee3: buildability.py's unused
  choose_location import was removed; topology_simulator.py's traits_row was
  retained as an intentional interface parameter. Recurrence is now covered
  by the Ruff gate merged at b84d971.

### CQ-015 â€” data_invariants.py unescaped % in ILIKE â€” RESOLVED 2026-07-16
- Fixed in PR #320: ILIKE '% belt%' â†’ '%% belt%%' at
  shared_contracts/data_invariant_contracts.py:121â€“122; verified by
  byte-identical replay. Escape chosen over params-skip to preserve psycopg2
  placeholder safety for all other checks. Merged at 123e88d.

- Original Open copy retained for consolidation:
> ### CQ-015 â€” data_invariants.py crash: unescaped % in ILIKE
> - Raised 2026-07-16 Â· surfaced by CI on PR #319 Â· Confirmed, contained
> - scripts/checks/data_invariants.py crashed with IndexError (tuple index out
>   of range) via shared_contracts/data_invariant_contracts.py: the
>   ring_association_status_drift check contained ILIKE '% belt%' with a bare %
>   that psycopg2 misreads as a format placeholder. Introduced in cac355b.
>   Blast radius bounded: the LIVE admin invariants endpoint uses asyncpg
>   fetchval(), which is unaffected â€” production-safe receipts were never
>   corrupt; only the psycopg2 CI script hard-crashed. Surfaced under the
>   misleadingly-named "OpenAPI types drift" job (crash is upstream of type-gen).
> - Close when: % escaped to %% at source; openapi-types job green in CI.
>

### CQ-007 â€” cluster-search endpoint typed â€” RESOLVED 2026-07-17
- Fixed in PR #328 (f5bdb6f): added ClusterResult + ClusterSearchResponse to
  models.py (extra='allow' result-model convention; schema-grounded nullability)
  + response_model on /api/search/cluster. Post-merge CI confirmed no
  ResponseValidationError on any path.

### CQ-018 â€” stale api.gen.ts â€” RESOLVED 2026-07-17
- Fixed in PR #329 (e2a0730): regenerated api.gen.ts (1,773-line catch-up of
  accumulated drift the perpetually-red drift job never forced). Diff verified
  benign (real admin routes, frontend-forward URL, no consumers of renamed
  fields). Determinism confirmed by re-run. Greened OpenAPI-drift.

### CQ-022 â€” backend-unit 64-failure triage â€” RESOLVED 2026-07-17
- Fixed across PR #331 (7e290ba) + #332 (395d618). Root cause of the bulk: a
  dual-import path (tests imported flat `from observations.models` while prod
  uses `edfinder_api.observations.models` â†’ two ObservedFact classes â†’ TypeError)
  â€” corrected to package path across 31 files, 62â†’5 failures. Colony-layout
  tests passed with the import fix alone (earlier "re-pin to stub" hypothesis was
  a misdiagnosis; they are mock-based endpoint tests). Remaining 5 were CQ-031
  (CRLF). 0 shipped-code bugs in this finding.

- Original Open copy retained for consolidation:
> ### CQ-022 â€” backend-unit CI job: 64-failure triage (umbrella)
> - Raised 2026-07-16 Â· local repro of the job's exact selection @ 983a212 Â·
>   counts Confirmed (64 failed, 1348 passed, 15 collection errors); bucket
>   severity varies
> - Buckets: (a) ~25 DB-dependent tests unmarked and failing "Database pool
>   not initialised" / 503-vs-422 in the no-DB job (test_stage6c_comparison,
>   test_stage6e_review, parts of test_observations) â€” marker/mock ruling
>   needed; (b) stale contract-pin tests asserting superseded text of
>   scripts/checks/data_invariants.py, stage-22/23/25 docs, evidence
>   fixtures, and one fetchval query shape; (c) POSSIBLE REAL BUGS, diagnose
>   before touching: test_observation_comparison Ã—11 (TypeError: Unsupported
>   observed fact value: ObservedFact), test_colony_layout_import Ã—4
>   (partial-vs-success semantics), test_observations 403-vs-200/422,
>   LivePlannerEvidenceResult missing 'coverage' arg; (d)
>   test_local_review_test_environment Unknown in CI (docker-dependent).
> - Close when: bucket (c) diagnosed and dispositioned as own findings;
>   (a)/(b) ruled by owner and fixed; the job green. Met 2026-07-17; see below.
>

### CQ-023 â€” Container image parity workflow red â€” RESOLVED 2026-07-17
- Resolved as part of the green board (PR #332, a8b1c14). "Built image parity"
  confirmed green and is now a required status check under branch protection.

### CQ-026 â€” CI seed invariant violations â€” RESOLVED 2026-07-17
- Fixed across PR #325 (rating_version '3.4' + body-data reconciliation UPDATE)
  and #326 (A-rich: 111 synthetic bodies for the 34 body-less systems so all 40
  are eligible+rated, satisfying both seed_check guards). Owner chose A-rich over
  A-minimal because seed_check assumes every system populated+rated. Proven
  locally: seed_check + data_invariants both green.

- Original Open copy retained for consolidation:
> ### CQ-026 â€” CI seed produced invariant-violating data
> - Raised 2026-07-16 Â· Confirmed Â· the seed (sql/seed_preview.sql) failed 3 of
>   9 data-invariants (rating_version not uniform; body-data flags/counts drift;
>   stale non-eligible systems carried ratings) plus both seed_check guards.
> - Close when: seed satisfies all 9 invariants + seed_check; verified locally
>   against postgres:16-alpine.
>

### CQ-027 â€” API boot / shared_contracts import â€” RESOLVED 2026-07-17
- Fixed in PR #327 (8fa45ed): PYTHONPATH=${{ github.workspace }} added to both
  Boot API steps, matching prod Dockerfile's co-location of shared_contracts and
  edfinder_api. API boots green; unmasked CQ-018 at the type-gen step.

- Original Open copy retained for consolidation:
> ### CQ-027 â€” API fails to boot in CI (shared_contracts import)
> - Raised 2026-07-17 Â· Confirmed Â· CI booted uvicorn from apps/api/src without
>   repo root on sys.path â†’ ModuleNotFoundError: shared_contracts. Prod Dockerfile
>   co-locates both packages; CI did not. Pre-existing latent, unmasked by CQ-026.
> - Close when: both Boot API steps set PYTHONPATH=repo root; API boots green.
>

### CQ-030 â€” SystemDetailRow under-declaration â€” RESOLVED 2026-07-17
- Fixed in PR #330 (f679977): declared the 9 archetype fields (Optional, LEFT
  JOIN nullable) + changed body_data_updated_at/status_updated_at
  Optional[Any]â†’Optional[str] (matches jsonable_encoder's ISO-string output).
  Frontend SystemDetail augmentation collapsed to = Schemas['SystemDetailRow'].

- Original Open copy retained for consolidation:
> ### CQ-030 â€” SystemDetailRow under-declared its own response
> - Raised 2026-07-17 Â· Confirmed Â· /api/system/{id64} returns archetype/
>   buildability fields (LEFT JOIN mv_archetype_rankings) + ISO-string timestamps,
>   but SystemDetailRow declared neither (archetype absent via extra='allow';
>   timestamps Optional[Any]â†’unknown in TS). Frontend hand-augmented to compensate.
> - Close when: model declares the fields honestly; frontend augmentation removed;
>   typecheck green.
>

### CQ-031 â€” CRLF on shell scripts â€” RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): affected Git blobs normalized to LF. H2 commit
  `0d80f4c` closed the remaining Windows checkout-parity gap by adding the
  repository-owned `.gitattributes` policy for all `*.sh` files.

- Original Open copy retained for consolidation:
> ### CQ-031 â€” Windows CRLF line endings on shell scripts
> - Raised 2026-07-17 Â· Confirmed Â· run_maintenance.sh, run_dirty_ratings.sh, an
>   operator script carried \r\n, failing bash-syntax tests.
> - Close when: scripts normalized to LF; .gitattributes guards recurrence.
>

### CQ-032 â€” evidence promote test data gap â€” RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): promote path given promotable data; test green.

- Original Open copy retained for consolidation:
> ### CQ-032 â€” evidence promote-canonical test data gap
> - Raised 2026-07-17 Â· Confirmed Â· test_evidence_mutations_accept_admin_token
>   asserted promoted_count>=1 but the first-by-id seed system lacked promotable
>   canonical data.
> - Close when: fixed so the promote path has promotable data; test green in CI.
>

### CQ-033 â€” systems endpoint shipped bugs â€” RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): added r.terraformable_count to the batch ratings
  SELECT; ::text-cast the timestamp fields at query level (fixing the int<None at
  systems.py:68) + _value_or_zero hardening in reconstruct_score_breakdown. Both
  endpoints green; tests unchanged (not loosened).

- Original Open copy retained for consolidation:
> ### CQ-033 â€” two shipped-code bugs in systems endpoints
> - Raised 2026-07-17 Â· Confirmed, shipping bugs Â· (1) POST /api/systems/batch
>   omitted r.terraformable_count from its ratings SELECT while
>   reconstruct_score_breakdown requires it â†’ KeyError â†’ 500 on any batch request.
>   (2) GET /api/system/{id64} raised TypeError int<None at systems.py:68 â€”
>   timestamp fields returned raw datetime objects.
> - Close when: batch query complete; timestamps ::text-cast; both endpoints green.
>

### CQ-034 â€” data-trust tests vs 034 trigger â€” RESOLVED 2026-07-17
- Fixed in PR #332 (395d618): fixtures seed legacy drift via SET LOCAL
  session_replication_role=replica to bypass the write-time trigger, faithfully
  modeling the historical/backfill drift the repair path targets. Repair path
  confirmed intentional defense-in-depth, not obsolete.

- Original Open copy retained for consolidation:
> ### CQ-034 â€” data-trust runtime tests vs 034 hardening trigger
> - Raised 2026-07-17 Â· Confirmed, test-infra Â· 3 test_data_trust_runtime tests
>   insert confirmed+lane='unknown' station_body_links to simulate drift, but
>   migration 034's trigger rejects that write. The repair path they test is
>   intentional defense-in-depth (shipped with 034 in 26a9a7d), not obsolete.
> - Close when: fixtures create the legacy-drift row via trigger bypass
>   (session_replication_role=replica); tests green.
>

### CQ-005 â€” CI lint gate â€” RESOLVED 2026-07-18
- The orphaned F401/F541/F841 sweep was recovered in PR #334 (57afee3), with
  current-tree F401 findings and CQ-006 completed in 44c2ca2. PR #335
  (b84d971) pinned Ruff 0.15.22, committed the E4/E7/E9/F contract, added
  exact per-file E402 bootstrap exceptions, and ran Ruff inside the existing
  required backend job. E701/E702 are explicitly accepted legacy style rather
  than defect findings. H2 commit `0d80f4c` expanded the required command from
  `apps tests` to `apps tests scripts shared_contracts`, fixing the nine newly
  exposed findings while preserving one narrow path-bootstrap exception. Local
  expanded Ruff passed; protected CI is the merge gate.

### CQ-006 â€” undefined `Any` â€” RESOLVED 2026-07-18
- Fixed in PR #334 (44c2ca2; merged at 57afee3) by importing Any in
  test_local_review_test_environment.py. The helper is exercised by multiple
  collected review-environment tests; the exact backend-unit selection passed
  1446 tests before merge. F821 is now prevented by the CQ-005 Ruff gate.

### CQ-014 â€” frontend typecheck baseline â€” RESOLVED 2026-07-17
- Fixed in PR #324 (7427ac7; merged at 7c5e9e7): corrected nullable and
  TanStack Query mock-shape errors plus stale unused bindings. Frontend
  typecheck and the protected Frontend build job are green.

### CQ-016 â€” Expansion Plans push-sync â€” RESOLVED 2026-07-17
- Fixed in PR #324 (3ae1803; merged at 7c5e9e7): added
  ed_expansion_plans_v1 to ProfileBlob and gatherLocalBlob(), preserving the
  pull path, and removed the duplicate rehydratePinnedStore() call.

### CQ-017 â€” nullable My Work timestamps â€” RESOLVED 2026-07-17
- Fixed in PR #324 (d93e739; merged at 7c5e9e7): widened the My Work
  formatTimestamp helper to string | null and added the explicit null guard.
  Typecheck and frontend tests passed.

### CQ-019 â€” CLAUDE.md root allowlist â€” RESOLVED 2026-07-17
- Fixed in PR #323 (0a4284f; merged at a3a2efd): added CLAUDE.md to the
  intentional visible-root allowlist. Script contracts are green.

### CQ-020 â€” pyzmq CI dependency â€” RESOLVED 2026-07-17
- Fixed in PR #323 (38f2cfc; merged at a3a2efd): pinned pyzmq 26.2.0 in
  tests/requirements-ci.txt so the EDDN test modules collect and run in the
  backend job.

### CQ-021 â€” My Work middot encoding â€” RESOLVED 2026-07-17
- Fixed in PR #324 (fa9cbf8; merged at 7c5e9e7): replaced all six
  double-encoded sequences. Byte verification reached 0 mojibake / 15 clean
  U+00B7 middots.

### CQ-024 â€” shipped design-system redesign recorded â€” RESOLVED 2026-07-18
- The healthy redesign landed at be7b381 and is now explicitly acknowledged
  in ROADMAP as the shipped Finder visual baseline. No code remediation was
  required; subsequent protected frontend build and E2E checks remain green.

### CQ-025 â€” tool/session artifacts ignored â€” RESOLVED 2026-07-17
- Fixed in PR #323 (9207b82; merged at a3a2efd): .gitignore now covers
  .mcp.json, .playwright-mcp/, and the two root session screenshots, preventing
  accidental inclusion by broad staging commands.
