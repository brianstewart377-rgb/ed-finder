# Spatial Platform Product Contract

**Status:** Stage 27A authority (2026-08-31)
**Scope:** product and representation contract; no renderer implementation
**Supersedes:** the global Stage 25/26 restriction that the map is only a
secondary Explore surface and may never participate in planning. It does not
supersede Colony Planner ownership of Build Plan persistence or mechanics.

## North star and invariant

The north star is **“If Frontier's Galaxy Map and ED-Finder had a child”**:
familiar Elite-style spatial interaction with ED-Finder's own identity, without
copying Frontier code, assets, or artwork. The Galaxy experience must be useful
and excellent when every ED-Finder overlay is off.

> **THE MAP IS THE CONSTANT; INFORMATION CHANGES AROUND IT.**

Camera, selection, reference, scale, and spatial context survive preset/layer
changes. `REALISTIC`, `FINDER`, `COLONISATION`, `POWERPLAY`, `EXPLORATION`, and
`ROUTES` are named starting presets, not mutually exclusive products. A preset
changes contributions and presentation; it does not replace the map.

Commander History / Journal is a cross-cutting product capability, not merely
an Exploration importer, raw-event viewer, or map preset. Exploration is one
major interpretation of Commander History and remains a first-class user goal.

## Three complementary Commander History surfaces

These are views over shared commander-scoped facts, not duplicated databases:

| Surface | Product responsibility |
|---|---|
| **Journal page** | Meaningful history, statistics, records, filters, expeditions and chronology; useful without a map. Raw events may be inspected, but are not the primary UX. |
| **Galaxy Map** | Where visits, discoveries, observations, records and expeditions happened, including bounded area summaries and route display/replay. It is not a separate Journal map. |
| **System Map** | What the commander observed, scanned, mapped or sampled at system/body level, with personal context distinct from catalogue knowledge. |

EDSM/EDSM-NET is product/research inspiration only for commander-history,
statistics and journal-event breadth. It is not mechanics authority, or a code,
asset or UI source. ED-Finder contracts derive from Elite Journal semantics and
verified repository evidence.

## One journey at three scales

| Scale | Purpose | Transition contract |
|---|---|---|
| Galaxy | Milky Way orientation, systems, regions, routes, spatial queries and comparison | Select a real system, then explicitly **Enter System**. |
| System | Semantic 3D hierarchy of stars, bodies, rings and attached infrastructure | Preserve the exact meaningful Galaxy camera/selection/layers for return. |
| Digital Twin | CRE-owned state, reasoning, evidence, history and uncertainty projected onto System spatial truth | It is a layer/mode of the same System scene, never a competing map or mechanics engine. |

The spatial platform may assist **Explore → Inspect → Plan → Review** wherever
spatial interaction is useful. ED-Finder's Colony Planner/Cockpit remains the
canonical detailed Build Plan workspace and current persistence owner. A map
may compare plans,
select a proposed location, or initiate an explicit planning action. It must
never silently mutate a Build Plan, execute Preview, or portray planned,
inferred, or schematic state as existing fact.

## Galaxy experience

The base scene uses true Elite Cartesian coordinates in light-years and a
recognisable 3D Milky Way form. It supports excellent top-down use, restrained
tilt, pan/orbit/zoom, an ED-like reference grid, useful stars, clear selected
and reference treatments, semantic labels, search/fly-to, picking, routes, and
named regions. Dust, nebulae, glow, and background are ambient only and never
feed gameplay facts.

Semantic zoom uses hysteresis at both entry and exit boundaries:

1. **Wide:** aggregate density, regions, major references and route overview.
2. **Regional:** real and important systems, semantic labels and regional facts.
3. **Local:** colonisation, routes, infrastructure, ranges and spatial queries.
4. **System:** a deliberate transition to a separate `SystemScene`, not ever
   denser Galaxy clutter.

No zoom boundary may cause selection, active route, or a guaranteed highlighted
target to disappear.

## Representation and truth

Every renderable datum carries a representation class and, where factual or
analytical, provenance. Missing evidence remains unknown.

| Class | Meaning | Required treatment |
|---|---|---|
| `AUTHORITATIVE` | Retained factual observation or accepted catalogue fact | Show source/freshness where material; never infer absent values. |
| `DERIVED` | Reproducible analysis from named inputs/rules | Explain inputs/version; renderer does not calculate domain results. |
| `PLANNED` | User or CPE proposal/hypothesis | Visually distinct; never labelled built/current. |
| `SCHEMATIC` | Deterministic layout or unresolved/uncertain association | Explicitly marked; cannot imply position or identity certainty. |
| `AMBIENT` | Decorative, non-factual visual context | Never selectable as a fact and never consumed by mechanics. |
| `UNAVAILABLE` | Schema/API cannot currently represent the property | Do not fabricate a substitute. |
| `UNKNOWN_COVERAGE` | Capability exists but real population was not safely measured | Preserve unknown until an authorized audit proves it. |

The first five are runtime representation classes. `UNAVAILABLE` and
`UNKNOWN_COVERAGE` are audit states and must not be coerced into factual values.

## Domain contributions

- **Finder:** existing filters and Development Scores select/rank results.
  Matches illuminate, score may affect prominence, and irrelevant systems may
  recede. Selected, highlighted and cluster members remain guaranteed. Score
  breakdown is accessible. Viewport/reference may become explicit Finder input.
  The renderer never calculates Development Score. Current evidence:
  `frontend/src/features/map-foundation/feature-handoffs.ts`,
  `apps/api/src/routers/search.py`, and `apps/api/src/mechanics/scoring_rules.py`.
- **Colonisation:** contributions may show authoritative candidates,
  valid/invalid states, expansion ranges, current and planned colonies,
  infrastructure, relationships, alternate paths, comparisons, clusters,
  blockers and route implications. Only domain owners decide validity.
- **Exploration / Commander History:** personal exploration is a first-class,
  sync-key-scoped interpretation of the Commander History fact set, not
  `visitedSystem: boolean` and not universal truth. Galaxy and System
  views share visits, scans/FSS, DSS mapping, retained first discoveries/maps,
  biological/organic and Codex events, timestamps and chronology. Completion is
  explainable (“8 known bodies, 7 scanned, 4 mapped”), never one opaque score.
  Future queries include missed bodies, visited-but-incomplete systems,
  bio-incomplete bodies, unvisited pockets near prior routes, expedition
  playback, and Finder × Exploration. Evidence:
  `sql/042_exploration_facts.sql`, `sql/044_exploration_projections.sql`, and
  `apps/api/src/edfinder_api/routers/exploration.py`.
- **Powerplay:** authoritative contributions may style systems/regions and
  relationships without changing base spatial truth. Existing presentation is
  in `frontend/src/features/map-foundation/PowerplayPointLayer.tsx`.
- **Routes:** routes are typed, ordered contributions with provenance and
  explicit unresolved endpoints. Rendering never becomes route mechanics.

Common explicit actions include **Open System**, **Enter System**, **Set
Reference**, **Find Around Here**, **Colonisation Analysis**, **Compare**,
**Plan From Here**, **Systems Within…**, **Show Cluster**, and **Plot Route**.
Multi-select and spatial queries operate on stable target identities, provide a
bounded result count/truncation state, and remain keyboard and text accessible.
Pointer picking likewise returns the complete stable-order overlap candidate
set up to an explicit positive bound, plus an explicit truncation flag; the
runtime must not discard overlap by choosing one arbitrary target for React.

## Commander History / Journal product contract

The Journal page must support source-qualified statistics and history such as
total jumps, systems visited, distance travelled where derivable,
Earth-like/Water/Ammonia worlds, bodies scanned/mapped, retained first-
discovery/first-map distinctions, biological signals/finds, organic
samples/sales, personal Codex observations, expeditions, regions visited, and
longest/farthest/chronological travel records. Every metric needs an explicit
event/fact derivation and coverage statement. Unknown inputs remain unknown;
accepting an event type does not mean every possible metric is implemented.

Any statistic, record, expedition or filtered result with meaningful spatial
identity can emit renderer-neutral `SpatialContribution`s. “37 Earth-like
worlds found” can highlight their systems; selecting one can highlight the
actual body and personal discovery/scan/map evidence in System Map. A visit
total can show travel history, an expedition can show/replay its observed route,
and personal Codex observations can show their recorded locations. Journal
never builds a parallel map or hands raw events directly to a renderer.

The flow is bidirectional. Galaxy/System Maps can ask Commander History to
summarise a viewport, explicit systems, selected area or route: visited systems,
ELWs/WWs, mapped bodies, biological finds, most recent visit, “what did I
discover here?”, and “what did I miss?”. Answers are bounded, active-commander
scoped, and based only on retained personal records. Missing observations are
not proof that an object does not exist.

Finder remains query/ranking owner and Commander History remains personal-fact
owner. Shared predicates may express “Earth-like worlds I have not discovered”,
“Water Worlds near my 2025 expedition route that I never mapped”, “visited
systems with incomplete scans”, or “biological-signal bodies with no recorded
completion”. Catalogue and personal facts compose through explicit source and
scope boundaries; Finder, Journal and renderer logic are not duplicated.

Commander History is also the personal time dimension. Later stages may support
expedition playback and “show my personal record of this system when I visited”
only from retained timestamped facts. Never interpolate missing observations or
manufacture historical state. Current catalogue knowledge and historical
personal knowledge remain separately labelled.

Game/global Codex knowledge and personal `CodexEntry` observations are distinct.
The former requires an authoritative catalogue source; the latter belongs to
Commander History and may project spatially. One commander's journal never
establishes global Codex truth.

## System Map contract

System Map is first-class architecture now and implementation later. It targets
stars/spectral colours, planets, moons, rings, atmospheres, classes,
landability, stations/outposts/settlements/facilities, current colony
infrastructure, planned infrastructure, and personal exploration state only
where data justifies them.

Literal astronomical scale is not usable. Physical measurements remain factual
in details while renderer-neutral semantic display scaling preserves hierarchy,
selection, and legibility. Display radius/spacing never overwrites physical
radius/distance. Present-time orbital phase must never be invented. If the
required phase and epoch are not trustworthy, placement is deterministic and
`SCHEMATIC`.

Canonical body identity is conceptually:

```ts
type BodyRef = { systemId64: string; bodyId: number };
```

`bodyId` is system-scoped source identity, not assumed globally unique; display
name is never the primary key. ED-Finder currently also has a local
`bodies.id` primary key, while exploration projections may fall back to a
lower-cased name (`sql/044_exploration_projections.sql`); this is an explicit
join gap, not permission to force a match.

### Fidelity ladder

| Level | Highest justified content |
|---|---|
| S0 | System identity and coordinates only |
| S1 | Stellar members/properties |
| S2 | Body hierarchy |
| S3 | Orbital and ring detail |
| S4 | Attached infrastructure |
| S5 | Digital Twin evidence/state/history/planning overlays |

Render the highest justified level per system, but retain per-property truth,
provenance and uncertainty. A system can be S4 overall while one station/body
association remains schematic or unresolved.

## CRE and CPE boundaries

CRE owns mechanics, ontology, evidence interpretation and Digital Twin state.
System Map owns spatial orientation and presentation. ED-Finder orchestrates and
presents; Babylon eventually renders. Today, ED-Finder's Colony Planner owns
Build Plan construction and persistence. CPE is the intended future owner of
plan construction, alternatives, sequencing, validation and persistence only
after an explicit migration is designed, implemented and authorized; this
contract does not claim that migration has happened. Spatial contributions can
carry current ED-Finder plan state, or future chosen plans, proposed facilities,
alternatives, rejected/blocked options and dependencies when their actual
owning contract supplies them.

## Accessibility, reliability and performance

React/DOM owns routing, panels, commands, keyboard/text equivalents, focus and
screen-reader output. Every pickable spatial target has an equivalent semantic
DOM route; colour is never the sole truth distinction. Reduced motion disables
nonessential animation and makes fly-to/transitions bounded and interruptible.

The runtime must survive resize/DPR changes, stale/empty/truncated/error data,
backend initialization failure, context/device loss and resource rebuild.
Selection and camera state are independent and restorable: System selection
continuity must not be inferred from, or collapsed into, camera focus.
Performance acceptance is measured
with production-like 20k and 40k stars, 100k stress, 500k torture, and 1m
extreme diagnostic scenes, in top-down and pitched views. The 1m case is a
diagnostic, not a blanket supported-device promise. WebGPU and WebGL2 results
are reported separately with CPU frame duration, GPU frame duration where a
trustworthy hardware timer exists, streaming latency and truncation, pick
latency, recovery outcome, visible count, draw calls, resources and buffer
bytes. Unavailable GPU timing is reported as unavailable/null, never estimated
from CPU frame duration.

## Deterministic fixture contract

Future fixtures: single-star, binary, multiple-star, moon-rich, ring-rich,
exploration/commander-history-rich, colonised, incomplete-data,
schematic-orbit, CPE-planning, and CRE-Digital-Twin. Synthetic deterministic
fixtures remain mandatory. Optional real commander logs may supplement them
for importer/replay, body identity, timestamp, exobiology and Codex edge cases
only when opt-in, privacy-safe/redacted as appropriate, and never committed
publicly without explicit approval. They must never be the sole corpus. Truth
tests must prove:

- unknown rings are not “no rings”;
- planned is not built;
- schematic position is not authoritative;
- unresolved associations are not forced;
- missing hierarchy is not invented;
- ambient visuals do not become facts;
- personal exploration is not universal truth;
- current catalogue knowledge is not manufactured historical personal truth;
- a personal Codex observation is not global Codex knowledge; and
- display-scaled radius does not overwrite physical radius.

## Stage 27A acceptance and non-goals

Stage 27A accepts this contract, the architecture decision, inheritance matrix,
capability inventory, data-readiness matrix and SELECT-only coverage pack. It
authorizes **Stage 27B only**. It does not add/upgrade Babylon, wire a runtime,
change production map behaviour, remove R3F/Three.js, implement System Map,
change CRE mechanics, implement CPE mechanics, write production data, touch V2
archives, deploy, merge, or begin 27B.
