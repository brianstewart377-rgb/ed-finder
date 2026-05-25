# Distance Display Contract

## Rules

1. **null / undefined / NaN distance → null (unknown)**: Render as `—` or "Distance unknown". Never render as `0.00 LY`.
2. **Zero distance → null by default**: Older backend galaxy-wide searches emitted `dist_expr = "0.0"` when no reference coordinate was set. This fake zero must not reach the UI as `0.00 LY`. The backend now projects `NULL::float`; `_safe_distance()` still converts any legacy `0.0` to `None`, and the frontend `formatDistance()` returns `null` for zero unless `allowZero: true`.
3. **Valid zero only with explicit reference**: `0.00 LY` should only display when the user is viewing a system that is genuinely at the reference point (e.g. the reference system itself). Use `formatDistance(0, { allowZero: true })` only in that case.
4. **Valid positive distance**: Render as `X.XX LY` with two decimal places.
5. **Unknown coordinates are not origin coordinates**: `x/y/z = NULL`, partial coordinates, and non-Sol `(0,0,0)` all mean the location is unknown. Render coordinates as "Unknown" and do not calculate distance-from-Sol.

## Reference point

- The default reference system is **Sol** (0, 0, 0).
- Users can change the reference via the `RefSystemPicker` in the search form.
- The search request sends `reference_coords: { x, y, z }` to the backend.
- The backend computes distance as Euclidean 3D distance from the reference.
- Galaxy-wide searches (`galaxy_wide: true`) skip distance filtering and project `NULL::float` for distance.
- Distance-bounded searches require complete `reference_coords`; the backend no longer silently substitutes Sol when the request omits coordinates.

## Backend fix (Stage 17N.2)

**Root cause**: `local_search.py::_build_system_record` had `"distance": float(row.get("dist", 0) or 0)` which coerced `None` and `0` to `float(0.0)`. Galaxy-wide searches always emitted `0.0` from the SQL expression, making every result show `0.00 LY`.

**Fix**: Added `_safe_distance()` helper that returns `None` for `None`, non-finite, and `<= 0` distance values. Only valid positive distances pass through as `round(f, 2)`.

## Coordinate fix (Stage 17N.2c)

**Root cause**: `systems.x/y/z` were `NOT NULL DEFAULT 0`, and import/list display paths used `?? 0`/`or 0` fallbacks. Missing coordinates were therefore indistinguishable from Sol and could be rendered as real origin coordinates.

**Fix**: `sql/019_nullable_coords.sql` makes `systems.x/y/z` nullable and converts existing non-Sol `(0,0,0)` rows to `NULL`. Backend response helpers treat non-Sol origin triples as unknown before and after that migration, and frontend coordinate formatters do the same for cached/persisted records.

Stage 17N.2c hardening also removed the remaining low-risk Spansh populated-system importer fallback that coerced missing coordinates to `0`. Import paths must now pass `NULL` when any coordinate axis is missing or invalid. EDDN live updates only write coordinates when a complete `StarPos` triple is present.

Production verification and recovery steps live in `docs/operations/stage17n2c-data-trust-runbook.md`.

## Frontend fix (Stage 17N.2)

**Root cause**: `ResultCard` used `system.distance != null ? system.distance.toFixed(2) : '?'` — any non-null value including `0` would show as `0.00`. The `'?'` fallback was also not consistent with the rest of the UI.

**Fix**: Added `formatDistance()` in `lib/format.ts`. All distance display sites (ResultCard, SystemTable, MapTab, CompareTab) now use `formatDistance(distance) ?? '—'`.

## Display sites

| Component | Location | Fallback |
|---|---|---|
| `ResultCard` | Search result header | `— LY` |
| `SystemTable` | Watchlist / pinned / cluster table | `—` |
| `MapTab.SelectionPanel` | Map selection detail | Row omitted |
| `CompareTab` | Side-by-side comparison | `—` |
