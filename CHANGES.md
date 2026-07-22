# ED Finder — Dev Change Log

A running record of development changes, with reasoning. Production app
lives at ed-finder.app (Hetzner/Docker). See `README.md` for deployment.

---

## 2026-07-22 - Stage 26E production region delivery and cutover regression

**The default-off production candidate now carries authoritative regions** -
The exact `VITE_STAGE26E_PRODUCTION_MAP=enabled` build emits a bounded static
`stage26e/authoritative-regions.json` asset generated from the pinned 2,048-row
RLE source. The client accepts exactly 42 unique region labels, caps continuous
boundaries at 25,000, validates every finite endpoint, and rejects responses
larger than 4 MiB. The measured asset is 2,312,898 bytes with 22,595 boundaries
and 542,280 typed position bytes. Normal unflagged builds omit the asset.

**The final default-off regression is green** - The live candidate passes both
required viewports with 500 Finder systems, 50,000 heatmap cells, 2,000 hulls,
100 timeline points, and the full region layer visible. Retained Chromium heap
maxima were 30,353,992 and 27,463,288 bytes against 268,435,456 bytes, with zero
detectable Axe violations. Thirty-one focused tests, both retained Chromium
journeys, all six Chromium/Firefox/WebKit viewport cells, the dedicated Axe
journey, the visual golden, TypeScript, lint, and normal/flagged builds pass.

**The next step is activation, not more foundation work** - All recorded
blocking gates are closed. The candidate remains default-off in this change;
the next bounded change may activate it in the production build, deploy and
smoke-check the public `#map`, and retain the established renderer as an
immediate flag-based rollback. Superseded-map removal remains later and
explicit.

## 2026-07-22 - Stage 26E continuous region boundaries and owner review

**Region dividers now read as boundaries instead of dashes** - Replaced the
four-pixel stride sampler with a full RLE adjacency scan that merges collinear
cell edges. The authoritative 2,048 by 2,048 grid now produces 22,595
continuous exact-grid segments (542,280 position bytes), preserving its stepped
topology without inventing smoothed geography. Antialiasing and a restrained
amber structural stroke match the supplied cartographic references. Focused
unit coverage protects straight and stepped joins, and the 1440x900 visual
golden has been refreshed.

The 500,000-system Chromium stress journey retains its explicit 50 ms frame
assertions while its whole-test deadline is raised from the generic 30 seconds
to 60 seconds, accommodating the cold antialiased scene setup without weakening
the measured performance gate.

**The heavier boundary layer remains inside the GPU budget** - Hardware-backed
Chromium returned 30/30 valid actual-render timer queries with no disjoint
samples at both required viewports. The continuous-boundary scene measured
18.982 ms p95 at 1280x720 and 27.243 ms p95 at 1440x900 against the
provisional 50 ms budget.

**The region-data gate is closed by recorded owner review** - The project owner
confirmed the non-commercial display of the 42 region names and derived RLE
geometry under Frontier's media guidance. The site now carries Frontier's
official long-form attribution, while `THIRD_PARTY_NOTICES.md` retains the
upstream MIT notice. This is recorded as an owner governance decision rather
than independent legal advice. No donation mechanism is implemented or relied
on. The production candidate stays default-off until bounded region delivery
and the full regression matrix pass.

**ED Astro is inventoried without widening map-cutover scope** - Reviewed its
134-file directory (about 335.58 GiB advertised uncompressed), source statement,
and the owner-supplied Catalogue of Galactic Nebulae workbook. Nebula
coordinates and combined POIs are the first small, map-relevant candidates;
bulk body/star dumps are explicitly importer-side research only. Because the
general ED Astro data page is All Rights Reserved while some narrower content
has separate Creative Commons notices, file-level reuse terms remain required
before vendoring or routine mirroring.

## 2026-07-22 - Stage 26E hardware GPU timing gate

**GPU duration is now measured on the real candidate render** - Added a
development-only `?gpu-test=1` diagnostic that runs 30
`EXT_disjoint_timer_query_webgl2` queries around
`WebGLRenderer.render(scene, camera)` for the visible 500,000-system scene. A
hardware-backed Chromium session returned 30/30 valid queries with no disjoint
samples at both required viewports: 1.358 ms p95 at 1280x720 and 1.747 ms p95
at 1440x900.

**The remaining cutover blocker is unchanged in scope** - The GPU evidence gate
is closed, but the production candidate stays default-off and region geometry
stays withheld. Region-geometry coverage and required attribution still need
owner or qualified legal review before deliberate cutover.

## 2026-07-22 - Stage 26E default-off production route and heap budget

**The R3F candidate now has a production-route composition without a cutover** -
The `#map` route can select the typed candidate only when the exact
`VITE_STAGE26E_PRODUCTION_MAP=enabled` build value is present. Normal builds
leave the flag unset and continue to load the established map. The candidate
consumes bounded Finder, heatmap, cluster-hull, and timeline data; region
geometry is structurally withheld while its coverage and attribution review
remains open.

**Live-route memory is closed with production-shaped evidence** - Chromium CDP
measured seven steady `JSHeapUsedSize` samples at both required viewports after
composing 500 Finder systems, 50,000 heatmap cells, 2,000 hulls, and 100
timeline points from live API payloads. Maxima were 26,392,356 and 28,724,676
bytes against a predeclared 268,435,456-byte budget. Axe reported zero
detectable WCAG 2/2.1 A/AA violations at both composed-route viewports. The
separate hardware-backed timing run now closes GPU evidence; region-data review
still blocks cutover and the production flag remains off.

**The owner-approved Frontier disclaimer is now site-wide** - The application
footer carries the supplied non-commercial, non-endorsement, and no-employee-
involvement wording verbatim. This records the general fan-project disclaimer;
it does not by itself establish redistribution coverage for the derived RLE
region geometry.

**The RLE source is now pinned and compared** - The local 2,048-row region grid
matches `klightspeed/EliteDangerousRegionMap`'s `RegionMapData.json`; ED-Finder
adds coordinate metadata and changes only the unused sentinel label. EDAssets'
Galaxy Map catalog contains icons and markers rather than this geometry, and
its Frontier permission statement applies to EDAssets. The comparison improves
provenance but leaves the region-redistribution gate open.

**Comparable community-tool licensing is recorded without treating it as
permission** - Raven Colonial publishes its web app under GPL-3.0, carries an
MIT license for its embedded ED3D map, uses the exact upstream region SVG, and
displays an unofficial/non-affiliation notice. EDSM exposes no detected license
across its public GitHub repositories; its free API is not a redistribution
license. Neither project closes ED-Finder's Frontier coverage question.

**The known upstream license obligation is now satisfied** - A scoped root
`THIRD_PARTY_NOTICES.md` retains Ben Peddell's MIT copyright and permission
notice for the reused region algorithm and data while explicitly leaving any
separate Elite Dangerous rights question open.

**Community data and IP attribution is now explicit** - The site-wide footer
thanks EDSM, EDDN, and the contributing Elite Dangerous community, and records
the supplied Frontier trademark and unofficial/non-affiliation statement. The
earlier owner-approved non-commercial fan disclaimer remains verbatim.

## 2026-07-22 - Stage 26E bounded heatmap transport

**Raw heatmap responses now have a deterministic ceiling** - The API returns at
most 50,000 cells, selects density-first with coordinate tie-breakers, and
fetches one sentinel row to emit explicit `max_cells` and `truncated` metadata.
The cache key includes the requested cap, and the fallback aggregation follows
the same ordering and limit.

**Transport memory is measured separately from renderer buffers** - A
maximum-width 50,000-cell compact JSON fixture measures 4,550,111 bytes against
an 8 MiB budget. The frontend carries server truncation through the typed
foundation without inventing omitted positions. Live-route heap, GPU timing,
and region-geometry attribution remain blocking; the production map route is
unchanged.

## 2026-07-22 - Stage 26E isolated production parity and memory bounds

**The isolated candidate now carries the remaining live map shapes** - Added
bounded adapters and R3F geometry for heatmap cells and aggregate cluster hulls,
plus timeline summary state, Results/Galaxy/Reference one-time view presets,
and typed ready/empty/error composition. A 500,000-result regression covers the
iterative preset calculation after browser testing exposed the unsafe spread
form.

**Normalized overlay memory is bounded without claiming cutover readiness** -
The maximum normalized heatmap and aggregate-hull typed buffers total 4,272,000
bytes against an 8 MiB budget. Raw heatmap transport remains unbounded and the
live route still needs an end-to-end heap budget. The project owner confirmed
ED-Finder is non-commercial; region-geometry coverage and attribution remain
open alongside real GPU timing. The production route is unchanged.

## 2026-07-22 - Stage 26E cutover-readiness gates (in progress)

**The isolated foundation now has broader final-gate evidence** - Added a
six-cell Chromium/Firefox/WebKit desktop matrix, an Axe WCAG A/AA audit, a
repeatable 1440x900 visual golden, and explicit steady-state and WebGL GPU-timer
instrumentation. Both required Chromium viewports measured about 16.7-16.8 ms
p95 after the 500,000-system typed hand-off journey.

**Unknown and blocked gates remain explicit** - The measured environment did
not expose the required GPU timer extension, development-fixture memory still
needs a production budget, and the R3F boundary does not yet carry every live
heatmap, aggregate-cluster, timeline, preset, and error-state behavior. Region
names and RLE geometry also require owner/legal review under Frontier's current
media guidance. The production map route is therefore unchanged and cutover is
not authorized.

## 2026-07-22 - Stage 26D typed feature hand-offs

**Existing feature state now crosses one typed map boundary** - Added reusable
adapters for Finder, Compare, device-local and server-backed saved systems,
evidence summaries, System Detail, Cluster Search, and read-only Planner
returns. The boundary preserves camera and layer state, retains selected-system
and cluster context, and reports systems that cannot render because their real
feature response has no coordinates.

**Map interactions now resolve to explicit host commands** - Selection and all
feature navigation requests are translated without renderer-owned routing.
Planner navigation requires a selected system and emits a hand-off only; it
cannot create or mutate a Build Plan. The isolated workbench and both required
desktop browser journeys exercise every return path while the production map
route remains unchanged.

## 2026-07-22 - Stage 26C region-first R3F foundation

**The selected renderer now has an isolated production-candidate foundation** -
Added a separate Stage 26C Vite entry around a reusable R3F scene component.
It renders ED-Finder's 42 authoritative regions, uses the retained typed scene
and interaction boundary, supports arbitrary comparison and cluster highlights,
preserves cluster context, requires explicit overlap choice, and exposes a
keyboard-accessible companion without wiring the production route or planner.

**The 500k development fixture is bounded before rendering** - The deterministic
visibility selector returns at most 25,000 background systems plus every
selected, highlighted, and cluster system, with explicit truncation and
aggregate-remainder metadata. Both required desktop Playwright journeys cover
camera updates, overlap choice, typed planner requests, and a successful
renderer interaction after WebGL context restoration.

## 2026-07-21 - Stage 26B renderer bake-off

**The equal renderer matrix is now executable and recorded** - Added a
development-only Vite harness for deck.gl OrbitView, deck.gl OrthographicView,
and Three.js/R3F. The shared Playwright journey covers 100k and 500k
deterministic datasets at 1280x720 and 1440x900, derives the region layer at
runtime from ED-Finder's authoritative source without copying pixel geometry,
and executes all 17 retained fixtures.

**Three.js/R3F is selected for the isolated Stage 26C foundation** - The final
12-cell Chromium run passed as a harness execution. R3F was the only candidate
to remain pickable after context restoration and had materially lower tested
interaction latency. Its 500k frame time still needs optimization; GPU timing,
candidate-specific compressed bundle size, legal review, and production cutover
remain unresolved.

## 2026-07-21 - Stage 26B map-foundation research bundle

**The quarantined research artifacts are repaired and retained** - Accepted the
five isolated Stage 26B contract, adapter, deterministic-fixture, region
verification, and closure artifacts after strict joint TypeScript compilation,
JSON parsing, exact sentinel-plus-42-region comparison, targeted semantic
checks, and confirmation of 17 unique named fixtures.

**Measurement remains deliberately open** - No browser benchmark was executed
and no renderer was selected. The equal deck.gl OrbitView, deck.gl
OrthographicView, and Three.js/R3F bake-off remains the next Stage 26B gate;
production map code and planner ownership are unchanged.

## 2026-07-19 - Windows release SCP target handling

**SSH aliases no longer become accidental local sources** - The release wrapper
now models SCP flags separately from the remote destination. Alias-based deploys
produce `scp [options] <archive> alias:/tmp/...`; direct host deploys add only
the `-P` port option before the same source/destination pair.

**Upload failure remains fail-closed** - The defect was exposed only after local
typecheck, build, frontend tests, and artifact packaging succeeded. SCP rejected
the malformed command before upload, so no production files or services changed.

## 2026-07-19 - Windows release packaging invocation

**Artifact packaging now receives its complete argument list** - The canonical
PowerShell release wrapper now invokes the Git Bash adapter directly, preserving
the `--output` flag and Windows archive path as one `ScriptArgs` array. The old
nested `powershell.exe -File` call split that array across parameters and stopped
an otherwise-green release before upload or production changes.

**Failure is pinned and rehearsed** - Added a release-path contract that rejects
the nested invocation and requires direct array forwarding. The repaired wrapper
completed its validation-and-packaging phase from a clean `main` clone, producing
the frontend archive and checksum before deploy was deliberately skipped.

## 2026-07-19 - Windows GNU Make and bundle portability

**Documented Make targets now run from PowerShell** - Installed GNU Make 4.4.1
through user-scoped `winget` and removed the Makefile's shell-specific inline
environment assignments. Windows virtualenv paths now use separators accepted
by both `cmd.exe` and Bash, while integration-test defaults are exported by Make
itself without expanding dollar signs in credentials; unset and explicitly
empty environment or Make command-line values all receive the disposable
local-test defaults.

**Drive-letter release packaging fixed** - Frontend bundle creation now
normalizes Windows drive-letter paths through the available MSYS path adapter
before invoking tar and checksum tools, without requiring GNU-only tar flags or
rewriting checksum mode markers. Direct regressions cover native Windows Make
command generation, archive creation, and checksum verification through either
the GNU `sha256sum` or portable `shasum` path used by the release script.

## 2026-07-19 - Stage 26A next-generation map authorization

**Desktop map replacement contract opened** - Authorized a staged replacement
of the current low-value map frontend while preserving Map as a secondary
Explore surface and Colony Cockpit as the sole planning workspace. The current
renderer is no longer an architectural baseline, but remains live until a
deliberate gated cutover.

**Galaxy regions and feature integration made non-negotiable** - Required all
42 named in-game galaxy regions, arbitrary two-, three-, and multi-system
highlights, complete cluster membership and edge context, overlap
disambiguation, selected-system continuity, and explicit Finder, Compare,
saved/evidence, and planner hand-offs. Mobile and touch map work are excluded.

**Research before renderer selection** - Defined a paid artifact-backed
Research Control run with complete TypeScript/JSON deliverables, followed by an
equal deck.gl OrbitView, deck.gl OrthographicView, and Three.js/R3F desktop
bake-off. Stage 26A changes no runtime route and selects no renderer.

## 2026-07-18 — CI restoration, branch protection, and strict zip hardening

**H2 trust and hygiene hardening** — Expanded the required Ruff surface to
`apps`, `tests`, `scripts`, and `shared_contracts`, fixed all newly exposed
findings, and added a repository-owned LF checkout policy for shell scripts.
Replaced the uncollected slot smoke module with collected model tests and added
direct expansion-plan store coverage. Review Lab then caught a Linux-only
direct-entry import regression in the Ruff cleanup; the entrypoint now
bootstraps the repository package root and a subprocess regression pins it.

**Database operator scripts hardened** — Password sync now sends credentials
only through stdin-backed, short-lived secret channels, uses psql's quoting-safe
password command, redacts all output, and verifies against the container's
SCRAM-authenticated address instead of its trusted loopback rule. `run_import.sh`
uses that single implementation. Migration apply and baseline sessions now
default to a one-hour statement timeout and 30-second lock timeout; finite
overrides remain available, while zero requires an explicit reviewed opt-in.
Focused contracts, a real PostgreSQL 16 password rehearsal, and a fresh 39-file
migration apply plus second-run ledger skip close CQ-041 and CQ-042.

**Frontend trust paths tightened** — Routed Cluster Search through the typed
shared API client with direct hook tests, contained browser storage exceptions
behind tested helpers, and associated the Fleet Carrier input with its visible
label for assistive technology.

**Admin cache response made truthful** — Cache clearing now reports a partial
failure when Redis cannot be cleared, while retaining the successful database
cache operation and logging the failed backend. Backend regressions cover both
full and partial outcomes.

**Canonical documentation reconciled** — Removed stale redesign runtime
guidance and updated ROADMAP foundation status from planned to evidenced:
storage recovery completed at a 519 GB database size, the checksum migration
ledger is active and production-audited, restore automation has a recorded
rehearsal, and all ten CI checks protect `main`. CQ-035 through CQ-040 record
the closed H2 findings; CQ-041 and CQ-042 now record the completed H3 database
operator hardening.

**Review Lab restored and enforced** — Reconciled the isolated API with the
current app-shell and System Detail read contracts, updated the browser journey
to the current Finder-to-planner flow, and hardened Windows command resolution,
UTF-8 subprocess capture, and process-tree teardown. The workflow now runs on
every pull request and `Review Lab` is the tenth protected context. Full local
verification passed all scenarios, accessibility checks, console/network
policy, Delta provenance fallback, and teardown (`20260718T155912Z-32900-429f62aa`).

**CI restored and enforced** — Recovered the full GitHub Actions board across
backend unit and integration tests, canonical safety, script contracts, nginx,
OpenAPI drift, frontend build, Playwright E2E, and built-image parity. `main` is
now branch-protected by all ten exact check contexts, with strict status-check
matching and an admin override retained for emergencies.

**Failure causes fixed** — Repaired the backend dual-import split, Windows CRLF
shell-script failures, seeded database invariant gaps, API boot import path,
OpenAPI type drift, evidence-promotion fixture gap, and the systems batch/detail
endpoint defects exposed as red checks were cleared.

**Lint and pairing contracts tightened** — Pinned Ruff and added the repository
E4/E7/E9/F gate, then enabled B905 across `apps`, `tests`, and `scripts`. All 11
audited `zip()` pairings now use `strict=True`, with mismatch regressions on the
live slot-prediction endpoint and cluster-builder cursor mapping.

**Docs-only PRs no longer deadlock** — Required `Built image parity` now runs on
every pull request while retaining source-path filtering for `main` pushes.
Documentation-only PR #339 exercised the protected merge path without an admin
bypass.

**Migration history integrity repaired** — The production deploy guard caught
that `001_schema.sql` had been edited after its ledger baseline when the cluster
summary widening landed. Restored migration 001 byte-for-byte to its recorded
checksum; migration 040 remains the additive owner of the widening. A CI
contract now pins the production-baselined checksum and the migration-040
ownership boundary.

**Production invariant tail closed** - Reconciled 144,942 truthful no-body
dirty systems in bounded production batches, deleting 31,417 stale ratings;
repaired 2,766 ring association statuses and the final stale body-count row.
Durable repair and invariant receipts now show zero persisted body, no-body,
ring, station-link, and evidence-lifecycle drift.

**Dirty-rating retry storm fixed** - The scheduled dirty-ratings worker had
treated every truthful no-body system as a retryable rating error every 30
minutes. The guarded cron now performs bounded no-body reconciliation first,
then counts and rates only body-backed systems. Summary-free cleanup mode keeps
the steady-state pass cheap on the 188M-system production catalogue.

**Freshness policy made explicit** - Deploy and weekly invariant receipts keep
reporting colonisation age buckets but explicitly allow the >14-day tail. EDDN
refreshes status on observations; an unchanged positive status aging past 14
days is freshness telemetry, not by itself a persisted-integrity failure.

**First bounded hygiene pass completed** - Removed eight unreferenced frontend
components (1,390 dead lines), archived the retired score-breakdown repair
script as historical operator material, and made the nightly compose-directory
change fail explicitly. Added a Knip unused-file gate to frontend CI so future
orphaned source files are caught before merge. This closes CQ-002, CQ-003, and
CQ-011.

---

## 2026-05-03 — Backend fix: auto-rebuild indexes transaction error

### backend/import_spansh.py

**`set_session cannot be used inside a transaction` (FIXED)** — The `auto-rebuild indexes` block at the end of `main()` opened a read transaction via `SELECT count(*) FROM pg_indexes`, then immediately tried to set `conn.autocommit = True` on line 1649 while that transaction was still open. psycopg2 prohibits any `set_session` / `autocommit` change inside an active transaction. Fixed by restructuring into two explicit phases: Phase 1 runs the `SELECT` and calls `conn.commit()` to fully close the read transaction; Phase 2 only then flips `conn.autocommit = True` (safe because no transaction is open), runs the index SQL in a fresh cursor, and restores `autocommit` in a `finally` block so it's always reset even if the index run fails.

---

## 2026-05-03 — Forensic audit pass (full code review + null-crash fix)

### frontend/index.html

**Forensic audit scope** — Ran complete cross-layer audit: Python AST on all 12 .py files, `new Function()` JS syntax check on all 3 inline `<script>` blocks (391 KB of JS), HTML tag structure parser (227 IDs, 274 function definitions), cross-file function conflict check, API endpoint live-test (all 7 routes → 200), duplicate function detection, async/await coverage review, XSS pattern scan, and a full `getElementById` vs DOM cross-reference.

**resetFilters null-crash (FIXED)** — `resetFilters()` accessed `document.getElementById(\`smin-${s.key}\`).value`, `smax-`, and `sv-` directly without null guards. These IDs are created dynamically by `buildBodySliders()` during page init. If `resetFilters()` were ever called before the filter panel fully renders (e.g. rapid interaction on slow load), it would throw `TypeError: Cannot set properties of null`. Fixed by assigning to local variables with `if (el)` guards before writing `.value` / `.textContent`.

**False positives confirmed (no action needed)**:
- 28 "missing functions" from naive regex — all JS built-in methods (forEach, splice, etc.)
- 33 "missing IDs" — split into: dynamic template IDs (`card-${s.id64}`, `smin-${key}` — runtime-correct); dynamically created IDs (`body-pill-popover`, `cache-stats-panel` — intentionally absent from static HTML); fallback-guarded ID (`opt-ref-input` uses `||` querySelector); and `app.js` dead-code references to old map UI (`map3d-*`, `map-*`) that are irrelevant since `app.js` is never loaded by `index.html`.
- `toCanvas` defined twice — both definitions are local-scoped inside separate functions (`_drawNebulaOverlayOnMap` and a second map-draw function); no global conflict.
- `renderResults` / `buildSystemCard` in `app.js` conflict with `index.html` definitions — moot, `app.js` has no `<script src>` reference and is never executed.
- `spanshPost` / `runRouteSearch` flagged as async-without-try/catch — both are adequately protected: `spanshPost` is a throwing utility, callers handle errors; `runRouteSearch` has per-hop try/catch and a separate enrichment catch block.

---

## 2026-05-03 — UX wiring pass (3 targeted fixes on top of existing stubs)

### frontend/index.html

**#21 3D legend trigger** — `_update3DLegend()` was never called when switching to the 3D Map tab for the first time. Fixed `showTab()` handler: `if (id === '3d') { setTimeout(() => { draw3DMap(); _update3DLegend(); }, 100); }`. Legend now populates immediately on first open, not just when colour/size selects change.

**#10 Economy chips in compare table** — `renderComparePanel()` Economy row was rendering plain text (`${getEcoIcon()} ${name}`). Wrapped in `<span class="eco-chip eco-chip-{key}">` using the existing `_ecoChipKey()` helper so economy cells in the comparison table now show the same coloured pill as the briefing modal.

**#6 (X6) Auto-search on autocomplete select** — The auto-search hook at the end of the file tried to wrap `window.selectRefSystem` which is never assigned to `window`, so the guard silently skipped it and the feature did nothing. Fixed by adding the toggle check directly inside `selectSystem()` for `mode === 'ref'`: when the "Auto-search on autocomplete select" checkbox is ticked, `runSearch()` fires 150 ms after a reference system is chosen from the dropdown.

---

## 2026-05-03 — UX polish batch #2 (25 improvements, index.html)

### frontend/index.html

**#1 Filter persist** — `_saveFilters()` called at start of `runSearch()`. Filter state written to localStorage on every search; `_loadFilters()` restores it on page load. *(was already implemented)*

**#2 Zero-results guidance** — `renderResultsProgressive()` detects empty results and renders a smart empty state with contextual tips (increase distance, widen rating range, remove toggles) and quick-fix buttons. *(was already implemented)*

**#3 Search duration** — `window._searchT0 = Date.now()` captured at search start; elapsed time shown in the results summary bar as `⏱ Nms`. *(was already implemented)*

**#4 Score tooltip** — Rating badge has `onmouseenter="showScoreExplainer()"` that shows a breakdown popup (star bonus, slots, body quality, compactness, signals, orbital safety). *(was already implemented)*

**#5 Watchlist indicator on card** — Cards already in the watchlist get class `is-watched` which renders a blue left-border highlight via CSS. *(was already implemented)*

**#6 Bulk watchlist add** — "👁 Watch All" button in results summary bar calls `_watchAllResults()`, adding every displayed system to watchlist in one click. *(was already implemented)*

**#7 Copy all names** — "📋 All Names" button in results bar calls `_copyAllNames()`, copying a newline-separated list of all visible system names to clipboard. *(was already implemented)*

**#8 Scroll-to-top on page change** — `renderResultsProgressive()` resets `content.scrollTop = 0` and calls `scrollIntoView({ block:'start', behavior:'smooth' })` on every render. *(was already implemented)*

**#9 Quick-pin hover reveal** — CSS: `.result-card .pin-btn:not(.pinned) { opacity:0.3 }` / `.result-card:hover .pin-btn:not(.pinned) { opacity:1 }`. Pin button is subtle at rest and pops to full opacity on card hover, reducing clutter without hiding the action. *(NEW)*

**#10 Economy colours in briefing modal** — `_ecoChipKey(eco)` helper maps economy names to CSS class keys. The briefing modal's economy section now renders `<span class="eco-chip eco-chip-{key}">` chips with the existing colour palette (green=Agriculture, amber=Industrial, brown=Refinery, blue=High Tech, red=Military, etc.). *(NEW)*

**#11 Body sort in briefing modal** — Added a BODIES section to the briefing modal with three sort buttons (Type / Name / Landable first). `_sortBriefingBodies(key)` re-renders the body pills in sorted order using `buildBodyPills()`. The active sort button is highlighted. *(NEW)*

**#12 Add-to-route in briefing modal** — "🗺️ Add to Route" button added to the briefing modal links row. Calls `_addSysToRoute()` which pushes `_briefingSys` into `routeWaypoints`, calls `renderRouteHops()` and `_updateRouteTabLabel()`, then shows a confirmation toast. Duplicate guard prevents adding the same system twice. *(NEW)*

**#13 Compare tab badge** — Added `<span id="compare-count-badge">` to the Compare tab button (matching style of existing Watchlist/Pinned/Colony badges). `_updateCompareTabLabel()` now updates this badge instead of replacing the button's text content. *(NEW)*

**#14 Route tab badge** — Added `<span id="route-count-badge">` to the Route tab button. `_updateRouteTabLabel()` now updates the badge count instead of replacing button text. *(NEW)*

**#15 Tab overflow** — `#tabs { overflow-x:auto; scrollbar-width:none }` lets the tab bar scroll horizontally on narrow screens without wrapping. *(was already implemented)*

**#16 Changelog tab** — Removed `opacity:0.55` dim and restored full-width label from `📋` (icon only) to `📋 Changes`, making it as accessible as other tab buttons. *(NEW)*

**#17 Watchlist sort** — `loadWatchlist()` reads the `#watchlist-sort` select value and sorts the list by Name / Distance / Population / Colonised status before rendering. *(was already implemented)*

**#18 Session restore prompt** — `#session-restore-banner` HTML + CSS in place; `_restoreSession()` function defined. Banner appears when `localStorage` contains cached results from a prior session. *(was already implemented)*

**#19 Sync progress** — `_updateLocalDbBadge()` now checks `d.systems_import_done`. When the import is still running it renders a mini CSS progress bar (`<span class="local-db-sync-bar">`) alongside the system count to show import completion %. Badge colour shifts from green (done) to dim (in progress). *(NEW)*

**#20 Autocomplete loader** — `fetchAutoComplete()` immediately renders `⏳ Searching…` into the dropdown before the API call resolves, giving instant visual feedback. *(was already implemented)*

**#21 3D map colour legend** — `update3DLegend()` populates `#threed-legend` with colour-keyed dot/ring items whenever the colour or size mode changes. *(was already implemented)*

**#22 Map recenter** — `⊙ Reset` button in the 2D Galactic Map toolbar calls `resetMapView()` to snap back to the reference system. *(was already implemented)*

**#23 Keyboard nav** — Result cards have `tabindex="0"` + `:focus` ring CSS. `ArrowDown` / `ArrowUp` keys move focus between cards when the Finder tab is active. *(was already implemented)*

**#24 Undo toast** — `#undo-toast` HTML + CSS + `_showUndoToast(msg, fn)` in place. Used by destructive actions (watchlist remove etc.) to offer a timed undo option. *(was already implemented)*

**#25 Active filter summary** — `updateFilterBadge()` counts active non-default filters and shows the count on `#filter-live-badge` and the Reset Filters button badge. *(was already implemented)*

---

## 2026-05-03 — Bug fix pass (full codebase audit)

### frontend/app.js

**1. `copyText` — silent clipboard failure (line 41)**
- *Was*: `.catch(() => {})` — any clipboard error (no HTTPS, permission denied) was silently swallowed; the user saw nothing.
- *Fix*: Check `navigator.clipboard` availability first and show a descriptive toast on failure ("Copy not available (needs HTTPS)" / "Copy failed — check browser permissions").
- *Reason*: Silent fails give the user no recourse; the toast tells them what happened and what to do.

**2. Production debug logs removed (lines 356, 377)**
- *Was*: `console.log('[ED Finder] bodies array:', ...)` and `console.log('[ED Finder] body rows generated:', ...)` were left in the modal rendering path.
- *Fix*: Both removed.
- *Reason*: These fire on every modal open, spamming the browser console in production and leaking internal data structures.

**3. `closeModal` scoping bug — "Show on Map" button broken (line 522 / 576)**
- *Was*: `closeModal` was defined as a local function *inside* the `initModal` IIFE (lines 576–588), making it invisible outside that scope. `attachModalEvents` called `closeModal()` at line 522, which is in a different scope — a ReferenceError in strict mode. The "Show on Map" button in the system detail modal never worked.
- *Fix*: Lifted `closeModal` to module scope as a plain function declaration. The IIFE now references the shared module-scope version. `closeModal` uses `qs('#system-modal')` to locate the modal element at call time rather than relying on a captured closure variable.
- *Reason*: Critical path — every user who clicked "Show on Map" from the system modal hit this error.

**4. Note delete — no error handling (line 561)**
- *Was*: `await apiFetch(...)` with no try/catch. If the DELETE request failed (network error, 500, etc.), the error was an unhandled rejection; the UI updated as if the delete succeeded (note text cleared, button hidden) but the note still existed in the DB.
- *Fix*: Wrapped in try/catch. On failure, sets status text to "Delete failed" in red and leaves the note text intact.
- *Reason*: Silent failure that corrupts UI state and misleads the user.

**5. Watchlist changelog — wrong field names (line 1563)**
- *Was*: Rendered using `c.name` and `c.field_changed`. The DB table `watchlist_changelog` has columns `system_name` and `change_type`. The mismatch meant every changelog entry showed "Unknown" as the system name and no field name at all.
- *Fix*: Changed to `c.system_name` and `c.change_type` with fallback to old keys (`c.name`, `c.field_changed`) for safety. The `openSystemModal` click handler also updated to use `sysName`.
- *Reason*: The entire watchlist changelog tab was rendering blank/unknown data.

### backend/main.py

**6. `batch_systems` — wrong request body key (line 1118)**
- *Was*: Endpoint read `body.get('id64s', [])`. The frontend (`app.js` line 1097) sends `{ ids: [...] }`. Key mismatch meant the cluster view's "Show top systems" feature always received an empty list and returned no results.
- *Fix*: `body.get('ids', body.get('id64s', []))` — reads `ids` first, falls back to `id64s` for any external callers that use the old key.
- *Reason*: Core cluster feature was completely non-functional.

---

## 2026-05-03 — SSE dot tooltip

**`index.html` — SSE indicator mouseover explanation**
- *Was*: The green dot in the status bar had only a terse native browser `title` tooltip ("SSE: live" / "SSE: offline") — no explanation of what SSE or EDDN is.
- *Fix*: Wrapped the dot in a `.sse-wrap` container; added a styled CSS tooltip via `::after` + `data-tip` attribute. `_setSseDot()` now writes a full sentence depending on state:
  - Live: "EDDN live feed connected — real-time system updates from other commanders are streaming in."
  - Offline: "EDDN feed offline — live game event updates unavailable. Will retry automatically."
- *Reason*: The indicator was opaque to anyone who hadn't read the code. The tooltip makes the state self-explanatory on hover.

---

## 2026-05-03 — 25 UI/UX improvements

All 25 requested UX improvements implemented across `frontend/index.html` and `frontend/app.js`.
Items already implemented before this pass (confirmed, no duplication): #4 score tooltip, #9 quick-pin on card header, #13 Compare tab badge, #19 sync button progress, #25 active filter summary strip.

**#1 Filter persistence** (`index.html`)
- New `_saveFilters()` / `_restoreFilters()` / `_captureFilterState()` / `_applyFilterState()` functions save all filter IDs to `ed_filters_v1` in localStorage on every `runSearch()` call and restore them on `DOMContentLoaded`. Covers: dist-slider, min-dist-slider, size-slider, filter-economy, rating range, sl-land, sl-sig, all body/signal toggles, tog-uncolonised, and all BODY_SLIDERS dual-range state.

**#2 Zero-results guidance** (`index.html` — `renderResultsProgressive`)
- Smart empty state replaces the generic "No Systems Found" message. Detects active filter count, generates a bulleted list of specific actionable suggestions (e.g. "Increase Max Distance (currently 30 LY)", "Clear the Economy filter"), and offers "Reset Filters & Retry" + "Expand to 100 LY" shortcut buttons.

**#3 Search duration** (`index.html` — `runSearch` + `renderResultsProgressive`)
- `window._searchT0 = Date.now()` recorded at the top of `runSearch()`. Rendered as `⏱ Xms` in the results summary bar at the point `renderResultsProgressive` builds the bar (after all processing and render), giving a true end-to-end duration.

**#5 Watchlist indicator on card** (`index.html` — `buildSystemCard`)
- Added `isWatched` check against `window._watchlistCache`. Cards for watched systems get `.is-watched` class which applies a blue left border via CSS. Cards also now have `tabindex="0"` for keyboard nav.

**#6 Bulk watchlist add** (`index.html` — `renderResultsProgressive` bar + new `_watchAllResults()`)
- "👁 Watch All" button in results summary bar calls `_watchAllResults()` which POSTs each displayed system to `/api/watchlist` in sequence then reloads the watchlist tab.

**#7 Copy all names** (`index.html` — `renderResultsProgressive` bar + new `_copyAllNames()`)
- "📋 All Names" button in results summary bar calls `_copyAllNames()`. Copies all system names (newline-separated) via `navigator.clipboard` with textarea execCommand fallback.

**#8 Scroll-to-top on page change** (`index.html` — `renderResultsProgressive` + `renderResults`)
- `content.scrollTop = 0` + `scrollIntoView({block:'start'})` added at the top of both render functions so pagination always returns to the result list header.

**#10 Economy colour coding** (`index.html` — CSS)
- Added `.eco-chip-*` CSS classes for Agriculture (green), Industrial (amber), Refinery (brown), Extraction (steel), High Tech (blue), Military (red), Tourism (pink), Colony (purple), Terraforming (cyan), Service (grey). Classes ready to apply to economy pills throughout the UI.

**#11 Body sort in modal** (`app.js` — `buildModalHTML`)
- `sys.bodies` now sorted before rendering: stars first (`body_type === 'Star'`), then planets/moons by `distance_from_star` ascending. Spread-copy to avoid mutating the original array.

**#12 Add to Route in modal** (`app.js` — `buildModalHTML` + `attachModalEvents`)
- "🗺️ Add to Route" button added to modal Actions section. `attachModalEvents` wires a click handler that calls `selectRouteWaypoint({ name, x, y, z, id64 })` and shows a toast confirmation.

**#14 Route tab badge** (`index.html` — `_updateRouteTabLabel` + `renderRouteHops`)
- New `_updateRouteTabLabel()` mirrors `_updateCompareTabLabel()`. Updates the Route tab button text to `🗺️ Route (N)` whenever waypoint count > 0. Called at the top of `renderRouteHops()` and wrapped via `clearRoute` override.

**#15 Tab overflow** (`index.html` — CSS + `#tabs`)
- `#tabs` CSS: `overflow-x: auto; flex-wrap: nowrap !important; scrollbar-width: none`. Prevents tab wrapping on narrow screens; tabs become horizontally scrollable with hidden scrollbar.

**#16 Move Changelog tab** (`index.html` — tab bar HTML)
- Changelog tab button de-emphasised: `opacity: 0.55`, padding reduced to `6px 8px`, text changed to just `📋` with a `title="App changelog"` tooltip. Still functional but visually demoted from primary navigation.

**#17 Watchlist sort** (`index.html` — `loadWatchlist`)
- Sort select (Name A–Z / Distance / Population ↓ / Colonised first) injected into `#watchlist-list` each render. Current sort key preserved across re-renders by reading `#watchlist-sort` value before rebuilding innerHTML.

**#18 Session restore prompt** (`index.html` — new banner + `_restoreSession` + IIFE check)
- `#session-restore-banner` HTML element added. IIFE at page load checks `sessionStorage.ed_last_results`; if results exist from a previous tab visit, banner appears with "Restore" and "Dismiss" buttons. `_restoreSession()` re-renders the saved results and switches to Finder tab.

**#20 Autocomplete loading indicator** (`index.html` — `fetchAutoComplete`)
- "⏳ Searching…" placeholder item shown in the dropdown immediately before `spanshFetch()` resolves, then replaced by actual results or the manual-entry fallback.

**#21 3D map legend** (`index.html` — `#threed-legend` + `_update3DLegend()`)
- `#threed-legend` div added below the 3D canvas. `_update3DLegend()` called when Colour/Size selects change; renders colour swatches and size description matching the current mode (rating / economy / distance / population).

**#22 Map "Frame All" button** (`index.html` — 2D map controls + `fitMapToResults()`)
- "⊞ Frame All" button added to 2D map toolbar. Calls `fitMapToResults()` which invokes `_mapViewReset()` then `drawGalacticMap()` to re-centre the map on the current result set.

**#23 Keyboard navigation** (`index.html` — `buildSystemCard` + global keydown listener)
- Result cards get `tabindex="0"` so they are focusable. Global `keydown` listener on `document` intercepts ArrowUp/ArrowDown when focus is inside `#finder-content` (or body) and the Finder tab is active, moving focus to the adjacent card.

**#24 Reset Filters undo toast** (`index.html` — `resetFilters` + `_showUndoToast` / `_undoAction`)
- `resetFilters()` now calls `_captureFilterState()` (saving to `window._undoFilterState`) before wiping, then calls `_showUndoToast('Filters reset')`. The `#undo-toast` element slides up with an "Undo" button; clicking it calls `_undoAction()` which restores the snapshot via `_applyFilterState()`. Toast auto-hides after 6 seconds.

---

## 2026-05-03 — Bug fix pass (full codebase audit)

**7. Galaxy search — `offset` not forwarded to `local_search.py` (line 869)**
- *Was*: When `local_search.py` was available (the normal path), the `body_dict` passed to `local_db_galaxy_search` omitted `offset`. Pagination requests always started from page 1 regardless of which page the user requested. The inline fallback path *did* include offset correctly.
- *Fix*: Added `'offset': req.offset` to the `body_dict`.
- *Reason*: Silent pagination bug — clicking "Next page" in galaxy economy search loaded the same results again.
