# Stage 25C Slice 2 - Selected-System Context Spine (Contract)

## Status

Stage 25C is not complete.

- **Slice 1 — product shell and navigation hierarchy:** `complete_merged` in PR #262.
- **Slice 2 — selected-system context spine:** `contract_defined_pending_implementation`.
- **Later Stage 25C slices:** pending their own bounded implementation and verification.

PRs #269 and #271 delivered bounded follow-on Plan work, but they did not complete
this selected-system continuity slice. This contract is the controlling document for
Stage 25C Slice 2. It corrects the historical Slice 1 pending-review wording in
`stage-25c-product-shell-shared-context-contract.md` for this slice's status and
scope; it does not declare Stage 25 or Stage 25C complete.

This is a contract-and-test checkpoint only. It authorizes no runtime implementation,
backend change, database work, source acquisition, infrastructure, deployment, or
Stage 19 activity.

## Purpose

Make one selected system persist honestly across the normal player journey:

```text
Explore → Inspect → Plan → back to Explore
```

The player must be able to tell which system is in focus without a System Detail modal
being open, without silently creating a draft, and without a saved candidate,
comparison membership, or existing project being mistaken for the selected system.

## Scope

This slice defines:

- the selected-system state model and its ownership;
- the distinction between selection, inspection, saving, comparison, and planning;
- route semantics for selected context, Inspect, and Planner entry;
- context transition, deep-link, unavailable-data, and invalid-link behaviour;
- the no-active-plan state;
- the minimum selected-system context bar;
- the acceptance and future runtime-test matrix.

It does **not** implement the state model or redesign the Planner.

## Terms And State Boundaries

### Selected system

The **selected system** is the single system currently in player focus for the
Explore, Inspect, or Plan journey. It has an ID64, a resolution state, and a route or
explicit user-action source.

A selected system is not merely the last result card rendered, the last modal opened,
or the system belonging to a previously active project.

### Inspection state

**Inspection state** controls whether System Detail is open as a contextual modal.
It is a presentation state layered on top of selected-system context. Opening Inspect
selects the system; closing Inspect must not necessarily clear the selected system.

### Saved candidate

A **saved candidate** is membership in the scoped saved-system/Watchlist model. It is
not selection. Saving or unsaving a system must not change selected-system context.

### Compared system

A **compared system** is membership in the comparison set. It is not selection.
Adding or removing a system from comparison must not change selected-system context.

### Active planner project

An **active planner project** is a specific local draft or project associated with a
system. It is not selection by itself. A project route establishes selected context
from its route system ID only after the route has been resolved honestly.

### Required separation

The implementation must not silently infer one state from another:

| State | Does it select the system? | Can it create a draft? | Can it open System Detail? |
| --- | --- | --- | --- |
| Result card visible | No | No | Only after explicit Inspect action |
| Saved candidate membership | No | No | Only after explicit Inspect action |
| Comparison membership | No | No | Only after explicit Inspect action |
| System Detail inspection | Yes | No | Yes, by definition |
| Planner system route | Yes | No | No modal by default |
| Planner project route | Yes, after route resolution | No | No modal by default |
| Explicit Create draft action | Keeps selection | Yes | Does not require a modal |

## Selected-System Resolution Model

The future runtime model must expose one of these mutually exclusive states:

- `none`: no system is selected by the current route or explicit player action;
- `loading`: a route or explicit action has requested an ID64 and its identity is
  being resolved;
- `available`: the selected ID64 resolved to a usable system identity;
- `invalid`: the route supplied an invalid or malformed system ID;
- `unavailable`: a syntactically valid ID64 could not be resolved or is unavailable
  to the current product surface.

A transition into `invalid` or `unavailable` must clear any previous available
selected-system identity. The UI must never retain a prior system name, evidence
posture, or project as if it belonged to the failed destination.

The selected-system context must be route-owned for deep links and refreshes. In-memory
state may make same-session transitions responsive, but it must never override the
truthful route destination after a direct link, refresh, or browser history action.

## Route Contract

The implementation must introduce a non-modal route form for selected-system context.
The exact parser implementation is deferred, but the logical route grammar is fixed:

| Logical route | Selected system | System Detail modal | Planner project |
| --- | --- | --- | --- |
| `#finder` | none | closed | none |
| `#finder/context/{id64}` | `{id64}` | closed | none |
| `#finder/system/{id64}` | `{id64}` | open | none |
| `#system/{id64}` | `{id64}` | open through the external Inspect alias | none |
| `#colony-planner/system/{id64}` | `{id64}` | closed | no active project implied |
| `#colony-planner/system/{id64}/project/{projectId}` | `{id64}` after project-route resolution | closed | `{projectId}` when it belongs to `{id64}` |

`#finder/context/{id64}` is required because the existing modal route means “open
Inspect.” Reusing that route for a Plan → Finder hand-off would reopen a modal the
player did not request.

A later route syntax may add an equivalent explicit selected-context form only if it
preserves every semantic distinction in this table and retains stable deep-link
behaviour. It must not overload `#finder/system/{id64}` to mean both “selected” and
“modal closed.”

## Required Transitions

### Explore → Inspect

An explicit Inspect action from Finder, saved systems, comparison, or another player
surface:

1. sets selected-system context to the requested ID64;
2. opens System Detail only after that selection;
3. keeps the selected system visible through the modal context;
4. resolves the requested system or enters an honest `invalid`/`unavailable` state.

### Closing Inspect

Closing System Detail from `#finder/system/{id64}` must transition to the non-modal
selected-context route for the same ID64. It must not silently discard the selection
or leave the modal open through a route mismatch.

### Inspect → Plan

The explicit Plan or Start plan action carries the same selected ID64 into the Planner
route. It must not open a second System Detail modal over the Planner. Whether a draft
exists is a separate decision handled by the no-active-plan contract below.

### Plan → Finder

The Planner’s return-to-Finder action must preserve the selected ID64 through the
non-modal Finder context route. Finder must show the selected-system context bar and
must not reopen System Detail unexpectedly.

### Direct Planner links

A direct Planner link establishes selected-system context from its `{id64}`. The
Planner must resolve that route before showing system-specific identity, evidence
posture, or project details. A project ID does not permit the Planner to substitute a
different system ID or preserve the last locally viewed plan.

### Explicit replacement

Opening Inspect or Planner for a different valid system replaces the selected-system
context with the new route-owned system. A saved candidate, comparison action, or
project deletion does not replace selection unless it is paired with an explicit
Inspect, selected-context, or Planner navigation action.

## Invalid And Unavailable Direct Links

Malformed, zero, negative, non-finite, or otherwise invalid IDs must enter `invalid`.
A syntactically valid ID64 that fails to resolve must enter `unavailable`.

For either state, the product must:

- show an explicit error in the destination workspace;
- identify that the requested system could not be established without presenting an
  older system as current;
- provide a safe recovery action such as returning to Finder;
- clear stale selected-system context, active-project context, and evidence posture;
- avoid silently navigating to an unrelated Finder result, saved candidate, or last
  plan.

A project route whose project is missing, unavailable, or associated with a different
system must show an honest project-route error. It must not load a previous project,
create a new one, or change the selected system to make the route appear successful.

## No-Active-Plan State

`#colony-planner/system/{id64}` selects the system but does not create a draft.

When the selected system resolves and no active project is specified or available, the
Planner must show:

1. the selected system identity;
2. the concise evidence posture;
3. a clear statement: **No active draft for this system**;
4. an explicit **Create draft** action.

The action may open the existing objective/start-approach choice or a bounded draft
creation step, but it must be explicit. Route entry, selected-system context, saved
membership, and visiting the Planner must never silently create a project or mutate
local plan storage.

## Minimum Context Bar

The selected-system context bar is product shell context, not a replacement for System
Detail or Planner content.

When the selected system is available, it must present information in this order:

1. **System name first**;
2. **concise evidence posture second**;
3. **ID64 as supporting technical detail**, not the leading identity.

The evidence posture must reuse existing truthful evidence language. It must not turn
unknown, unavailable, observed, bounded, report-only, or non-canonical evidence into
an optimistic planning claim.

While loading, the bar may say that the requested system is loading, but it must not
show a previous system name. In `invalid` or `unavailable`, it must present an honest
error state rather than an apparently selected system.

The bar and its controls must remain keyboard reachable, expose a visible focus state,
and use text labels in addition to colour.

## Implementation Boundary

The follow-on implementation PR may change only the client-side selected-system state,
route parser/builder, shell context bar, no-active-plan presentation, and directly
related tests needed to make this contract real.

It must not:

- change colony-planning rules, economics, simulation, recommendations, or facility
  logic;
- wire `simulation-preview` into live routes;
- redesign the map or make it a primary planning surface;
- add a facility browser, mission intelligence, or mining/ring planning;
- add database writes, Stage 19 work, source acquisition, deployment, accounts,
  collaboration, or cloud-sync redesign;
- treat this contract as evidence that Stage 25E, Stage 25F, or the full Stage 25D
  programme is complete.

The implementation is a prerequisite for deeper user-facing Stage 25D cockpit
integration. It does not retroactively invalidate the bounded, already merged work in
PRs #269 and #271.

## Acceptance And Test Matrix

The future implementation PR must provide passing tests and product verification for:

| Area | Required proof |
| --- | --- |
| Desktop shell | 1440x900 and 1280x720 show selected name, evidence posture, and supporting ID64 in the required order. |
| Finder / Inspect mobile | At 390x844, selected-context navigation and System Detail inspection remain usable without lost context. |
| Planner phone-width resilience | At 390x844, a selected system remains truthful, no modal is unexpectedly opened, and the player has a clear exit/back path. |
| Explore → Inspect | Inspect selects the exact system and opens the modal. |
| Closing Inspect | Closing the modal preserves selected context through the non-modal Finder route. |
| Inspect → Plan | The exact selected ID64 reaches Planner without opening System Detail over it. |
| Plan → Finder | Finder retains selected context without reopening System Detail. |
| Direct selected-context link | A valid direct Finder context route resolves the requested system and keeps the modal closed. |
| Direct Planner link | A valid Planner route establishes selected context from its system ID. |
| Invalid / unavailable link | The destination shows an honest error and does not retain stale context. |
| No active plan | Planner shows selected system plus explicit Create draft; no project is silently created. |
| Project mismatch / missing project | The route fails honestly without loading an unrelated project or selection. |
| State separation | Saving, unsaving, comparing, uncomparing, and deleting a project do not silently select a system. |
| Keyboard | Context bar, disclosure, modal close, and recovery actions are operable via keyboard with visible focus. |

## Closeout Condition For This Contract Checkpoint

This documentation checkpoint is complete only when the contract is indexed by the
Stage 25C parent contract, the static documentation tests cover its required state and
route rules, and no runtime change is claimed as part of this PR.

The next implementation PR must begin from current live Git and GitHub state, read
this document and the parent Stage 25C contract, and keep its runtime scope within the
Implementation Boundary above.