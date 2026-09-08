# Ratings V4 Validation Fixtures

**Status:** proposed acceptance fixtures for Ratings V4 coefficient tuning
**Depends on:** `ratings-v4-mechanics-evidence.md`, `ratings-v4-scoring-contract.md`

## Purpose

These fixtures define expected **ordering and score bands** before implementation. Exact coefficients may move during tuning, but a candidate scorer that violates these expectations needs an explicit mechanics/product explanation rather than ad-hoc coefficient changes.

All fixtures assume complete/high-confidence evidence unless marked otherwise.

## F1 — Pure Rocky Refinery specialist

System contains multiple clean Rocky bodies, no rings, no biological/geological modifiers, favourable reserve state where relevant, and at least one usable planetary location.

Expected:

- Refinery potential: **excellent to exceptional**
- Refinery specialisation: **very high**
- Extraction/Industrial/Agriculture: low unless other facts create them
- A second/third clean Rocky raises depth but with diminishing returns

Acceptance invariant: clean Refinery purity must not be penalised merely because the system has many ordinary non-contributing bodies.

## F2 — Mixed Rocky Refinery contamination case

Same as F1 except the best Rocky bodies carry combinations of rings, biologicals and geologicals.

Expected:

- Refinery potential remains strong because native Refinery inheritance still exists
- Refinery specialisation is lower than F1 because competing inherited economies are introduced
- Extraction/Industrial/Agriculture rise according to the actual modifiers

Acceptance invariant: contamination changes specialisation more than raw Refinery potential.

## F3 — Pure Icy Industrial specialist

Several clean Icy bodies, favourable reserve state, no competing local modifiers.

Expected:

- Industrial potential: excellent/exceptional
- Industrial specialisation: very high
- Refinery/Extraction remain low absent supporting inheritance

## F4 — Rocky-Ice dual Industrial/Refinery system

Several Rocky-Ice bodies.

Expected:

- Industrial and Refinery both strong
- neither raw score is attenuated because the other is also strong
- specialisation for each is lower than a perfectly pure single-economy equivalent, but top-two protection prevents a severe penalty

## F5 — Extraction reserve ladder

Three otherwise identical HMC/Metal-Rich systems:

- F5a Pristine/Major reserves
- F5b Average/Common reserves
- F5c Low/Depleted reserves

Expected ordering:

`F5a Extraction > F5b Extraction > F5c Extraction`

The reserve difference must be visible in explanation components.

## F6 — Geological + volcanic Extraction system

HMC with geologicals and volcanism.

Expected:

- native Extraction from HMC
- additional Extraction + Industrial inheritance from geologicals
- volcanism strengthens Extraction but does not create a second inheritance event
- Extraction potential very high
- Extraction specialisation below a comparable clean HMC because Industrial pressure exists

## F7 — Water-World Agriculture/Tourism system

Multiple Water Worlds, no contradictory evidence.

Expected:

- Agriculture and Tourism both excellent/exceptional
- neither is attenuated because both are strong
- Military remains low
- High Tech only receives effects supported by the active mechanics ruleset/provenance

## F8 — ELW mixed-economy system

One or more ELWs.

Expected:

- Agriculture, Tourism and High Tech all receive meaningful positive support
- Military receives inheritance eligibility but no fabricated environmental/strategic bonus
- Agriculture/Tourism should normally outrank Military for an otherwise uncomplicated ELW fixture
- no global cross-economy attenuation

## F9 — Ammonia High-Tech/Tourism system

Ammonia World(s), otherwise uncomplicated.

Expected:

- High Tech and Tourism strong
- Agriculture/Military low absent independent support

## F10 — Exotic-star High-Tech/Tourism system

Black Hole, Neutron Star or White Dwarf with no unrelated strong economy bodies.

Expected:

- High Tech and Tourism are the principal raw economy opportunities
- Tourism benefits from any documented system-level exotic-star modifier
- Military does not inherit from the exotic star

## F11 — Main-sequence Military system

Main-sequence/Brown-Dwarf stellar environment with no ELW and no strong competing economy bodies.

Expected:

- Military is the principal raw economy score
- Military score is driven by inheritance, not invented strategic/slot bonuses
- specialisation is high where no asteroid-belt/modifier pressure introduces competition

## F12 — Deep-body diminishing returns

Compare:

- F12a: one perfect candidate for economy E
- F12b: two perfect candidates
- F12c: four perfect candidates
- F12d: twenty perfect candidates

Expected approximate bands from the proposed roll-up:

- one perfect: ~82
- two perfect: ~93
- three perfect: ~98
- four perfect: 100
- twenty perfect: still 100, never >100 and never rewarded beyond the best four

Acceptance invariant: quality dominates sheer catalogue size.

## F13 — One excellent vs many mediocre

Compare:

- one local opportunity score 100
- ten local opportunities around 45

Expected:

The single excellent-site system should rank at least comparably and normally above the many-mediocre system for raw economy potential.

This guards against body-count inflation.

## F14 — Unknown evidence vs known absence

Two otherwise identical systems:

- F14a rings/bio/geo/reserve facts are explicitly known absent/normal
- F14b those same evidence families are unknown

Expected:

- potential scores may be similar if no positive evidence is present
- F14a has materially higher evidence completeness
- F14b must not receive fake negative contributions for unknown inputs
- confidence guard must prevent F14b from presenting as near-certain

## F15 — Top-two protection

A system with two naturally strong compatible economies and a weaker third.

Expected:

- both top economies keep their independent raw potential
- the weaker economy is not artificially attenuated merely because it ranks third
- specialisation/archetype logic may describe competition, but raw scores remain honest

This explicitly rejects Ratings v3.4 global attenuation.

## F16 — Terraformability amplifier only

Two otherwise identical non-Agriculture-native bodies, one terraformable and one not.

Expected:

- terraformability alone must not manufacture Agriculture eligibility where no Agriculture inheritance exists

Then repeat with an Agriculture-eligible body:

- terraformability may improve Agriculture local opportunity according to the active mechanics ruleset

## F17 — Geologicals vs volcanism distinction

Compare:

- body with geologicals only
- body with volcanism only
- body with both

Expected:

- geologicals can add Extraction/Industrial inheritance
- volcanism only modifies an existing Extraction opportunity
- the two features must produce different explanation records and cannot be collapsed into one boolean

## F18 — Absolute-score stability

Run the same deterministic fixture against two canonical generations containing identical relevant facts but different unrelated catalogue population.

Expected:

- all V4 raw economy scores identical
- percentile/rank may differ outside Ratings V4

This proves scores are absolute rather than galaxy-relative.

## Real-system validation lane

After deterministic fixtures pass, select a small reviewed set of real systems representing:

- known Tourism/Agriculture showcase
- known extraction/refinery specialist
- strong Industrial chain candidate
- High-Tech/exotic system
- Military specialist
- mixed multi-role system
- sparse/uncertain system

For each, record expert expected ordering before running V4. Exact system names and expected results belong in the validation receipt, not hard-coded in the scoring algorithm.

## Freeze rule

Do not freeze coefficients solely because all numerical tests pass. The fixture suite must also demonstrate:

- explanations match the mechanics evidence;
- unknown remains unknown;
- specialisation and potential are visibly distinct;
- ELW is not flattened into equal Agriculture/HighTech/Military/Tourism treatment;
- no old v3.4 global attenuation survives;
- score changes from coefficient tuning are understandable from stored contributors.
