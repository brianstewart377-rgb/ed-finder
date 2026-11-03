# UI concept pack — 1 November 2026

Static visual concepts supplied by the owner as the **visual direction** for the
V3 UI redesign ([plan](../2026-11-02-v3-ui-redesign-plan.md)). They are
generated mockups with illustrative data. They are **reference only**: not
product behaviour, not business rules, not acceptance baselines of pixel
fidelity, and not assets to ship.

## Files

| File | Shows |
|---|---|
| `01-finder.png` | Finder: archetype selectors, Body filters pop-out, results-first table with Show on map / Inspect per row, Results / Pinned / Watchlist tabs. |
| `02-map.png` | Show on map window beside the results: titled for the system, Local / Galaxy, Regions, Layers, controls under the map, Centre on, Back to results, Inspect. Defines styling and **placement** only. |
| `03-inspect.png` | Inspect tabs, independent economy potentials, evidence explanation pop-out. |
| `04-plan.png` | Plan System layout / Build order tabs and facility picker. |
| `05-review.png` | Review / export pop-out and the unresolved-information state. |
| `home-background-black-hole.png` | Candidate **homepage background** supplied by the owner on 1 November (evening): an in-game Elite Dangerous screenshot of a black hole with an orange glow and the owner's ship in the corner. A background candidate, not a layout. |
| `reference-live-map.png` | The real captured map, for comparison with `02-map.png`. |
| `HANDOFF.txt` | The owner's handoff note (rules, finder details, limits). |
| `journey-notes.txt` | Journey, design and scope notes for the set. |

## Rules that come with the pack

- Use the **existing map renderer and real coordinates/regions**. The drawn
  galaxy in `02-map.png` is illustrative geography, never data.
- Results, scores, ranking and plan contents are illustrative. Seven economy
  potentials stay independent; confidence is evidence completeness; unknown
  slots stay unknown; planned and built stay distinct; Tier 2 and Tier 3
  balances stay separate.
- Count filters are not ranking weights. The pack shows 18 count controls; the
  owner decided on 2026-11-03 to **keep all 19 existing controls**, including
  Rocky ice (plan §7 decision 3).
- Where a mockup and the repo contracts or API capabilities disagree, the repo
  contracts win. Report the gap instead of inventing behaviour.

## Not included, and why

- `00-orbis-home.png` (the cinematic Orbis homepage) is **held back from this
  public repository**. Per its generation notes it is an AI-edited composite
  built from a third-party artist's Orbis artwork, so publishing it or shipping
  its pixels needs a rights decision first. The composition is described in
  `HANDOFF.txt`: Orbis hero imagery, a serif display headline, Reference system
  and Colony archetype fields with an orange primary action, and three numbered
  steps. The owner holds the original. `home-background-black-hole.png` is the
  owner's own in-game screenshot offered as the homepage background instead.
- The generation prompt logs are not committed: they contain local file paths.
- Any use of pixels from this folder in the product needs an
  `assets/PROVENANCE.json` entry and rights review first.
