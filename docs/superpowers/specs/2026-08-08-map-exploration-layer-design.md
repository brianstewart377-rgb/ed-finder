# Personal Exploration Layer on a Generalized Map Substrate — Design

## Status

Proposed. Not yet authorized for implementation — this is a design document, not a
roadmap authorization. Per `docs/ROADMAP.md`'s own rule, the roadmap remains the
single source of truth for what happens next; this design's roadmap-amendment
section describes what that file would need to say, but does not itself amend it.

## Context

The owner wants the galaxy Map to become the shared visual home for the app: not
just colonisation-adjacent data (Finder results, Compare, System Detail, saved
systems — already wired in Stage 26D), but also a new domain, personal Elite
Dangerous exploration data (systems visited, bodies scanned/mapped, discoveries,
exobiology, Codex entries), rendered as switchable layers on the same map.

This is deliberately **not** a proposal to make the map a planning surface. Colony
Cockpit remains the sole canonical planning workspace. Exploration is a read/display
feature that lives entirely in the `Explore` step of the product journey
(`Explore -> Inspect -> Plan -> Simulate/Sequence -> Review Evidence -> Export/Share`).
Nothing here mutates a Build Plan, runs Preview, or promotes evidence to canonical
truth. The existing hard boundary — "planner-map fusion remains prohibited" — is
unaffected.

## Goals

- Generalize the map's existing typed layer/adapter pattern (already used by Finder,
  Compare, System Detail, Cluster Search, and read-only Planner state since Stage
  26D) into an explicitly documented, reusable on-ramp for *any* Explore-journey
  feature — not a special case for those five features.
- Ship a first concrete second consumer of that generalized pattern: a personal
  exploration data layer, covering the full set of exploration facets the owner
  asked for (not a bounded starter slice).
- Make the map feel alive: animated/pulsing markers, a self-drawing travel trail,
  and a smooth zoom transition from abstract points to detailed stars — reusing
  patterns the map already has precedent for (the existing live-activity-pulse
  layer style; the existing camera-distance-driven rendering in `SceneContents.tsx`).

## Non-Goals

- No accounts/auth system. Frontier's own OAuth2 (Companion API) is the intended
  real identity backend; the owner has applied but is not yet approved. This design
  does not build a parallel login system and does not block on that approval.
- No change to Colony Cockpit's ownership of planning, Preview, or Build Plan
  mutation.
- No canonical/shared-truth promotion of exploration data. It is personal display
  data, never treated as a claim about what's true for other users.
- No community/global exploration layer (e.g. "systems scanned by anyone") in this
  design. EDDN is structurally unsuited to personal attribution (see Data Sources)
  and a global layer is a separate, later idea if wanted.

## Roadmap Amendment Needed

Before implementation, `docs/ROADMAP.md` needs a short addition stating: the map's
typed scene/layer boundary (from the Stage 26 contract) is the standing pattern for
any Explore-journey feature that wants map presence, not a closed list. This follows
the same amendment pattern already used for the Stage 26A contract
(`stage-26a-next-generation-map-foundation-contract.md`'s "Amendment scope
(2026-08-08)" notes). It does not reopen or change the "Map remains a secondary
Explore surface" / "Colony Cockpit remains canonical planning" posture.

## Identity Model

Exploration data needs to know whose data it is without a login system:

- On first use, the browser generates a random opaque ID (a UUID) and persists it
  in `localStorage`.
- Exploration facts written to the backend are tagged with this ID as an
  `owner_key` column — no name, email, or Frontier identity attached.
- This does not sync across devices/browsers. Accepted trade-off (owner is
  currently the only user).
- When Frontier OAuth2 access is approved, the real Commander identity gets
  attached to an existing `owner_key` as an additive migration (linking, not
  replacing) — this design's schema must not need to change shape for that to
  happen later.

## Data Sources

Three candidate sources were evaluated:

1. **Local journal files (primary).** The existing journal-import flow (client-side
   parse via `journalImportWorker.ts`, staged server-side) is extended with
   exploration event types: `Scan`, `FSSDiscoveryScan`, `SAASignalsFound`,
   `FSSBodySignals`, `CodexEntry`, and related mapping/discovery events. This is
   the richest source (scan depth, mapped status, exobiology genus, Codex category)
   but only covers however far back the player's kept journal files go — Frontier
   journals are typically only retained for recent sessions unless manually
   archived.
2. **EDSM flight log (optional backfill).** EDSM's `api-logs-v1/get-logs` endpoint
   returns a specific commander's system-visit history, gated by that player's own
   EDSM API key (from their EDSM account settings) — verified via EDSM's public API
   docs, not guessed. Many commanders already have months/years of history in EDSM
   from EDMC/EDDiscovery sync. This design allows an optional "import EDSM history"
   step using the player's own key, to backfill the visited-systems trail (dots,
   trail, heat map) further into the past than local journals allow. EDSM cannot
   supply scan/mapped/exobiology/Codex detail — only system visits with timestamps.
3. **EDDN — explicitly excluded from personal tracking.** Verified via EDDN's own
   developer docs: the relay obfuscates the uploader identity specifically to
   prevent tracking individual players. It is structurally unsuited to "where has
   this specific player been" and stays reserved for the community-facing ingestion
   the app already does (`apps/api/src/ingest/eddn_client.py`). Not part of this
   design.

## Data Model

All exploration facts are personal (`owner_key`-scoped), never promoted to
canonical/shared truth, and trusted directly as first-party data from the player's
own journal/EDSM account — no review/comparison-engine step. (The existing
`observations/review` engine exists to compare a player's reported outcome against
an independently-computed engine prediction, e.g. simulated CP/build state; there is
no equivalent "predicted exploration state" to compare exploration facts against, so
that engine does not apply here.)

Tracked facets, each rendered as its own toggleable map layer:

- **Systems visited** — timestamped; rendered three ways from the same data: dots,
  a chronological trail line, and a visit-density heat map (reusing the existing
  heat-map-style overlay pattern from the map's freshness/age layer).
- **Bodies scanned** — basic scan vs. detailed surface scan, tracked separately.
- **Bodies mapped** — the deeper probe/mapping action, distinct from scanning.
- **First discovered / first mapped** — flags the game itself reports.
- **Exobiology signal finds** — species/genus found per body.
- **Codex entries** — the game's own discovery catalogue (geological sites,
  guardian ruins, etc.).

## Backend Storage

A new domain (mirroring `journal_import/`'s shape, e.g. `apps/api/src/exploration/`)
with its own staging table(s), separate from colonisation tables — different kind of
data, different lifecycle, no shared-truth implications. `owner_key` is indexed for
per-player lookups. EDSM-sourced visit rows are tagged with their source distinctly
from journal-sourced rows, since they carry less detail.

## Map Layer Integration

Exploration layers plug into the map's existing typed `MapSceneDescriptor` layer
system (the same mechanism already serving Finder/Compare/System Detail/Cluster
Search/Planner hand-off since Stage 26D) — new layer types, not new renderer
architecture.

## Visual / Interaction Design

Settled via the visual-companion mockup review in this session:

- **Markers:** pulse/glow gently, reusing the map's existing live-activity-pulse
  animation style — not static dots.
- **Trail line:** draws itself in chronological order like a flight path unfolding,
  once or twice on load/update, then settles into a permanently fully-drawn static
  line (not a perpetual loop).
- **Zoom-to-detail:** smooth crossfade — abstract points fade out while detailed,
  glowing stars fade/grow in over the zoom range, rather than an instant swap or a
  visited-systems-first priority reveal. Matches the in-game galaxy map's feel most
  closely of the three options compared.

## Error Handling

Malformed or unexpected journal/EDSM data is skipped with a visible note to the
user, not silently dropped and not a hard failure of the whole import — matching
the existing journal-import behavior.

## Testing Strategy

Real Elite Dangerous journal event samples and real EDSM API response shapes are
used as test fixtures (verified against source documentation, not guessed) — same
discipline already applied to the Colonisation journal-import event types added
this session. A broken parser must fail a test before it ships.

## Open Questions / Future Work

- Exact EDSM API response shape and rate-limit handling (360 requests/hour) need
  verification at implementation time against EDSM's live docs.
- Whether/how a future community-facing "global exploration" layer (via EDDN, not
  personal) gets built is explicitly out of scope here and untouched by this design.
- Cross-device sync remains blocked on Frontier OAuth2 approval; no workaround is
  in scope.
