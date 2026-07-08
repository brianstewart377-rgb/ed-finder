# Stage 25B - Evidence Language And Visual-System Primitives

## Status

Stage 25B is `implemented_in_this_pr_pending_review`.

This checkpoint applies a small shared visual and evidence-language layer to the
live `Inspect` and `Plan` surfaces so the player can move through:

`Explore -> Inspect -> Plan -> Review Evidence`

and still recognize the same product hierarchy, context language, and truth
boundaries.

It does not claim Stage 25B is complete until the implementing PR is reviewed
and merged.

## Purpose

Stage 25B exists to make ED-Finder more coherent as a product without changing
planner logic, evidence contracts, runtime routing, or backend authority.

The goal is not a cosmetic reskin.

The goal is that:

- the current workspace is obvious;
- the selected system is obvious without overemphasising raw ID64;
- evidence answers the player-first questions first;
- technical truth remains available and explicit;
- canonical planner truth stays visibly separate from report-only evidence.

## Live Surfaces Touched

Stage 25B touches exactly these live user-facing surfaces and narrowly related
presentation helpers:

- `frontend/src/features/system-detail/SystemDetailModal.tsx`
- `frontend/src/features/colony-planner/WorkspaceHeader.tsx`
- `frontend/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- `frontend/src/features/colony-planner/WarehouseEvidenceCard.tsx`
- `frontend/src/components/SemanticStatusBadge.tsx`
- `frontend/src/components/WorkspaceContextHeader.tsx`
- `frontend/src/components/EvidencePostureSummary.tsx`
- `frontend/src/lib/evidenceLanguage.ts`

No shared selected-system state, route rewiring, query-key changes, planner-rule
changes, or evidence-contract changes are authorized here.

## Primitives Introduced And Reused

Stage 25B introduces only the smallest reusable primitive set needed for
coherence:

1. `WorkspaceContextHeader`
   - reusable journey/workspace identity;
   - primary title plus supporting context;
   - selected-system identity block;
   - optional status content;
   - optional actions;
   - responsive heading hierarchy.
2. `SemanticStatusBadge`
   - visible text labels for semantic state;
   - colour is supplementary only;
   - reusable for evidence, workspace status, caution, canonical, observed, and
     unavailable language.
3. `EvidencePostureSummary`
   - player-first evidence summary layer;
   - explicit next action and canonical planner boundary;
   - accessible progressive disclosure for technical detail.
4. existing tokens and styles reused
   - existing palette from the frontend Tailwind config;
   - existing panel rhythm and spacing conventions;
   - no parallel design system and no broad theme replacement.

## Evidence-Language Rule

Stage 25B preserves the Stage 25A evidence-language rule:

- evidence must be player-facing first;
- the first visible layer must answer what the evidence state is, what it means
  for planning, what the player should do next, and whether planner truth
  remains canonical;
- the wording must remain technically honest and must never hide uncertainty,
  freshness, provenance, report-only status, bounded or incomplete coverage,
  unavailable state, unknown state, or non-canonical status;
- player-facing wording must never convert a weak, unavailable, observed,
  bounded, or report-only signal into apparent canonical truth.

The implementation language model is:

- `Available`: selected-system evidence is available as review context. Your
  plan still uses canonical planner data.
- `Unavailable`: no approved selected-system evidence is linked here. Continue
  planning with canonical data.
- `Not evaluated`: evidence was not safely evaluated in this runtime. Continue
  with canonical planner data; no staging conclusion is available.
- `Unknown`: selected-system evidence has not been established. Continue with
  canonical planner data.

## Progressive-Disclosure Rule

Stage 25B moves dense provenance and contract detail behind an accessible
progressive-disclosure control rather than deleting it.

The first layer remains readable normal body copy.

The disclosure layer retains technical truth where present, including:

- freshness;
- source class;
- provenance and source run;
- report-only status;
- selected-system-only scope;
- bounded or incomplete coverage;
- unavailable or unknown state;
- non-canonical status;
- source-posture fallback;
- manual-review requirement;
- bounded staging detail and row limits.

Technical disclosure remains keyboard accessible and readable without relying on
colour.

## Preserved Truth Boundaries

Stage 25B preserves these boundaries explicitly:

- Colony Planner remains canonical live;
- `simulation-preview` remains `reusable_but_unwired`;
- available evidence remains report-only where the contract requires it;
- canonical planner truth remains visibly separate from evidence;
- selected-system evidence remains bounded and not full coverage where the
  contract says so;
- unavailable, unknown, and not-evaluated states do not imply false or empty
  canonical conclusions;
- dedicated contract preference remains in place;
- provenance fallback remains in place only when the dedicated endpoint cannot
  be read.

Stage 25B does not alter:

- evidence-envelope API types;
- governed source semantics;
- planner data model;
- planner scoring, role logic, build-plan persistence, or selected-system
  routing.

## Accessibility And Visual Rules

Stage 25B follows the restrained cockpit-oriented visual-system refresh defined
in Stage 25A.

It applies these rules:

- one readable hierarchy: workspace context -> primary decision/action ->
  content -> evidence/supporting detail;
- explicit text alongside semantic colour;
- visible focus rings on actions and disclosure;
- reduced motion remains respected;
- responsive layouts remain intact;
- dense evidence surfaces avoid added blur or decorative glass;
- evidence does not look "good" merely because it is coloured.

## Relationship To Stage 25C

Stage 25B deliberately stops before Stage 25C.

It creates reusable presentation primitives only.

It does not introduce shared selected-system state, unified cockpit navigation,
route ownership, or simulation-preview wiring. Those remain Stage 25C or later
work.

## Explicit Exclusions

Stage 25B does not:

- redesign the map;
- alter `GalacticMap`;
- add map layers, overlays, zoom work, renderer work, or map-plan coupling;
- wire `simulation-preview` into live routes;
- start Stage 25C, Stage 25D, or Stage 25E implementation;
- authorize or run Stage 19 commands;
- run database commands or perform database writes;
- authorize canonical apply;
- authorize rebaseline;
- enable scheduler, service, or timer work;
- acquire source data;
- add backend endpoints;
- alter navigation behaviour beyond the existing actions already wired;
- alter planner logic or persistence;
- surface secrets, private URIs, or unsafe internal detail.

Stage 25B does not redesign the map.

Stage 25B does not alter `GalacticMap`.

Stage 25B does not wire `simulation-preview` into live routes.

Stage 25B does not authorize or run Stage 19 commands.

## Validation Plan

Validation for this checkpoint should include:

- strict project-state resolver;
- focused frontend tests for `SystemDetailModal`, `ColonyPlannerWorkspace`,
  `WarehouseEvidenceCard`, and the new shared primitives;
- evidence bridge / contract-preference behaviour checks;
- Stage 25A baseline governance tests;
- Stage 25B implementation governance tests;
- frontend typecheck;
- frontend lint if the documented command still exists;
- manual visual review in the live app when available.

Manual review should confirm:

- Inspect and Plan feel like the same product journey;
- selected-system context is clear on both surfaces;
- player-first evidence summary is understandable;
- technical disclosure keeps provenance, freshness, report-only, bounded, and
  non-canonical limits explicit;
- disclosure interaction and focus handling remain usable;
- narrow widths do not show obvious overflow failures.

## Authority Boundaries

Stage 24 remains closed.

PR #257 remains the map recovery point and does not authorize a map redesign.

Stage 19 remains separately gated.

This checkpoint does not authorize:

- Stage 19 execution;
- database commands;
- database writes;
- canonical apply;
- rebaseline;
- scheduler enablement;
- source acquisition;
- operator activity.

