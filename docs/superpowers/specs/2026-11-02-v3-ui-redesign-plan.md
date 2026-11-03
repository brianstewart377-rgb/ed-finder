# V3 UI redesign plan

## 1. Status and authority

**2026-11-02 — implementation plan; no deployment authority.** Phase 1 is
**done-pending-merge in [PR #998](../../../../../pull/998)**. Phase 4 is
**implemented in this PR**, with visual validation still required before
promotion. The other phases below retain their recorded status; implementation
is not a claim of deployed behaviour.

The approved 1 November 2026 concept pack is not in this repository. This plan
records the owner's supplied direction; it does not reconstruct unseen images
or invent features. The map-window image governs styling and placement, not
galaxy data. Its visual comparison remains an implementation acceptance input.

Follow the [ROADMAP](../../ROADMAP.md), [application stack](../../development/v3-application-stack-decision.md),
[spatial product contract](../../colonisation-redesign/spatial-platform-product-contract.md),
[renderer boundary](../../colonisation-redesign/spatial-platform-architecture-decision.md),
[search/data decision](../../development/v3-search-spatial-derived-data-decision.md),
[Ratings V4 freeze](../../development/ratings-v4-freeze/README.md) and
[browser lanes](../../development/v3-browser-validation-lanes.md).
Only `apps/web/` is the application frontend; `frontend/` is retired evidence.
The [Finder design](2026-10-10-v3-finder-f4-archetype-ui-design.md) and
[Planner design §7](2026-10-30-v3-colony-planner-design.md#7-slices) retain their
domain contracts. Current code and dated amendments resolve their older status
paragraphs. Main and production status remain distinct in ROADMAP.

## 2. Visual and interaction direction

Elite Dangerous orange, glossy gunmetal, midnight navy and neon deep blue;
rounded panels/buttons, soft reflections, crisp text and condensed uppercase
HUD headings. Use Phase 1's kit rather than per-page palettes. In #998's
[`app.css`](../../../apps/web/src/app.css), the named tokens are:

| Purpose | Tokens |
|---|---|
| Background and panels | `--bg-void`, `--bg-deep`, `--panel`, `--panel-raised`, `--panel-sunken`, `--panel-gloss` |
| Orange and blue | `--accent`, `--accent-hi`, `--accent-text`, `--accent-glow`, `--neon`, `--neon-hi`, `--neon-soft` |
| Text and boundaries | `--text`, `--text-muted`, `--text-dim`, `--line`, `--line-strong`, `--line-glow` |
| Status and focus | `--ok`, `--warn`, `--danger`, `--focus` |
| Shape, depth, motion | `--radius-sm`, `--radius`, `--radius-lg`, `--radius-pill`, `--shadow-panel`, `--ease` |
| Headings | `--font-hud`: self-hosted Saira Semi Condensed, with fallback |

Keep compatibility aliases (`--color-void`, `--color-panel`, `--color-signal`,
`--color-cyan`, `--muted`, `--metal`) and tier tokens stable. Pill actions are
opt-in; catalogue rows and autocomplete options must not become giant pills.
Gloss must preserve text contrast and cannot communicate status by itself.

Main tasks use **tabs**. Occasional tools use **closable, movable/dockable
pop-outs**, non-modal by default, with Escape dismissal and focus return.
The existing [Layers](../../../apps/web/src/lib/features/explore/MapLayers.svelte),
[Body filters](../../../apps/web/src/lib/features/explore/BodyFilters.svelte)
and Sources & freshness pop-outs establish the interaction pattern. They are
already anchored and viewport-clamped; movement/docking is additional work.
Tabs preserve their content state. Moving, docking or closing a tool never
commits a filter, adds a facility or changes the search implicitly.

Every phase inherits these accessibility requirements:

- Tabs use labelled tablists, roving focus, arrow/Home/End navigation and linked
  tab panels; hidden panels cannot retain keyboard focus.
- Pop-outs have labelled open/close controls, a useful initial focus and return
  focus to the opener (or a stable task control if it disappeared). Non-modal
  tools do not trap focus. Escape closes the topmost tool first.
- Movement/docking has keyboard controls as well as pointer/touch interaction;
  resize/zoom clamps windows into the viewport and keeps Close reachable.
- Preserve visible focus, readable contrast, text alternatives and labelled
  numeric inputs; never rely solely on colour, hover or dragging.
- Run axe for changed open/closed/tab states and respect reduced motion for
  transitions, reflections and camera fly-to; motion remains interruptible.

## 3. Finder counts and truth rules

Archetype selection and results come first. **Any = Best Colony Potential**;
a selected archetype means **fit for that archetype**. Preserve the actual
request's ordering and scope: anchored Any currently requests distance order;
this redesign does not silently turn that into a different ranking.

Body filters are optional grouped sliders with **Reset / Cancel / Apply**.
Reset clears the draft, Cancel discards it, Apply commits once. Applied chips
remain visible when the tool is closed, with removal and Clear all. This is
already shipped, including the Planets / Stars / Features tabs and bounded,
refresh-safe `near` and `bodies` URL state.

The owner's list contains 18 counts (9 planets, 4 stars, 5 features). **All 18
already exist in the UI and `/api/local/search` contract** on this branch:

| Group | Requested count | Existing `body_filters` key |
|---|---|---|
| Planets | Earth-like | `elw_count` |
| Planets | Water worlds | `ww_count` |
| Planets | Ammonia worlds | `ammonia_count` |
| Planets | Terraformable | `terraformable_count` |
| Planets | Gas giants | `gas_giant_count` |
| Planets | High metal content | `hmc_count` |
| Planets | Metal-rich | `metal_rich_count` |
| Planets | Rocky | `rocky_count` |
| Planets | Icy | `icy_count` |
| Stars | Black holes | `black_hole_count` |
| Stars | Neutron stars | `neutron_count` |
| Stars | White dwarfs | `white_dwarf_count` |
| Stars | Other stars | `other_star_count` |
| Features | Landable | `landable_count` |
| Features | Walkable | `walkable_count` |
| Features | Rings | `ring_count` |
| Features | Biological signals | `bio_signal_total` |
| Features | Geological signals | `geo_signal_total` |

Evidence: [UI definitions](../../../apps/web/src/lib/features/explore/body-filters.ts),
[`BodyFilters` model](../../../apps/api/src/models.py),
[column mapping](../../../apps/api/src/search_economies.py) and
[local-search validation](../../../apps/api/src/local_search.py).
The existing nineteenth control, **Rocky ice** (`rocky_ice_count`), is retained
pending owner decision 3. Do not describe it as missing or silently remove it.
Min/max are inclusive; maximum zero means none, minimum zero alone adds no
restriction. The UI's whole-number bound is 0–999, with an unbounded maximum
shown as Any; 999 is a UI limit, not a newly asserted backend limit.

The honest gap is **scope**, not absent count fields. Only anchored Any searches
currently apply the filters. Galaxy-wide Any rejects effective hard filters
with 422. Selected-archetype requests use `/api/archetypes/rankings` without
these filters; chips remain visible as paused. Anchored picked-archetype filters
still need a probe and re-attestation per ROADMAP. Phase 3 cannot enable them
through a cosmetic change. If a supported field is unavailable in a request
mode, explain that beside the disabled tool and preserve the paused chips.

Counts are constraints, **not ranking weights**. Future ranking-weight dimensions
are undefined and must not be invented. The existing backend rerank contract
for archetype-fit weights is not permission for body-count or economy sliders;
the current Finder keeps `WEIGHT_CONTRACT_DEFINED = false`. The earlier
URL-only decision for eventual custom weights does not define those dimensions.

## 4. Execution order: one PR per slice

Each row is one independently reviewable PR, in this order. All implementation
rows retain the contracts and truth rules in §§3 and 6 and the gate in §5.
No slice needs a SQL migration or new backend contract.

| Phase / slice | Contents | Migration? | Visual? |
|---|---|---|---|
| P0 | This plan, ROADMAP link and CHANGES entry | No | No |
| P1 | Shared tokens, Saira headings, glossy panels, opt-in pill actions, tabs, chips and pop-out skins; **done-pending-merge, #998** | No | Yes |
| P2a | Extract Explore view state from layout ownership; retain query, filters, selection, result scroll and spatial context through layout changes; **implemented in this PR** | No | Verify unchanged |
| P2b | M09: on-demand map window, **Show on map**, **Expand**, close/reopen and state preservation using the existing canvas | No | Yes |
| P2c | Explore main-task tabs and shared movable/dockable tool behaviour; keep Layers and map controls accessible in the window | No | Yes |
| P3 | Finder control polish: archetype/results priority, existing count-group tabs, persistent chips and truthful scope gaps; no missing count fields to add today | No | Yes |
| P4 | Inspect **Overview / Bodies / Stations** tabs; evidence explanation pop-out and retained Sources & freshness; **implemented in this PR** | No | Yes |
| P5a | Plan **System layout / Build order** tabs; facility preview pop-out with explicit **Add to plan** | No | Yes |
| P5b | Review/export pop-out over the plan, per-item unresolved-information links and explicit **DRAFT** export | No | Yes |
| P6a | Home polish: existing hero actions and three tool cards adopt the kit; truthful Review/export entry wording | No | Yes |
| P6b | Final visual sweep across the complete journey, responsive layouts and all tool states | No | Yes |

### Phase 1 — shared design kit

Use #998's `apps/web/src/app.css`, `apps/web/src/lib/design-kit.test.ts` and
self-hosted fonts under `apps/web/static/fonts/`. Its implementation is complete
pending merge; do not rebuild it or claim it is deployed. It supplies styling,
not the later tab orchestration or movement/docking behaviour.

Routes, components' domain actions, renderer and data contracts stay unchanged.
Verify tokens, opt-in skins, font fallback, focus contrast and reduced motion
with the design-kit Vitest coverage. Product Cypress captures representative
existing pages with axe and visual approval; Review Lab retains its existing
failure-state coverage and containment. Apply §5 before promotion.

### Phase 2 — map workspace (M09)

Resolve **“the map and controls do not share a useful viewport.”** In
[`ExploreWorkspace.svelte`](../../../apps/web/src/lib/features/explore/ExploreWorkspace.svelte),
keep search/archetype/results usable together. **Show on map** opens the selected
system on demand in a map window. **Expand** gives that same window space for
broader exploration; closing restores the results' scroll position and keeps
the search, filters and selection. Reopening retains meaningful camera/layer
context. Only an explicit search action changes the search.

Extract a proposed `ExploreMapWindow.svelte` and view-state helper under
`lib/features/explore/`; keep the route `routes/explore/+page.svelte` and embed
[`SpatialCanvas.svelte`](../../../apps/web/src/lib/spatial/SpatialCanvas.svelte).
Use its existing renderer-neutral camera/selection interface and Babylon
runtime. Keep one logical Galaxy context: window visibility is presentation,
not a second map. Preserve CPU state through any suspend/rebuild and avoid
duplicate canvases, subscriptions, queries or leaked GPU resources.

Keep Layers, camera controls, hover cards and their keyboard equivalents,
Finder/catalogue star separation, viewport streaming, density and nebula layers,
scope/radius and deliberate System entry/return now on main. Retain actual
coordinates and regions; missing coordinates stay unavailable. The concept
image is a placement/style reference, **never generated geography**. Renderer
algorithms, scene contracts, layer provenance, API requests and routes stay
unchanged. Explore tab labels/partition and phone behaviour need §7 decisions;
the primary Finder task keeps archetype selection and results together, and
Body filters/Layers remain occasional tools rather than primary task tabs.

Extend `ExploreWorkspace.test.ts`, its workload tests, `MapLayers.test.ts` and
spatial component/lifecycle tests for state retention, bounds and single-runtime
ownership. Product `product-journey.cy.ts` and `spatial-foundation.cy.ts` cover
Show/close/reopen/Expand, tab switches, scroll retention, resize, keyboard docking,
topmost Escape, focus return, axe and reduced-motion camera behaviour. Review
Lab retains injected map failure/recovery and empty/partial/oversized data
checks through the real canvas. Apply §5 to every visible slice.

### Phase 3 — Finder controls

Touch `ExploreWorkspace.svelte`, `ArchetypePicker.svelte`,
`FinderResultRanking.svelte`, `BodyFilters.svelte`, `body-filters.ts` and
`search-state.ts` only as presentation/state wiring requires. Reuse the shipped
Planets / Stars / Features tabs and all supported groups in §3. There are no
remaining requested count fields to implement; remaining work is layout,
kit adoption and scope explanations. Keep selection/results prominent and
optional sliders in the closable tool, with applied/paused chips outside it.

Keep `/api/local/search`, archetype contracts, current ordering, caps, anchor
resolution, URL roundtrips, feature gate and saved/compare score identities.
No automatic query on a plain `/explore`, tab switch, draft edit or map close.
Extend `BodyFilters.test.ts`, `body-filters.test.ts`, `search-state.test.ts`,
`ranking-state.test.ts` and `ExploreWorkspace.test.ts` for keyboard inputs/tabs,
Reset/Cancel/Apply, chips, paused modes and no speculative weight fields.
Product Cypress covers archetype choice, anchored Apply/reload, chips after
close and returning from the map, with axe and reduced motion. Review Lab owns
injected empty/error searches; normal request-shape checks stay in Vitest and
`tests/test_local_search_v3.py`. Apply §5 before promotion.

### Phase 4 — Inspect tabs

Touch `routes/inspect/+page.svelte` and the existing `SystemDetail`,
`SystemRatings` and `SourcesFreshness` components under `lib/components/`.
Organise **Overview / Bodies / Stations** without discarding selection or
refetching solely on a tab switch. Retain seven independent economy potentials:
Agriculture, Refinery, Industrial, High Tech, Military, Tourism and Extraction.
Move the existing SystemRatings inline Why explanations into an evidence
pop-out; keep Sources & freshness as the provenance pattern. No new aggregate
score, inferred evidence, freshness timestamp or build-eligibility badge.

Canonical Inspect routes/IDs, typed facade, published generation identities,
ratings mechanics, body hierarchy/System Map and availability language stay
unchanged. Extend the components' Vitest tests for tab/focus retention,
explanation content and unknown/unavailable distinctions. Product Cypress
covers Explore → Inspect → all tabs → evidence → close/return, keyboard,
axe and reduced motion. Review Lab covers injected partial/failed detail and
ratings reads without fabricating known values. Apply §5 before promotion.

### Phase 5 — Plan and Review/export

Touch `routes/plan/+page.svelte`, `lib/features/plan/PlanWorkspace.svelte`,
`SystemPane.svelte`, `BuildOrder.svelte`, `FacilityPicker.svelte`,
`SummaryPane.svelte`, `WhyDrawer.svelte` and `plan.css`; add a proposed
`ReviewExport.svelte` there. Replace the current Build order toggle with
**System layout / Build order** tabs. Keep the floating picker's existing
Both / Orbital / Surface tabs, but make facility selection a preview; only
**Add to plan** mutates the plan. Closing a preview adds nothing.

Review/export opens over the current plan. Each unresolved item links to the
relevant body/slot editor or build, activates its task tab and moves focus there.
Existing first-blocked/first-unknown shortcuts are not a complete per-item
review. Keep Tier 2 and Tier 3 balances separate in Now and After the plan.
Unknown slots stay unknown; surface predictions retain their source label and
orbital slots remain entered/imported. Review never implies build eligibility.

Existing Export plan downloads JSON without a DRAFT marker. Make the action
and artifact explicitly **DRAFT** (including the filename), preserving the
`cpe_plan_export_v1` import/export roundtrip and avoiding eligibility claims.
Retain CPE checks/rules, browser-kept plans, Raven import, plan ownership and
existing routes/API. No new account storage or export format is implied.

Extend PlanWorkspace, FacilityPicker, BuildOrder, SummaryPane and model/codec
Vitest tests for preview/no mutation, explicit Add, tab state, T2/T3 separation,
per-item focus links and DRAFT export. Product `plan.cy.ts` covers Inspect →
Plan → preview/Add → reorder → review unknowns → DRAFT export/import/reload,
keyboard move controls, axe and reduced motion. Review Lab owns deliberately
failed evaluation/partial body states via guarded scenarios when needed;
it does not duplicate the normal plan journey. Apply §5 to P5a and P5b.

### Phase 6 — home polish and final visual sweep

[`routes/+page.svelte`](../../../apps/web/src/routes/+page.svelte) already has
the hero's primary **Explore the galaxy**, secondary **Inspect a system** and
three **Explore / Inspect / Plan** tool cards. Retain those routes and actions.
Remaining work is kit/typography/spacing polish and replacing “Review & export —
Coming later” once P5b is available; do not invent a fourth tool or new route.
Touch `app.css`, shared `WorkspaceHeader`/shell styles and affected components
only for inconsistencies found during the final sweep. Data and renderer remain
unchanged; decorative home art must not masquerade as factual map content.

Vitest covers home links, shared skins and regressions found by the sweep.
Product `foundation.cy.ts`, `product-journey.cy.ts`, `spatial-foundation.cy.ts`
and `plan.cy.ts` capture the complete journey on phone/tablet/desktop, keyboard
and focus paths, all pop-out/tab states, axe and reduced motion. Review Lab
reruns affected synthetic scenarios and containment/teardown only. Apply §5;
this final sweep does not defer visual approval for earlier promoted slices.

## 5. Validation and promotion gate

For each implementation PR, run focused Vitest and web check/lint/format/build
on Node 24 and pinned pnpm; keep required CI and existing contract checks green.
Every visible slice above requires the [browser-validation lanes](../../development/v3-browser-validation-lanes.md)
**before production promotion**, including P1 and layout/component extractions
even when their intended appearance is unchanged:

1. **Product E2E / Visual Acceptance** owns normal Cypress journeys, keyboard,
   axe, reduced motion, resize/remount, Chrome/Chromium and Firefox acceptance,
   console/network checks and approved screenshots/baselines. Compare with the
   owner concept references; retain evidence for the candidate being promoted.
2. **Review Lab** uses the same Svelte/Babylon runtime with isolated synthetic
   empty/partial/error/oversized or renderer-loss states and containment/teardown
   proof. Add only genuinely needed guarded scenarios. Lab screenshots are
   diagnostics, never product visual approval; neither lane substitutes for the
   other. No production credentials/data enter local validation.
3. Follow the [PR acceptance policy](../../development/pull-request-acceptance-policy.md)
   on the exact latest head, including explicit dispositions of findings, then
   the separate governed application-promotion authority. Merge is not deploy.

For **this docs-only P0**, run `pytest tests -k "roadmap or changes or docs" -q`
and check links/diff. No browser or renderer change is made by this document.

## 6. Non-goals and incremental delivery

No invented ranking weights, generated galaxy/region geography, new mechanics,
eligibility claims, backend contracts, SQL migrations, derived rebuilds or
production operations. Unsupported capability needs a separate design; do not
hide a contract change inside a visual slice. Preserve bounded/fail-closed API
validation, generated facade boundaries, routes, source labels and unknowns.
Future migrations additionally need the V3 registration/promotion cascade.

Use **incremental merges**: merge #998, then complete independently usable rows
in §4. P2a keeps today's presentation; each later row replaces a working surface
only when its own tests and review pass. If a row cannot be complete in one PR,
split it again or keep the incomplete replacement behind a separate default-off
UI flag with both paths tested; do not expose dead controls or reuse the Finder
F4 flag as a redesign switch. Keep existing URLs/storage readable and main
shippable throughout. Mobile decisions gate the affected replacement, not all
unrelated work. Promotion always retains §5's separate visual gate.

## 7. Open owner decisions

1. **Phone Explore layout:** after Show on map, should the window occupy the
   available workspace or leave part of the result list visible? Search,
   filters, selection and scroll must survive either choice.
2. **Mobile modality:** keep the map non-modal at phone width, or explicitly
   make it modal there? Only the latter needs a focus trap/background inertness;
   both require Close, Escape and focus restoration. Other tools remain non-modal.
3. **Count exposure:** keep the already-supported nineteenth Rocky ice control,
   or present exactly the owner's 18? All 18 exist today; for modes lacking
   support, retain paused chips/disabled controls or hide only the unavailable
   inputs? No choice authorizes widening API support.
4. **Explore task tabs:** approve labels and grouping for the existing Finder,
   saved-list and comparison surfaces while keeping archetype/results together.
   Body filters and Layers keep their pop-outs; this adds no new task feature.
5. **Visual reference hand-off:** identify the approved map-window image and
   phone variant for P2/P6 comparison. Until available, do not claim pixel-level
   fidelity or treat invented placement as an approved baseline.
