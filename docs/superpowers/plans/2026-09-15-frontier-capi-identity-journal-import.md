# Frontier CAPI Identity + Journal-Import Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After Frontier login show the real in-game commander name (via CAPI `/profile`), fix the client-side journal-import defect, and confirm the existing travel heatmap populates from imported visits.

**Architecture:** Backend adds one authorized CAPI `/profile` call to the existing Frontier OAuth callback and feeds the already-present name parser, with a strict fail-open rule so login never breaks. A small `associate_verified_commander` change lets a real name replace the `Verified commander F<fid>` placeholder. The journal-import fix is diagnose-first: reproduce with the existing Cypress lane + a production build inspection, then apply the minimal fix plus safe hardening.

**Tech Stack:** FastAPI + asyncpg (CPython 3.14, uv), httpx for Frontier calls; Svelte 5/SvelteKit 2 + TypeScript + Vite (Node 24, pnpm), Vitest unit tests, Cypress E2E; Babylon for the heatmap (unchanged).

## Global Constraints

- Runtime: exact CPython 3.14; API deps via uv 0.11.33 + frozen `apps/api/uv.lock`; async Postgres via asyncpg.
- Frontend: Svelte 5 / SvelteKit 2 / TypeScript, Node 24, pnpm 11.25.0; `apps/web/pnpm-lock.yaml` authoritative; API access only via `apps/web/src/lib/api/` facade (no flat `src/lib/api.ts`).
- `main` is protected — all work on branch `feat/frontier-capi-identity-journal-import` → PR.
- Frontier OAuth scope becomes `auth capi`; profile host `https://companion.orerve.net/profile`; `commander.name` holds the in-game name.
- **Fail-open:** if CAPI `/profile` fails, is empty, or returns `204`, login MUST still succeed with the placeholder/journal name.
- CAPI access/refresh tokens stay function-local — never persisted, returned, or logged. Only `commander.name` is used.
- No production DB reads/writes from this task. No secrets in code, args, or logs.
- E2E regression coverage goes in the **Cypress** lane (`apps/web/cypress/e2e/`), not a parallel Playwright suite. Playwright MCP is for interactive diagnosis only.
- Ownership is always derived server-side from the session; a client never chooses an account or FID.

---

## File Structure

- `apps/api/src/routers/auth.py` — add CAPI scope + `/profile` fetch (fail-open) in `_exchange_frontier_code`; pass real name into `associate_verified_commander`.
- `apps/api/src/edfinder_api/journal/commanders.py` — accept an optional real `commander_name` and let it replace the placeholder.
- `tests/test_frontier_auth_v3.py` — update the contract that currently locks in `commander_name: None` / no CAPI call.
- `tests/test_frontier_auth.py` — update the `scope=['auth']` assertion to `auth capi`.
- `tests/test_journal_commander_association.py` — add real-name-replacement cases.
- `apps/web/src/lib/journal/parse.ts` — surface the real worker error instead of a generic message.
- `apps/web/src/lib/components/JournalAccountPanel.svelte` — accept-filter + disabled/empty/error affordance (fix per diagnosis).
- `apps/web/src/lib/journal/import-worker.ts` — (only if diagnosis implicates it).
- `apps/web/src/lib/components/journal-account-panel.test.ts` — unit coverage for surfaced errors / affordance.
- `apps/web/cypress/e2e/account-journal.cy.ts` — regression for the reproduced failure mode.
- `docs/development/frontier-capi-identity-and-journal-import-design.md` — append the recorded import root cause (from Task 5).

---

### Task 1: Confirm CAPI request shape (scope + audience) and record the decision

**Files:**
- Modify: `docs/development/frontier-capi-identity-and-journal-import-design.md` (fill the `audience` open item)

**Interfaces:**
- Produces: a recorded decision — `SCOPE = 'auth capi'` and the chosen `audience` value — consumed by Task 2.

- [ ] **Step 1: Read the current authorize builder**

Run: `sed -n '150,166p' apps/api/src/routers/auth.py`
Confirm current `scope: 'auth'` and `audience: 'all'`.

- [ ] **Step 2: Cross-check against the EDMC reference already cited by the code**

Confirmed values (EDCD/EDMarketConnector `companion.py`): authorize `https://auth.frontierstore.net/auth`, `scope=auth capi`, `audience=frontier,steam,epic`, token `/token`, profile `https://companion.orerve.net/profile`.

Decision rule: keep `audience='all'` (works today for `auth`) as the first attempt; only switch to `frontier,steam,epic` if the real-login validation in Task 8 shows CAPI rejects `all`. Record this decision in the design doc's "Open items / risks" section.

- [ ] **Step 3: Commit the recorded decision**

```bash
git add docs/development/frontier-capi-identity-and-journal-import-design.md
git commit -m "docs(auth): record CAPI scope=auth capi and audience decision"
```

---

### Task 2: Backend — fetch CAPI `/profile` in the OAuth callback (fail-open)

**Files:**
- Modify: `apps/api/src/routers/auth.py` (`build_frontier_authorize_url` ~152-165; `_exchange_frontier_code` ~213-270)
- Test: `tests/test_frontier_auth_v3.py`

**Interfaces:**
- Consumes: existing `identity_from_frontier_payloads(decoded, account, profile=None)` (already parses `profile.commander.name`), `settings.frontier_capi_base_url`, `settings.frontier_user_agent`.
- Produces: `_exchange_frontier_code` returns a `FrontierIdentity` dump whose `commander_name` is the real name when `/profile` succeeds, else `None`; authorize URL scope is `auth capi`.

- [ ] **Step 1: Write failing tests for scope + profile fetch + fail-open**

Add to `tests/test_frontier_auth_v3.py` (mirror the existing mocked-httpx style used in that file):

```python
def test_authorize_url_requests_capi_scope():
    url = build_frontier_authorize_url(state="s", code_challenge="c")
    from urllib.parse import parse_qs, urlsplit
    scope = parse_qs(urlsplit(url).query)["scope"][0]
    assert scope == "auth capi"


@pytest.mark.anyio
async def test_exchange_populates_commander_name_from_capi(monkeypatch):
    # Arrange mocked /token, /decode, /me as the existing tests do, then a
    # /profile returning {"commander": {"name": "Jameson"}}.
    identity = await _run_exchange_with_mocked_frontier(
        monkeypatch,
        profile={"commander": {"name": "Jameson"}},
    )
    assert identity["commander_name"] == "Jameson"


@pytest.mark.anyio
async def test_exchange_fails_open_when_profile_unavailable(monkeypatch):
    identity = await _run_exchange_with_mocked_frontier(
        monkeypatch,
        profile_status=204,   # game syncing
    )
    assert identity["commander_name"] is None  # login still succeeds
    identity = await _run_exchange_with_mocked_frontier(
        monkeypatch,
        profile_status=500,   # CAPI error
    )
    assert identity["commander_name"] is None
```

Add a small `_run_exchange_with_mocked_frontier(...)` helper next to the existing Frontier test fixtures that stubs the four endpoints (`/token`, `/decode`, `/me`, `/profile`) and calls `_exchange_frontier_code("code", "verifier")`. Reuse whatever transport-mocking the file already uses (e.g. `respx`/`httpx.MockTransport`); do not invent a new mocking framework.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest ../../tests/test_frontier_auth_v3.py -k "capi or fails_open or capi_scope" -v`
Expected: FAIL (scope still `auth`; no `/profile` call).

- [ ] **Step 3: Change the authorize scope**

In `build_frontier_authorize_url`, replace the scope line:

```python
        # Identity login requests CAPI so the callback can read the real
        # in-game commander name from companion /profile. The companion token
        # is used once for the name and never persisted.
        'scope': 'auth capi',
```

- [ ] **Step 4: Fetch `/profile` fail-open and pass it to the parser**

In `_exchange_frontier_code`, after `account = account_response.json()` and the `isinstance` validation, before `return`, add:

```python
    profile: Optional[dict[str, Any]] = None
    try:
        async with httpx.AsyncClient(headers=headers, timeout=12.0) as capi:
            profile_response = await capi.get(
                f"{settings.frontier_capi_base_url.rstrip('/')}/profile",
                headers=auth_headers,
            )
            if profile_response.status_code == 200:
                parsed = profile_response.json()
                if isinstance(parsed, dict):
                    profile = parsed
            # 204/4xx/5xx: fail open — login proceeds with no CAPI name.
    except (httpx.HTTPError, ValueError):
        profile = None

    return identity_from_frontier_payloads(decoded, account, profile).model_dump()
```

(`auth_headers` and `headers` are already in scope from the token/decode block. `profile` never leaves this function except as the parsed commander name.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest ../../tests/test_frontier_auth_v3.py -k "capi or fails_open or capi_scope" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/routers/auth.py tests/test_frontier_auth_v3.py
git commit -m "feat(auth): read real commander name from Frontier CAPI /profile (fail-open)"
```

---

### Task 3: Backend — let a real name replace the commander placeholder

**Files:**
- Modify: `apps/api/src/edfinder_api/journal/commanders.py` (`associate_verified_commander` ~31-107)
- Modify: `apps/api/src/routers/auth.py` (call site ~465-469)
- Test: `tests/test_journal_commander_association.py`

**Interfaces:**
- Consumes: `identity.commander_name` from Task 2.
- Produces: `associate_verified_commander(conn, *, account_id, issuer, fid, verified_at, commander_name: str | None = None)` — a non-empty `commander_name` is stored on insert and replaces an existing placeholder; a `None`/empty name preserves current behaviour (placeholder).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_journal_commander_association.py` (reuse its existing DB fixture):

```python
@pytest.mark.anyio
async def test_associate_stores_real_name_on_insert(db_conn):
    cid = await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER,
        fid="F123", verified_at=NOW, commander_name="Jameson",
    )
    name = await db_conn.fetchval(
        "SELECT commander_name FROM v3_identity.commander WHERE commander_id=$1", cid,
    )
    assert name == "Jameson"


@pytest.mark.anyio
async def test_associate_replaces_placeholder_with_real_name(db_conn):
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid="F123", verified_at=NOW,
    )  # placeholder created
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid="F123",
        verified_at=NOW, commander_name="Jameson",
    )
    name = await db_conn.fetchval(
        "SELECT commander_name FROM v3_identity.commander"
        " WHERE commander_id IN (SELECT commander_id FROM"
        " v3_identity.commander_external_identity WHERE subject='F123')",
    )
    assert name == "Jameson"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest ../../tests/test_journal_commander_association.py -k "real_name or placeholder" -v`
Expected: FAIL (`commander_name` kwarg not accepted).

- [ ] **Step 3: Add the parameter and name logic**

Change the signature:

```python
async def associate_verified_commander(
    conn: Any,
    *,
    account_id: uuid.UUID,
    issuer: str,
    fid: str,
    verified_at: datetime,
    commander_name: str | None = None,
) -> uuid.UUID:
```

Compute the stored name once near the top of the body (after the validation guard):

```python
    clean_name = commander_name.strip()[:128] if commander_name and commander_name.strip() else None
    placeholder = f'Verified commander {fid}'
    stored_name = clean_name or placeholder
```

In the insert branch (`row is None`) replace `f'Verified commander {fid}'` with `stored_name`.

In the existing-row branch, replace the placeholder-only update block (currently `commanders.py:87-98`) with:

```python
        existing = row['commander_name']
        is_placeholder = (
            not existing
            or existing == 'Verified commander'
            or existing.startswith('Verified commander ')
        )
        if clean_name and existing != clean_name:
            await conn.execute(
                '''UPDATE v3_identity.commander
                   SET commander_name = $2, updated_at = transaction_timestamp()
                 WHERE commander_id = $1''',
                commander_id, clean_name,
            )
        elif is_placeholder and existing != placeholder:
            await conn.execute(
                '''UPDATE v3_identity.commander
                   SET commander_name = $2, updated_at = transaction_timestamp()
                 WHERE commander_id = $1''',
                commander_id, placeholder,
            )
```

- [ ] **Step 4: Pass the name from the OAuth callback**

In `apps/api/src/routers/auth.py` `_upsert_account_and_session`, update the call:

```python
            if identity.journal_fid:
                await associate_verified_commander(
                    conn, account_id=account_id, issuer=identity.issuer,
                    fid=identity.journal_fid, verified_at=now,
                    commander_name=identity.commander_name,
                )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest ../../tests/test_journal_commander_association.py -k "real_name or placeholder" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/edfinder_api/journal/commanders.py apps/api/src/routers/auth.py tests/test_journal_commander_association.py
git commit -m "feat(auth): replace commander placeholder with real CAPI name"
```

---

### Task 4: Backend — update the contract tests that locked in the old behaviour

**Files:**
- Modify: `tests/test_frontier_auth_v3.py` (the assertions requiring `commander_name: None` and no `companion.orerve.net` call)
- Modify: `tests/test_frontier_auth.py` (the `'scope': ['auth']` assertion)

**Interfaces:**
- Consumes: the new contract from Tasks 2–3.
- Produces: a green contract suite asserting the CAPI-enabled behaviour.

- [ ] **Step 1: Find the stale assertions**

Run: `grep -rn "companion.orerve.net\|commander_name.*None\|'scope'.*auth\|scope.*\['auth'\]" tests/test_frontier_auth.py tests/test_frontier_auth_v3.py`

- [ ] **Step 2: Update `test_frontier_auth.py` scope assertion**

Change the expected authorize `scope` from `['auth']` to `['auth capi']` (match however the test parses the query string).

- [ ] **Step 3: Update `test_frontier_auth_v3.py`**

Replace the old "no CAPI, name is None" assertions with the new contract: the callback DOES call `companion.orerve.net/profile`; when `/profile` returns a name the session/user `commander_name` is that name; when `/profile` fails the login still succeeds and `commander_name` falls back to the placeholder/`None`. Keep any assertion that the CAPI token is never written to Postgres or returned to the client.

- [ ] **Step 4: Run the full Frontier auth suites**

Run: `cd apps/api && uv run pytest ../../tests/test_frontier_auth.py ../../tests/test_frontier_auth_v3.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_frontier_auth.py tests/test_frontier_auth_v3.py
git commit -m "test(auth): assert new CAPI commander-name contract"
```

---

### Task 5: Frontend — reproduce and diagnose the journal-import failure

**Files:**
- Modify: `docs/development/frontier-capi-identity-and-journal-import-design.md` (append the recorded root cause under "Open items / risks")

**Interfaces:**
- Produces: a written root-cause statement consumed by Task 6, and a known-good/known-bad signal from the Cypress lane + production build.

- [ ] **Step 1: Install and run the existing Cypress account-journal E2E locally**

Run:
```bash
cd apps/web && pnpm install --frozen-lockfile
pnpm exec cypress run --spec cypress/e2e/account-journal.cy.ts
```
This spec seeds a real Frontier identity fixture + session cookie and drives select-files → Import. Record: does it PASS (import completes, `events_inserted > 0`) or FAIL, and if it fails, the exact assertion/step and any console error.

- [ ] **Step 2: Build the production bundle and inspect the worker chunk**

Run:
```bash
cd apps/web && pnpm build
# locate the emitted import-worker chunk and confirm it exists and is a module
ls -la build/**/*import-worker* 2>/dev/null || find build -name '*worker*'
```
Record whether the `import-worker` chunk is emitted and how it is referenced. This distinguishes a dev-only pass from a prod-build/serving failure (the leading hypothesis, since prod shows the symptom but the flow is fully wired).

- [ ] **Step 3: (Optional) Interactive confirmation with Playwright MCP**

If the Cypress signal is ambiguous, use Playwright MCP to load `/account` (dev server, seeded session), click Import with a sample `.log`, and read `browser_console_messages` + `browser_network_requests` to capture the real failure (worker load error, 4xx/415 on the worker chunk, or no request at all).

- [ ] **Step 4: Record the root cause**

Append a short "Import root cause (2026-09-15)" note to the design doc stating exactly which candidate is confirmed: (1) module-worker load/serving, (2) `accept` filter, (3) disabled-affordance, or another finding. This drives Task 6.

- [ ] **Step 5: Commit the finding**

```bash
git add docs/development/frontier-capi-identity-and-journal-import-design.md
git commit -m "docs(journal): record reproduced journal-import root cause"
```

---

### Task 6: Frontend — fix the import defect + safe hardening

**Files:**
- Modify: `apps/web/src/lib/journal/parse.ts` (surface the real worker error)
- Modify: `apps/web/src/lib/components/JournalAccountPanel.svelte` (accept filter + affordance; the confirmed root-cause fix)
- Modify (only if Task 5 implicates it): `apps/web/src/lib/journal/import-worker.ts`, or the Vite worker/build config
- Test: `apps/web/src/lib/components/journal-account-panel.test.ts`

**Interfaces:**
- Consumes: the recorded root cause from Task 5.
- Produces: an import flow that completes for valid `.log` journals and surfaces real errors.

- [ ] **Step 1: Write a failing unit test for surfaced worker errors**

In `journal-account-panel.test.ts`, add a case where `parseJournals` rejects with a specific message and assert the panel's `role="alert"` shows that message (not a generic one):

```ts
it('surfaces the real worker error text', async () => {
  // mock parseJournals to reject with new Error('Worker failed to load: 415')
  // select a file, click Import, then:
  expect(screen.getByRole('alert')).toHaveTextContent('Worker failed to load: 415');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm test -- journal-account-panel`
Expected: FAIL (generic message today).

- [ ] **Step 3: Surface the real error in `parse.ts`**

In `parse.ts`, change the `worker.onerror` handler to reject with the event's actual message when present:

```ts
  worker.onerror = (event) => {
    const detail = (event && (event as ErrorEvent).message) || 'Journal parsing failed';
    reject(new Error(detail));
  };
```

- [ ] **Step 4: Apply the confirmed root-cause fix**

Per Task 5's recorded cause, apply the minimal fix:
- **If module-worker serving:** correct the Vite worker emission / nginx MIME so the `type:'module'` worker chunk is served as JS (record the exact config change and why).
- **If `accept` filter:** in `JournalAccountPanel.svelte` broaden the input to also accept extension-less/`.log` variants, e.g. `accept=".log,.jsonl,.txt,application/json,text/plain"`, keeping the worker's own size/type validation as the real guard.
- **If affordance only:** add helper text and an explicit empty/disabled explanation next to the button so it no longer reads as dead.

- [ ] **Step 5: Run unit tests**

Run: `cd apps/web && pnpm test -- journal-account-panel`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/journal/parse.ts apps/web/src/lib/components/JournalAccountPanel.svelte apps/web/src/lib/components/journal-account-panel.test.ts
git commit -m "fix(journal): repair journal import flow and surface worker errors"
```

---

### Task 7: Frontend — Cypress regression for the reproduced failure

**Files:**
- Modify: `apps/web/cypress/e2e/account-journal.cy.ts`

**Interfaces:**
- Consumes: the fix from Task 6.
- Produces: a Cypress assertion that would have caught the reported failure.

- [ ] **Step 1: Add a regression case**

Extend `account-journal.cy.ts` so it asserts the specific failure mode is gone — e.g. that selecting a valid `.log` enables Import, that clicking it issues `POST /api/v1/journal/verified-imports` and renders a receipt with `events_inserted > 0`, and that an injected worker error renders in `role="alert"` rather than silently doing nothing.

- [ ] **Step 2: Run the spec**

Run: `cd apps/web && pnpm exec cypress run --spec cypress/e2e/account-journal.cy.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/cypress/e2e/account-journal.cy.ts
git commit -m "test(journal): regression for import completion and error surfacing"
```

---

### Task 8: Full validation, heatmap verification, and PR

**Files:** none (validation + PR)

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a green branch and an open PR.

- [ ] **Step 1: Repo state + backend gates**

Run:
```bash
make state-check
cd apps/api && uv run pytest ../../tests/test_frontier_auth.py ../../tests/test_frontier_auth_v3.py ../../tests/test_journal_commander_association.py -v
```
Expected: PASS.

- [ ] **Step 2: Frontend gates**

Run:
```bash
cd apps/web && pnpm check && pnpm lint && pnpm format:check && pnpm test && pnpm build
```
Expected: PASS.

- [ ] **Step 3: Travel-heatmap verification (fixture/seed)**

Using the seeded Cypress session with imported visits, load Explore, toggle "Show my travel heatmap", and confirm real cells render. Capture a screenshot into the change's evidence (visual-changes contract). If a heatmap-specific E2E does not exist, add a minimal assertion that the toggle produces a non-empty `/api/exploration/viewport-visits` render.

- [ ] **Step 4: Self-review the diff**

Run: `git diff origin/main...HEAD` and run the `code-review` skill over the diff (adversarial pass) before pushing. Fix anything it surfaces.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/frontier-capi-identity-journal-import
gh pr create --fill --base main
```
PR body must note: the CAPI scope change (`auth capi`), the fail-open guarantee, that no CAPI token is persisted, the import root cause + fix, and the required owner real-login check post-merge.

- [ ] **Step 6: Post-merge owner check (manual, tracked in PR)**

After deploy: a real Frontier login on prod shows the real CMDR name; a real journal import completes and lights the travel heatmap. Record the result on the PR.

---

## Self-Review

**Spec coverage:** CAPI name (Tasks 1–3), fail-open (Task 2), placeholder replacement (Task 3), contract-test update (Task 4), import diagnose+fix (Tasks 5–6), Cypress regression (Task 7), heatmap verification + gates + PR + owner check (Task 8). All spec sections map to a task.

**Placeholder scan:** Backend code is concrete (exact scope string, `/profile` fetch, name logic, call-site). The import *fix* code is necessarily conditional on Task 5's reproduction, but each branch gives concrete code/config — this is diagnose-first, not a placeholder.

**Type consistency:** `associate_verified_commander(..., commander_name: str | None = None)` is defined in Task 3 and called with `commander_name=identity.commander_name` in the same task; `identity.commander_name` is produced by Task 2 via the existing `FrontierIdentity` model; `parseJournals`/`role="alert"` names match the traced components.
