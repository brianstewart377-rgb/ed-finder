# ED-Finder — Feature Design Report: Journal Import & Colonisation Proximity Routing (V1)

> Historical design reference kept at repo root because `docs/ROADMAP.md`
> intentionally links to it. It is not a second roadmap or an active control
> document.

- **Repo:** `brianstewart377-rgb/ed-finder`, grounded against commit `7913c68` (same tree as the V1.1 audit)
- **Scope:** (A) importing in-game journal log files and using them for enrichment; (B) nearest-colonised-system lookup with suggested route(s)
- **Posture:** design recommendation, read-only analysis. Game-rule constants are flagged where they must be verified against the current game version per your `docs/reference/colonisation/source-priority.md` discipline.

---

## 0. The headline finding: the codebase was already built for Feature A

Three pieces of existing infrastructure mean journal import is a *completion*, not a greenfield build:

1. **`sql/017_observed_facts.sql`** — header comment: *"Generic observed facts table for future journal/manual/API/EDMC ingestion."* It already has `source_commander`, `raw_event_ref`, `observed_at`, and a `confidence` default of `'observed'`. The landing table exists.
2. **`sql/030_evidence_store_foundation.sql`** — `evidence_records.source_name` has a CHECK constraint whitelisting **`'frontier_journal'`**. The evidence tier for journals was reserved in advance.
3. **`apps/eddn/src/eddn_listener.py`** — already parses the journal event vocabulary (`FSSDiscoveryScan`, `Scan`, `SAASignalsFound`, `NavBeaconScan`, `FSDJump`/`Location`, colonisation events), because EDDN messages *are* relayed journal events. `handle_scan`, the ring-row normaliser, and `safe_int`-style sanitisation are directly reusable for file-sourced events.

The design question is therefore not "how do we model journal data" — it's **transport, trust, attribution, and write-path governance.**

---

# Part A — In-Game Journal Import & Enrichment

## A.1 What journals give you that EDDN doesn't

The journal files (`%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous\Journal.*.log`, newline-delimited JSON, one event per line) are strictly richer than the EDDN relay you already ingest:

| Dimension | EDDN (current) | Local journals (new) |
|---|---|---|
| Coverage | Only what other players uploaded, live | The commander's **entire play history** — months of scans EDDN never saw |
| Fidelity | Personal fields stripped by relays | Full events, including `ColonisationConstructionDepot` resource manifests and `ColonisationContribution` amounts |
| Attribution | Anonymous | First-party: "this commander observed this" — your highest possible trust tier |
| Personal state | None | The player's *own* colonisation projects, visited systems, carrier jumps, discoveries |
| Latency | Live only; history unrecoverable | Backfill: a new user can donate months of exploration data on day one |

The strategic value splits in two, and the design should treat them as separate lanes:

- **Lane 1 — Communal enrichment:** journal scans/docks/colonisation events fill gaps in canonical `systems`/`bodies`/`stations` data, exactly like EDDN does, but with backfill depth and a named-source trust tier.
- **Lane 2 — Personal telemetry:** the commander's own visited systems, active construction depots, and contribution progress become *user-owned observed evidence* feeding My Work and the Colony Planner ("your depot at X is 62% delivered — **observed**, not predicted").

Lane 2 is the differentiator. No competing tool closes the loop between *planning* a colony and *observing your own delivery progress* against that plan in the same workspace. You already have the evidence-language vocabulary to present it honestly.

## A.2 Transport architecture — three options evaluated

### Option 1 — Server-side raw file upload
Drag-and-drop `.log` files; API stores and parses them.
*For:* simplest client. *Against:* you accept arbitrary user files into the backend (parsing attack surface + storage), you upload personal fields you'll immediately discard, files can be hundreds of MB per active player, and it maximally violates your "no implicit write automation" boundary by putting untrusted bytes closest to the canonical DB.

### Option 2 — Companion app / EDMC plugin streaming events
A desktop agent (or a plugin for the community's EDMarketConnector) tails the journal and POSTs events live.
*For:* real-time, ecosystem-native (EDMC users already run it). *Against:* a second deliverable to build, sign, distribute, and maintain; auth story required on day one; and it does nothing for the backfill case, which is where most of the enrichment value sits. Right feature for Phase 3, wrong place to start.

### Option 3 — Client-side parsing in the SPA, normalised batch submission ★ recommended
The browser reads files locally (drag-drop / file picker), a **Web Worker** parses NDJSON, filters to an **event allowlist**, strips personal fields, shows the user a preview ("2,341 body scans, 118 systems visited, 3 construction depots — nothing else leaves your machine"), then submits *normalised observation batches* to a staging endpoint.
*For:* raw files and personal data never leave the client; the server receives typed, schema-validated observations only; payloads shrink ~50×; the preview step *is* the privacy consent UI; and Chromium's File System Access API upgrades the same code path to live folder-tailing later with zero server changes.
*Against:* parsing logic ships in the frontend bundle (mitigated: it's a worker chunk, lazy-loaded), and Safari/Firefox get batch-only, no live tail (acceptable — batch is the core value).

**Recommendation: Option 3 now, Option 2 (EDMC plugin) as Phase 3 once the ingest contract is proven.** Option 1 should not be built at all.

## A.3 Write-path governance — the non-negotiable part

This must ride the rails you already built, or it undermines the entire Stage 18–19 investment:

```
browser worker (parse, allowlist, sanitise)
  → POST /api/journal/import          (batch of normalised observations + client manifest)
    → journal_import_staging          (new staging table, mirrors enrichment_staging patterns)
    → source_runs row                 (existing ledger, sql/029 — one run per import session)
    → observed_facts / evidence_records  (source_name='frontier_journal', origin='imported')
         ↓ existing guarded reconciliation lane
    → canonical systems/bodies/stations   (ONLY via the guarded apply path, never direct)
```

Concretely:

- **The API endpoint writes to staging + evidence tables only.** Canonical promotion reuses the reconciliation/guarded-apply machinery from the enrichment lane (`enrichment_staging_db_loader`, write-plan patterns). Journal import must not become a second, softer door into canonical tables — that would be the exact failure your review protocol exists to prevent.
- **Fast-lane exception, explicitly bounded:** the EDDN listener already writes scans/jumps to canonical tables live. It is defensible for journal-sourced events *of the identical event types EDDN already trusts* to use the same handlers (they're the same shapes) — but I'd argue against it initially. EDDN events are corroborated by network-wide volume; a single user's file upload is not. Start staging-only; graduate specific event types to the EDDN-equivalent path only after dedupe/conflict behaviour is observed in production. **[Judgment call — flagged for your decision, not asserted.]**
- **Dedupe key:** `(event_type, system_id64, body_id/subject, timestamp)` hashed into `evidence_key` (the `UNIQUE` on `evidence_records.evidence_key` does the rest). Journal timestamps are second-precision and stable, so re-importing the same file is a clean no-op — which matters, because users *will* re-drag their whole folder.
- **Trust ordering:** journal observations should rank above EDDN for the same fact at the same timestamp (first-party beats relay) but below newer observations from any source. Your `source-priority.md` conflict rules already define the vocabulary for this; encode it in the reconciliation scoring rather than ad hoc per handler.

## A.4 Event allowlist and privacy

Parse only these (Phase 1), drop everything else **in the worker, before network**:

| Event | Feeds |
|---|---|
| `FSDJump`, `Location`, `CarrierJump` | visited-systems personal layer; system economy/population/allegiance confirmation |
| `Scan` (AutoScan/Detailed), `FSSDiscoveryScan`, `FSSAllBodiesFound` | bodies table gaps; `has_body_data`/`body_count` — which trips your `rating_dirty` triggers (022) so **ratings rebuild automatically follows imports**, no new plumbing |
| `SAASignalsFound`, `FSSBodySignals` | ring composition, bio/geo signals — direct rating inputs |
| `Docked` | station services/economies/landing pads — feeds the station identity lane |
| `ColonisationConstructionDepot`, `ColonisationContribution`, `ColonisationBeaconDeployed`* | is_being_colonised confirmation; **personal depot progress for Lane 2** |
| `SellExplorationData`/`MultiSellExplorationData` | optional: first-discovery credit for the user's map layer |

\* Exact colonisation event names/payloads must be verified against the current game build — Frontier has revised these since Trailblazers; treat the journal schema doc as the authority and version the parser accordingly. **[Confidence: medium on exact event names; high on the category.]**

**Strip always:** commander name (unless the user opts in to attribution), squadron, wing/crew members, friends events, chat (`ReceiveText`/`SendText` are never parsed), ship loadout/credits, and every event not on the allowlist. `observed_facts.source_commander` should hold an opaque per-user identifier, not the CMDR name, until the user explicitly opts into public credit. Journals are personal data under GDPR the moment they're attributable — Edinburgh means you're squarely in scope, so the preview-and-consent step in the worker is a compliance feature, not just UX.

## A.5 Attribution dependency — be honest about the ordering

Lane 2 (personal depot progress, visited layer) requires knowing *whose* observations these are across sessions. Today that's the sync_key; properly it's the accounts lane from the audit (§6). **Recommendation:** ship Lane 1 (communal enrichment) attributed to an import-session `source_run` only — no user identity needed. Gate Lane 2 behind sync_key at minimum, and treat it as the flagship reason to prioritise the accounts MVP. Do not invent a third identity mechanism for journals.

## A.6 New surface area (small, by design)

- **Tables:** `journal_import_staging` (one; mirrors enrichment staging shape). Everything else lands in existing `observed_facts`, `evidence_records`, `source_runs`.
- **API:** `POST /api/journal/import` (batch, size-capped, rate-limited per key), `GET /api/journal/imports/{run_key}` (status/summary for the UI).
- **Frontend:** `features/journal-import/` — dropzone, worker parser, preview/consent panel, import receipt ("run `jrnl-…`: 2,341 observations staged, 3 conflicts flagged"). Entry points: My Work (primary) and System Detail's evidence panel ("have you visited? import your scans").
- **Importer/ops:** journal-sourced rows flow through existing reconciliation reports; the provenance cockpit already knows how to display source runs.

## A.7 Phasing

1. **A-1 (one stage):** worker parser + allowlist + preview; staging endpoint + `source_runs` integration; `observed_facts`/`evidence_records` writes; import receipt UI. No canonical writes.
2. **A-2:** reconciliation → guarded canonical promotion for `Scan`/`SAASignalsFound` classes; watch `rating_dirty` drain behaviour after large imports (the 250-row threshold in `run_dirty_ratings_if_needed.sh` will trip constantly during adoption spikes — verify the cron cadence can absorb it).
3. **A-3:** Lane 2 personal surfaces (depot progress card in Colony Planner: *observed* delivery vs *planned* requirement); live folder-tail via File System Access API.
4. **A-4 (optional):** EDMC plugin speaking the same batch contract.

**Risks:** malformed/hostile NDJSON (mitigated: client-side parse + server-side Pydantic validation of normalised shapes only); duplicate-flood re-imports (mitigated: evidence_key dedupe); trust poisoning by fabricated files (real — one user can forge scans; mitigated by staging-first, per-source-run quarantine/rollback via the ledger, and never letting single-source journal evidence *overwrite* multi-source consensus in reconciliation scoring); parser drift across game patches (version-stamp the parser, store `raw_event_ref` for reprocessing).

---

# Part B — Nearest Colonised System + Suggested Route(s)

## B.1 Define the product question first — there are two, and conflating them ruins both

Given a target system/planet:

1. **"Can this be claimed?"** — colonisation requires the target to be within the claim radius (**~16 ly** under Trailblazers rules — make this a config constant `COLONISATION_CLAIM_RANGE_LY`, sourced from the Mega Guide per `source-priority.md`, and verify against the current game build before shipping **[Confidence: medium on the exact number, high on the mechanic]**) of an existing colonised system. The answer is: nearest colonised anchor(s), distance, in/out of range.
2. **"If it's out of range, how do I get colonisation *to* it?"** — this is not a travel route. It's an **expansion corridor**: a chain of intermediate systems, each within claim range of the previous one, that a player (or squadron) would colonise in sequence to bridge the gap. Your own reference shelf contains the "OASIS Guide for Bootstrapping a Bubble" — this feature is that guide, computed.

A conventional ship jump route (A→B in N jumps at X ly jump range) is the *third* and least valuable interpretation — the in-game galaxy map already does it, and your FC Planner (`useFcPlanner.ts`, pure Euclidean leg math) already approximates it for carriers. Offer travel legs as a garnish; **the corridor is the feature.** It's the one only ED-Finder can do well, because ranking intermediate hops requires exactly what you have and nobody else does: per-system colonisation ratings.

## B.2 Nearest-colonised query — implementation

Current spatial reality (verified): distance is raw `SQRT(POWER(…))` arithmetic (`local_search.py:611`); systems carry `grid_cell_id` (500 ly cubes) and `macro_grid_id` (2,000 ly) from `build_grid.py`; `scripts/migrate_postgis.sh` exists but is a manual post-import step whose production status is unknown from the repo — **do not design against PostGIS being present.**

The colonised subset is tiny relative to 41M rows (tens of thousands of systems), which makes this easy:

```sql
-- one-time, additive:
CREATE INDEX IF NOT EXISTS idx_systems_colonised_coords
  ON systems (x, y, z) WHERE is_colonised = TRUE;   -- partial index, small

-- query: bounding-box prefilter + exact distance, K nearest
SELECT id64, name, x, y, z,
       SQRT(POWER(x-$1,2)+POWER(y-$2,2)+POWER(z-$3,2)) AS dist
FROM systems
WHERE is_colonised = TRUE
  AND x BETWEEN $1-$r AND $1+$r    -- expand r: 20 → 50 → 150 → 500 ly until K hits
  AND y BETWEEN $2-$r AND $2+$r
  AND z BETWEEN $3-$r AND $3+$r
ORDER BY dist LIMIT $k;
```

Even a full scan of the partial index is milliseconds at this population size; the expanding-box loop just keeps it tidy in deep space. If `migrate_postgis.sh` *is* applied in prod, swap in a KNN `<->` GIST query behind the same function signature — but the partial index makes PostGIS unnecessary for this feature. Include `is_being_colonised = TRUE` systems as a second, visually distinct tier ("anchor under construction — pending"), because a system being colonised *now* is a future anchor and players plan against futures.

**Endpoint:** `GET /api/systems/{id64}/nearest-colonised?k=5` → anchors with distance, in-claim-range boolean, colonisation status, and rating summary. Cache in Redis (`ttl_system`-class); invalidate on the EDDN colonisation handler path.

Note the "given planet" nuance: distances in the colonisation mechanic are system-to-system (star coordinates). A planet resolves to its host system's coords — say so in the UI ("measured star-to-star") so nobody expects orbital geometry.

## B.3 Expansion-corridor routing — the algorithm

**Graph:** nodes = systems; edge u→v exists iff `dist(u,v) ≤ CLAIM_RANGE`. Start set = all colonised anchors near the target (or a user-chosen origin anchor); goal = target system. Find a path where every hop is claimable from the previous.

**Search:** A* with straight-line-distance ÷ claim-range as the admissible heuristic (it lower-bounds remaining hops). Neighbour expansion is the B.2 query re-aimed at *all* systems (not just colonised) within `CLAIM_RANGE` of the current node — this needs the general spatial path, so per-node neighbour lookups should use `grid_cell_id` (a 16 ly ball always fits inside one 500 ly cell plus at most adjacent cells at borders; in practice one cell) with a `LIMIT` on candidates per node.

**Cost function is where the product lives.** Pure hop-count gives geometrically shortest corridors through garbage systems. Weight edges by hop cost plus a penalty inversely related to the candidate's colonisation score (`ratings.score`, `slots`, confidence) so the search prefers corridors whose intermediate systems are *worth colonising* — every hop in the answer is itself a plannable colony. Return **2–3 route variants** (e.g. "fewest hops", "best systems", "balanced") by running with different weightings; that maps directly onto a UI pattern you already use (variant cards).

**Guards against blowup:**
- Cap search radius at, say, 500 ly and max hops ~30; beyond that return the partial frontier with an explicit diagnosis: *"no corridor within N hops — nearest reachable frontier system is X, gap of Y ly"* — an honest dead-end is evidence-language-correct and genuinely useful (it tells the player where the bubble's edge is).
- Bound the open set; in dense bubble space, prune neighbours to the best-M by score per expansion.
- Redis-cache by `(target, params)`; corridors change slowly (only when colonisation status changes along them).
- **Data-trust caveat surfaced in-product:** `is_colonised` freshness depends on import/EDDN recency, and this feature is the first one where the audit's mixed-`rating_version` problem (D3) leaks into *recommendations* — a corridor ranked on legacy-saturated scores is a bad recommendation wearing a confident face. **Part B's score-weighted variant should not ship before the R2 rebaseline closes.** Hop-count-only corridors can ship immediately.

**Endpoint:** `POST /api/route/colonisation-corridor` `{target_id64, origin_anchor_id64?, claim_range_ly?, max_hops?, weighting}` → `{variants: [{hops: [{id64, name, dist_from_prev, rating_summary, status}], total_hops, total_ly, diagnosis?}]}`. Server-side, stateless, no new tables.

## B.4 UI/UX

- **System Detail (Inspect):** a "Colonisation proximity" card — nearest anchor, distance, big in/out-of-range verdict in evidence language ("within claim range of HIP 12345 — 11.2 ly, *observed colonised 2026-07-01*"). Out of range → "Suggest corridor" action.
- **Map (Explore, secondary — per roadmap posture):** draw the returned corridor as a polyline of hops over the existing canvas; anchors solid, proposed hops dashed. The map *displays* the corridor; it doesn't compute it — keeps the Map in its roadmap-mandated supporting role.
- **Colony Planner handoff (Plan):** every intermediate hop gets "Plan this hop" → `#colony-planner/system/{id64}` — the corridor becomes a queue of planner projects. This is the Explore→Inspect→Plan spine, and it's also where Part A's Lane 2 closes the loop: as the player's journals show each hop's depot completing, the corridor updates from *proposed* to *observed*. That end-to-end arc — suggest corridor → plan each hop → observe your own construction progress against it — is a product no one else in this niche has.
- **FC Planner tie-in (cheap win):** "Send corridor to FC route" pre-loads hops as carrier waypoints — and quietly gives the orphaned FC lane (audit weakness #3) its reason to exist.

## B.5 Phasing

1. **B-1 (small):** partial index + nearest-colonised endpoint + System Detail card. No routing. Ships in days.
2. **B-2:** corridor A*, hop-count weighting only, map polyline, planner handoff.
3. **B-3 (after audit R2):** score-weighted variants, "best systems" corridor, FC handoff.
4. **B-4 (optional):** squadron mode — multi-target corridor trees; precomputed "frontier edge" map layer (which colonised systems are expansion-viable anchors).

---

## Shared sequencing against the audit

Neither feature should jump the audit's remediation queue, but they interleave cleanly: **B-1 is independent of everything** and is the cheapest visible win in this report. **A-1 depends on nothing critical** (staging-only writes) but its Lane 2 payoff is gated on accounts (§6), and A-2's canonical promotion should land only on top of the migration ledger (R1) — adding a new write lane to a schema with no migration ledger and no backups would be compounding exactly the risks the audit flagged. B-3's ranking quality is gated on R2. Net: **B-1 now → A-1 next → R1/R2 remediation → A-2/B-3 → accounts → A-3 Lane 2.**

— End of report. Game-rule constants (claim range, colonisation event names/payloads) carry explicit verification flags; everything about the codebase is derived from the pinned tree.
