# UI reskin concept mockup brief

Last updated: 2026-07-23

## Purpose

This brief turns the owner's UI review into a bounded visual-design exercise.
It asks for interactive mockups, not a production implementation. The mockups
must show how the existing product and a small number of roadmap-backed future
concepts could share one coherent Elite Dangerous cockpit identity.

The working design branch is `codex/ui-reskin-salvage`. It contains the clean,
reviewable shell, Finder, and Map reskin recovered from the first Emergent pass.
The unrelated-history `redesign` branch must not be used or merged.

## Owner feedback

- Remove the news ticker. It consumes space without enough player value.
- Stop presenting the application as floating panels dropped over a background
  image. The shell, workspaces, and background should feel like one designed
  instrument.
- Make the Frontier/EDSM/EDDN compliance and attribution notice opaque and
  readable. After the user views it, allow it to be dismissed so the workspace
  reclaims the space. The full attribution must remain available from a
  persistent About or Legal control.
- Keep the Map map-first. The renderer must not begin two-thirds of the way down
  the screen behind explanatory and status panels.
- Retain the orange, brushed-metal, dark cockpit, and nebula identity. Cyan may
  support information and neutral controls, but must not replace orange as the
  product identity.
- Use a more integrated, confident composition inspired by the supplied
  industrial orange-and-charcoal reference. Do not copy its assets, typography,
  layout, or branding.
- Rework Finder so its filter categories behave like a compact instrument
  selector. Activating a category should open a larger adjacent editing surface;
  completing or closing it should return the category to the compact state with
  a professional, reduced-motion-aware transition.
- Simplify My Work. Journal Import is a utility, not the visual purpose of the
  entire workspace.
- Make Compare self-explanatory in both empty and populated states. It already
  compares up to four Finder systems, identifies per-metric best values, opens
  System Detail, removes candidates, and exports CSV; the UI should teach that
  flow without requiring prior knowledge.

## Visual principles

1. **One instrument, not a pile of cards.** Use connected rails, bays, seams,
   edge controls, and deliberate depth. Avoid a separate rounded container for
   every paragraph or control.
2. **Content owns the viewport.** Map, results, comparison data, and planning
   state receive the largest useful area.
3. **Orange is identity and commitment.** Use it for the active route, primary
   action, selected state, and decisive focus. Use cyan for information,
   telemetry, and neutral system state; gold for warnings or provisional state.
4. **Nebula is atmosphere, not wallpaper.** It may appear through restrained
   masks, edge glow, or deep background fields without reducing contrast.
5. **Progressive disclosure is purposeful.** Hide complexity until requested,
   but keep current selections and the next action obvious.
6. **Motion explains state.** Transitions should communicate expansion,
   selection, or context movement. Respect `prefers-reduced-motion`.
7. **Dense information remains opaque.** Tables, map labels, evidence, legal
   copy, and planning surfaces must not use low-contrast glass.
8. **Desktop-first, responsive, keyboard-complete.** Mock 1440x900, 1280x720,
   and 390x844 states and show visible focus, Escape close, focus return, and
   non-colour status labels.

## Mockup set

### 1. Shared shell and legal notice

Show the shell as a connected cockpit frame with the current player routes.
Remove the ticker. Include:

- active-route treatment in orange;
- selected-system context without adding a second full navigation bar;
- an opaque, readable first-view legal notice;
- a dismiss action that reclaims its space;
- a persistent About/Legal control that reopens the full attribution.

### 2. Finder

Show both an untouched/idle state and populated results. The filter instrument
should have compact category controls for the existing search groups. Selecting
a category opens an adjacent editor rather than extending one very long left
column. Include:

- a clear primary reference-system search;
- compact summaries of applied filters;
- Reset and Search actions that remain obvious;
- result count/loading/error status;
- a larger result area;
- keyboard and reduced-motion behaviour notes.

Do not change search fields, defaults, API payloads, result data, or ranking.

### 3. Map

Show the production R3F map as a full remaining-viewport workspace. Use compact
edge-mounted controls for:

- Results, Galaxy, and Reference views;
- 2D and 3D projection;
- Regions, Heatmap, Clusters, and Timeline;
- return to Finder, Inspect selected system, About, and Legal.

Legend, selection, and timeline detail may float over the renderer only when
needed. Do not add a planning canvas or allow Map to mutate a Build Plan.

### 4. My Work

Recompose My Work as a useful personal command surface. The primary hierarchy
should be:

1. Continue where I left off;
2. Saved Systems;
3. Plans and Expansion Plans;
4. My Colonies;
5. Personal Telemetry.

Journal Import should be a compact action or drawer inside Personal Telemetry,
not a full-width opening hero. Show one useful populated state using mock data
and one restrained empty state.

### 5. Compare

Show:

- an empty state that explains how to add up to four systems from Finder and
  provides a direct `Open Finder` action;
- a populated side-by-side comparison using realistic mock system data;
- readable metric grouping, winner explanation, confidence, missing-data
  treatment, Inspect, remove, clear, and CSV export;
- a note that build-plan comparison belongs in the Colony Cockpit rather than
  silently turning this screen into a second planner.

Do not invent new comparison calculations.

### 6. Roadmap-backed concept gallery

These screens must carry a visible `Concept - not implemented` label and must
not call live APIs, create persistence, or imply production availability.

#### B-2 colonisation corridor

Mock a hop-count-only corridor from a start system to a target area, with
waypoints, total hops, maximum jump distance, and inspect hand-offs. Do not show
score-weighted recommendations; B-3 remains gated on scoring and confidence
work.

#### A-3 personal telemetry

Mock how imported journal observations could enrich My Work and Planner with
recently visited systems, observation freshness, event mix, and personal
context. State that identity continuity is required before this can become a
durable cross-device feature.

#### Nebula and POI overlays

Mock optional nebula and community POI layers on Map using clearly synthetic
placeholder data. State that file-level reuse terms, provenance, and bounded
ingestion must be confirmed before implementation.

#### Account and sync direction

Provide one low-detail settings concept showing what could eventually sync:
saved systems, plans, colonies, and personal telemetry. State that accounts,
OAuth, collaboration, and plan sync remain deferred pending an explicit
product and identity decision.

Do not mock mission intelligence, mining/ring recommendations, automatic
canonical journal promotion, or score-weighted corridor ranking as available
features.

## Isolation and implementation boundaries

- Create static interactive mockups only.
- Keep them isolated from canonical routes, hooks, stores, APIs, data engines,
  datasets, production configuration, and deployment.
- Use representative local mock data with obvious `Concept` labels.
- Do not rewrite the real Finder, Map, My Work, Compare, or shared shell during
  this exercise.
- Preserve existing accessibility semantics and demonstrate the intended
  interaction model.
- Do not add platform scaffolding, cron files, environment files, or a new
  package manager.

## Emergent Git and save requirements

1. Fetch the existing `brianstewart377-rgb/ed-finder` repository.
2. Start from `origin/codex/ui-reskin-salvage`, not `main`, `redesign`, an
   imported snapshot, or an empty platform repository.
3. Create exactly the branch `codex/ui-concept-mockups`.
4. Do not initialize a new Git repository, create orphan/unrelated history,
   rewrite history, or force-push.
5. Do not push or merge directly into `main` or
   `codex/ui-reskin-salvage`.
6. Preserve `frontend/yarn.lock` and use Yarn 1.22.22.
7. Do not add `.emergent` files, platform cron files, deployment
   configuration, generated environment files, or unrelated scaffolding.
8. Change only the isolated mockup implementation and this design
   documentation when necessary.
9. Do not deploy.
10. Before reporting completion, run:

```bash
git fetch origin
git merge-base --is-ancestor origin/main HEAD
git merge-base --is-ancestor origin/codex/ui-reskin-salvage HEAD
```

Both commands must exit successfully. If either fails, stop and report the
problem. Do not create replacement history.

Return:

- exact branch name;
- commit SHA;
- GitHub branch URL;
- changed-file list;
- preview instructions or URL;
- typecheck, lint, test, and build results;
- confirmation that both ancestry checks passed.

## Review decision after the mockups

The mockup gallery is a decision aid. The owner and Codex will review it, choose
the strongest patterns per workspace, and write a bounded production
implementation plan. No concept becomes roadmap authority or production scope
merely because it appears in the gallery.
