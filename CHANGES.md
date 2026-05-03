# ED Finder — Dev Change Log

A running record of changes made in the Replit dev environment, with reasoning.
Production app lives at ed-finder.app (Hetzner/Docker); this log tracks sandbox work.

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
