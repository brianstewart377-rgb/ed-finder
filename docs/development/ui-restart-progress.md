# UI restart: reference-led Finder slice

Last updated: 2026-07-24

## Why this restart exists

The previous concept pass was rejected because it rearranged the existing application into smaller dark boxes without solving the underlying problems. This restart begins from Brian's `SOC.docx` and the embedded Zonar reference image. It is being built in the real application, one reviewable vertical slice at a time.

The reference image is inspiration only. Its assets, branding, copy, and exact composition are not being copied.

## Visual direction

- Treat the application as one designed instrument, not panels floating over wallpaper.
- Keep Elite Dangerous orange as the functional identity colour.
- Use brushed steel and charcoal for structure, seams, rails, and depth.
- Keep the Coalsack nebula as a controlled view or atmosphere inside work areas.
- Use strong hierarchy, asymmetric orange geometry, numbered modules, and deliberate edge rails.
- Avoid cyan re-theming, excessive rounded pills, low-contrast black boxes, and tiny text as the main interface.

## Interaction direction

The Finder filter list is now a compact **filter array**. Every category shows its current selection as a summary. Selecting a category expands a connected editing workspace beside the array using the real controls:

- Reference system
- Quick profiles
- Search radius
- System profile
- Five body-composition groups
- Result ordering

`Done`, the close control, or `Escape` collapses the editing workspace and returns focus to the category that opened it. The results area resizes; the filter workspace does not cover it. On narrow screens the workspace opens below the compact module grid.

## First implementation slice

- [x] Clean branch created from current `origin/main`
- [x] Finder visual foundation and connected instrument layout
- [x] Real filter controls moved into adjacent category workspaces
- [x] Compact category summaries
- [x] Distinct, meaningful filter-module symbols and plain-language module descriptions
- [x] Stronger ED:Finder navigation brand lockup with clearer name/version hierarchy
- [x] Removed decorative Finder eyebrow copy that did not explain a feature or state
- [x] Replaced Finder masthead jargon with clear filter, results, origin, range, and search-status language
- [x] Increased Finder filter title/summary legibility with orange hierarchy, larger type, and stronger contrast
- [x] Corrected Regions mode semantics: all 42 authoritative named regions are available in an explicit selector, the selected region constrains both cluster anchors and matched systems through the cluster-search API, and the result-limit control now says it limits cluster matches rather than regions
- [x] Replaced raw reference-system coordinates in Regions mode with the user-facing consequence: results are ranked by distance from the chosen system
- [x] Renamed Regions mode's slot controls from vague “Colony Worlds / Add World” language to “Economies Needed / Add Economy Requirement”
- [x] Simplified Compare to one route-owned header with a clear 0–6 count and practical empty-state instructions; removed the duplicated shell explanation and unrelated empty selected-system panel
- [x] Replaced the awkward Finder empty-state slogan with the owner-approved “Search the galaxy, find your future.”
- [x] Removed the redundant decorative “01 / 02” Finder header counter; Systems and Regions remain clearly identified by the actual mode controls
- [x] Removed the equally redundant “10 categories” counter from the filter heading instead of merely renaming the old “10 modules” decoration
- [x] Rewrote all ten Finder filter summaries as practical user guidance, removing raw coordinates, inventory counts, and "all counts accepted" wording; active body filters now name their actual constraints
- [x] Increased filter-summary text to a readable size and allowed two-line descriptions instead of truncating useful guidance to an ellipsis
- [x] Rewrote the expanded filter-panel instructions in plain language and removed the last raw reference coordinates from the Systems filter workspace
- [x] Removed the leftover decorative "ED:F / EXPLORATION SYSTEM" footer label and corrected the Regions empty state to ask for economies rather than "colony worlds"
- [x] Keyboard close and focus return
- [x] Reduced-motion treatment
- [x] News ticker removed from the live shell
- [x] Attribution changed to a compact, opaque disclosure
- [x] Typecheck, focused frontend/backend tests, lint, and production build
- [x] Visual QA at 1440×900, 1280×720, and 390×844
- [ ] Brian review of the actual Finder before expanding the direction

Local review URL: `http://127.0.0.1:4182/#finder`

## Brian feedback audit

Checked against the rendered app on 2026-07-23, not only against source changes:

- [x] Decorative Finder `01 / 02` header counter removed; the two real Systems and Regions mode controls remain labelled
- [x] Decorative filter-category total removed
- [x] Ten filter categories use distinct, meaningful symbols
- [x] `ED:FINDER` navigation identity enlarged and given clearer name/version hierarchy
- [x] Vague `EXPLORATION INSTRUMENT`-style chrome removed, including the leftover Finder footer label
- [x] `FILTER ARRAY` / `SCAN OUTPUT` jargon replaced with `SEARCH FILTERS` / `SEARCH RESULTS`
- [x] Filter names use the orange hierarchy and their summaries are larger, wrap to two lines, and explain purpose or current selection
- [x] Collapsed and expanded descriptions use plain language; active body filters name their actual constraints
- [x] Finder origin coordinates replaced with an explanation of how the selected reference is used
- [x] Regions exposes all 42 canonical named regions and lets the user select one or search all
- [x] Regions limits cluster matches rather than implying that only a subset of regions exists
- [x] Regions uses `Economies Needed` and `Add Economy Requirement` consistently, including its empty state
- [x] Compare has one concise header, an explicit 0–6 system count, and direct empty-state instructions
- [x] Finder empty-state slogan changed to `Search the galaxy, find your future.`
- [x] Removed the segmented decorative orange rail from the Finder's left edge; orange edge markers now communicate the active filter instead of forming unrelated broken stripes
- [x] Simplified the expanded filter header to the filter name only; removed the unexplained repeated category number and internal “Active module” label
- [x] Removed the redundant “Reference origin” eyebrow and raised low-contrast secondary text throughout the Finder, including instructions, control notes, range labels, presets, footer help, category indices, chevrons, and results metadata
- [x] Increased the results-header labels and origin/range metadata to a readable size at the compact review resolution; contrast alone was not sufficient at the previous sub-8px rendering
- [x] Removed the numeric prefixes from the Systems/Regions mode controls and restyled them as a larger, rounded premium segmented control with a restrained active-state glow
- [x] Extended the premium radius language across the Finder shell, navigation, filter workspace, controls, results stage, Regions surfaces, and attribution; added continuous diffused orange highlights to the top and left structural edges
- [x] Explained the 0–100 minimum development score directly beside its control, including what the filter removes, the effect of higher values, and that zero applies no minimum

## Deliberately not in this slice

The Finder direction was approved on 2026-07-24 and is now being propagated through Map, My Work, Colony Planner, Compare, and FC Route Planner. Existing data hooks, APIs, route behaviour, and result actions remain unchanged. Regions mode exposes the backend `galaxy_region_id` filter through a validated request field and an explicit Finder control; selected-region scope is applied to cluster anchors and their returned slot matches.

## Cross-site design rollout

- [x] Reviewed the supplied map references before continuing the renderer: `klightspeed/EliteDangerousRegionMap` for canonical 42-region geometry, EDDiscovery for independent galaxy/region/grid/star/path layers, zdam's EDGalaxyMap for point-cloud selection and camera interaction, Elite Dangerous Warboard for fit/pan/zoom/reset and graceful API fallback patterns, and ED Codex as an API directory rather than a single map-data source
- [x] Replaced the camera-tweaked line diagram with distinct map surfaces: a layered whole-galaxy chart, an origin-centred distance chart, and a Finder-result chart
- [x] Added an ED:FINDER-native diffuse galactic light field and deterministic star cloud behind the authoritative region boundary geometry; no third-party visual asset was copied
- [x] Replaced the faux orthographic tabletop with a true perspective camera for 3D and plotted Finder systems using their real galactic Y coordinate where available
- [x] Corrected the local map scale clamp from 2 LY per pixel to 0.01 LY per pixel so local 20-200 LY searches use the available canvas instead of collapsing into a few pixels
- [x] Added adaptive, labelled distance rings and a clear origin marker to Finder-result and Origin-system modes
- [x] Promoted Finder systems from faint background dots to primary orange markers with glow, collision-aware names, stacked labels for identical coordinates, and a selected-system state
- [x] Fixed the zero-results viewport lifecycle so Whole galaxy remains available before a Finder search and fits the live canvas rather than the 1280x720 fallback
- [x] Kept the visible Finder-system count stable when a result is selected instead of subtracting the guaranteed/selected point from the displayed total
- [x] Rendered-browser QA completed at the active 1105x858 review resolution for Finder results, Whole galaxy, and Origin system in both 2D and 3D using the live three-result Sol search; HIP 22460 selection and Inspect hand-off were also checked
- [x] 15 focused Map foundation tests passed; focused ESLint and full frontend typecheck passed after the renderer rebuild
- [x] Promoted the Finder’s warm charcoal surfaces, premium rounded corners, top/left orange diffusion, stronger secondary text, and enlarged ED:FINDER navigation identity into the shared panel and navigation primitives
- [x] Removed empty global route-context banners from Map and FC Route Planner so their route-owned headers are no longer duplicated
- [x] Replaced the implementation-facing “R3F galaxy map” heading with “Interactive galaxy map”
- [x] Removed stage/build jargon from Map, clarified its purpose, and replaced My Work journal-import staging jargon with user-facing storage, preview, privacy, and sync-key language
- [x] Simplified FC Route Planner and Colony Planner guidance and removed Compare’s redundant eyebrow label
- [x] Route-specific visual refinement and rendered QA for Map, My Work, Colony Planner, Compare, and FC Route Planner at the active 1105×898 review resolution
- [x] Finder regression check after the shared design-system rollout
- [x] 86 focused frontend tests, typecheck, ESLint, and production build after the cross-site rollout
- [x] Simplified the Map from five stacked chrome bands to one map workspace with a compact header, essential view controls, collapsible layers/legend, and an integrated empty canvas
- [x] Repaired the Galaxy view fit using the authoritative region geometry, removed the empty inspector column, and suppressed colliding region labels at the review resolution
- [x] Renamed the Map camera choices to plain-language “Finder results”, “Whole galaxy”, and “Origin system”, with concise hover explanations
- [x] Restyled the Map’s Back/Inspect actions as clearly separated premium rounded controls, with a polished neutral Back surface and a legible orange Inspect state
- [x] Matched the Map’s selected view controls to the Finder’s readable active state with bright white type, stronger weight, orange depth, and a diffused glow
- [x] Repaired both Map projections: fixed viewport measurement for the 2D fit, expanded the galaxy-scale 3D clipping range, and added a centre-locked 54° warm tabletop plane with spatial grid cues
- [x] Removed the visible “floating grid card” from 3D, enlarged both projections, extended the tabletop beyond the camera frame, softened its grid, and strengthened perspective-label legibility
- [x] Replaced the reconstructed Whole Galaxy 2D surface with the complete MIT-licensed `RegionMap.svg` from `klightspeed/EliteDangerousRegionMap`, retained its 42 canonical regions and authored label placement, included the upstream licence, and added visible Ben Peddell/MIT attribution
- [x] Locked the Whole Galaxy 2D chart to the galactic centre with zoom-only interaction; Whole Galaxy 3D now uses orbit and zoom rather than allowing the galaxy to be translated away
- [x] Replaced the tight procedural spiral in the 3D backdrop with a diffuse barred-disc treatment and made the chosen region-label set stable while the camera orbits
- [x] Corrected the source-map coordinate projection for Finder overlays: the source lookup rows run bottom-to-top, so galactic Z is inverted for SVG/CSS Y; the live Sol/Alpha Centauri results now render in Inner Orion Spur rather than Formorian Frontier
- [x] Stabilised the idle Finder result array so parent-shell updates no longer reset an empty Whole Galaxy view back to Finder results during map interaction
- [x] Rendered-browser QA at the active 1105×898 review resolution confirmed the exact SVG and attribution, all-region label layout, locked-centre 2D drag, centred 2D zoom, persistent Whole Galaxy selection, 3D orbit with stable labels, and live three-result Finder marker placement
- [x] 13 focused frontend tests passed for the authoritative map, production map, parity logic, and Finder result stability; focused ESLint and full frontend typecheck passed
- [x] Updated the Review Lab Finder journey for the approved compact filter workspaces: it now opens Settlement & economy, chooses the colony-status fixture, closes the workspace, and runs the search through visible controls
- [x] Repaired the 1024×768 Finder breakpoint that collapsed the filter panel behind the results stage; the compact two-column module grid now receives its own height and the results stage begins below it
- [x] Rendered-browser QA at 1024×768 and 390×844 confirmed all ten filter modules remain visible and usable, the expanded workspace is readable, and neither viewport has horizontal overflow
