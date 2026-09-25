# V3 watchlist, pins and comparison

## Existing contracts

`apps/api/src/routers/watchlist.py` uses a watchlist **sync key as its credential**; these routes do not depend on Frontier account authentication. Keys must match `[A-Za-z0-9_-]{16,128}`. The UI preserves this contract. Its query cache includes both the current account ID (or null) and watchlist key, with a 30-second freshness window and five-minute garbage collection. No previous-scope placeholder data is used. Mutations invalidate only their captured scope.

| Method | Path                                        | Request                                                              | Response                                |
| ------ | ------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------- |
| GET    | `/api/v2/watchlist/{sync_key}`              | None                                                                 | `{sync_key, watchlist: WatchlistRow[]}` |
| POST   | `/api/v2/watchlist/{sync_key}/{id64}`       | No body                                                              | `{ok: true, sync_key}`                  |
| DELETE | `/api/v2/watchlist/{sync_key}/{id64}`       | No body                                                              | `{ok: true}`                            |
| PATCH  | `/api/v2/watchlist/{sync_key}/{id64}/alert` | `{min_development_score?: number \| null, economy?: string \| null}` | `{ok: true}`                            |
| GET    | `/api/v2/watchlist/{sync_key}/changes`      | None                                                                 | `{changes: WatchlistChange[]}`          |

`WatchlistRow` contains database fields `id`, `system_id64`, `name`, `x`, `y`, `z`, `population`, `is_colonised`, `alert_min_score`, `alert_economy`, `added_at`, `last_checked_at`, `last_status`, and `sync_key`. The list joins nullable `score`, `economy_suggestion`, `alert_min_development_score` (alias of `alert_min_score`), `primary_archetype`, `secondary_archetype`, `archetype_score`, `buildability_score`, and `purity_score`. Rows are newest first. The facade projects the fields needed by the UI and preserves decimal-string Id64 values without numeric rounding.

`WatchlistChange` contains `id`, `system_id64`, `system_name`, `change_type`, nullable `old_value`/`new_value`, and `detected_at`; the endpoint returns the latest 100 changes. Reads are limited to 60/minute; writes to 20/minute. Adding/removing is idempotent; adding an unknown system returns 404. Invalid keys return 400/422.

Legacy GET `/api/watchlist`, POST/DELETE `/api/watchlist/{id64}`, PATCH `/api/watchlist/{id64}/alert`, and GET `/api/watchlist/changes` or `/api/watchlist/changelog` return 410 with a migration hint.

The existing generated SDK already supplies every operation, but watchlist responses are `unknown` because the backend declares no response models. `apps/web/src/lib/api/client.ts` now validates and types the established GET/POST/DELETE shapes and delegates to those generated operations. No OpenAPI regeneration, backend change, flat `lib/api.ts`, route change, or renderer change is required. Alert editing and the changes feed remain outside this UI task, matching the V2 watchlist panel.

## UI and persistence

Explore/Finder results provide Pin, Watch and Compare buttons, with pressed states and named accessible actions. Saved systems and comparison panels sit below the Finder/map and have jump links near the top.

- Pins use the existing `pins` persisted store and `pinnedCodec` (`ed_pinned`). Full snapshots are retained, newest pins first. The panel supports sorting, removal, confirmed clear, JSON export, Inspect, Spansh/Inara, Watch and Compare.
- Comparison uses the existing `compare` store and `compareCodec` (`ed_compare_v2`). Up to six full snapshots survive search changes and reloads. The panel supports empty and single-system guidance, removal, confirmed clear, CSV export and Inspect links. Best values have text labels and typography, with no feature-specific colours. Missing facts stay unavailable.
- Watches use the existing `syncKey` store (`ed_sync_key`) and the backend through TanStack Svelte Query. The list supports loading, empty, populated and retry states; refresh, sorting, pinning, comparison and removal. Local pins and comparisons remain usable when watchlist requests fail.
- `myWork` is unchanged; this task does not add a My Work workflow or new persistence mechanism.

V2 reference files: `frontend/src/features/watchlist/WatchlistTab.tsx`, `useWatchlist.ts`; `frontend/src/features/pinned/PinnedTab.tsx`, `pinnedEntry.ts`, `frontend/src/store/pinnedStore.ts`; `frontend/src/features/compare/CompareTab.tsx`, `useCompare.ts`, and `frontend/src/app/compareSnapshot.ts`.

Pinned and watched list columns mirror V2's shared `SystemTable`, including coordinates/Sol distance, development, archetype/economy, timestamps, population for watches, and reference distance/external links for pins. Comparison includes development, primary/secondary archetypes, confidence, buildability, purity, estimated slots, primary economy, reference distance, population, status, main star, security, allegiance, ELW, water worlds, ammonia, terraformable/landable bodies, biological/geological signals, and external links. Snapshot values reflect when selected.

## Owner decision

Confirm whether a future backend task should bind watchlists to Frontier accounts and provide watchlist-key management in V3. The current backend is key-scoped; changing accounts alone does not change which list that key accesses. The new UI describes that ownership honestly. Existing browser pins/comparison stay local, as in V2. V3 has no Settings route, so this feature does not link to one or introduce a settings workflow.

## Verification

Tests were introduced before implementation and observed failing for the missing facade/UI/actions. Focused Vitest suites cover empty/populated panels, persistence actions, the comparison cap and metrics, CSV escaping, exact large Id64 values, generated transport boundaries, mutation failures, cache isolation and accessible DOM. On this Windows environment Vitest's default fork workers timed out during startup; focused runs use `--pool=threads --maxWorkers=1` without changing project configuration.

Validation completed:

- `pnpm check`: zero errors and warnings.
- `pnpm test src/lib/features/explore src/lib/api/watchlist-api.test.ts src/lib/api/query.test.ts src/lib/api/client.test.ts src/lib/api/id64-facade.test.ts src/lib/persistence/storage.test.ts --pool=threads --maxWorkers=1`: 10 files, 107 tests passed.
- Final watchlist component rerun after the captured-key and retry regressions: 16 tests passed. Comparison coverage includes an axe accessibility check.
- `python -m pytest tests/test_svelte_generated_client_boundary.py tests/test_svelte_web_foundation_contract.py -q`: 19 passed (existing Python plugin deprecation warnings).
- `pnpm exec prettier --write` on all changed TypeScript, Svelte and Markdown files; `git diff --check` passed.

No production access or push was used.
