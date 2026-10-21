> Read-only audit, 2026-10-21.
> Evidence, not execution authority (see CLAUDE.md authority order).

# Are the CRE and CPE pulling their weight? (read-only audit, 2026-10-21)

Snapshots audited: ed-finder `main` at `c396eb21` (2026-10-21); CRE (`elite-dangerous-research-engine`) at `e6d34cf` (2026-07-09); CPE (`colony-planning-engine`) at `9d5ff8c` (2026-07-03). No production access was used: anything about production comes from the code and from the repository's own recorded state, and is labelled as such.

## Executive summary (plain language)

1. **CRE today gives the live app nothing at runtime.** No code, build step, test or CI job in ed-finder reads any CRE file. That covers its CSV exports, its mechanics documents and its claim, rule or mechanic IDs. The only trace of CRE in the code is a confidence vocabulary that was copied by hand, with CRE IDs in its comments.
2. **ed-finder keeps its own copy of the game rules, written by hand, sometimes two or three times over.** I counted 13 mechanic areas. 0 of them come from CRE with a traceable ID. 11 are hand-coded in ed-finder, and 2 (population, system score) are missing from ed-finder entirely.
3. **Where the two disagree, CRE is sometimes the one that is right.** ed-finder's port construction-point cost table is invented (its own comment says the curve is "NOT publicly documented"). CRE has the exact table from the Mega Guide, and ed-finder never used it.
4. **The live Finder ratings (V4) were researched straight from Frontier patch notes and the Mega Guide.** The list of evidence sources behind them does not mention CRE at all.
5. **CRE itself has gone quiet.** Its last commit was 2026-07-09 and its export bundle (2026-06-29) is labelled "0.2.0-draft, prototype". 331 of its 343 claims are only "Extracted" (copied from a source document, not checked in game). 3 of its 13 mechanics are Confirmed. None of the 12 planned in-game tests has been run.
6. **CRE uses the same Mega Guide version as the current text (2.3.0, with the 2.4.0 WIP header), but its copy lost every footnote.** One result is that CRE says population grows on "weekly" ticks, while the guide's footnote says the ticks are daily, spread over about 15 days. Several other caveats are missing too.
7. **The journal "research export" to CRE is not a working loop.** The API endpoints are deployed, but the current web app has no button for them. Nothing sends the files anywhere. CRE has no way to take them in (its own README lists "ed-finder integration" as a non-goal). The files also carry exploration and exobiology scans, which CRE does not study at all.
8. **CPE is a single README.** The seven-phase design dossier could not be found: not in ed-finder `main`, not at four older `main` commits, and not on the 100 remote branches checked. The `docs/ai/` folder the CPE README points to does not exist.
9. **The planner code the ownership model gives to CPE actually lives in ed-finder.** That is about 12,500 lines of Python plus about 9,100 lines of TypeScript. It is deployed but cannot work on V3: it queries old V2 tables that production no longer has, and the web app's "Continue to Plan" button leads to a "Migration placeholder" page.
10. **Verdict:** neither CRE nor CPE delivers runtime value today. CRE has real but unused value: a correct, ID-tagged rule register. CPE delivers no value yet: it exists only as an idea, plus an empty database schema (`r1_plan`, `r1_meta`) already applied in production.
11. **Cheapest win:** CRE publishes one pinned rules file. A test in ed-finder then checks the hand-coded constants against it. This changes no live behaviour (ratings V4 stay frozen) and immediately catches wrong values like the CP table.
12. **Owner decisions needed:** (D1) what CRE is for (rulebook or research lab); (D2) whether CPE stays a separate repo or becomes a module inside ed-finder; (D3) what the first real Plan feature is, and what to do about the dead "Plan" links until it exists.

---

## 1. What ed-finder actually consumes from CRE

### 1.1 Searches run (all negative except the confidence vocabulary)

- File names: `claims.csv`, `mechanics.csv`, `planner_rules`, `economy_rules.csv`, `construction_rules`, `export_manifest`, `claim_provenance`, `unknowns.csv`, `contradictions.csv`, `graph_nodes`, `planner_risks`, `research-engine`, `research_engine`. Searched across all non-doc files in ed-finder (apps, packages, shared_contracts, sql, scripts, tests, frontend). **0 hits.**
- CRE ID patterns (`M-00xx`, `CL-xxxx`, `PR-00xx`, `ER-`, `CR-`, `U-`, `C-`, `R-`, `EV-`, `EXP-`, `LV-`, `CM-`, `SA-`). Searched in `apps packages shared_contracts sql scripts tests frontend/src`. **Only hits: `apps/api/src/mechanics/confidence.py`** (SA-0001..SA-0006, CM-0001, CM-0006A, CM-0007), and all of them are in comments and docstrings (`confidence.py:23-60`, `:188`).
- CI: no workflow in `.github/workflows` checks out a CRE or CPE repo. There is no `.gitmodules`. No `pyproject.toml` or `package.json` depends on them.
- Vendored data: the only bundled mechanics data is `apps/api/src/domain/facility_catalogue_v1.json`. Its header (lines 3-7) names its source as `apps/importer/src/import_facility_templates_from_daftmav.py` reading "Colonization Construction v3 (By DaftMav).xlsx". That is the DaftMav spreadsheet itself, **not CRE**, even though CRE extracted the same spreadsheet as DM-0001. `docs/reference/colonisation/*` holds prose only. `sql/v3/*` and `sql/r1_v3/*` hold no CRE data.
- `apps/api/src/mechanics/versions.py:5-12` lists the "mechanics sources" stamped into outputs: Mega Guide, DaftMav, Frontier strong/weak link explanation, community catalogue. **CRE is not listed.**
- The live Finder's mechanics authority, `docs/development/ratings-v4-mechanics-evidence.md:25-42`, has an evidence hierarchy of Frontier patch notes, then the Mega Guide, Raven Colonial, HerzbubeWiki and community tests. **CRE does not appear.**
- ed-finder's own Stage 27A inventory already says it outright: "CRE is not wired into ED-Finder at runtime" (`docs/colonisation-redesign/stage-27a-spatial-capability-inventory.md:34`).
- The confidence-vocabulary plan says it too: "No runtime CRE consumption yet" (`docs/superpowers/plans/2026-08-13-confidence-vocabulary-redesign.md:7`, Phase 1 only).

**Conclusion: confirmed.** Nothing reads CRE at build time, import time or runtime. The single CRE-derived artefact is a hand-copied confidence taxonomy.

### 1.2 Mechanic-by-mechanic: sourced from CRE, or hand-coded?

| # | Mechanic | Where ed-finder encodes it (file:line) | Matching CRE item | Sourced from CRE with an ID? |
|---|---|---|---|---|
| 1 | Body type → base economies | **Live Finder:** `apps/api/src/domain/ratings_v4.py:425-447`. **Legacy planner:** `domain/colonisation_rules.py:157-197`. **Retired React planner:** `packages/planner-core/src/stationBaselineEconomy.ts:115+` | M-0008 (CRE itself *withholds* it from release: `exports/withheld_items.md`) | No. Hand-coded 3 times. The legacy copy disagrees with the guide: Ammonia becomes Tourism + HighTech-as-modifier (`colonisation_rules.py:163-167`), and main-sequence or brown-dwarf stars get no Military (`:170-173`) |
| 2 | Local body modifiers (rings, organics, geologicals) and the non-stacking rule | `ratings_v4.py` (modifier path), `colonisation_rules.py:174-197` | M-0008, U-0007 | No |
| 3 | Inheritance strengths | `ratings_v4.py:17-19` (75/55/85, frozen); `mechanics/economy_rules.py:7-9` (1.0/0.8/0.45); duplicated in `stationBaselineEconomy.ts:4-6` | M-0007 (qualitative only) | No. Three numeric schemes across two languages |
| 4 | Strong/weak link base values | `mechanics/link_rules.py:5-12` (0.4/0.8/1.2; weak 0.05); `ratings_v4.py:20-21` (±10, cap 25) | CL-0146, CL-0147 (same values) | No. Same numbers, copied by hand without an ID |
| 5 | Strong-link modifiers (ELW, WW, terraformable, bio, icy, tidal…) | `link_rules.py:14-31`; `ratings_v4.py:598-640` | M-0006, CL-0053, U-0013 | No |
| 6 | Top-two economy protection | V4: handled as a policy decision (`ratings-v4-mechanics-evidence.md:220-231`), citing patch wording only. Legacy: purity/tertiary penalties `economy_rules.py:29-41` | M-0010 (includes the guide's supply-protected / demand-not-protected nuance) | No. CRE has the more precise rule |
| 7 | T2/T3 port construction-point escalation | `mechanics/cp_rules.py:5-13` ([16,20,26,34,44,56] / [40,52,68,88]); `simulation/cp_simulator.py:21-23` says "Exact escalation curves are NOT publicly documented… community estimates" | CL-0013..CL-0018 etc. (3,3,5,7,9 → 3+(n−2)·2 T2 points; 6,6,12,18,24 → (n−1)·6 T3 points), which matches guide p.26 | No. **ed-finder's values are wrong and CRE's are right** |
| 8 | Facility catalogue (stats, prerequisites, CP generated) | `domain/facility_catalogue_v1.json` (from the DaftMav xlsx) | M-0009, M-0011 (from DM-0001, the same spreadsheet) | No. Two independent extractions of one source |
| 9 | Service unlocks | `mechanics/service_rules.py:9-18`, `simulation/services.py`, `simulation/service_graph.py` | M-0011 | No |
| 10 | Colony-port inheritance / economy propagation to the main port | `simulation/port_economy.py`, `domain/economy_state.py` | M-0005, M-0007 | No |
| 11 | Slot prediction (surface/orbital) | `ingest/slot_prediction.py` (ed-finder's own validated algorithm) | M-0001 only (water worlds) | No. ed-finder original; CRE has no equivalent |
| 12 | Population growth / body multipliers | **Not implemented** (code search for logistic / asymptotic / sqrt(pop) found nothing) | M-0012, population register | n/a |
| 13 | System score and weekly payout | **Not implemented** | M-0013, CL-0184 onward | n/a |
| — | Confidence vocabulary | `mechanics/confidence.py:23-60` | CRE confidence-model register (SA-/CM- IDs) | Hand-aligned, with IDs in comments only |
| — | Regional roles, archetype fit, ranking | `mechanics/regional_rules.py`, `mechanics/scoring_rules.py`, `shared_contracts/v3_system_archetype_model.py` | — | ed-finder's own judgement, not game mechanics. Correctly ed-finder's (or CPE's) |

**Count:** 13 mechanic areas. **0** sourced from CRE with a traceable ID. **11** hand-coded in ed-finder: area 1 three times, area 3 three times, areas 4 and 5 twice (legacy + V4). **2** missing. At least **1** is wrong where CRE is right (#7), and at least **1** legacy copy disagrees with both the guide and CRE (#1, `colonisation_rules.py`).

The rules that matter in production today are V4's (#1–#6 in `ratings_v4.py`). They are frozen and attested (`docs/development/ratings-v4-freeze/README.md`), and they came from ed-finder's own evidence audit, not from CRE.

## 2. What ed-finder sends to CRE (journal research export)

- **Code:** consent ledger `apps/api/src/edfinder_api/journal/consent.py:37-38` (`PURPOSE='CRE_RESEARCH_EVIDENCE'`, `AUDIENCE='CRE'`); export builder `journal/export.py:44` (schema id kept "after the CRE→EDRE rename (2026-08-29)"); sanitizer `journal/sanitize.py:52-64`; router `routers/v3_journal_research.py:31` (`/api/v1/journal/research-consent`, `/research-exports`; routes at `:327`, `:338`, `:378`, `:401`, `:437`).
- **Deployed?** Yes at the API level. It is mounted in the production entrypoint (`apps/api/src/main.py:406`; the release image runs `edfinder_api.main:app`, `apps/api/Dockerfile.release:44`). Its tables are created by `sql/v3/migrations/005_v3_journal_intelligence.sql:141,176`, which `sql/v3/migration-manifest.txt` records as confirmed applied in production on 2026-09-12. The production edge forwards all `/api/*` (`deploy/v3-production/public-auth-edge.nginx.conf:95-96`).
- **Reachable by a user?** Only by calling the API directly. In the current web app (`apps/web/src`), `createV3ResearchExport`, `putV3ResearchConsent` and the rest appear **only** in the generated SDK (`lib/api/generated/*`), with no caller. The only consent UI is in the retired React tree (`frontend/src/features/account/ResearchConsentPanel.tsx`), which is not built or deployed.
- **What it carries:** only `Scan, FSSBodySignals, SAASignalsFound, SAAScanComplete, CodexEntry, ScanOrganic, SellOrganicData, FSSDiscoveryScan, FSSAllBodiesFound` (`sanitize.py:60-64`). That is exploration and exobiology data. The V3 journal allowlist has **no colonisation events at all** (`journal/event_contract.py:16-24`), even though the design called for `ColonisationConstructionDepot` and `ColonisationContribution` (`docs/colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md:34,94`).
- **Does anything on the CRE side ingest it?** No. CRE has no intake for this schema (a search for the export schema id, `OBSERVED_PERSONAL` and `exportManifest` found nothing). Its only tool, `bin/cre-vault`, imports local files, and its README lists "ed-finder integration" as a non-goal (`tools/evidence_vault/README.md:148-154`). CRE contains no exobiology research at all.
- **Is the loop closed?** **No.** Batches are written to `v3_private.research_export_batch` and stop there: no push, no pull, no consumer. With no UI and (per the owner, 2026-10-17) no users yet, there are probably no batches at all. I could not check that in production.

## 3. CRE health and currency

**Dates and versions:** last commit 2026-07-09 (`e6d34cf`, "Add B2a Agriculture negative test evidence"). Export manifest `0.2.0-draft`, generated 2026-06-29T22:22:06Z. `exports/release_notes.md:3` calls it "a prototype … not a final public knowledge release". That is about 3.5 months of no activity, during which ed-finder ran a full mechanics audit (Ratings V4, September 2026) that never flowed back into CRE.

**Counts (from `exports/*.csv`):**

| Register | Total | Status breakdown |
|---|---|---|
| Mechanics | 13 | Confirmed 3 (M-0001..M-0003, all from one live system, Wregoe), Likely 5, Extracted 5 |
| Claims | 343 | **Extracted 331**, Observed 7, Confirmed 3, Confirmed_Narrow 1, Pending 1. 127 flagged "needs live verification". By source: Mega Guide 233, DaftMav 71, links reference 16, Wregoe 11, flowchart 11 |
| Planner rules | 13 | Confirmed 7, Likely 3, Extracted 3 |
| Economy rules | 20 | Confirmed 1 (+2 narrow/caution), Likely 6, Needs verification 3, Extracted 8 |
| Construction rules | 23 | Confirmed 1 (+1 caution), Likely 6, Extracted 15 |
| Unknowns | 20 | U-0001..U-0020, all open |
| Contradictions | 9 | 8 of 9 "Needs live verification" (or more examples) |
| Live verification matrix | 12 | **0 run.** All "Needs live verification" (`experiments/live_verification_register.md`). EXP-0001 "Awaiting completion" |
| Withheld from release | — | M-0008 (body economies, the most-used mechanic) and CS-0001 |

**Structural problems that block using CRE IDs as traceable keys:**
- ID collisions. `PR-0001..` means planner rules in `exports/planner_rules.csv` but population rules in `mechanics/population_rules_register.md:5+`. `EV-0004` is used by two different evidence files (reference pack, and the 2026-07-09 B2a agriculture test). The newest evidence (B2a) never reached the exports.
- The population and market rule registers exist (`mechanics/population_rules_register.md`, `market_rules_register.md`) but are **not in the export manifest**.
- The source register has only four sources: MG-0001, FW-0001, DM-0001, DD-0001 (`reference_sources/source_register.csv`). **There are no Frontier first-party patch notes**, which ed-finder's V4 audit treats as the top authority.

**CRE vs the current Mega Guide (headline gaps only):**
- **Same document version.** CRE's MG-0001 text is the same 2.3.0 document with the 2.4.0 WIP line (`reference_sources/MG-0001-megaguide-v2-3/elite-dangerous-colonization-mega-guide-v2-3.txt:2-12`). The 8-word overlap with the new text is about 75%. Nearly all of the difference is table layout and **footnotes, which CRE's DOCX-to-text extraction dropped**.
- **M-0012 (population): partly wrong.** CRE says growth is on "weekly maintenance ticks" (`population_rules_register.md:5-11`, claim CL-0173 marked *High*). The guide's own footnote 27 says these are **daily ticks over about 15 days** (13 full ticks plus partial ticks on C+1 and C+15/16). The table values (610m/1,525m/3,100m ELW T3, and so on) were extracted correctly (CL-0062..CL-0072). Neither CRE nor the guide's text layer has the formula itself, because in the guide it is an image (an OCR/transcription task). The ground-port inflection point (120 vs 100 days, footnotes 28/29) is also missing from CRE.
- **M-0010 (top-two protection): consistent with the guide.** Supply of the top two economies is protected and their demand is not; rank is by strength, with a tie-breaker. CRE still lists U-0002 (rank vs percentage) and U-0014 (same-strength ordering) as open, though the guide's text largely answers U-0002.
- **M-0008 (body economies and modifiers): tables match the guide.** It is missing footnote 13 ("Volcanism ALSO provides a bonus to planetary intrinsic values", which matches the guide's 2.2.0 "TO FIX: modifiers on planetary intrinsics DO apply") and footnote 14 (geologicals and rings do not boost Extraction on an intrinsic-Extraction body). It is still withheld from release.
- **M-0013 (score and payouts): consistent with the guide** (Score × ~10,000 × (1 + Happiness)). It is missing footnote 31 (about ±2% weekly variance) and footnote 30 (mid-week build pro-rating).
- **Not in either:** the 4.2.2.0 patch nerf (−70%, then −25%), which the guide itself has not incorporated. Footnote 18 ("no Tier 3 facility autonomously creates strong links") is missing from CRE.

## 4. CPE

**What exists in CPE:** one README (`colony-planning-engine/README.md`, one commit 2026-07-03), which says "CPE is currently documentation-only". It points to "the cross-repository governance record … in `ed-finder/docs/ai/`". **That folder does not exist.** It is absent from `main`, from `main` as of 2026-07-05, 07-20, 08-15 and 09-05 (checked through the GitHub contents API), and from all 100 remote branches listed. **The design dossier `CPE_SYSTEM_ASSESSMENT_ENGINE_AND_CRE_CPE_RELEASE_CONTRACT_DESIGN_DOSSIER_V1.md` was not found anywhere**, so I could not check its seven phases one by one. The owner may have it only locally, as happened with the 2026-07-14 regional-search decision doc. Below, I mapped the capabilities named in the CPE README and in memory against what actually exists.

| CPE capability (per README / dossier summary) | Where it exists | Designed / implemented / reachable |
|---|---|---|
| Ownership boundary | CPE README; `docs/development/cross-repo-workspace.md`; `docs/ROADMAP.md:728-729` | Documented |
| CRE→CPE pinned release contract | CRE manifest `0.2.0-draft` (no consumer); empty slot `r1_meta.mechanics_revision` (`sql/r1_v3/001_structural_shell.sql:11-34`) | Schema only. Applied to production 2026-08-31 (manifest). **No code reads or writes it** (search for `r1_meta`, `r1_plan`, `mechanics_revision` in apps/packages: 0 hits) |
| Assessment state, Plan Fit, carrier scenario, capacity sufficiency, programme revisions | `r1_plan.plan_assessment` (`assessment_state`, `plan_fit`, `reserve_capacity`, `logistics_state`, `carrier_mode`, `mechanics_revision_id` at `:386+`), `r1_meta.programme_revision` (`:64`), `r1_plan.saved_plan` / `plan_revision` (`:219`, `:242`) | Schema only, in production, empty, no code |
| System Assessment Engine (runtime) | Nothing in CPE. Closest in ed-finder: the generic archetype fit (`shared_contracts/v3_system_archetype_model.py`), which is a "universal" score; CPE's README explicitly disowns that | Not implemented as designed |
| Colony Plan Construction (candidates, sequencing, alternatives) | ed-finder legacy: `optimiser/` (3,034 lines: `candidate_generator.py`, `guided_planner.py`, `ranker.py`, `plan_quality.py`), `simulation/` (5,246), `recommendations/` (458), `regional/` (404), `mechanics/` (919), `domain/` planner parts (~1,065), `routers/simulate.py` + `simulation.py` (1,292); `packages/planner-core` (~9,100 non-test TS lines) | Implemented for V2. **Not reachable on V3** (details below) |
| Observed-vs-predicted validation | `observations/comparison_engine_pkg/*` (4,277 lines in `observations/`), plus an ed-finder evidence → rule-proposal → decision pipeline (`evidence_store/store.py:486+`, `sql/030_evidence_store_foundation.sql:110`) | V2 tables only. This is also CRE's job, duplicated |

**Can a user reach ed-finder's planner in production today? From code: no.**
- **Routes:** mounted in the production app (`main.py:396-400`: simulate, simulation, optimiser, observations, colony_planner).
- **Data:** every planner endpoint queries V2 `public` tables without a schema prefix. Examples: `optimiser/candidate_generation_context.py:30-38` (`SELECT * FROM systems` / `bodies`); `routers/simulate.py:269-294` (`bodies`, `body_scan_facts`); and simulation, observations and evidence code using `observed_facts`, `system_archetype_scores`, `system_slot_topology`, `buildability_analysis`, `system_regional_analysis`, `rule_proposals`. **None of these tables is created by any V3 migration** (`sql/v3/migrations/*`, `sql/r1_v3/*`; checked). V3 keeps systems and bodies in `v3_gen_<generation>` schemas (`sql/v3/migrations/001_v3_baseline.sql:1021-1060`). The V3 decision forbids relying on a hidden `search_path` (`docs/development/v3-search-spatial-derived-data-decision.md:23`). ed-finder's own delivery plan says these older paths "query the V2 schema that production does not have" (`docs/development/v3-finder-delivery-plan.md:21`). So `/api/optimiser/candidates` will fall into its catch-all and return 503 "Suggested Builds are temporarily unavailable" (`routers/optimiser.py:56-70`). That message is misleading: the feature is not temporarily down, it cannot work. Inferred from code and repo docs; not live-tested.
- **One exception:** `/api/facility-templates` can still answer, from the bundled DaftMav JSON fallback (`main.py` lifespan, catalogue fallback).
- `/api/colony-planner/system/{id64}/import-layout` is a stub. It always returns "not wired yet" (`colony_planner/layout_import_provider.py:15-35`).
- `/api/archetypes/simulate` *is* on V3 (`routers/archetypes.py:1003-1050`), but it only looks up the published archetype score for the planned archetype. It builds no plan.
- **UI:** `/plan` is matched by `apps/web/src/params/journey.ts` and rendered by `apps/web/src/routes/[journey=journey]/+page.svelte`, which shows "Migration placeholder … This product surface has not been ported yet." Users are actively sent there: Inspect's primary button "Continue to Plan" (`routes/inspect/+page.svelte:29`), Explore's "Plan here" (`lib/features/explore/ExploreWorkspace.svelte:1090`), and the shell's "Open plan" (`lib/components/AppShell.svelte:72`). No web code calls any planner or simulate endpoint. The only `@ed-finder/planner-core` import in `apps/web` is the journal parser (`lib/journal/import-worker.ts:1`). The planner parts of planner-core are used only by the retired `frontend/` (97 files).

**Is ed-finder doing CPE's job?** Yes. Plan construction, sequencing, candidate generation and plan ranking were all built inside ed-finder, before CPE existed, as V2 code. Under the locked ownership model this is CPE territory. It is now dormant code: about 21k lines, 27 test files still covering it, and maintenance and audit cost, with zero production use.

## 5. Verdict and recommendations

### CRE
- **Value today:** runtime value **none**. Indirect value: (a) a carefully ID'd claim register that is more accurate than ed-finder in at least one place (the CP escalation table); (b) the confidence vocabulary ed-finder copied; (c) an organised record of the owner's own Wregoe tests, the only Confirmed mechanics anywhere.
- **Why it isn't pulling its weight:** it never shipped a release anyone consumes. ed-finder went to primary sources directly for V4. CRE stopped in July, before the September mechanics work. Its IDs are not yet unique enough to cite.
- **What it would take (ordered, small steps; "do" = can just be done, "D" = owner decision):**
  1. **D1, owner:** say what CRE is for. My recommendation: a *versioned rulebook* (curated rules with IDs, sources and status), with live experiments as an optional extra. Without this decision, the rest is guesswork.
  2. **do, in CRE:** fix the ID collisions (rename population rules to e.g. `POP-`, renumber the duplicate `EV-0004`). Re-extract the Mega Guide *with footnotes* (from the PDF, or the text the owner already has). Correct the "weekly ticks" population rule. Add Frontier patch notes (Trailblazers U3, Vanguards P1) as sources. Add the population and market registers to the export.
  3. **do, in CRE:** publish one machine-readable `planner_safe_rules.json` with stable IDs, status, source and exact values: CP escalation, link base values, body-economy table, modifiers, strong-link modifiers, top-two rule, population table, score table. Tag it (e.g. `cre-knowledge-v0.3.0`) and record its sha256.
  4. **do, in ed-finder (no behaviour change):** vendor that file at a pinned version with its hash. Add a *parity test* that compares ed-finder's hand-coded constants (`cp_rules.py`, `link_rules.py`, `ratings_v4.py` body tables) with the CRE values and reports every difference. It touches nothing frozen. It will immediately flag `cp_rules.py:5-13`.
  5. **do, after Finder go-live:** fix the legacy disagreements the test finds, and delete the triplicated body tables in dead code (see CPE step 2).
  6. **D, after go-live:** a Ratings V4.1 / archetype ruleset version that *reads* the body-economy and modifier tables from the pinned CRE file instead of hard-coded dicts. It needs a new mechanics version, evidence and a rebuild, as the V4 freeze rules require. Record the CRE release in `r1_meta.mechanics_revision`.
  7. **D, owner:** decide the journal export. Either repoint it at what CRE studies (colonisation events: `ColonisationConstructionDepot` / `ColonisationContribution` / market snapshots, which would also need V3 allowlist and privacy work), plus a small CRE intake script; or hide or pause the research-export endpoints until CRE can use them. Today it is a privacy-sensitive feature with no consumer.

### CPE
- **Value today:** **none.** It is one README, and the dossier cannot be located. The only built artefact matching its design is the empty `r1_plan` / `r1_meta` schema in production.
- **What it would take:**
  1. **D2, owner (biggest call):** is CPE a separate repo, or a module inside ed-finder? For a solo developer whose planner code is Python in the same API, using the same V3 tables, my recommendation is to **fold CPE into ed-finder as a clearly bounded module** (e.g. `apps/api/src/cpe/` plus a `cpe` package boundary test). Keep the ownership rule as a code boundary rather than a repo boundary. Archive the CPE repo README with a pointer, or keep it purely as the design home. A separate repo only pays off once there is a second consumer.
  2. **do:** find the dossier (probably local-only on one of the owner's machines) and commit it, or remove the dangling `docs/ai/` references from the CPE README and `cross-repo-workspace.md`.
  3. **D3, owner:** choose the first real Plan feature. A good first slice that needs no V2 data is a **"CP budget and port-order calculator"**. It would use the facility catalogue, the guide/CRE CP escalation table (Primary Port exempt) and V3 bodies, so it validates the CRE-to-CPE handoff end to end. Until something ships, decide whether "Continue to Plan" / "Plan here" / "Open plan" should stay live. Changing them is a visual change and needs visual validation.
  4. **do, after D2:** mark the V2-only planner endpoints honestly. Either remove them or feature-flag them off in production with a clear "not available on V3" response instead of "temporarily unavailable". Port only what step 3 needs, through a V3 body/system adapter (explicit `v3_gen_*` reads, not `search_path`).
  5. **do, after the first slice:** persist plans in the already-applied `r1_plan` tables, pinning `mechanics_revision_id` to the CRE release from CRE step 3. That is the point where CRE, CPE and ed-finder are actually connected.

**Constraints respected:** Ratings V4.0 (`scorer 4.0.0`, `v4-mechanics-2026-09`) and `v3-archetype-4` are frozen and attested for go-live. Every step above that would change live scores is post-go-live and versioned (CRE step 6). Steps marked "do" before that point change no production behaviour: they are docs, tests and the CRE repo.

**Owner decisions, in one list:** D1 (CRE purpose) · D2 (CPE: repo or module) · D3 (first Plan feature and the dead Plan links) · the journal research export's purpose (CRE step 7) · when to version the ruleset (CRE step 6).
