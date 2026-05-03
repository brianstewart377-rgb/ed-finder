# ED Finder — Dev Change Log

A running record of changes made in the Replit dev environment, with reasoning.
Production app lives at ed-finder.app (Hetzner/Docker); this log tracks sandbox work.

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

## 2026-05-03 — Bug fix pass (full codebase audit)

**7. Galaxy search — `offset` not forwarded to `local_search.py` (line 869)**
- *Was*: When `local_search.py` was available (the normal path), the `body_dict` passed to `local_db_galaxy_search` omitted `offset`. Pagination requests always started from page 1 regardless of which page the user requested. The inline fallback path *did* include offset correctly.
- *Fix*: Added `'offset': req.offset` to the `body_dict`.
- *Reason*: Silent pagination bug — clicking "Next page" in galaxy economy search loaded the same results again.
