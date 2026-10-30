# V3 Colony Planner (the Plan journey) design

## 1. Status

**Status: Design only; not implemented — 2026-10-30 — base `origin/main`
`1807ca33ef6903a16380c76735cd99f82010fcac`.**

**Owner direction (2026-10-30):** "The colony planner is part of the ed-finder.
Once a system has been decided on, a user needs to be able to build." The owner
also asked for "our version of Raven Colonial, but more intuitive and linking
into the wider app", recreated from the rules and **not** copied from Raven's
code.

This design builds on owner decisions D2 and D3 of 2026-10-21 (`docs/ROADMAP.md`,
"Owner decisions 2026-10-21 on that audit's open questions"):

- D2: the CPE lives inside ED-Finder as a bounded module, `apps/api/src/cpe/`,
  guarded by a boundary test.
- D3: the first real Plan feature is a construction-point (CP) budget and
  port-order calculator on V3 data, using the guide and CRE cost rules.

This design does not change go-live, step P (the governed purge), or any F4 gate.
Section 9 says how the slices fit around P. The owner's answers to the design's
questions are in section 10.

## 2. What the commander gets

The journey is **Explore/Finder → Inspect → Plan → Review/Export**
(`docs/ROADMAP.md`, "Product journey and spatial north star"). Today the three
Plan entry points lead to a placeholder page:

- Inspect: "Continue to Plan" (`apps/web/src/routes/inspect/+page.svelte:29-30`).
- Explore: "Plan here" (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:1154-1155`).
- App shell: "Open plan" (`apps/web/src/lib/components/AppShell.svelte:72`).

All three open `/plan?system=<id64>`. The `[journey=journey]` route renders it
as "Migration placeholder" (`apps/web/src/routes/[journey=journey]/+page.svelte`).

The planner replaces that placeholder. On `/plan?system=<id64>` the commander can:

1. **See the system's bodies.** Bodies are listed as a parent/child tree, each
   showing its orbital and surface slots (predicted, or entered by the
   commander) and how many slots the plan has used.
2. **Add builds.** The commander picks a facility from the catalogue, puts it
   on a body (orbital or surface), and gives it a status: Planned, Building or
   Complete. They can name it, reorder it, move it to another body, or remove
   it. The first site is the Primary Port and is labelled as such.
3. **See the CP budget live.** Tier 2 and Tier 3 points are shown in two views:
   - "Now": what is complete or building.
   - "After the plan": every site in the list.

   Every port shows what it costs at its place in the order. The cost of the
   *next* port is shown before it is added.
4. **Check the build order.** Each step gets one of three results, with a
   reason:
   - **OK**
   - **Blocked**: short of points, a missing prerequisite, no free slot, or
     more than five builds under construction.
   - **Needs info**: for example, the body's slots are unknown.

   Where points run short, the check lists the facilities that would earn the
   missing points and fit a free slot. This is a lookup, not an optimiser.
5. **Ask "why?" about any number.** Every cost, reward and check result names
   the rulebook rule (`RB-xxxx`) or catalogue row it came from, with the
   rulebook's quote and status (Extracted, Confirmed, Likely or Disputed).
6. **Keep the plan.** The first release keeps plans in the commander's browser.
   A later slice adds plans saved to the account (section 7, S6).

Later slices add economies, links and Raven import (section 7). Moving between
ED-Finder pages keeps the selected system (the existing `selectedSystem` store,
`apps/web/src/lib/persistence/stores.ts:105`).
The Plan page header shows the system's Finder rating and archetype, so the
commander can see why they picked it.

### 2.1 Taking ideas from Raven, and doing better

| Raven Colonial idea we keep | What the ED-Finder planner adds |
|---|---|
| Bodies list with sites per body | Slots come from the validated predictor, with "unknown" when inputs are missing; the commander can enter slots seen in Architect Mode |
| Site status (plan / build / complete) | The Primary Port is labelled and, once complete, protected from changes (RB-0008) |
| CP totals | Two clear views ("Now" and "After the plan"); the next port's cost is shown before you add it |
| Named plan copies | Several plans per system: kept in the browser first, then in the account (S6) |
| Ordering | Per-step OK/Blocked/Needs-info results with reasons and "what pays for this" |
| — | Every number links to its rulebook rule and quote |
| — | Plans are linked to the Finder, Inspect and the watchlist |
| — | Keyboard and screen-reader access throughout (section 6) |

## 3. Scope

**In scope:**

- A plan for one system at a time.
- Bodies and slots.
- Sites with status and order.
- The CP budget with port escalation.
- Order checks.
- Explanations.
- Browser-kept plans.
- Later: economies, strong and weak links, account-saved plans, Raven import.

**Out of scope for this design:**

- Automatic plan design (an optimiser) and any language model. Code computes
  plans; a model never decides a number.
- Multi-system plans.
- Live in-game state, beyond what the V3 catalogue already holds.
- Any change to Finder scores or to frozen Ratings V4.0.
- Any write to canonical or derived data.

The legacy V2 planner is not reused or revived. That covers `optimiser/`,
`simulation/`, `routers/simulate.py`, `routers/simulation.py`,
`routers/optimiser.py`, `routers/colony_planner.py` and `packages/planner-core`.
It reads V2 tables that production does not have
(`docs/development/evidence/2026-10-21-cre-cpe-utilisation-audit.md`, section 4).
Marking its endpoints "not available on V3" is a separate change (that audit,
CPE recommendation 4).

## 4. Where the rules come from

| Rule area | Source in ED-Finder | Rulebook IDs |
|---|---|---|
| Facility list, costs, CP earned, tiers, economies, prerequisites (text) | `apps/api/src/domain/facility_catalogue_v1.json` (56 templates from the DaftMav sheet), loaded by `apps/api/src/domain/facilities.py` | RB-0002 |
| Port escalation | `apps/api/src/mechanics/cp_rules.py`: T2 port = max(3, 2n−1) T2 points; T3 port = 6·max(1, n−1) T3 points; n counts T2 and T3 ports together | RB-0003, RB-0005 |
| Primary Port exempt and fixed | new `cpe` rule code | RB-0004, RB-0008 |
| Escalation counts from construction start | new `cpe` rule code | RB-0006 |
| At most five under construction | new `cpe` rule code | RB-0007 |
| Economies (later slice) | rulebook values; `domain/colonisation_rules.py` only where the parity test shows it matches | RB-0009 to RB-0014, RB-0027 |
| Links (later slice) | `mechanics/link_rules.py` where it matches | RB-0015 to RB-0020 |
| Slots | `apps/api/src/ingest/slot_prediction.py` (`validated-slot-v1`) | none yet: CRE gap |

**The rulebook is the authority.** The pinned copy is
`docs/reference/colonisation/cre-rulebook/rulebook.json`: release
`cre-knowledge-v0.3.0`, 27 rules, CRE commit `59dd198`, sha256 `0487fcfb…1bd4`.
`tests/test_cre_rulebook_parity.py` already compares ED-Finder's hand-coded
tables with it. The planner adds its own rules to that parity check. A rule
marked **Disputed** in the rulebook (for example RB-0012, "Body economies and
modifiers do not stack") is shown as disputed on the page, never as fact.

Where the planner's economy explanation differs from the frozen Finder score
(the Ratings V4.0 findings listed for V4.1 in the 2026-10-21 Mega Guide audit),
the page says so. It does not quietly disagree with the Finder.

**Prerequisites need structure.** The catalogue's prerequisites are free text:
13 of 56 templates have one, for example "Installation - Mining Outpost". The
`cpe` catalogue wrapper maps each text to facility ids in a reviewed table. A
test fails if a catalogue prerequisite has no mapping.

**Gaps to feed back to the CRE.** The rulebook has no machine-readable facility
list, prerequisite list, slot rules or goods table. It also does not yet state
two things the planner relies on:

- a site earns its points only once it is complete;
- the Primary Port is the first site, and it must be a port.

Both are how the game and Raven behave. Until the rulebook covers all of these,
the planner uses ED-Finder's catalogue and slot predictor, plus these two
behaviours written as `cpe` code. The CRE is asked to publish each one as a
rule. When a later rulebook release adds them, the parity test switches to
compare against it.

### 4.1 Raven Colonial: an answer key, not a source

RavenColonialWeb is licensed **GPL-3.0**. ED-Finder does not copy, translate or
vendor any of its code, data files (for example its cost tables) or page text.

Raven is used in two ways only:

1. **Ideas for what a planner should let you do** (section 2.1), written fresh
   from the rules.
2. **An answer key for tests.** The test fixtures record the numbers Raven
   showed for a real layout: points, costs and scores. Each fixture names the
   Raven revision and date it was read. A test fails if the planner differs
   from those numbers, unless the difference is listed with a rulebook
   reason.

One difference is already known. At the sixth counted port, Raven charges 12
T2 points; RB-0003 and `cp_rules.py` give 11. The planner follows the rulebook,
and the page notes the difference.

## 5. Architecture

### 5.1 The `cpe` module (D2)

`apps/api/src/cpe/` holds pure, synchronous code with no database access and no
web framework. It is made of these files:

| File | Purpose |
|---|---|
| `plan.py` | The plan model (system id64, sites, order) and its validation |
| `catalogue.py` | Wraps `domain/facilities.py`; holds the structured prerequisites |
| `rules.py` | Loads the pinned rulebook; looks rules up by id |
| `budget.py` | Walks the plan and works out the budget (the D3 calculator) |
| `checks.py` | Per-step order checks |
| `explain.py` | Rule ids and quotes for each number |

The plan model:

- **System:** the system's id64.
- **Sites:** each site has:
  - `site_id`;
  - `facility_id` (a catalogue id);
  - `body_ref` (a V3 body id, or `null` for "not placed yet");
  - `slot_kind` (`orbital` or `surface`);
  - `status` (`planned`, `building`, `complete` or `demolished`);
  - an optional name.
- **Order:** the list order is the build order. The first site in the order is
  the Primary Port and must be a port (`is_port` in the catalogue). Section 4
  lists this as a CRE gap.

The budget walk:

- **Primary Port.** The Primary Port is free and is not counted (RB-0004).
- **Order of payment.** Ports pay in list order: T2 at max(3, 2n−1), T3 at
  6·max(1, n−1) (RB-0003).
- **When a port counts.** A port counts towards the escalation from the moment
  its construction starts (RB-0006).
- **Costs and rewards.** A site's cost is charged when it is laid down. A site
  earns its reward only when it is complete (RB-0002 gives the costs and
  rewards; the "only when complete" part is a CRE gap, section 4).
- **Demolished sites.** They count for nothing.
- **"Now" view.** Rewards come from complete sites. Costs come from complete
  and building sites.
- **"After the plan" view.** Every site counts.
- **Result for each step:** points before the step, its cost, its reward,
  points after, and the counted port number n.

The order check, based on the owner's own Elite Colony Copilot review:

- Building sites are assumed to finish before any planned site starts.
- A Blocked step is skipped, and the walk goes on.
- A Needs-info step is assumed to go ahead, and this is said in the result.
- These are blocking checks:
  - points would go negative for a site with a cost;
  - a prerequisite is not complete earlier in the order;
  - the body has no free slot of that kind;
  - more than five sites are marked Building at once (RB-0007);
  - a change would replace, move or remove a completed Primary Port (RB-0008).

The boundary test is `tests/test_cpe_boundary.py`. `cpe` may import only:

- the standard library;
- `domain.facilities`;
- `mechanics.cp_rules`;
- `mechanics.link_rules` (later slice);
- the pinned rulebook file.

It must never import:

- `optimiser`, `simulation` or `routers`;
- `asyncpg` or `fastapi`;
- any V2 module.

### 5.2 API

There is a new router, `apps/api/src/routers/plan.py`, under the prefix
`/api/v1/plan`. The same app serves the existing `/api/v1` canonical routes.
Every input is bounded:

- one system per request;
- at most 300 sites;
- names at most 64 characters;
- facility ids must be in the catalogue.

| Route | Purpose |
|---|---|
| `GET /api/v1/plan/catalogue` | Facilities with costs, rewards, tier, location, economy, structured prerequisites and rule ids. Static; no database. |
| `POST /api/v1/plan/evaluate` | Takes a plan and returns the budget walk (both views), per-step checks and explanations. Stateless; no database. |
| `GET /api/v1/plan/systems/{id64}/bodies` | The body adapter (section 5.3) |

Response shapes go into OpenAPI. The web client is regenerated
(`apps/web/src/lib/api/`), following `tests/test_svelte_generated_client_boundary.py`.

### 5.3 V3 body adapter and slots

The adapter reads the published canonical generation the same way
`routers/v3.py` does: `current_canonical_generation()` and the explicit
`v3_gen_*` schema, never `search_path`. It returns, for each body:

- the fields `listV3SystemBodies` returns;
- the extra inputs the predictor needs;
- the slot prediction.

The predictor (`predict_body_slots`) needs these inputs. The V3 canonical
`bodies` table (`sql/v3/migrations/001_v3_baseline.sql:1059-1121`) and its
neighbours supply them:

| Predictor input | V3 source | Conversion |
|---|---|---|
| `is_landable` | `bodies.is_landable` | none |
| `radius` (metres) | `bodies.radius_km` | × 1000 |
| `surface_temp` (K) | `bodies.surface_temperature_k` | none |
| `gravity` (g) | `bodies.surface_gravity_g` | none |
| `atmosphere` | `atmosphere_classification_id` → `v3_vocab.atmosphere_classification` | vocabulary name |
| `planet_class` | `body_type_id` → `v3_vocab.body_type` | vocabulary name |
| `terraform_state`, `is_terraformable` | `terraforming_state_id` → `v3_vocab.terraforming_state` | vocabulary name |
| `volcanism` | `volcanism_type_id` → `v3_vocab.volcanism_type` | vocabulary name |
| `is_ringed` | the system's rings (`kind = 'RING'`) on that body | true if any |
| `geo_signal_count`, `bio_signal_count` | `body_signal_current` | signal counts |

Each conversion gets a unit test. The predictor was written against journal
names, so the adapter's vocabulary mapping is checked against the predictor's
expected strings with fixtures.

When an input is missing, the body's slots are "unknown" with the predictor's
own reasons. The page asks the commander to enter what Architect Mode shows. A
commander-entered value is sent as `observed_orbital_slots` /
`observed_ground_slots` and is shown as "entered by you".

The adapter is read-only and bounded in the same way as the existing body
route. It is tested on a disposable PostgreSQL 18 database.

### 5.4 Web

- `apps/web/src/routes/plan/+page.svelte` replaces the placeholder for `plan`.
  A concrete route outranks the `[journey=journey]` matcher. `plan` is removed
  from `apps/web/src/params/journey.ts` in the same slice, with a test.
- The feature code lives in `apps/web/src/lib/features/plan/`. It uses only the
  generated API facade.
- The layout is three panes on wide screens and stacked panes on a phone:
  - bodies tree with slots;
  - the selected body's sites;
  - the budget and order-check panel.

  The order list can be reordered with buttons as well as dragging.
- Browser storage holds plans by system id64. Every read and write is wrapped
  so the page still works when storage is blocked. A plan can be exported and
  imported as a JSON file.

## 6. Accessibility, visual validation and tests

Accessibility:

- Every action works from the keyboard.
- Reordering uses "Move up" and "Move down" buttons.
- Check results are announced in a polite live region.
- Colour is never the only signal: Blocked, OK and Needs-info each have a word
  and an icon.

Visual validation: the page is a visual change, so each UI slice needs the
visual validation lanes in `docs/development/v3-browser-validation-lanes.md`.

Tests:

- **`cpe`:** unit tests for every rule above, plus the answer-key fixtures.
- **Parity:** the rulebook parity test is extended to the new rules.
- **Body adapter:** a PostgreSQL 18 test.
- **Web:** Svelte unit tests, plus Cypress for the main path. The main path is:
  1. open from Inspect;
  2. add a port and two installations;
  3. see the budget and a Blocked step;
  4. fix the order;
  5. reload, and the plan is still there.

Acceptance: Codex and Octopus on the exact final head of each PR
(`docs/development/pull-request-acceptance-policy.md`).

## 7. Slices

Each slice is its own PR. The slices are drafted for the Codex runners and
reviewed before merge.

| Slice | Contents | Needs a migration? | Visual change? |
|---|---|---|---|
| S0 | This design and a roadmap entry | No | No |
| S1 | `cpe` core: plan model, catalogue wrapper with structured prerequisites, budget walk (D3), order checks, explanations; boundary test; parity additions; answer-key fixtures | No | No |
| S2 | `/api/v1/plan/catalogue` and `/api/v1/plan/evaluate`; OpenAPI and client regeneration | No | No |
| S3 | Body adapter `/api/v1/plan/systems/{id64}/bodies` with slot predictions; PostgreSQL 18 test | No | No |
| S4 | The `/plan` page, browser-kept plans, JSON export and import; replaces the placeholder | No | Yes |
| S5 | Economies and strong and weak links, with explanations (RB-0009 to RB-0020, RB-0027) | No | Yes |
| S6 | Account-saved plans: new empty `v3_private` tables following migration 014's pattern (new relations only, lock and statement timeouts); Raven layout import from a file the commander exports | Yes | Yes |
| S7 | Mark the legacy V2 planner endpoints "not available on V3" | No | No |

D3 said that, until a Plan feature ships, the `/plan` page should say plainly
that planning is being rebuilt. That interim message stays the owner's decision.
S4 removes the need for it.

## 8. Risks

- **Slot predictions on V3 data are unproven.** The predictor was validated on
  journal scans. S3 compares V3-adapter predictions against the predictor's own
  evidence set before the page relies on them. Bodies stay "unknown" rather than
  guessed.
- **The rulebook is incomplete** (section 4). The planner states which numbers
  come from the catalogue rather than the rulebook.
- **The guide is behind the game.** RB-0001 says the 4.2.2.0 change is not
  included. The page shows the rulebook version it used.
- **Raven differs** at the sixth port (section 4.1). Other differences found by
  the answer key are listed, not hidden.

## 9. Sequencing with step P and F4

**Owner answer (2026-10-30):** build the planner alongside step P (the purge)
and F4, provided it does not tie up the runner the purge needs.

It does not, for three reasons:

- **The purge does not use the Codex runners.** Production purge dispatches
  run on a GitHub-hosted `ubuntu-24.04` runner
  (`.github/workflows/v3-production-derived-purge.yml:102`).
- **Codex tasks use their own runners.** They run on the three self-hosted
  Contabo runners (`.github/workflows/codex-laptop.yml:106`,
  `[self-hosted, Linux, X64]`).
- **The rehearsal runner is out of reach.** It is registered with
  `--no-default-labels`, so it cannot pick up a Codex task, and no further
  rehearsal is planned.

The planner's CI also runs on GitHub-hosted runners.

**The one shared lock is the production deploy.** The purge and application
promotion share the `v3-production-application-authority` concurrency group
(`v3-production-derived-purge.yml:95-96`,
`v3-production-application-deploy.yml:42-43`). Each planner slice therefore
goes through code, CI and review at any time. A deploy is dispatched only when
no purge phase is running, so it never queues behind a purge dispatch or holds
one up.

The rules are therefore:

- **S0–S5 are built now.** They add no migration. They read only the published
  canonical generation and none of the derived products P is purging. They
  change no Finder product. They ship only through the normal governed
  application promotion, between purge phases.
- **S6 waits.** Its migration is not applied while step P is between its first
  preflight and `complete`. A migration changes the production schema identity,
  and P's operations are being run one owner approval at a time.
- **F4 is unaffected.** The planner does not touch the Finder ranking UI or its
  feature flag.

## 10. Owner answers (2026-10-30)

The owner chose the default for each question:

1. **Order against P and F4:** alongside, as section 9 sets out.
2. **Where plans are kept first:** in the browser first. Account-saved plans
   follow in S6.
3. **Raven import:** from a file the commander exports from Raven. ED-Finder
   does not fetch from Raven's servers.
4. **The sixth-port difference:** follow RB-0003 (11 T2 points) and show
   Raven's figure (12) as a note.
