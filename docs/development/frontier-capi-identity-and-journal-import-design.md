# Frontier CAPI identity + journal-import fix — implementation design

**Status:** current implementation design, **not** programme or product authority.
**Date:** 2026-09-15
**Target:** `apps/api/` (Frontier auth) and `apps/web/` (account/import UI), Svelte 5/SvelteKit 2 + FastAPI/asyncpg.
**Scope:** Piece #1 of a three-part map-and-identity programme (agreed order: identity → density-swirl map → visual polish).

This design obeys `CLAUDE.md`, the authority chain, and the existing
[accounts / journal UI plan](accounts-journal-ui-plan.md) and
[journal-commander-contributions](journal-commander-contributions.md). Where it
conflicts with those, they win. It does not authorize production deployment,
production DB writes from a coding task, or a journal-import automation scheduler
beyond the existing named EDDN exception.

## Problem (verified)

Frontier OAuth2 developer access is now approved with scope **`auth` + CAPI**.
Owner-observed behaviour on **production** (`nb79a3d.mevnode.com`): Frontier
sign-in succeeds and a verified commander is linked, but the account displays the
placeholder `Verified commander F…` instead of the real in-game CMDR name, and
the "Import journals" button does not complete an import.

Root causes, established by code trace (not speculation):

1. **No real name at login.** `build_frontier_authorize_url` requests
   `scope=auth` only and the callback never calls Frontier CAPI `/profile`
   (`apps/api/src/routers/auth.py:157-165, 213-270`). The commander name parser
   `identity_from_frontier_payloads(..., profile=...)` (`auth.py:195-201`) exists
   but is always called with `profile=None`, so `commander_name` is `None` and
   `associate_verified_commander` stores the placeholder `Verified commander
   F<fid>` (`apps/api/src/edfinder_api/journal/commanders.py:63, 87-98`). A test
   locks this in: `tests/test_frontier_auth_v3.py` asserts `commander_name: None`
   and that no `companion.orerve.net` call is made.
2. **Journal import is client-side broken, not a pipeline failure.** The import
   chain (button → module Web Worker → shared parser → `POST
   /api/v1/journal/verified-imports` → per-FID transactional write) is fully
   wired and tested (`apps/web/src/lib/components/JournalAccountPanel.svelte`,
   `apps/web/src/lib/journal/{parse,import-worker}.ts`,
   `apps/api/src/routers/v3_journal.py`). Because prod already has a valid
   verified commander with the correct FID, the backend would accept an import —
   and a *successful* import would overwrite the placeholder name from the
   journal's `Commander.Name` (`ownership.py:57-59`). The name is still a
   placeholder, so the import is not completing on the client.

The FID link itself is sound: Frontier `customer_id` → `F<customer_id>`
(`commanders.py:22-28`) matches the `FID` in journal `Commander`/`LoadGame`
events (`ownership.py:50-65`); this is the documented EDMC-referenced mapping.

## Goals

- After Frontier login, show the **real** in-game commander name.
- Make the "Import journals" flow actually import (fix the reproduced
  client-side defect).
- Confirm the **already-implemented** Commander History travel heatmap lights up
  with real cells once an import succeeds.

## Non-goals (this piece)

- Multi-commander partitioning / resumable chunked import protocol (that is the
  later workstream in `accounts-journal-ui-plan.md`).
- Publishing journal observations to the shared galaxy catalogue.
- Storing any CAPI data beyond the commander name; storing CAPI tokens.
- Any change to the density/real-star map (that is piece #2).

## Design

### 1. Real commander name via CAPI `/profile`

Confirmed Frontier facts (verified against EDCD/EDMarketConnector `companion.py`):

- authorize `https://auth.frontierstore.net/auth`, scope **`auth capi`**
  (space-separated, URL-encoded `auth%20capi`);
- token `https://auth.frontierstore.net/token`;
- profile `https://companion.orerve.net/profile`, `commander.name` holds the
  in-game name; requires a `capi`-scoped access token and a `User-Agent`
  (ed-finder already has `settings.frontier_user_agent`).

Changes:

1. `build_frontier_authorize_url` — change scope from `auth` to `auth capi`.
   Keep PKCE/state/redirect as-is. **Risk to verify:** ed-finder currently sends
   `audience=all`; EDMC uses `audience=frontier,steam,epic`. Keep `all` if CAPI
   works with it; otherwise adopt the explicit audience — validated with a real
   login, since `audience` changes can affect the working `auth` flow.
2. `_exchange_frontier_code` — after the existing `/decode` and `/me` calls, add
   one authorized `GET https://companion.orerve.net/profile` using the same
   access token and the Frontier user-agent. Pass the parsed JSON as `profile=`
   into `identity_from_frontier_payloads`, which already extracts
   `profile.commander.name`. The access/refresh tokens remain function-local and
   are **never** persisted or returned (unchanged from the existing contract at
   `auth.py:268-269`).
3. `associate_verified_commander` — allow a real CAPI name to **replace** the
   placeholder. Today it only ever writes `Verified commander F<fid>`
   (`commanders.py:87-98`); update so a non-empty real name wins, while a missing
   name still falls back to the placeholder. Real CAPI name and real journal name
   are both acceptable; latest verified write wins.

**Fail-open rule (load-bearing):** CAPI `/profile` may be slow, rate-limited, or
return `204 No Content` while Frontier's servers sync. If `/profile` fails or is
empty, **login must still succeed** with the placeholder / journal-derived name.
Fetching a nicer name must never break authentication.

The `/api/v1/auth/frontier/link` flow shares `build_frontier_authorize_url`, so
it inherits CAPI consent consistently.

### 2. Journal-import UI fix (diagnose-first)

This defect is reproduced before it is fixed (systematic debugging), by running
`apps/web` locally and driving the `/account` import flow with Playwright while
watching the browser console and network. Ranked candidates from the trace, to
confirm or eliminate:

1. **Module Web Worker fails to load in the built bundle.** `parse.ts` uses
   `new Worker(new URL('./import-worker.ts', import.meta.url), {type:'module'})`.
   This can work under the Vite dev server yet fail on prod's nginx (MIME type,
   missing/renamed chunk). The prod build output and served worker chunk are
   inspected, not only the dev server. `worker.onerror` currently rejects with a
   generic message; surface the real error to the user.
2. **File-picker `accept=".log,.jsonl"` hides journals.** Elite journals are
   `Journal.<timestamp>.NN.log`, so `.log` should match; confirm on Windows and
   relax the filter if it blocks selection.
3. **Disabled-until-file-selected reads as "dead".** `disabled={busy ||
   !selected?.length}`; improve empty/disabled affordance.

The fix is whatever the reproduction proves, plus low-risk hardening: clearer
disabled/empty/error states and no silently-swallowed worker error. If (and only
if) the defect is confirmed to be a prod-build/serving issue not reproducible in
dev, the fix extends to the build/serve config with its own evidence.

### 3. Travel heatmap — verification only

The Commander History heatmap is already implemented and wired: a "Show my
travel heatmap" toggle in `ExploreWorkspace.svelte` fetches
`/api/exploration/viewport-visits` and renders per-cell heat instances
(`commander-history.ts`, `babylon/adapter.ts`). No new build here — this piece
**verifies** the heatmap renders real cells after a successful import.

### Data flow

```text
Login:  /frontier/login (scope=auth capi) → Frontier consent → /frontier/callback
        → /token → /decode + /me → /profile (companion) [fail-open]
        → identity_from_frontier_payloads(decoded, account, profile)
        → associate_verified_commander (real name replaces placeholder)
        → session; GET /auth/session returns real commander_name → AccountControls

Import: /account (rendered only when authenticated) → select .log files
        → module worker → shared parser → POST /journal/verified-imports
        → per-FID transactional write; commander name updated from journal
        → account queries refetch; travel heatmap toggle shows real cells
```

## Testing & validation

- **Update the contract test** `tests/test_frontier_auth_v3.py` to assert the new
  contract: authorize scope includes `capi`; `/profile` is called; a real name is
  stored; and — critically — login still succeeds when `/profile` returns
  `204`/`5xx` (fail-open), with the token never persisted. (Per `CLAUDE.md`: when
  a contract intentionally changes, update the test to assert the new contract.)
- **New mocked backend tests** for `/profile` success, empty/`204`, and error
  paths, and for placeholder→real-name replacement in
  `associate_verified_commander`.
- **Frontend:** extend `journal-account-panel.test.ts` and
  `cypress/e2e/account-journal.cy.ts` to cover the reproduced import failure mode
  and its fix; assert worker errors are surfaced.
- **Local validation gates** for touched surfaces: `make state-check`; backend
  focused tests; `apps/web` → `pnpm install --frozen-lockfile`, `pnpm check`,
  `pnpm lint`, `pnpm format:check`, `pnpm test`, `pnpm build`; Playwright/Cypress
  for the import journey. Visual validation for the account-panel/name UI change.
- **One real check by the owner** after deploy: a real Frontier login on prod
  shows the actual CMDR name (mocks cannot prove Frontier's live `/profile`
  shape), and a real journal import populates the travel heatmap.

## Boundaries & safety

- Branch → PR; `main` is protected; no production DB reads/writes from this task.
- CAPI tokens stay function-local, never persisted or logged; only
  `commander.name` is used. No secrets in code, args, or logs.
- Same-origin/CSRF, rate-limit, and PKCE protections on auth/import routes stay
  intact. Ownership is always derived server-side from the session; a client
  cannot choose an account or FID.
- Rendering/UX change → visual validation per the visual-changes contract.

## Acceptance criteria

1. A real Frontier login stores and displays the real in-game commander name;
   the placeholder appears only when CAPI genuinely returns no name.
2. Login succeeds even when CAPI `/profile` fails (fail-open), and no CAPI token
   is persisted.
3. The reproduced journal-import defect is fixed; selecting real `.log` journals
   and clicking Import produces a receipt with `events_inserted > 0`, and worker
   errors are surfaced rather than silent.
4. After an import, the "Show my travel heatmap" toggle renders real cells.
5. Updated/added tests pass; all required CI gates for the change are green.

## Open items / risks

- **`audience` value** for CAPI (`all` vs `frontier,steam,epic`) — verify with a
  real login without regressing the working `auth` flow.
- **Worker-in-prod-build** reproducibility — the defect may be environment/build
  specific and not visible under the dev server.
- **CAPI `204`/latency** — handled by fail-open; the real name may first appear
  on a subsequent login or after a journal import.

## References

- `apps/api/src/routers/auth.py`,
  `apps/api/src/edfinder_api/journal/{commanders,ownership}.py`,
  `apps/api/src/routers/v3_journal.py`
- `apps/web/src/lib/components/JournalAccountPanel.svelte`,
  `apps/web/src/lib/journal/{parse,import-worker}.ts`,
  `apps/web/src/lib/features/explore/ExploreWorkspace.svelte`,
  `apps/web/src/lib/spatial/commander-history.ts`
- `docs/development/accounts-journal-ui-plan.md`,
  `docs/development/journal-commander-contributions.md`
- EDCD/EDMarketConnector `companion.py` (Frontier OAuth2/CAPI reference)
