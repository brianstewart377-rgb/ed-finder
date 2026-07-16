# Product Feature Opportunities — Making ED-Finder Well-Rounded

**Date:** 2026-07-15 | **Context:** Product features beyond the evidence/enrichment pipeline

---

## Part 1: What The App Does Today

```
Explore (Finder) → Inspect (System Detail) → Plan (Colony Cockpit) →
Simulate/Sequence → Review Evidence → Export/Share
```

The core journey exists. But it's a **linear, single-player, desktop-only** experience. Here's what would make it rounder.

---

## Part 2: Discovery & Search (Finder Tab)

### 2.1 Save Search Presets
**Problem:** Every time you open Finder, you re-enter the same filters. A player who always searches for "unpopulated systems, G/K stars, 0-500 LY from my carrier, agriculture score ≥ 70" types the same thing every session.
**Solution:** "Save Search" button — names the preset, saves filter state to localStorage. Dropdown to load/delete presets. "Default search" option loads on Finder open.

### 2.2 Search Result Comparison Checkboxes
**Problem:** You can save a system, but you can't compare two candidates side-by-side without opening both details and switching tabs.
**Solution:** Add a checkbox to each search result row. "Compare Selected (2)" button appears when 2-5 checked. Opens a side-by-side comparison modal showing: economy scores, body counts, distance to bubble, nearest colonised system, star type, landable count, estimated slots.

### 2.3 "Colonisation Candidate" Quick Filter Preset
**Problem:** New players don't know what filters to use to find colonisable systems.
**Solution:** A "Colonisation Candidates" one-click preset button that applies: population=0, has_body_data=true, within 16 LY of populated space, sort by development score. Takes the guesswork out.

### 2.4 Search Result Map Thumbnail
**Problem:** The search result list is text-only. You can't see where a system is in the galaxy without clicking through.
**Solution:** Tiny 2D positional dot next to each result showing its location relative to the reference system (like a minimap). Click to zoom in. Gives spatial context instantly.

---

## Part 3: System Detail (Inspect Modal)

### 3.1 "Similar Systems" Section
**Problem:** You found a good system. What else is like it?
**Solution:** A "Similar Systems" strip at the bottom of System Detail showing 5 nearby systems with similar economy scores, body counts, and star types. "If you like this, you might also like..."

### 3.2 System Notes Persist Across Sessions
**Problem:** You have notes about a system but they're only visible when you inspect it.
**Solution:** Notes already exist (`/api/v2/systems/{sync_key}/{id64}/note`). Surface them on the My Work saved systems card and in search results with a note icon indicator. "Has notes" badge.

### 3.3 "Share System" Link
**Problem:** You want to show a system to a squadron mate. You send a screenshot.
**Solution:** Copy a shareable URL like `ed-finder.app/s/10477373803` that opens the app directly to that system's detail. The `/s/{id64}` route already exists on the backend for OG cards — extend it to redirect the frontend.

### 3.4 Body Quality Radar Chart
**Problem:** The body list is a table. Hard to scan for quality at a glance.
**Solution:** A small radar/spider chart showing: landable count, terraformable count, ELW/WW/AW count, ring count, bio signals, geo signals. Six axes, one glance. The data is already there — just needs visualization.

---

## Part 4: Colony Planner

### 4.1 Construction Cost Estimator (THE KILLER FEATURE)
**Problem:** "What will this colony cost me in commodities and time?" Nobody knows until they start building.
**Solution:** Given a planned facility list, estimate: total commodities by type, approximate credit cost, fleet carrier trips required (configurable cargo capacity), solo vs. squadron hauling time estimates. Uses approximate costs from DaftMav/Mega Guide with a clear variance caveat ("actual requirements vary ~10% per construction instance").

### 4.2 Economy Outcome Preview
**Problem:** The planner shows what you're building but not what the result will be.
**Solution:** An "Economy Projection" panel that predicts: final primary economy, secondary economy, commodity imports/exports, population estimate, system stat scores (Development, Security, Tech Level, Wealth, Standard of Living). Based on documented link mechanics and body type overrides.

### 4.3 "What If?" Scenario Comparison
**Problem:** Should you build Refinery+Hightech or Refinery+Industrial? You can't compare.
**Solution:** Branch the current plan into Scenario A and Scenario B. Each has its own facility list. Side-by-side comparison shows economy outcome, CP usage, commodity costs, and projected stats for both. Pick a winner.

### 4.4 Body Economy Badges
**Problem:** You have to mentally cross-reference body types with their economy bonuses.
**Solution:** Each body in the system map shows a small badge: "Economy: Extraction" (for metal-rich), "Economy: Refinery" (for rocky), etc. Click to see all bonuses that body provides. Makes the body type override mechanic visible.

### 4.5 "Sell Me This System" Summary Card
**Problem:** After building a plan, you want to share or remember WHY you chose this system.
**Solution:** Auto-generate a "System Pitch" card: "HIP 37316 is a G-class system 287 LY from Sol with 5 landable bodies including 1 metal-rich (ringed) and 2 HMCs. It scores 96/100 for Refinery archetype. Estimated 6 orbital + 12 surface slots. Nearest colonised system is 8.2 LY away." One-click copy as formatted text for Discord.

### 4.6 Construction Progress Tracker (from Journal)
**Problem:** Once you start building, the planner doesn't know your progress.
**Solution:** If the player imports their journal, show construction progress inline: "Coriolis Starport: 73% complete. Steel: 10,241/14,076 delivered. CMM Composite: 8,592/11,261. Estimated 2 more fleet carrier loads." The journal has this data every 15 seconds — just needs the import allowlist we already added.

---

## Part 5: Map

### 5.1 Colonisation Layer
**Problem:** The map shows stars. It doesn't show the colonisation wave.
**Solution:** A toggleable colonisation layer: colour uncolonised-but-claimable systems green, colonised systems white, population centres orange. Time slider to replay the colonisation spread. "Frontier boundary" line showing the edge of inhabited space. Already have the data — just needs the visualisation.

### 5.2 "Show Me My Colonies" Filter
**Problem:** You own multiple colonies. Where are they on the map?
**Solution:** If the player has imported their journal or manually tagged their colonies, a "My Colonies" filter highlights them in gold on the galaxy map. Shows claim range (16 LY) around each as a translucent sphere.

### 5.3 Faction Territory Overlay
**Problem:** You want to avoid colonising in hostile territory or support your own faction.
**Solution:** Consume faction data (already in the DB from Spansh imports — `system_factions` table) to show faction-controlled space on the map. Filter by faction name. "Show me all uncolonised systems within 16 LY of my faction's territory."

### 5.4 POI Layer
**Problem:** "I want to colonise near something interesting."
**Solution:** Overlay ED Astrometrics GEC/GMP points of interest: tourist beacons, generation ships, Guardian sites, notable nebulae, community landmarks. Hover shows name and description. Toggleable.

---

## Part 6: My Work

### 6.1 Dashboard Summary
**Problem:** My Work is a tabbed list. No overview.
**Solution:** A dashboard view at the top: "You have 3 colonies in progress. 2 expansion plans. 12 saved systems (3 ready to plan). 1 colony reached Established status this week. Your telemetry shows 847 systems visited this month." Quick-glance status.

### 6.2 Colony Timeline
**Problem:** You can't see how your colonies have evolved over time.
**Solution:** A timeline for each colony: "Jun 15: Claimed system. Jun 22: Primary port completed (Coriolis). Jul 3: First refinery hub online. Jul 10: Population reached 50,000." Built from journal event history.

### 6.3 Commodity Shopping List
**Problem:** You're planning 3 colonies and need to buy 500K tons of stuff. What's the combined list?
**Solution:** "Shopping List" view: combines commodity requirements across all active construction projects. "Total Steel needed: 72,488. Total CMM Composite: 56,305." Sortable by commodity. Shows which project needs what.

### 6.4 Export/Import All Data
**Problem:** Your data is locked in one browser.
**Solution:** "Export My Work" button downloads a JSON file of all saved systems, plans, expansion plans, and notes. "Import" restores them. Uses the existing profile sync infrastructure but as a manual file operation for portability. Already partially implemented — just needs a UI.

---

## Part 7: Cross-Cutting UX Improvements

### 7.1 Onboarding Flow
**Problem:** First-time user arrives at a blank Finder. No guidance.
**Solution:** A 3-step onboarding overlay: (1) "Find a system to colonise" → pre-fills colonisation candidate filters, (2) "Inspect it" → opens an example system detail, (3) "Plan your colony" → opens the Colony Planner with a guided "first plan" walkthrough. Dismissable, never shown again after completion.

### 7.2 "What's New" Changelog
**Problem:** Users don't know what features exist.
**Solution:** A small "What's New" bell icon in the navbar. Drops down a changelog of recent features. Auto-shows on first visit after deploy. Populated from commit messages or a manual changelog file.

### 7.3 Keyboard Shortcuts Reference
**Problem:** Power users want speed but don't know the shortcuts.
**Solution:** Press `?` to show a keyboard shortcuts overlay. `F` = Finder, `P` = Colony Planner (last system), `M` = Map, `W` = My Work, `Esc` = close modal, `/` = focus search. The skip-link already added in Stage 25H proves the pattern works.

### 7.4 System Name Autocomplete Everywhere
**Problem:** Some fields require manual system name entry. Other use the RefSystemPicker.
**Solution:** Every system name input in the app should use the same autocomplete component. Consistency reduces cognitive load.

### 7.5 Loading Skeleton Consistency
**Problem:** Different panels have different loading states — some show spinners, some show "Loading...", some flash.
**Solution:** Standardize on a single `<Skeleton />` component with variants (card, table, detail). Every async panel uses it. The app already has `WorkspaceHeaderSkeleton` — extend the pattern.

### 7.6 Empty States With CTAs
**Problem:** Empty states say "No X yet" but don't tell you what to do.
**Solution:** Every empty state includes a call-to-action button. "No expansion plans yet → Create one from Region Search" (and clicking takes you there). "No colonies marked yet → Mark a system as colonised" (and clicking opens the right panel).

---

## Part 8: Features The Competition Has That We Don't

| Feature | Who Has It | Value |
|---------|-----------|-------|
| **Commodity market search** | Inara, EDDB (RIP) | "Where can I buy 5,000 tons of CMM Composite within 50 LY?" |
| **Trade route finder** | Spansh, Inara | "What's the most profitable route from my carrier's current location?" |
| **Ship build sharing** | Coriolis, EDSY | "Here's my fleet carrier pre-load plan — copy it" |
| **Commander profile** | Inara | "This is CMDR Mechan. They've built 47 colonies." |
| **System traffic reports** | EDSM | "This system gets 200 visits/day — it's a trade hub" |
| **Nearest station finder** | EDDB, Inara | "Nearest large-pad station to HIP 37316 with a shipyard" |
| **BGS influence graphs** | Elite BGS API | "Faction X's influence in this system over the last 30 days" |
| **Colonisation leaderboard** | EDColonise.net | "Top 10 architects by systems colonised this month" |

### Which of these could ed-finder realistically add?

1. **Nearest station finder** — we have the station data. A spatial query. Medium effort.
2. **System traffic reports** — EDSM has the data. Would need to ingest their dumps. Low effort if we wire the EDSM pipeline.
3. **Commodity market search** — needs live market data. Inara or journal crowd-sourcing. Harder. Gated on Inara integration.
4. **BGS influence graphs** — Elite BGS API is already planned as a source. Low effort once wired.
5. **Colonisation leaderboard** — needs system architect tracking. The `colonisation_status` evidence type already exists. Query it.

---

## Part 9: Features Nobody Has (Blue Ocean)

These are opportunities where ed-finder could be first to market:

1. **"What body types are in this system?" → economy projection** — Nobody does the body type → economy override mapping automatically. ed-finder has the body data. This is a unique feature.

2. **Construction progress tracking from journal** — No other tool shows your colony's live progress inside the planner itself. EDDiscovery and BGS-Tally track progress but in separate tools. Integrating it into the planner is unique.

3. **Expansion Plans (already shipped!)** — The slot-based colony plan from cluster search doesn't exist anywhere else. "I need a Refinery+Industrial world AND an Agriculture world within 500 LY" — this is a genuinely novel query type.

4. **Economy outcome simulation** — "If I build X, Y, and Z on these bodies, what will my colony's economy be?" Nobody does this as a pre-build simulator. Everyone else is documentation that you have to manually look up and calculate yourself.

5. **"Colonisation corridor" routing** — "Find me a path of claimable systems from the Bubble to Colonia, each within 16 LY of the next." This is on the roadmap as B-2 (hop-count-only). Nobody has built this.

6. **System quality scoring with ML** — Train on what makes a "good" colony (high population, active markets, player satisfaction) and score every uncolonised system. This is the Zillow-for-colonisation idea.

---

## Part 10: Prioritized Roadmap

### Now (This Sprint) — Polish What Exists

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 1 | "Colonisation Candidates" one-click filter preset | 1 hour | Removes the #1 new-user friction |
| 2 | Empty states with CTAs | 2 hours | Every empty panel becomes a discovery path |
| 3 | Construction Cost Estimator (facility picker + cost table) | 1 day | THE killer feature that every coloniser wants |
| 4 | Body economy badges in planner | 3 hours | Makes the override mechanic visible |

### Next (This Month) — The Differentiators

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 5 | Economy Outcome Preview in planner | 1 week | "What will my colony's economy be?" — unique feature |
| 6 | "What If?" scenario comparison | 3 days | Builds on #5, multiplies its value |
| 7 | Colonisation map layer | 3 days | Visualizes the colonisation wave — nobody has this |
| 8 | "Share System" link + "Sell Me This System" card | 2 days | Social sharing, Discord integration |
| 9 | Commodity Shopping List (combined across projects) | 2 days | Practical logistics tool |
| 10 | Construction Progress Tracker (from journal) | 3 days | Closes the planning→playing loop |

### Soon (This Quarter) — Rounding Out

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 11 | Nearest station finder | 3 days | EDDB-replacement utility |
| 12 | System traffic reports (from EDSM) | 2 days | Data we already ingest, just not surfaced |
| 13 | Onboarding flow | 1 week | Converts lookers into users |
| 14 | Dashboard summary on My Work | 2 days | Overview screen for returning users |
| 15 | Keyboard shortcuts reference | 1 day | Power user love |
| 16 | Export/Import My Work | 2 days | Data portability, trust |

### Later — The Blue Ocean

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 17 | Colonisation corridor routing (B-2) | 2 weeks | On the roadmap, gated on foundation |
| 18 | ML system quality scoring | 3 weeks | Zillow-for-colonisation |
| 19 | Commander profile / colony showcase | 2 weeks | Social proof, community building |
| 20 | Public API for other tools | 1 month | EDDB-replacement ecosystem play |

---

## Part 11: Quick Quality-of-Life Fixes (Under 1 Hour Each)

1. Add a "Copy system name" button to every system name display
2. Show "last updated" timestamp on every data panel
3. Add a "scroll to top" floating button on long pages
4. Show result count in the browser tab title ("(12) Finder — ED-Finder")  
5. Persist the last-used Finder mode (System/Region) across sessions
6. Add tooltip explanations to all economy score abbreviations
7. Color-code distance values (green < 100 LY, yellow < 500 LY, white > 500 LY)
8. Add a "random colony name generator" for fun
9. Show fleet carrier jump range rings on the map (from journal import)
10. Add a "system visited" counter to My Work telemetry
