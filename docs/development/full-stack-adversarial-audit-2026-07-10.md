# ED-Finder — Current-State Adversarial Audit: Stage 25 Closeout Checkpoint (V1)

- **Repo:** `brianstewart377-rgb/ed-finder`
- **Audited target:** branch `stage25-closeout-checkpoint`, commit `98a3ff4b66f329fbda2415d046a37410dba48d02` — "Complete Stage 25 closeout checkpoint" (verified against the remote by hash and message before audit start)
- **Prior audit:** `7913c68` (V1.1). This report re-derives everything from the current tree; prior findings are referenced only where their remediation status is itself a current-state fact.
- **Confidence labelling:** claims are verified against the pinned tree unless tagged.

---

# Executive Summary

The 13 commits leading to this checkpoint contain the best engineering this repo has ever received: a real checksummed migration ledger with a manifest and a declarative manual mode, committed nightly backups with validation and a rehearsed restore, a CI overhaul that runs the actual unit estate under a frozen lockfile, a 558-line data-invariants runner, and a journal-import implementation that follows its design brief's privacy and staging-first principles almost to the letter. Taken in isolation, this is the remediation the last audit asked for.

**It is not in isolation, and that is the problem.** The blunt assessment:

**Stage 25 is nominally closed, not actually closed.** Three findings make the closeout claim unsound:

1. **The closeout exists on a branch that nothing deploys and nothing else contains.** `main` — the deploy source per `release-main-to-prod.ps1`/`deploy_main.sh` — has the migration applier (as a *different commit with the same message*, `d8977a0` vs this branch's `e37c8e4`) but **does not have the backup automation, the CI overhaul, the journal import, or the closeout itself**. Meanwhile `devscore-retire-ratings` holds 7 commits this checkpoint lacks — including "Canonicalize frontend directory cutover" and **three consecutive "Recover … from safety snapshot" commits** — restructuring work on product-shape fundamentals performed *around* the closeout and reconciled with it nowhere. The repository currently has three divergent lines, each containing unique recent work, with duplicate-message cherry-picked commits scattered across them. A stage cannot be "explicitly closed" (Stage 25H's own words) when the closed state is neither the deployed state nor the most-recently-worked state.

2. **The most critical fix from the last audit — backups — is stranded on this side branch.** Production, which deploys from `main`, is still running with no backup automation *today*. The fix being written is not the fix being run.

3. **The ratings integrity problem was not so much closed as renamed.** The data machinery genuinely improved (invariants, freshness checks, repair scripts). But the product answer was a pivot: the UI now leads with "Development Score," the API speaks "archetypes," the database still says `ratings` / `rating_version='3.4'`, `docs/ROADMAP.md` simultaneously declares "the canonical current scorer is **Ratings v3.4**," a 79-line hand-styled static page (`frontend/public/development.html`) explains the new vocabulary outside the app's design system, and a still-diverging branch is literally named `devscore-retire-ratings`. That is a three-layer naming stack over one concept, with the retirement it names still in flight — on a different branch — after the closeout.

The biggest truth the team may not want to hear: **the git topology is now a bigger data-trust risk than any line of code in the tree.** The same duplicate-commit/squash-traceability failure the A0 continuity audit flagged for PRs #297/#298 has recurred at branch scale, during the exact window when the repo's most safety-critical scripts were being written. Which `apply_migrations.sh` is real? (They differ by history, if not by content.) Which branch's crontab runs in prod? The answer currently requires forensics, and "requires forensics" is the definition of the problem.

Second truth: the new hygiene regime ratified its own exception in the week it was born — the repo-root allowlist test explicitly permits a design document at root, and the prior audit report was committed to `docs/archive/` under a Windows-duplicate filename ending in `(1).md`.

What deserves to be said plainly and positively: the remediation *content* is high quality. This is not a "fake work" checkpoint — it is real work published to the wrong topology and declared closed one merge too early.

---

# Severity-Ranked Findings

### CRITICAL-1 — Three divergent branch lines; the closeout is on none that matter
- **Why it matters:** Source-of-truth integrity. Every safety property claimed at this checkpoint (ledger, backups, CI honesty) is only true *of this branch*.
- **Evidence:** `git merge-base` forensics: checkpoint and `devscore-retire-ratings` diverged at `43b7f84`; checkpoint holds 30 commits devscore lacks; devscore holds 7 the checkpoint lacks (`7e8ff80` frontend directory cutover, `6b65b91`/`d907d82`/`2e94067` snapshot recoveries, UI polish, a news parser fix). `origin/main` head `d8977a0` shares a commit *message* ("Harden migrations and post-rerate repairs") with this branch's `e37c8e4` but not a hash; the checkpoint is not an ancestor of main. The five economy-chip commits exist as different hashes on two lines.
- **Consequence if ignored:** deployed behaviour permanently diverges from audited behaviour; future merges of these lines will conflict across the most dangerous files in the repo (deploy, migrations, crontab); "recover from safety snapshot" commits suggest this has already bitten once.
- **Action:** Freeze feature work. Pick one integration branch, merge/rebase all three lines with explicit conflict review on `scripts/`, `sql/`, `apps/maintenance/`, `.github/`, fast-forward `main`, delete or archive the losers, and only then re-declare the closeout — on the merged line.

### CRITICAL-2 — Production still has no backups; the fix is unmerged
- **Why it matters:** The single most existential operational gap from the prior audit is fixed in code and unfixed in reality.
- **Evidence:** `git ls-tree origin/main apps/maintenance/scripts/` shows `crontab` + `run_maintenance.sh` only — no `run_backup.sh`. The backup implementation, crontab entry (`10 2 * * *`), restore script, and rehearsal receipt (`checks/backup-rehearsal/local-restore-receipt-2026-07-09.json`) all exist solely on this branch. The rehearsal receipt is local-environment only; no production backup or prod restore rehearsal is evidenced anywhere.
- **Consequence:** one disk failure on the Hetzner box between now and the merge loses the hand-tuned 128 GB database. Every day of branch limbo is uncovered exposure.
- **Action:** cherry-pick the backup commit chain to `main` and deploy **today**, independent of the larger topology reconciliation. Then schedule the first *production* restore rehearsal and commit its receipt.

### HIGH-3 — Journal import writes anonymously and unthrottled into the shared evidence layer
- **Why it matters:** The design brief said staging-first; the implementation is staging-*plus*. `store.import_journal_batch` inserts, in one call, into `source_runs`, `journal_import_staging`, **and directly into `observed_facts` and `evidence_records`** (store.py:167, 195) — the shared evidence layer other lanes trust — with no authentication, no sync_key, and no rate limiting of any kind (`grep limiter` on the router and store: nothing). The only bound is Pydantic's 50,000-observations-per-request cap, which is a *floor* for abuse, not a ceiling: one anonymous request = up to 150k rows across three tables, repeatable forever.
- **Evidence:** `apps/api/src/routers/journal_import.py` (no dependencies beyond the pool), `journal_import/api_models.py:93`, `journal_import/store.py`.
- **Consequence:** evidence-store flooding/poisoning by a single hostile client; disk and dedupe-index growth; and — worse — pollution of the exact layer whose credibility the whole assessment vocabulary depends on. Hash dedupe (`ON CONFLICT (source_record_hash) DO NOTHING`) stops replays, not fabrication.
- **Action:** before this endpoint is exposed beyond localhost: per-IP and per-key rate limits; require a sync_key (the credential already exists) recorded on the `source_run`; make the `observed_facts`/`evidence_records` writes contingent on a per-run quarantine/trust flag so a poisoned run is revocable by run key; add a total-rows-per-day circuit breaker. The client-side privacy design (allowlist worker, consent preview, `strip_before_network`) is faithful and good — the gap is entirely server-side.

### HIGH-4 — The ratings/Development identity pivot is unfinished and now three vocabularies deep
- **Why it matters:** Data trust and next-engineer comprehension. The DB layer says `ratings`/`rating_version='3.4'`; the API canonical rerank is `/api/archetypes/rerank`; the UI says "Development Score"/"Development Tuning"; `docs/ROADMAP.md:19` says the canonical scorer is "Ratings v3.4 Best-Build Potential"; `docs/development/ratings-resume-handoff-2026-07-06.md` says legacy ratings payloads are retired from the active contract; and the branch continuing the retirement (`devscore-retire-ratings`) diverges from this "closed" checkpoint. `frontend/public/development.html` — a static page with its own inline GitHub-dark design system, outside the SPA, outside the token system — explains the model as a fourth surface.
- **Consequence:** the last audit's D3 (silent two-tier ratings) has been replaced by a subtler risk: a *terminology* two-tier. Every future contributor must learn that ratings=archetypes=development, and every doc that says "ratings" is now ambiguous between the DB layer and a retired product concept.
- **Action:** one decision doc naming the canonical term per layer (DB / API / UI), a rename plan for the survivors, deletion or in-app absorption of `development.html`, and — critically — merge the retirement branch before calling any of it closed.

### HIGH-5 — Data invariants never run against production, and "uniformity" was quietly re-scoped
- **Why it matters:** `scripts/checks/data_invariants.py` is excellent, and CI runs it — against **seeded** databases. The maintenance crontab has backup and maintenance jobs only; no invariants schedule exists for prod. Production uniformity is still a manual ritual, which is precisely the risk-class the prior audit flagged (D3's operational half).
- Additionally, the invariant asserts uniformity **for rebuild-eligible rows** (`has_body_data = TRUE`), with separate carve-out checks for non-eligible systems and an `--allow-…` escape flag. That re-scoping may be entirely legitimate post-rebaseline — but it means the headline "eligible rating rows are uniformly on the target version" is a narrower promise than "the mixed population is gone," and nothing in the tree evidences a *production* run receipt proving either.
- **Evidence:** `data_invariants.py:55-70, 169-176, 497`; `apps/maintenance/scripts/crontab`; CI invocations against seeded/OpenAPI DBs only.
- **Action:** add a weekly cron + post-deploy invariants run against prod (read-only DSN), committing a dated receipt artifact, exactly like the backup rehearsal receipts. Document the eligibility scoping in the runbook so the narrowing is a stated contract, not a quiet one.

### MEDIUM-6 — `config/nginx-ci.conf` replaced the sed hack with a fork
- The old CI job mutated the real config with sed and brace-counting Python (prior audit §1.4). The new job validates a dedicated `nginx-ci.conf` (189 lines). Better mechanics, new failure mode: **no test couples nginx-ci.conf to the production nginx config**, so CI now validates a file that can silently drift from what prod serves. `tests/test_ci_build_reproducibility_contracts.py` contains no nginx drift lock (verified by grep).
- **Action:** generate both from one template, or add a structural-diff test asserting the CI config's routing/security-header blocks match production's.

### MEDIUM-7 — `edfinder_api/__init__.py` is a `__path__` hack, not the packaging fix
- The new package shim mutates `__path__` to expose the legacy flat `src/` directory, by its own docstring "without forcing a giant import rewrite." Meanwhile brand-new code still uses flat imports (`routers/journal_import.py`: `from deps import get_pool`). The bridge is a reasonable transition device **only** with a deadline; as-is it adds an indirection layer on top of the debt instead of retiring it, and new modules are still being written in the old style.
- **Action:** lint-forbid flat imports in new files now; schedule the mechanical rewrite.

### MEDIUM-8 — The colony feature is half-dead: component orphaned, hook still wired into the shell
- `#colony` now correctly aliases to My Work (`useHashRoute.ts:16`) and `LazyColonyTab` is gone from routing — good. But `features/colony/ColonyTab.tsx` remains in the tree referenced by nothing, while `useColony` is still instantiated in the `App.tsx` god-shell (line 102). Half-retired features are worse than un-retired ones: the next engineer cannot tell which half is load-bearing.
- **Action:** delete `ColonyTab.tsx`; either move `useColony` ownership into My Work or fold its state into `myWorkStore`; remove `'colony'` from the `Route` union (keep only the alias parse).

### MEDIUM-9 — "Development Tuning" still sits in the player nav; `#optimizer` alias retained
- `NavBar.tsx:71` — an internal tuning surface remains a peer of Finder/Map in the Explore group, under a name that is itself mid-pivot (see HIGH-4), with a legacy third name (`optimizer`) still parsed. Stage 25's one primary objective was shell coherence; this is the most visible incoherence left in the shell. (Credit where due: Map now literally carries `title: 'Secondary Explore surface'` — the roadmap posture made it into the DOM.)
- **Action:** gate behind Admin/Operator or a flag, or commit to it as a player feature with a player name.

### MEDIUM-10 — Windows dev-environment sprawl is instability leaking into the repo
- New at this checkpoint: `bootstrap-windows.ps1`, `doctor.ps1` (386 lines), `run-bash.ps1` (a bash-invocation wrapper), `reset_local_db.ps1`, `windows-dev-environment.md` (148 lines), plus tests asserting on the *text* of the PS1 files (`test_windows_local_db_reset_contract.py`). Committed docs carry personal absolute paths (`c:\Users\brian\Documents\trae_projects\ED-Finder`) and OneDrive-failure archaeology; the ratings handoff records resuming "after a chat loss." The pattern: environment instability (OneDrive, tooling, lost sessions) is being remediated by growing the repo's dev-orchestration surface, which itself now needs tests, which are text-asserts. A 386-line doctor script is a symptom being managed, not a cause being fixed.
- **Action:** keep the docs, halve the scripts. Prefer one `make doctor` shelling to Python (cross-platform) over parallel PS1/bash stacks; strip personal paths from committed files (repeat finding — prior audit flagged the same in `stage-19-state-authority.json`).

### MEDIUM-11 — The hygiene regime ratified its own exceptions at birth
- `tests/test_repo_hygiene_contract.py` allowlists `ED_FINDER_JOURNAL_IMPORT_AND_COLONISATION_ROUTING_DESIGN_V1.md` at repo root and then asserts the file *contains a sentence explaining why it's allowed to be there* — a test enforcing the presence of an excuse. The prior audit report was committed as `docs/archive/ED_FINDER_FULL_STACK_ADVERSARIAL_AUDIT_V1(1).md` — a Windows duplicate-download filename, in the archive meant to demonstrate hygiene. `_redesign/` was relabelled "archived prototype, quarantined" but still lives inside `frontend/src/` — an archive inside the live source tree (its `main.tsx` bootstrap fork *was* genuinely removed, verified).
- **Consequence:** small individually; collectively they teach that the hygiene contract bends on request, which is the one thing a contract must not do in its first week.
- **Action:** move the design doc to `docs/colonisation-redesign/` (its briefs already reference it), rename the `(1)` file, relocate `_redesign/` to `docs/archive/` or delete it, and shrink the allowlist back.

### MEDIUM-12 — Nearest-colonised verdict: hardcoded game constant, unverified bound, silent absence
- The B-1 proximity surface shipped by reusing regional-analysis data — legitimately cheaper than a new endpoint. But: `COLONISATION_CLAIM_RANGE_LY = 16` is hardcoded **in a UI component** (`RegionalPositionPanel.tsx`) with no verification note and no server-side ownership, contravening the repo's own source-priority discipline for game mechanics; the "nearest observed colonised anchor" is nearest **within the regional-analysis row set**, so if the region query's radius is smaller than the true nearest anchor's distance, the verdict is silently absent (`nearest_colonised_system: None` → panel renders nothing) or scoped-wrong [Confidence: medium — region radius bound not fully traced]; and there is no "beyond N ly" empty state for deep-space systems, where this feature matters most.
- **Action:** promote the constant to server config surfaced in the API response; document the search bound in the response (`searched_radius_ly`); render the absent case explicitly.

### LOW-13 — Persistent habits, noted
- Text-assert contract tests continue to multiply alongside the (genuinely good) new runtime tests — `test_repo_hygiene_contract`, Windows script contracts, doc-phrase assertions. They protect wording, not behaviour. yarn is now honestly frozen (`packageManager: yarn@1.22.22`) but that is a pinned EOL toolchain. `CHANGES.md`/`README.md` archaeology unchanged. Journal allowlist omits the colonisation depot events (Lane 2 correctly deferred, but the brief should say so explicitly).

---

# Product Truth Check

**Is Explore → Inspect → Plan → Review/Export genuinely coherent?** Closer than it has ever been. The nav groups routes by journey stage, Map self-describes as secondary in its own tooltip, review-workspace context continuity has real code and tests behind it (`ReviewWorkflowRail`, `ReviewReadinessStrip`, `CockpitIntelligencePanel` — all new, all tested). The journey exists in the DOM, not just the roadmap.

**Is My Work truly canonical?** Mostly yes — watchlist/pinned/colony all alias into it at the router, and the old Colony tab is unroutable. But "canonical" is undercut by the shell still instantiating `useColony` separately and the dead `ColonyTab.tsx` in the tree: canonical at the route layer, unfinished at the state layer.

**Is Map truly secondary in practice?** Yes, and demonstrably: labelled as such, and Stage 25G's "no planner-map expansion" posture matches the code (map diff at this checkpoint is cache refactoring, not feature growth).

**Ghost/competing surfaces remaining:** "Development Tuning" in the player nav (an internal surface wearing a mid-pivot name); `frontend/public/development.html` (a static doc page with its own visual language — a fourth place the scoring story is told); `_redesign/` (quarantined but resident in src/); FC Route Planner (still an orphan lane in the Review group, still absent from the journey narrative); Compare (still a shallow snapshot table in a simulation-first product — unchanged this checkpoint).

**One product or stitched workspaces?** One product with visible seams. The seams are no longer *structural* (routing and shell are unified); they are *lexical* (ratings/archetypes/development) and *residual* (dead colony half, Development Tuning, static page). That is genuine progress — and it is exactly the kind of progress that makes a "closed" stamp premature, because the remaining seams are the ones users read.

---

# Codebase Truth Check

**Architectural weak points.** The App.tsx god-shell persists (all feature hooks still lifted and prop-drilled; the new review-workspace components hang off the same spine). The packaging shim (MEDIUM-7) formalises rather than fixes the flat-import debt. The journal-import module is the best-structured new backend code in the repo (`journal_import/` as an actual package with models/store separation — ironically demonstrating the structure the rest of `src/` lacks).

**Route/state risks.** Router aliasing is clean and specified. State risk concentrates in the half-retired colony feature and in the fact that the new review-context continuity state lives in the shell rather than an owned context module (the Stage 25C contract doc describes a "context spine"; the runtime is still `useState`-in-shell + localStorage key).

**Test-signal quality.** Materially improved and honestly mixed. Real signal: `test_data_trust_runtime.py` (527 lines against live Postgres), migration applier/ledger runtime tests, invariants in CI, the frozen-lockfile and reproducibility contracts, journal import tests both sides of the wire. Warning noise: the text-assert family keeps growing; the nginx CI config has no drift lock (a green check certifying a fork); invariants green in CI proves seeded-DB health, not production health — and the ROADMAP's headline "1487 passed" is a *local* burn-down number, quoted in the roadmap as if it were a gate.

**Duplication/residue.** Duplicate-message commits across three branches (the big one); dead `ColonyTab.tsx`; `_redesign/` in src; `development.html`; `(1)` filename in the archive; personal absolute paths in committed docs.

**Where future work gets slower.** Any merge of the three branch lines (conflicts in the most dangerous files); anything touching scoring vocabulary (three names to update per change); anything touching the shell (god-component blast radius); Windows dev-env maintenance (a second platform stack to keep green).

---

# Operations / Data / Trust Risks

**Deploy safety.** Improved on this branch: deploy now calls the ledger applier, verifies the lockfile exists, and supports `--frontend-archive` so prod can install the CI-built bundle instead of rebuilding on-box — that closes the prior audit's reproducibility gap *if used*; nothing forces the archive path, so on-box builds remain the default trap. But the governing fact is CRITICAL-1/2: **deploys come from `main`, and `main` has neither this deploy script's full lineage nor the backups.**

**Migration safety.** The applier is genuinely good: SHA-256 checksums, mismatch = hard fail, manifest ordering (which also resolves the duplicate-025 by renaming to `031` and sequencing it explicitly), `019` as a declarative `manual` mode instead of a shell exclusion, and a baseline script for adopting existing databases. Runtime tests cover it. Open risk: no evidence the **production** ledger baseline has been executed (receipts in-tree are local); until a prod baseline receipt exists, prod's ledger state is assumed, not known.

**Backup/restore posture.** On this branch: nightly `pg_dump -Fc` with compression, sha256 sidecars, retention pruning, `pg_restore --list` validation, restore + rehearsal scripts, and an honest header ("this is not WAL archiving or PITR"). Local rehearsal receipt committed. Missing: production deployment (CRITICAL-2), offsite copy (a Hetzner Storage Box is the stated later stage — until then, backups share the failure domain of the data), and a prod restore rehearsal.

**Data integrity follow-ups.** The invariants runner covers exactly the right things (version uniformity, body-flag truthfulness, ring identity drift, stale non-eligible ratings, station-body link drift) — and runs against production never (HIGH-5). The three repair scripts (`repair_body_contract.py`, `repair_body_ring_association_status.py`, `repair_station_body_links.py`, ~1,400 lines combined) are one-shot production mutators; they follow the operator-script conventions, but they are the newest members of the "executable history" class the prior audit flagged — archive them after their runs are receipted.

**What product work may be masking.** The Stage 25 shell/cockpit polish and the closeout ceremony sit on top of: an unreconciled branch topology, an undeployed backup fix, an unthrottled anonymous write endpoint into the evidence layer, and a scoring-identity pivot that is still moving on a sibling branch. None of these is visible from the UI. All of them are the actual current risk.

---

# What To Do Next

### 1. Do now (this week, before any further feature or polish work)
1. **Cherry-pick backups to `main` and deploy.** Hours of work, closes the live existential gap regardless of the wider merge. Then run and receipt the first production restore rehearsal and the production ledger baseline.
2. **Reconcile the branch topology.** One integration branch; merge `stage25-closeout-checkpoint` + `devscore-retire-ratings` + `main` with hand-review of `scripts/`, `sql/`, `apps/maintenance/`, `.github/`; fast-forward `main`; archive the rest. Re-stamp the Stage 25 closeout on the merged line — until then, amend the ROADMAP's "complete and closed" to "closed pending integration," because today it is not true of any deployable ref.
3. **Gate the journal endpoint.** Rate limits, sync_key requirement, per-run quarantine flag on the evidence-layer writes, daily row circuit-breaker. Do not announce the feature before this lands.
4. **Schedule production invariants** (cron + post-deploy) with committed receipts.

### 2. Do next (the following stage)
5. Finish the colony retirement (delete `ColonyTab.tsx`, re-home `useColony`); remove `'colony'` from the Route union.
6. Resolve the scoring vocabulary: one decision doc, one term per layer, absorb or delete `development.html`, rename or gate "Development Tuning."
7. nginx-ci ↔ production config drift lock.
8. Hygiene follow-through: design doc off the root, `(1)` filename fixed, `_redesign/` out of `src/`, allowlist shrunk.
9. Offsite backup target (Storage Box/S3) — the honest header in `run_backup.sh` already names this as the next step; hold it to that.
10. Flat-import rewrite with the shim's retirement date attached; lint-forbid flat imports in new files immediately.

### 3. Defer deliberately
- Corridor routing (B-2/B-3) — correctly sequenced after data-trust closure; the shipped B-1 card is the right scope, pending MEDIUM-12 fixes.
- Journal Lane 2 (personal depot telemetry) — still correctly gated on accounts.
- pnpm/toolchain modernisation — yarn is frozen and honest; churn later.
- App.tsx shell decomposition — do it when the accounts stage forces state re-ownership anyway, not as standalone churn.
- Windows dev-stack expansion — freeze at current size; consolidate before adding.

---

**Final verdict, stated once:** the work at this checkpoint is the strongest remediation wave in the project's history, and the checkpoint itself is unsound — closed on paper, on a branch, while production runs older code without backups and a sibling branch keeps restructuring what "closed" is supposed to mean. Merge first. Then close. In that order, and only that order.

— All findings re-derivable from `98a3ff4b66f329fbda2415d046a37410dba48d02` and the remote refs inspected (`origin/main` @ `d8977a0`, `devscore-retire-ratings` @ `6b65b91`) at audit time; confidence tags mark the exceptions.
