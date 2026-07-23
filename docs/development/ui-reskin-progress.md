# UI reskin progress

Last updated: 2026-07-23

## Status

The first shared-shell, Finder, and Map reskin pass is under local review on
`codex/ui-reskin-salvage`. It is based on current `main`; it is not deployed
and does not alter the API, datasets, map engine, feature flags, or production
configuration.

## Source and recovery

The initial visual pass was produced in Emergent and saved to the remote
`redesign` branch. Emergent saved that branch with unrelated Git history and
also added platform cron files while deleting `frontend/yarn.lock`.

Only the legitimate React changes were recovered onto a clean branch based on
`origin/main`. The Emergent platform files and lockfile deletion are excluded.

## Implemented

- Shared navigation switches to the compact route/menu presentation below
  1380px, preventing route labels from overlapping at common laptop widths.
- Finder has an always-visible search status, a collapsible desktop filter rail,
  grouped filter disclosures, and a mobile off-canvas filter drawer.
- The mobile Finder drawer now traps keyboard focus, closes with Escape, locks
  background scrolling, and returns focus to its opener.
- The production Map uses one compact toolbar for view, projection, layers,
  help, Finder return, and Inspect actions.
- Map legend, source status, timeline summary, and selection details now float
  over the renderer instead of consuming separate rows.
- The production Map renderer fills the remaining viewport below the shared
  navigation without normal page scrolling.
- Map routes omit the legal footer and news ticker; those remain unchanged on
  every non-Map route.

## Visual direction

The pass uses cyan for redesigned navigation states and controls while retaining
the existing ED-orange identity and gold selection/warning treatment. A global
colour-token migration is intentionally out of scope until this layout pass is
approved.

## Validation

- `yarn typecheck`: passed.
- Strict ESLint over all changed TypeScript and test files: passed.
- Focused shell, Finder, legacy Map, and production Map suites: 92/92 passed.
- `yarn build`, including the Stage 26E production-map contract: passed.
- Browser smoke at 1280x720: compact navigation does not overlap; the populated
  production Map has a 549px renderer and document `scrollHeight` equals the
  720px viewport.
- Browser smoke at 390x844: the populated Map stays within the 844px viewport;
  the Finder drawer scrolls internally, traps focus, closes with Escape, and
  restores focus to the Filters button.
- The existing `SearchForm` default-colony-status test fails identically on
  untouched `main` and is tracked separately from the reskin.

## Next review gate

The owner's broader review is captured in
[`ui-reskin-concept-mockup-brief.md`](./ui-reskin-concept-mockup-brief.md).
The next external design pass is an isolated interactive mockup gallery for the
shared shell, Finder, Map, My Work, Compare, and explicitly labelled
roadmap-backed concepts. It must branch from `codex/ui-reskin-salvage`, must not
change canonical runtime behaviour, and must pass both `main` and reskin-branch
ancestry checks before it is accepted.

Review the mockup gallery at desktop and mobile breakpoints. Only after the
owner selects the strongest patterns should the work proceed to bounded
production implementation, a wider token migration, or the remaining
application workspaces.

## Concept gallery branch correction

Emergent initially pushed the isolated mockup gallery directly onto this reskin
branch. Its ancestry and file scope were safe, but the destination did not
match the brief. The gallery has been recovered and reviewed on the dedicated
`codex/ui-concept-mockups` branch. The misplaced gallery commit is reverted
here without force-pushing so this branch and draft PR remain limited to the
production reskin and its design documentation.
