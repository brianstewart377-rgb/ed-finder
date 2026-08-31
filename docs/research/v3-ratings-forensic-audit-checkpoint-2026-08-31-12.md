# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 12

Date: 2026-08-31
Scope: research only. No production writes, V3 database writes, scoring-code changes, or migrations.

## This iteration

This pass continued from checkpoint 11 and deliberately moved through more than one unfinished item:

1. traced Raven Colonial / SrvSurvey slot-prediction ancestry and implementation boundaries;
2. adversarially checked whether Raven/SrvSurvey and related clients are independent evidence sources;
3. pinned the Top-Two-Economies anti-cannibalisation rule to the Vanguards Patch 1 chronology;
4. revisited the long-running terraformable-Agriculture modifier bug and found evidence that its live state changed again with the July 2026 Operations update;
5. expanded the commodity/self-sufficiency queue with current empirical claims that need market-history validation.

## Raven / SrvSurvey slot ancestry: important correction to evidence independence

### What the public SrvSurvey code actually does

`njthomson/SrvSurvey` contains a Raven client in `SrvSurvey/net/RavenColonial.cs`. It is an HTTP/API client, not the current slot-prediction implementation.

Observed API flow includes:

- `GET /api/v2/system/{nameOrNum}/sites`
- `GET /api/v2/system/{nameOrNum}`
- `POST /api/v2/system/{nameOrNum}/import/bodies`
- body-data PUTs to Raven's service

The body payload carries the same broad physical/feature space that matters to our validated surface-slot model: radius, temperature, gravity, landability, atmosphere, terraformability, tidal state, rings, biologicals, geologicals and volcanism.

Critically, the public SrvSurvey `SitesPut` model explicitly comments that `slots` are intentionally missing. The slot/site result is therefore derived on the Raven side and returned to clients; the public SrvSurvey code does not independently reimplement the current Raven slot algorithm.

### Raven frontend found

A public repository `njthomson/RavenColonialWeb` was found. The obvious frontend/code-search paths inspected did not surface the slot algorithm. No separate public backend repository containing the current slot function has yet been found.

Do **not** strengthen that into “Raven is closed-source” yet: a backend may exist under a different repository/name or may not be indexed. The bounded finding is that the slot engine did not surface in the public SrvSurvey client or Raven web frontend inspected in this pass.

### Ancestry from the community guides

CMDR Dubior's advanced guide explicitly attributes the ground-slot research to CMDR Nyatto, Flynnvali and others, and says the most up-to-date implementation should be in Raven Colonial. Its acknowledgements also credit CMDR Grinning2001 for SrvSurvey/Raven and Nyatto for spearheading identification of the ground-slot formula.

This produces a much cleaner lineage model:

`Nyatto / Flynnvali / community empirical slot research -> Raven server implementation -> SrvSurvey / Raven web consumers -> derivative Raven reporting clients`

This means Raven can be a useful current implementation/check, but it is **not** an independent empirical vote against the workbook merely because a second UI/client agrees.

### Derivative clients found

Two further GitHub clients reinforce the lineage conclusion rather than adding independent mechanics evidence:

- `EDToolbox/EDMC-Ravencolonial` reports Journal/colonisation data to Raven and credits the SrvSurvey/Raven implementation lineage.
- `pequalsnp/ed-colonization-reporter` explicitly names SrvSurvey's `RavenColonial.cs` as its primary reference for the Raven API surface.

These are reporters/transports. They should not be counted as independent validation of slot mathematics.

### Structural match to our slot model

Raven's transmitted body fields strongly overlap the feature set independently identified in our workbook analysis (radius, temperature, gravity, atmosphere, terraformability, geo/volcanism, bio, landability, etc.). This raises the probability that the workbook and Raven descend from the same empirical research family.

It does **not** prove threshold or coefficient equality.

**Falsification test:** compare current Raven site/slot outputs with our workbook predictor on a deliberately chosen threshold corpus (just below/above 700 K, 2.7 g, radius breakpoints, atmosphere states, HMC, terraformable, geo/volcanism, bio) plus the two workbook residuals. Agreement would establish implementation compatibility, not independent validation; disagreement would identify current formula drift.

## Raven is not an economy oracle

Dubior's guide also records known Raven limitations at its then-current state: incorrect initial High Tech/Tourism calculations with multiple strong-link modifiers, missing rocky-ice Agriculture penalty, and uncertainty around some tidal-lock behaviour.

Therefore:

- Raven is potentially high-value for current slot prediction;
- Raven economy output must be validated claim-by-claim;
- “Raven says so” is not adequate evidence for CRE economy mechanics.

## Top-Two-Economies anti-cannibalisation: chronology now pinned

The Mega Guide identifies the rule change as game patch **4.2.0.1**. External patch mirrors of Frontier's Vanguards Patch 1 place the live release on **22 August 2025** and preserve the Frontier wording: goods produced by the top two economies are no longer consumed by ports or settlements linked to that economy, intended to prevent market links from cannibalising production into limited/zero market supply.

The guide's later empirical interpretation is more precise:

- supply associated with economy ranks #1 and #2 is protected from demand netting;
- this protection is on **production/supply**, not on demand;
- demand from the top two can still net against supply from non-top-two economies;
- supply and demand of economies ranked #3+ remain subject to netting;
- same-strength tie ordering remains uncertain in the guide (alphabetical is a hypothesis, not locked fact).

This is materially different from a vague “top two economies are immune to cannibalisation” rule. CRE should preserve the directional supply-vs-demand semantics.

### Consequence for self-sufficiency modelling

A colony that contains all required production economy identities is not automatically a good self-sufficient construction supplier. The useful question is commodity-level:

`producing economy strength + rank -> consuming economy mix -> top-two protection -> population/output multiplier -> BGS/state/wealth effects -> observed stock/restock/price`

This supports keeping a separate **commodity availability / supply-chain model** rather than treating economy score as a proxy for realistic construction self-sufficiency.

## Terraformable Agriculture modifier: temporal bug state changed again

This pass resolved one of the explicit queue items.

### Intended rule

Trailblazers Update 3 (30 April 2025) says Agriculture strong links are boosted when on/orbiting a terraformable body.

### Observed 2025 bug

A July 2025 controlled player report measured two ports on terraformable bodies and found the +0.4 Agriculture boost absent, with reported values matching the calculation that omits the terraformable modifier. This was reported to Frontier as Issue 77445.

The June-2026 Library copy of Dubior's advanced guide still says the terraformable modifier does **not** apply to Agriculture despite the patch notes and that Frontier had indicated the behaviour might be intended.

### Post-Operations evidence

Dubior's updated guide announcement posted after the July 2026 Operations release now states: **the Terraforming modifier applies to all terraformable and Earthlike bodies as of the Operations update**.

The July 1 Operations release notes inspected do not explicitly enumerate this Agriculture fix. Therefore the current classification should be:

- 2025 patch text / intended rule: official primary;
- 2025–June 2026 non-application: direct community observation + current-at-the-time guide evidence;
- post-Operations application: recent experienced-researcher/community observation, not yet tied to an explicit Frontier line item.

This is another strong case for CRE temporal state and for separating `intended_rule` from `observed_live_behavior`.

**Falsification test:** obtain a current post-Operations controlled market/strong-link fixture where terraformability is the only Agriculture modifier (plus a matched non-terraformable control if possible), or retrieve Raven/current market calculations only as a secondary check.

## Additional current economy evidence worth modelling, not yet locking

Dubior's advanced guide reports the following empirical relationships for current colonisation markets, with explicit uncertainty around exact formulae:

- absent self-cannibalisation, supply is proportional to economy proportion;
- consumption is proportional to economy proportion when the commodity is not locally produced;
- population associated with the local body/facility strongly affects output;
- wealth appears to affect supply, with a large difference between zero and non-zero wealth;
- it gives rough output multipliers for port/body types (e.g. ELW/WW/T3/Dodec), but labels several relationships approximate/currently believed.

These are hypotheses for EDGalaxyData/EDDN/EDCAS validation, not CRE facts yet.

A particularly useful distinction emerges: current ratings should score **capacity/potential** separately from actual market **throughput**. The latter depends on facility population, economy rank, cannibalisation, state and potentially wealth—not merely system body composition.

## Adversarial review

### Evidence quality

- **High:** SrvSurvey source-code architecture and request/data model; Vanguards Patch 1 release wording/date from preserved Frontier/Steam announcement; Trailblazers Update 3 official intended modifier semantics.
- **Medium-high:** Dubior/Nyatto lineage attribution and current guide mechanics where backed by worked examples/repeated observation.
- **Medium:** post-Operations Terraformable-Agriculture fix claim until reproduced or tied to a Frontier issue/patch resolution.
- **Low/illustrative only:** old Reddit speculation on orbital-slot determinants or historic Architect screenshots without patch/state provenance.

### Circular-sourcing traps

Do not count these separately unless a claim has its own observations:

- SrvSurvey client
- Raven web UI
- EDMC-Ravencolonial
- ed-colonization-reporter
- external planners consuming Raven output

They are substantially one Raven data/API lineage.

Likewise Mega Guide / Dubior / Raven share named researchers (notably Nyatto) on multiple mechanics. Corroboration must be traced to raw observations where possible.

## Hypotheses to test against V3 / read-only analysis

1. Our workbook and current Raven ground-slot results will agree on nearly all threshold fixtures because both likely descend from the Nyatto/Flynnvali empirical lineage; any disagreements will be particularly informative current-rule deltas.
2. Treating top-two protection directionally at the commodity level will substantially change “self-sufficient colony” rankings compared with a simple economy-pair score.
3. Post-Operations terraformable Agriculture support means any CRE/rating implementation frozen to the June-2026 bug state is now stale.
4. Current market throughput will correlate more strongly with local population + protected economy rank than with raw system-wide economy potential alone.
5. The two workbook ground-slot residuals are more likely observation/UI anomalies or narrow missing conditions than evidence for a broad new +1 rule; do not alter the formula until re-observed.

## Unresolved questions

- Where is Raven's current server-side slot algorithm implemented, and is any backend source publicly available under another repo/name?
- Does current Raven match the workbook on the two residual HMCs and all threshold fixtures?
- What exact server/patch change made terraformable Agriculture start working in Operations, and was Issue 77445 formally resolved?
- What determines rank order when two economies have exactly equal strength?
- What is the exact self-cannibalisation/netting function for economies ranked #3+?
- How do facility population, local-body population, wealth and BGS state quantitatively combine into supply/restock and prices?
- Which current market-history source has enough observation density and station identity continuity to estimate these effects safely?

## Next queue — continue, do not treat this checkpoint as completion

1. Search for Raven's backend/API implementation under alternate repositories/names and inspect Raven issues/commits around July 2026.
2. Build a Raven-vs-workbook **read-only threshold corpus**, including the two known residuals.
3. Trace Issue 77445 / post-Operations Agriculture terraformability into current Frontier issue state and independent market observations.
4. Find controlled post-Vanguards markets for top-two-protected vs rank-3 cannibalised commodities and derive testable netting equations.
5. Continue EDGalaxyData/EDDN/EDCAS market-history feasibility and identify a small golden station set with repeated observations.
6. Continue post-July-2026 orbital-slot corpus, recording patch epoch, observation date, body/ring/belt state, Architect state and demolition/build history.
7. Run a read-only V3 sensitivity analysis replacing system-wide signal totals and fake slot abundance with body predicates + predicted/observed capacity; compare rank movement in the 90+ band.
8. Continue CRE source-universe audit and add temporal-state requirements to the eventual CRE design recommendation.