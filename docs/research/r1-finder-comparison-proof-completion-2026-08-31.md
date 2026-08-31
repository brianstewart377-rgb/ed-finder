# ED-Finder R1 — Finder Comparison Proof Completion

Date: 2026-08-31  
Status: **implementation proof complete; isolated and not production-wired**  
Branch: `chatgpt-ed-new-ops-requests`

## 1. Scope and commit boundary

Contract source:

- `docs/research/r1-finder-comparison-proof-stage-review-1-2026-08-31.md`
- `docs/research/r1-finder-comparison-proof-stage-review-2-2026-08-31.md`

Implementation comparison range:

```text
base: 00b056860b64eec7637a78dc856a0fd71206b751
head: bd6b2f22e75e882c01570acbbf219c5d22642517
```

GitHub compare reports `ahead_by=8`, `behind_by=0`, with exactly these eight added files:

```text
apps/api/src/r1_finder_compare/__init__.py
apps/api/src/r1_finder_compare/types.py
apps/api/src/r1_finder_compare/fixtures.py
apps/api/src/r1_finder_compare/evidence.py
apps/api/src/r1_finder_compare/programmes.py
apps/api/src/r1_finder_compare/evaluator.py
apps/api/src/r1_finder_compare/search_compare.py
tests/test_r1_finder_compare.py
```

No pre-existing source file changed in the implementation range.

## 2. What the proof implements

The proof evaluates the same seven fixture candidates under three explicit contexts:

1. `facts_only`
2. `role_extraction_v1`
3. `programme_p_er_01_v1`

It demonstrates the intended Finder/Ratings relationship:

```text
factual candidate filtering
+ explicit comparison context
→ context-bound assessment
→ assessment-state precedence
→ optional provisional Plan Fit
→ deterministic candidate ordering
→ deterministic search-to-detail handoff
```

There is no universal system/development score and no hidden fallback to legacy/v4/archetype output.

## 3. Focused test result

Command:

```text
PYTHONPATH=apps/api/src python -m pytest tests/test_r1_finder_compare.py -q
```

Result from the isolated verification workspace:

```text
.........................                                                [100%]
25 passed in 0.07s
```

The committed package blobs were byte-checked against the locally verified package source for all seven `r1_finder_compare` modules. The committed test source was separately fetched/reviewed and contains the same 25 required contract assertions.

Python compilation also passed for all new package modules.

## 4. Source-boundary result

Scan terms:

```text
asyncpg|psycopg|redis|fastapi|requests|httpx|
build_ratings|build_archetype_scores|build_topology|
search_economies|local_search|economy_state|placements
```

Result:

```text
source-boundary: clean
```

The proof has no DB, Redis, API-route, network, legacy-rating, v4/archetype, current topology, or current placement/economy-state dependency.

## 5. Candidate ordering by context

### Facts only

| Rank | System | Assessment | Fit | Reserve | Logistics |
|---:|---|---|---:|---|---|
| 1 | Refinery First | — | — | — | — |
| 2 | Incomplete Promise | — | — | — | — |
| 3 | Compact Prospect | — | — | — | — |
| 4 | Plateau Thirty | — | — | — | — |
| 5 | Plateau Sixty | — | — | — | — |
| 6 | Geo HMC | — | — | — | — |
| 7 | Far Abundance | — | — | — | — |

Facts-only uses deterministic factual ordering; it has no assessment or hidden Plan Fit.

### Extraction role

| Rank | System | Assessment | Fit | Reserve | Logistics |
|---:|---|---|---:|---|---|
| 1 | Compact Prospect | Supported | 99 | Resilient | Compact |
| 2 | Geo HMC | Supported | 98 | Sufficient | Compact |
| 3 | Plateau Thirty | Supported | 97 | Sufficient | Moderate |
| 4 | Plateau Sixty | Supported | 97 | Expandable | Moderate |
| 5 | Far Abundance | Supported | 83 | Expandable | Extreme |
| 6 | Refinery First | Not supported | — | Resilient | Compact |
| 7 | Incomplete Promise | Not assessable | — | Sufficient | Unknown |

The Extraction role does not require Refinery or pair-stability evidence. Far Abundance has greater raw material abundance but ranks below the compact candidates because logistics is material under the declared proof policy.

### P-ER-01 Extraction / Refinery programme

| Rank | System | Assessment | Fit | Reserve | Logistics |
|---:|---|---|---:|---|---|
| 1 | Compact Prospect | Supported | 98 | Resilient | Compact |
| 2 | Plateau Thirty | Supported | 98 | Sufficient | Moderate |
| 3 | Plateau Sixty | Supported | 98 | Expandable | Moderate |
| 4 | Geo HMC | Supported | 93 | Sufficient | Compact |
| 5 | Far Abundance | Conditionally supported | 88 | Expandable | Extreme |
| 6 | Refinery First | Not supported | — | Resilient | Compact |
| 7 | Incomplete Promise | Not assessable | — | Sufficient | Unknown |

The three orderings are intentionally different. This demonstrates that the comparison context—not a universal score—defines what “better” means.

## 6. State precedence proof

The evaluator separately tests a case where a conditional candidate has a higher provisional fit than a supported candidate. Default ordering remains:

```text
Supported
> Conditionally supported
> Not supported
> Not assessable
```

Therefore a Conditional 97 cannot outrank a Supported 85 merely because its provisional number is higher.

Unsupported and Not-assessable candidates never receive Plan Fit.

## 7. Composable body/modifier proof

`geo_hmc_composable` contains a canonical:

```text
base_identity = High metal content world
has_geologicals = true
```

The HMC identity remains present; geological evidence is an independent modifier.

The test suite proves:

- adding geological evidence cannot reduce Extraction-source capability merely through reclassification;
- one geological signal and ten geological signals on the same body produce the same body-local modifier credit in this proof;
- signal count is not multiplied into repeated economy evidence.

## 8. Plateau proof

P-ER-01 results:

```text
Plateau Thirty: Fit 98, Reserve sufficient
Plateau Sixty:  Fit 98, Reserve expandable
```

The surplus fixture may legitimately have better reserve/expansion headroom while fixed-programme Plan Fit remains unchanged. This prevents the old “more bodies always means better” saturation pattern from returning through a new formula.

## 9. Carrier compare-both proof

For `remote_extraction_abundance`:

```text
no_carrier:
  state = conditionally_supported
  fit = 88
  logistics = extreme

carrier_available:
  state = supported
  fit = 97
  logistics = moderate
```

Evidence snapshot ID is identical in both scenarios:

```text
sha256:a27c9b5b55435d7c466a7cdcc1bb986bcc59ea5d441a0f7c36dcde355997a677
```

Carrier mode changes the declared logistics-sensitive result only. It does not rewrite body facts, source evidence, pair stability, physical capacity, provenance, or the frozen evidence snapshot.

## 10. Search-to-detail continuity proof

For Compact Prospect, the generated candidate plan ID is:

```text
sha256:1d444904e432a68d12b5ffeb1d37db2551cd8e4b88f85687466519ed05a2f927
```

Re-evaluating from the search handoff reproduces the same canonical base assessment payload after excluding Plan Fit, which is explicitly strategy-derived:

```text
HANDOFF_EQUAL = True
```

This proves the search result is not using one semantic model while detail assessment uses another.

## 11. Determinism

Repeated evaluation of the same frozen evidence, programme revision, carrier comparison and strategy produces deeply equal ordered results:

```text
DETERMINISTIC = True
```

Evidence snapshot IDs exclude strategy and carrier mode. Candidate-plan IDs exclude fit strategy and bind the programme revision, carrier scenario and stable allocation trace.

## 12. Important interpretation boundary

The provisional strategy is:

```text
bounded_geometric_v1
```

It computes a geometric mean of explicitly bounded `0..1` plan dimensions.

This is a laboratory/product comparison policy, **not an Elite Dangerous mechanic and not an accepted production scoring formula**. Its purpose is to prove search/rating semantics, state gating, plateau behaviour and context-sensitive ordering.

## 13. Product-redesign principle retained

This proof does not attempt V2 feature parity.

V2 remains a source of player jobs, useful interaction patterns, regression cases and mistakes to avoid. The redesign is free to merge, remove, split or reframe V2 features when a better evidence-first R1 workflow serves the underlying player job.

## 14. No-production-change confirmation

Confirmed for this implementation range:

- no production Finder search SQL changed;
- no `local_search.py` change;
- no `search_economies.py` change;
- no frontend Finder/search change;
- no production API route or contract change;
- no DB write;
- no migration;
- no ratings rebuild;
- no archetype rebuild;
- no production deployment;
- no merge;
- no network or persistence dependency added.

## 15. Completion decision

**The isolated Finder/Ratings semantic proof passes its Review-2 contract.**

The next stage should not immediately wire this provisional fit formula into production Finder. The useful next design task is to define how real canonical body evidence is projected into the same R1 candidate/evidence contract and how the first reimagined Finder interaction selects/communicates comparison context without preserving V2 feature parity or hidden archetype semantics.
