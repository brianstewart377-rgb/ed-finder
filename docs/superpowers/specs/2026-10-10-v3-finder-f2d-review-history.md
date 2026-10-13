# V3 Finder F2d design — review history

Dated review rounds of
`2026-10-10-v3-finder-f2d-wide-archetype-and-product-attachment-design.md`
(PR #806), moved out of the design on 2026-10-12 when the design was rewritten
to state each rule once. Each entry records a reviewer finding and its
disposition; the PR #806 review threads hold the same record. This file is
evidence only — the current design is the design document, and where this
history disagrees with it the design wins.

Rounds 1–7 were dispositioned in the PR threads before the in-document log
began at round 8.

### Review round 8 (2026-10-11)

1. **P1 — Add local-search identity wiring to PR1** → the shared identity model,
   the product-row lookup in `_current_derived_generation()`, the local-search
   envelope construction and assertions on both envelopes are named in PR1's file
   list (`apps/api/src/local_search.py` is PR1 work, not deferred to PR2).
2. **P1 — Keep publication out of the pre-go-live release gate** → PR4's gate
   requires READY + VERIFIED validation receipts, identities and row counts, and
   explicitly must not require `published_at` or a publication audit; publication
   is verified by the publish action's receipt and a post-go-live check.
3. **P2 — Make the claimed index-only ranked query executable** → the picked
   query is specified in four stages: index-only window (only the partial index's
   own columns), filter, page, then a bounded primary-key fetch of ≤ `page_size`
   rows for the response columns; plan assertions cover both nodes. INCLUDE
   payload on 24 partial indexes was considered and rejected.
4. **P1 — Run calibration before making its histogram a PR1 input** → PR1's
   footprint receipt uses the declared synthetic bell-shaped distribution and says
   so; the histogram-driven measurement moves to the pre-build capacity gate,
   after the governed probe runs, via a new `--fractions-json` input.
5. **P2 — Bound the explanation identity parameters** → `expected_generation_id`
   is a `uuid.UUID`, `expected_archetype_version` is
   `Query(None, min_length=1, max_length=128)` and `expected_manifest_sha256` is
   `Query(None, pattern=r'^[0-9a-f]{64}$')`; malformed or oversized values are
   422s from validation, with tests for each case.

### Review round 9 (2026-10-11)

1. **P1 — Apply hard filters before selecting the ranking window** → neither
   placement is acceptable, so the combination is rejected: PR1 makes a picked
   request carrying `galaxy_region`, `max_distance_ly`, `has_elw`, `min_slots` or
   `max_contamination` a 422 naming the parameters and the reason, Any mode keeps
   every filter, the F4 UI disables those controls while an archetype is picked,
   and `total`/`is_truncated` then mean exactly what they say. Filtered archetype
   ranking needs a filter-first access path and stays deferred. Recorded as owner
   question 9.
2. **P1 — Record the discrete `min_score` contract in the ROADMAP** → the
   ROADMAP now states `Literal[60, 76, 88]` with default 60 (not the continuous
   60–100 range), says why — each accepted value needs its own partial index, and
   70 or 100 are 422s — and records the hard-filter rejection in the same place.
3. **P1 — Account for all 24 indexes in the capacity ceiling** → the three
   predicates per key are nested, so section 3.3 now gives the cost as
   `44 GB heap + 16 GB (PK + weighted) + 9.9 GB × Σ_all`, where Σ_all is the sum
   of all 24 per-key tier fractions (1.54 synthetically ⇒ ≈ 76 GB), states the
   true absolute ceiling of ≈ 297 GB (not the rejected layout's 132 GB), and moves
   the capacity gate onto Σ_all with a stop above 4.0 and a named fallback (index
   fewer floors or fewer archetypes). The ROADMAP, capacity decision and
   rollout-state table carry the same arithmetic.
4. **P1 — Keep the old API fail-closed until the new release is deployed** →
   the rollout is reordered: the release deploys at step 5, **before** any product
   reaches READY, gated on the applied migration set, the ranking identity, the
   bounded route and the publication check — and on no Finder product rows **on
   the pinned target generation**, because none exist there (the retained `opt1`
   `system_search` must not block it). Steps 6–7 build Search then Archetype (the deployed build keeps
   answering 503 because they are unpublished), step 8 publishes both, step 9
   verifies from the live app. The reasoning — the deployed build gates only on
   READY, and post-`015` views hide unpublished rows — is written out under the
   table.

### Review round 10 (2026-10-11, from the F4 design's review)

1. **Outer `ORDER BY` is mandatory.** Stage 3 of the picked query restates
   `ORDER BY <key>_weighted_e4 DESC, system_id64 ASC` on the ≤ 10,000 survivors
   before pagination: an ordered index scan inside a subquery does not fix the
   final order and the planner may hash-join stage 2. The plan tests assert the
   sort node's input is ≤ 10,000 rows.
2. **The 10,000 offset ceiling is enforced at the API boundary.** PR1 bounds
   `POST /api/local/search`'s `from` to 0–10,000 as well as the rankings route's
   `offset`, so a direct caller cannot force `OFFSET 2000000000` against the
   ranking index once the products are published.

3. **PR4's gate carries no product prerequisites** (round 10 follow-up). The
   gate text now matches rollout step 5 exactly: generation identity, the applied
   migration set and hashes, the ranking identity and built-image contracts —
   and explicitly not product READY, validation receipts, row counts,
   `published_at` or publication audits, any of which would force the products to
   be built under the old deployed build and recreate the unsafe interval.

### Review round 11 (2026-10-11)

1. **P1 — Separate the identity check from the 503 probe** → a 503 carries no
   response envelope, so step 5 now verifies the two separately: the live request
   proves only the 503, while the ranking identity and the bounded-route
   contracts are proved from the release evidence (the gate's recorded
   `ranking_version`/`ranking_sha256`, the deployed image digest, the served
   `/openapi.json`), with the identity re-verified from a real envelope at
   step 9. The ROADMAP says the same.
2. **P2 — Enforce the result window on `from` plus `size`** → the local-search
   request model enforces the combined bound `from + size <= 10_000` (and
   `size >= 1`), like the rankings route, so `from=10000&size=500` cannot return
   rows beyond the window a capped total of 10,000 describes; tests pin
   `9_950+50` (ok), `10_000+1` (422) and `10_001` (422).
3. **P2 — Remove the post-window filter rule from the profile** →
   `PROFILE_SPEC` hashes the **hard-filter rejection rule** (the exact rejected
   parameter set, and that carrying one is a 422) and the
   `total = min(qualifying, 10000)` rule; the post-window filter rule is gone,
   since the route cannot execute it and hashing it would make `ranking_sha256`
   describe behaviour that does not exist. The identity test mutates the
   rejected-parameter set too.
4. **P1 — Wire the capacity gate into the Archetype action** → the gate is a
   fail-closed precondition of `v3-system-archetype.sh start`, with its own exit
   codes and receipt: it requires the recorded calibration histogram covering all
   eight keys and three floors, refuses `Σ_all > 4.0`, requires a footprint
   receipt whose `score_distribution_source` is `measured-histogram` and whose
   `011` hash matches the applied ledger entry, and takes a fresh read-only `df`
   of the data volume, refusing unless the measured archetype total plus 15 %
   working room fits. Four refusal tests plus a passing case that records the
   arithmetic.

### Review round 12 (2026-10-11)

1. **P1 — Bind capacity receipts to the governed histogram** → the footprint
   script now records `fractions_canonical`, `fractions_sha256` (SHA-256 of the
   canonical, key-sorted form) and `sigma_all`, and the gate requires that digest
   to equal the digest of the committed calibration evidence, so a stale or
   substituted JSON cannot pass as a measured histogram. Verified end to end.
2. **P1 — Run the capacity gate before building Search** → correct: Search is
   itself an irreversible 198.5 M-row insert-only write, so building it first and
   failing the gate afterwards would strand an unpublishable 87 GB product. The
   rollout gains an explicit **step 6, a combined Search + Archetype capacity
   gate**, which both build actions call as a fail-closed precondition.
3. **P1 — Preserve a schema-compatible rollback release** → PR4's authority
   records the F2d release as the **minimum schema-compatible image**, marks every
   earlier accepted image incompatible with the applied migration set, trims the
   deployment workflow's rollback target list to that image and later, and refuses
   promotion unless a compatible rollback artifact is recorded; a rollback below
   that line is an incident with its own plan, not a routine redeploy.
4. **P2 — Remove the remaining post-window filter stage** → stage 2 is now
   “Join (no filtering)”, for response columns only, stating that no hard filter
   appears anywhere in the query because such a request is rejected with 422
   before any SQL is built.
5. **P2 — Add an executable production-plan verification step** → new read-only
   `v3-archetype-plan-probe.sh` runs the real page and count SQL under
   `force_generic_plan` with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and asserts
   the index-only window (≤ 10,001 rows), the ≤ 10,000-row sort input and the
   ≤ `page_size` fetch at both 50 and the route's maximum 500; step 10 names it instead of the lifecycle-status action,
   which contains no `EXPLAIN`.
6. **P1 — Gate publication on the deployed F2d release** → the publish action
   fails closed before publishing anything: it compares the running API
   container's image digest with the accepted-release attestation for the F2d
   release and confirms the live advertised `ranking_version`/`ranking_sha256`,
   with distinct exit codes and an out-of-order test (products READY, old image).
7. **P2 — Align calibration and release ordering with the ROADMAP** → one order
   now, in both documents: 4 deploy the release, 5 calibration probe (its
   histogram is the gate's input), 6 combined capacity gate, 7 Search build,
   8 Archetype build, 9 publish, 10 post-go-live verification.

### Review round 13 (2026-10-11)

1. **P1 — Verify identity without calling the unpublished Finder** → correct:
   the Finder answers 503 until publication, so the publish action's identity
   check comes from the accepted-release attestation and the served
   `/openapi.json` plus the running image digest, never from a response envelope.
   The live envelope is checked at step 10, once it exists.
2. **P1 — Align the capacity decision with the pre-Search gate** →
   `v3-finder-capacity-decision-2026-10-10.md` section 4 is updated to put the
   combined gate before the Search build, matching the controlling sequence.
3. **P2 — Separate the page and count window sizes** → the page query's window
   is `LIMIT 10000` (so the stage-3 sort receives at most 10,000 rows, as the plan
   assertion and the production probe require) and the count query's is
   `LIMIT 10001` (the sentinel). The plan assertions distinguish the two.
4. **P2 — Read the stored row in the explanation query** → the single round trip
   also reads the generation-pinned wide `system_archetype` row, so the mandated
   recomputed-vs-stored comparison happens on one consistent snapshot; a missing
   row is a 404, and a test seeds a divergent stored row and asserts the
   fail-closed response.

5. **Any-mode count sentinel** (round 13 follow-up, from the F4 design's review).
   PR1 also gives the galaxy-wide count query the 10,001st-row sentinel
   (`LIMIT cap + 1`), so `total_is_capped` means “more than 10,000 exist” rather
   than “at least 10,000 were counted”. Without it a search with exactly 10,000
   matches raises the same flag as one with a million, and the F4 UI cannot
   honestly write “10,000+”. Tests pin exactly 10,000 (false) and 10,001 (true).

### Review round 14 (2026-10-11)

1. **P2 — Correct the stale Any-mode count claim** → the ranking section no
   longer says the galaxy-wide count is “capped the same way”: it states that the
   live path is bounded but **not** sentinel-based (`cap=10000` with
   `total_is_capped` on `>= 10000`) and that PR1 changes it to `LIMIT cap + 1`
   with `total_is_capped = count > cap`, so Any mode is not left unchanged.
2. **P2 — Keep the fetch bound consistent with the 500-row API limit** → the
   stage-4 bound is `page_size` up to the route's **500**, not 50; the plan
   assertions and the production probe exercise both 50 and 500 so a legal large
   page is neither truncated nor left unverified, and the INCLUDE-payload
   rejection is restated against the real bound.
3. **P1 — Remove the pre-publication live-identity requirement** → the ROADMAP's
   step 9′ now requires the pre-publication check to use the accepted-release
   attestation, the running image digest and the served OpenAPI contract, with the
   **response** identity verified only after publication, matching the design.

### Review round 15 (2026-10-11)

1. **P1 — Define the denominator for the capacity reserve** → correct, and the
   ambiguity was load-bearing: at `Σ_all = 4.0`, 15 % of the ~187 GB new
   footprint is ~28 GB, 15 % of the 292 GB free reading is ~44 GB, and 15 % of
   the 1,948 GB volume is ~292 GB — the last of which is the entire free space,
   so that reading would make the gate unpassable and indistinguishable from a
   hard stop. Section 10's PR4 row now pins the exact formula: the reserve is
   **15 % of the projected new footprint**, the only denominator that scales with
   the risk it covers (WAL written during the build, `CREATE INDEX` temp spill
   beyond `maintenance_work_mem`, and the gap between the measured per-row
   figures and reality). `required_bytes = ceil(1.15 × projected_new_bytes)`,
   with `projected_new_bytes` computed from the measured per-row constants, the
   live `system_count` and the calibrated `sigma_all`, plus 87 GB for Search when
   it is not yet written. Two tests differing only in the `df` fixture pin the
   boundary at `available == required` (passes) and `available == required − 1`
   (refuses); a third pins the receipt's reported inputs so the decision can be
   recomputed without rerunning the gate. The worked examples were checked
   arithmetically and reproduce the directly measured 75.7 GB archetype total to
   within 0.4 %.
2. **P1 — Do not require OpenAPI to prove the ranking identity** → correct, and
   the check was worse than merely weak: `RankingIdentity.ranking_version` and
   `ranking_sha256` are unconstrained `str` (`apps/api/src/models.py:378-379`),
   so an OpenAPI comparison would have passed against **any** image, including
   the old keyed-schema one — exactly the failure the gate exists to catch. Took
   the first of the two offered options. The deployed image digest now carries
   the identity on its own: if the digest matches the one the F2d release was
   attested at, the attested `ranking_version`/`ranking_sha256` are the values
   that code computes. That places one requirement on step 4, now recorded — the
   accepted-release attestation **must record both concrete values**, and the
   publish action refuses when the attestation carries no identity rather than
   treating a missing value as a match. `/openapi.json` keeps the job it can do,
   proving parameter shape, where the values are concrete in the schema (the
   `Literal[60, 76, 88]` enum, the combined `from`/`offset` maximum). Both
   normative sites are corrected (section 10 step 4, and the publish action).
   Rounds 12.1 and 13.1 above described the superseded version.
3. **P2 — Restate the ranking order after the fetch join** → correct. Stage 3's
   `ORDER BY` orders stage 3's output and does not survive stage 4's join, so a
   hash or nested-loop fetch plan could return the right 50 systems in an
   arbitrary sequence. That is the worst shape this bug could take: every row
   correct, only the ranking wrong, and no row-set assertion would see it. Stage
   4 now requires the outermost `SELECT` to repeat `ORDER BY <key>_weighted_e4
   DESC, system_id64 ASC` over the ≤ `page_size` materialized rows, and — taking
   the second half of the finding, which matters as much as the first — the tests
   now assert the **returned row order** on a fixture seeded with deliberate
   ties, plus that two adjacent pages concatenate into one correctly ordered
   sequence with nothing repeated or skipped. Bounding the sort node's input
   proves the query is cheap; only the row order proves it is right.

### Review round 16 (2026-10-11)

Seven findings, all accepted. Three of them (1, 4, 6) are the same class of
error on my part: treating a check that *can* be written as a check that *proves*
the thing it names.

1. **P1 — Account for partial rows when re-running the capacity gate** → correct,
   and the arithmetic inverts near the ceiling: a build interrupted at 90 % needs
   ~21 GB to finish but the full-cost formula would demand 214.8 GB of space it
   has already spent, so the gate would refuse the restart and strand the very
   insert-only rows it exists to protect. Each projected term is now scaled by
   `remaining_fraction`, computed from the build's **own sealed chunk receipts** —
   the same records the resume uses, so there is no second source of truth — and
   a resume counts as a resume only when those receipts carry the same product,
   generation and manifest identity. Both fractions go in the receipt so a
   smaller requirement reads as deliberate scaling, not a weakened gate. A fourth
   PR4 test pins it: 90 % sealed at `Σ_all = 4.0` with low free space passes, and
   the same free space with receipts from a different manifest identity refuses.
2. **P1 — Keep future generation publication atomic with Finder visibility** →
   correct, and the contract reference is the right one. This rollout is safe
   because the pointer already names `parallel_v1` and no Finder products exist
   on it, so nothing becomes invisible. A **later** promotion is a different
   thing: the flip retires the visible generation at commit, and unpublished
   incoming products mean the views hide their rows and the Finder answers 503
   until a second action lands — down, having been up a moment earlier, and
   avoidably, since the ordering was only a choice. `publish_derived_generation`
   now refuses the flip unless, at commit, every registered Finder product on
   the incoming generation is published **or** had no published counterpart on
   the outgoing one. That single rule covers the first launch (second clause) and
   every later promotion (first clause) with no special case, and it lives in the
   function beside the READY/VERIFIED check so no caller can skip it.
3. **P1 — Remove OpenAPI from the ranking-identity check** → correct, and this is
   the finding I should have anticipated when fixing round 15.2: I corrected the
   design and left the controlling ROADMAP saying the superseded thing, which is
   worse than not having fixed it, because the higher authority would have won.
   ROADMAP steps 4′ and 9′ now take the identity from the digest-bound
   accepted-release attestation alone.
4. **P2 — Verify the combined pagination bound outside OpenAPI** → correct, and
   the same mistake as 3 in a different place: JSON Schema cannot relate two
   fields, so `offset + limit <= 10000` is not expressible and an image that
   dropped the validator would publish a byte-identical schema and pass. The
   combined bounds are now proved by a behavioural probe against the deployed
   image — which the 503 does not obstruct, because request validation raises 422
   before the generation is consulted: `offset=9999&limit=1` accepted,
   `offset=9999&limit=2` rejected. OpenAPI keeps the individual maxima and the
   floor enum, which its schema does state concretely. Fixed in the design and
   the ROADMAP together this time.
5. **P1 — Pin the identity check and explanation read to one snapshot** → correct;
   making the data query internally consistent closed the wrong window. The
   window is *between* the check and the query, so a publication landing there
   would return an explanation computed from the new generation under the old
   identity — a 200 carrying exactly the confusion the 409 exists to prevent. The
   identity lookup, the comparison and the generation-pinned read now share one
   read-only `REPEATABLE READ` transaction, as the rankings path already does. A
   test commits a publication from a second connection while the request is
   suspended between the two statements and asserts the answer comes from exactly
   one snapshot: the old explanation or a 409, never a mixture.
6. **P1 — Gate builds on an approved, matching coefficient decision** → correct
   on both halves, and the second half is what makes the first worth anything. A
   complete in-bounds histogram proves the build would *fit*, not that its logic
   was *approved*: a review that rejected the coefficients leaves exactly that
   evidence behind. The committed evidence now carries an explicit
   `coefficient_decision: accepted` (anything else, absent included, refuses),
   **and** the probe's `code_identity` and coefficient digest must equal the
   manifest the builder registers — without which an approved probe could still
   authorize a build whose real tier fractions were never capacity-tested.
7. **P2 — Specify one exact weighted-key rounding rule** → correct, and this one
   would have been very hard to find later: Python's `round` is ties-to-even and
   PostgreSQL `numeric` rounds ties away from zero, so the builder and the exact
   validator could order tied systems differently while every version string
   matched. The definition is now closed in integers with no float anywhere:
   `(score × confidence_ppm × completeness_ppm + 50_000_000) // 100_000_000`. The
   divisor follows from the units rather than being chosen. Checked rather than
   asserted: the numerator peaks at 1e14 (exact in `bigint`), the key at 1e6
   (inside `integer`), and over 500,000 random triples the integer rule agrees
   with the floating-point product at **every** non-tie input — so it changes
   nothing except making ties decidable. The worked tie in the spec
   (`score=1, confidence_ppm=50, completeness_ppm=1_000_000`) is a true half where
   Python yields 0 and PostgreSQL yields 1; the rule yields 1. Half-boundary
   vectors are added to the builder, validator and ranking-identity tests.

### Review round 17 (2026-10-11)

1. **P1 — Require counterparts for every published outgoing product** → correct,
   and my round-16 rule was quantified over the wrong set. Over *incoming
   registrations*, a generation that registers and publishes only `system_search`
   satisfies it vacuously: `system_archetype` is simply absent, so there is no
   registered product to find fault with, and the flip commits while the Finder,
   which needs both, answers 503. The rule is now anchored to what is visible now
   and must not stop being visible — the **outgoing published set**: every Finder
   product published on the outgoing generation must have a published counterpart
   on the incoming one. A missing counterpart and an unpublished counterpart
   become the same violation, which is right, because in both cases something the
   Finder is serving stops being served. The first launch still passes (the
   outgoing generation publishes no Finder products), so it remains one rule with
   no dated exemption. A test now covers the search-only promotion specifically —
   the case the previous rule let through.
2. **P1 — Use an exact integer completeness source end to end** → correct on both
   counts, and the first is the more embarrassing: I specified an exact
   `completeness_ppm` input without checking that it existed.
   `system_search.completeness` is `double precision`
   (`004_v3_search_spatial_clusters.sql:41`), so reading it would have put a float
   straight back into a definition whose purpose is to have none. The exact source
   does exist and the builder already reads it — `evidence_completeness` is an
   integer array in 1e-4 units that the builder divides by `10000.0`
   (`scripts/v3_system_archetype.py:277`) — so `completeness_ppm =
   min(evidence_completeness) × 100`, taken **before** any division, which is
   exactly the source suggested. Verified: it lands in `0..1_000_000`, the
   numerator peaks at 1e14 (exact in `bigint`) and the key at 1e6 (inside
   `integer`). `completeness_ppm` is also now **persisted on the wide row**, so
   the builder, validator and explanation route read one stored integer instead of
   each deriving their own; that costs 4 bytes per row (≈ 0.8 GB), and the
   capacity gate's 221.7 B/row constant must be re-measured against the final
   migration text before the build, as section 8 already requires. On the second
   count: the manifest definition string and the validator check both still
   carried floating `round(...)` forms, which would have reintroduced the exact
   ambiguity round 16 removed. Both now carry the integer expression verbatim, and
   the validator additionally re-derives the stored `completeness_ppm` from the
   rating vector and fails closed if the two disagree.
3. **P1 — Scope the empty-product gate to the target generation** → correct, and
   the consequence is that the gate could never have passed: a READY
   `system_search` is deliberately retained on `opt1` with its purge deferred
   (ROADMAP lines 140-143), so a literal global emptiness check against
   `v3_meta.derived_product` would have blocked the very deployment it authorizes,
   permanently. Both the design and the controlling ROADMAP now require zero
   Finder product rows **on the pinned `parallel_v1` target generation** only, and
   say why, so retained products elsewhere cannot be mistaken for a blocker.

Swept rather than reviewed — three further instances of the same two errors,
fixed in the same commit:

4. The **ROADMAP** still said "no product rows" (finding 3 in the
   higher-authority document, which would have won). Fixed there too; round 16
   taught me to check the ROADMAP in the same pass rather than the round after.
5. The **`011` DDL comment** still documented the key as `round(score ×
   confidence × completeness × 10,000)`. A comment next to the column is where an
   implementer will actually look, so it now carries the integer expression and an
   explicit "never `round()`".
6. The **`_confidence_ppm` conversion** has the same tie ambiguity, and no review
   round had reached it: `round(confidence * 1_000_000)` with `round()`'s default
   mode. Unlike completeness there is no integer source, because model confidence
   is genuinely a float, so instead of inventing one the rule is pinned to a
   single place — `floor(confidence * 1_000_000 + 0.5)`, round-half-up and named
   explicitly, computed by a shared helper that the validator **calls** rather
   than reimplements, and never recomputed in SQL.

### Review round 18 (2026-10-11)

Six findings, all accepted, and all the same failure on my part: a decision made
in one section and not carried to the places that depend on it. Round 17 added
three such decisions (the persisted `completeness_ppm`, the integer key rule, the
half-up confidence helper) and round 31 on PR #801 added a fourth (the
generation-free model digest); each of those is where one of these six landed. So
after fixing the six I swept the normative body for **every** mention of each
decision rather than only the cited lines, and found two more (below).

1. **P1 — Add `completeness_ppm` to the wide-table DDL** → correct, and it was the
   most basic kind of gap: I wrote that the column is persisted and that the
   validator recomputes and compares it, and never added it to the `CREATE TABLE`.
   An implementer following the normative DDL would have had nothing to store the
   value in. Added with its range check, a comment naming the exact source, and
   its migration tests.
2. **P1 — Derive the capacity heap cost from the final measurement** → correct, and
   the silence is what makes it serious: the gate checks the footprint receipt's
   provenance and then ignored its numbers in favour of a hard-coded 221.7 B/row,
   so near the free-space boundary the irreversible build could pass while short
   of the reserve the gate claims to enforce, with a valid receipt sitting right
   there unconsulted. **Every** per-row cost now comes from the receipt — heap,
   primary key, weighted index and the tier coefficient — and the gate refuses
   when the receipt does not carry all four rather than falling back to a default.
   The figures in the document are now explicitly illustrative of the arithmetic
   rather than inputs to it, which also means a future migration edit cannot leave
   a stale constant behind.
3. **P2 — Carry `archetype_model_sha256` through PR1's envelopes** → correct.
   Section 5.1 added the digest and required it in `ranking_provenance`, but the
   implementation list, both envelope constructors and the generated-client entry
   still named only two fields — so the field would have existed in the design and
   never reached the wire, and F4's cross-generation comparison would have had
   nothing to compare on. All three digests now go through the shared model, both
   envelopes, the regenerated clients and the identity tests, with a note on why
   both hashes are needed: the manifest digest cannot answer "same model?" because
   it embeds generation identity, and the model digest cannot answer "same build?"
   because it deliberately does not.
4. **P1 — Scope the unpublished-generation success test** → correct, and this is
   the one that would have done real damage: the test as written required
   `publish_derived_generation` to **succeed** whenever registered products are
   READY but unpublished, which is section 7.4's forbidden case stated as an
   acceptance criterion. An implementer satisfying the test suite would have built
   the outage. Case 8 is now scoped to an empty outgoing published set — the
   first-launch case — and a new case 8b requires refusal when any product
   published on the outgoing generation lacks a published incoming counterpart,
   whether unpublished or not registered at all.
5. **P2 — Hash the exact integer key formula in `PROFILE_SPEC`** → correct, and
   `PROFILE_SPEC` is precisely the wrong place to leave it ambiguous, because it
   is the **hashed** authority: two implementations could order boundary rows
   differently while claiming the same `ranking_sha256`, which is the one
   guarantee that hash exists to give. The exact integer expression is now hashed,
   with the reason recorded next to it.
6. **P2 — Use the shared half-up helper in validation** → correct, and the
   direction of the failure is the notable part: a row built **correctly** by the
   half-up builder would be **rejected** by a ties-to-even validator, so the
   immutable product could never reach READY — a build that fails with no bad data
   to point at, on one row in a few hundred million. The validator now **calls**
   the shared helper rather than restating the expression, which is the only form
   of this fix that cannot drift, and its tests carry a half-boundary confidence
   vector.

Swept rather than reviewed:

7. The Search dependency's stated reason was now false — "the stored ranking keys
   depend on `system_search.completeness`" — since round 17 moved completeness to
   the rating vector. The dependency itself still holds for different reasons (the
   builder reads `system_search` confidence for `weighted_potential`, and the
   rankings envelope joins it for response columns), so the requirement stands
   with a corrected justification rather than being dropped. A requirement resting
   on a reason that no longer applies is one refactor away from being deleted as
   dead weight.
8. Section 3.1 still told the reader the capacity gate's "221.7 B/row heap
   constant must be re-measured", which finding 2 had just made meaningless. It
   now says what actually has to happen: the receipt must be produced against the
   final migration text including the new column.

### Review round 19 (2026-10-11)

1. **P1 — Cast the weighted-key numerator to bigint** → correct, and it is a hard
   failure rather than a nuance. The declared operands are `smallint` and
   `integer`, so PostgreSQL evaluates `smallint × integer × integer` as
   **`integer`** and overflows at entirely ordinary values: `100 × 1_000_000 ×
   1_000_000` is 1e14 against an `integer` ceiling of 2.1e9. The "exact in
   `bigint`" range I had verified is the range of the *result*, which the
   expression would never reach — validation would raise `integer out of range`,
   no correct product row could pass, and the immutable build could never reach
   READY. I had checked the arithmetic in Python, where integers are unbounded,
   and carried the conclusion into SQL where it does not hold.
   The spec now carries the exact casted expression
   (`(<key>_score::bigint * <key>_confidence_ppm * completeness_ppm + 50000000) /
   100000000`) for the validator and the boundary tests to use verbatim, notes
   that one cast promotes the whole chain, and records that SQL's truncating
   division equals the floor here because every operand is non-negative.
2. **P2 — Exclude build code from the model-only digest** → correct, and your
   suggested division is better than either of my two attempts. Round 31 included
   the broad `code_sha256`, which made a builder fix or a storage-only migration
   change suppress the comparison. Round 32 then removed **all** source hashes,
   which was the opposite error: the digest rested entirely on declared constants,
   so a change to the model's *logic* that left its constants alone would not show
   up at all.
   Hashing the **shared model file only** is the division that matches the field's
   meaning. `code_identity()` covers three files — builder, model, migration — and
   the model file owns scoring while the builder owns iteration, batching and
   storage and the migration owns layout. So a change to how scores are computed
   always moves the digest, and a change to how they are written never does. The
   broad `code_sha256` stays in `archetype_manifest_sha256`, where identifying one
   exact build is the point. This also retires most of the "declaration, not proof"
   caveat round 32 had to add.
3. **P1 — Scope the release gate to the target generation** → correct, and this is
   the third place the same scoping had to reach. Round 17 fixed the step-4 table
   row and the ROADMAP; the PR4 implementation list and the rollout-reordering
   paragraph still said "no product rows at all", and the implementation list is
   what someone writing the gate would read. Both now require zero Finder product
   rows **on the pinned `parallel_v1` generation**, each with the reason attached
   (the retained `opt1` `system_search`, purge deferred), because the bare scoping
   without its reason is what keeps getting simplified back to a global check.

### Review round 20 (2026-10-11)

1. **P2 — Replace the ambiguous weighted-key rounding rule** → correct, in a third
   document. Round 16 fixed the design, round 19 the DDL comment and the manifest,
   and `docs/operations/v3-finder-capacity-decision-2026-10-10.md` still defined the
   key with `round(...)`. That document is the owner-facing decision record, so an
   implementer reading it would have built rows the exact validator rejects. It now
   carries the integer expression, the Python-versus-PostgreSQL tie difference, and
   the `bigint` cast — all three, because the short form is what keeps coming back.
2. **P2 — Verify the model digest after go-live** → correct. Step 10 checked two of
   the three archetype identity values, and the omitted one is the only one F4 uses
   to decide whether scores from different generations may be compared. A response
   that omitted or mis-populated exactly that field would have passed live
   verification and silently disabled the comparison — no error, just a feature that
   never fires. Step 10 now compares all three.
3. **P1 — Convert the probe histogram before measurement** → correct, and this one
   **blocks the rollout** as written. The probe emits counts under
   `per_archetype.<key>.tier_histogram` keyed `S`/`A`/`B`/`C`/`D`;
   `--fractions-json` takes `{<key>: {"60": f, "76": f, "88": f}}`. Handing the probe
   artifact to the script reports every archetype missing and exits, so the mandatory
   measured-histogram receipt could never be produced and step 6 would block
   indefinitely — a prescribed command that cannot run, sitting on the critical path.
   The conversion is now specified exactly, and it is **cumulative** because each
   floor admits its own tier and every higher one: `f["88"] = S/total`,
   `f["76"] = (S+A)/total`, `f["60"] = (S+A+B)/total`, so
   `f["60"] >= f["76"] >= f["88"]` by construction. PR4 owns a committed converter
   rather than a documented manual step, deliberately: the fractions digest is a
   fail-closed gate input, so the transformation producing it must be reproducible
   and reviewable, and a by-hand JSON edit is neither. The converter asserts the
   cumulative ordering, that every exposed key is present, and that each total
   matches the probe's recorded row count.
4. **P1 — Remove the superseded fresh-generation instructions** → correct, and this
   is the most serious of the four because of **where** it is: the highest-authority
   programme document continued, immediately after the replacement sequence, with
   the pre-wide-row route — "the only executable path", build actions in the old
   steps 5 and 7, and an owner choice before step 4 between accepting a fresh
   Ratings V4 generation (1.59 billion keyed archetype rows plus a separate summary
   table) or designing a purge path first. An operator following the authority chain
   in order would have hit the current sequence and then been told to do something
   incompatible with it, by the same document.
   That block is now explicitly marked superseded, with each stale instruction named
   and corrected rather than silently deleted: both products attach to the published
   `parallel_v1` generation, so no fresh generation is built and no purge decision
   gates step 4; the wide row is one row per system with the summary as a view, so
   the 1.59-billion and separate-summary figures describe nothing that will be
   written; and capacity is settled by the fail-closed combined gate rather than by
   an owner choice. The parts that remain true — the insert-only triggers, the
   absence of a governed purge path — are kept and marked as no longer being
   prerequisites, with disk reclamation tracked against the read-only inventory
   instead.

### Review round 21 (2026-10-11)

1. **P1 — Compare model outputs only when source vectors match** → correct, and it
   is the same defect the F4 design had in its round 34, on this side of the
   contract: I fixed it there and left it here. A later generation may be rebuilt
   from a different canonical generation, so a system present in both can
   legitimately carry different rating vectors or completeness and therefore a
   different `<key>_weighted_e4` under an identical model. Requiring equal keys
   because the digests match would reject that valid build and **block
   publication** — failing on exactly the data refresh the generation-free digest
   exists to permit.
   The assertion is now against a committed **frozen input fixture** of
   `(score, confidence_ppm, completeness_ppm)` vectors including the half
   boundaries, which isolates the model from the data it is applied to. Of your two
   options I took the fixture rather than restricting comparison to
   byte-identical source vectors, because the fixture is deterministic and
   reviewable while "systems whose complete source vectors are byte-identical" is a
   set that could be empty on any given pair of generations — a check that silently
   verifies nothing.
2. **P2 — Regenerate the evidence with the checked-in script** → correct, and I
   could not do the first half: the disposable PostgreSQL 18 instance this was
   measured on no longer exists, so I cannot rerun it, and I would rather say that
   than commit a figure I did not produce.
   I took the second option and made the provenance verifiable rather than merely
   asserted. The artifact's fields are exactly those emitted by the script at
   **`6f9f79e`**; `fractions_canonical`, `fractions_sha256` and `sigma_all` were
   added at `c0e49fa` (round 12), which is why the current revision could not have
   produced it. That commit is now recorded in the artifact itself along with the
   reason.
   Recording it surfaced something worth stating outright, which is now also in the
   artifact: this file is **not** a capacity-gate input and must never be
   substituted for one. Its `score_distribution_source` is
   `declared-synthetic-bell` with no fractions digest, so the gate would refuse it.
   It is layout-comparison evidence for section 3.4, and the gate's input is the
   pre-build receipt measured against the final `011` with the real histogram.
3. **P1 — Gate publication on the production plan before commit** → correct, and
   this is the best finding on this PR. The step as written made its **first
   assertion against production statistics at the one moment where failing it could
   not be undone**: after `published_at` had committed, a one-way transition with no
   governed path to clear it. Disposable-fixture plans passing is not evidence about
   production statistics or view expansion, so users would have been exposed
   immediately on any divergence, with no way back.
   Your mechanism is what makes the fix available: the transaction **can see its own
   newly visible rows**, so the picked query can be planned against the real
   statistics and the expanded views after both updates and before commit, while the
   change is still reversible. Any plan mismatch now rolls the publication back. The
   post-commit probe at step 10 is kept, but as confirmation that the committed
   state still plans correctly rather than as the first check.

### Review round 22 (2026-10-11)

Six findings, all accepted. Three of them (1, 5 and the ROADMAP half of 2) are the
same lesson I have now been taught several times: a fix recorded only in the design
does not bind, because the ROADMAP outranks it.

1. **P1 — Gate the build on the approved probe identity** → correct. Round 16 added
   `coefficient_decision: accepted` and the probe-identity match to the design and
   not to the ROADMAP, which still gated on histogram completeness, digest, size and
   disk space alone. Since the ROADMAP wins, an implementation following it could
   still launch the immutable, non-purgeable build from a **rejected** probe, or from
   an approved probe whose scoring logic differs from the manifest the builder
   registers. Both checks are now in step 6′, with the cumulative histogram
   conversion alongside them, since that is the other thing step 6′ cannot be
   executed without.
2. **P1 — Run the plan probe on the publication connection** → correct, and the
   pre-commit check was **impossible as specified**. Round 21 said the probe runs
   inside the publication transaction; the implementation plan still described a
   standalone read-only action, which opens its own connection and therefore cannot
   see the publisher's uncommitted `published_at` updates. So the one thing the
   round-21 fix existed for — planning against the newly visible views while the
   change is still reversible — could not have happened. The publish action now
   executes the same generated `EXPLAIN` statements on its **own** connection inside
   its transaction, sharing the SQL builders and plan assertions with the read-only
   action so the two cannot diverge; that action remains the post-commit form.
3. **P1 — Validate model identity against frozen inputs** → correct. I fixed the
   prose in section 5.1 and left the implementation list asserting that equal digests
   must produce identical keys for a shared sample of systems **across generations** —
   which is the defect, stated as an implementation requirement. A later generation
   rebuilt from different canonical data can legitimately give a system a different
   key under an identical model, so the assertion would reject a valid rebuild and
   block READY. The list now states what it does assert (digest stability) and
   explicitly that key equality is against the frozen fixture, not across
   generations.
4. **P1 — Probe every archetype's production plan** → correct, and the same defect as
   the F4 scale receipt's (its round 35), here on the production gate where it matters
   more. One archetype at three floors tests 3 of 24 pairs, and planner choices depend
   on each weighted-key column's own statistics and its partial index's selectivity —
   so the tested key can use its bounded partial while another chooses a sequential
   scan and sort over 198.5 million rows. Publication would pass, and that
   user-selectable archetype would serve the unbounded plan. All eight keys at all
   three floors, before commit.
5. **P1 — Keep implementation blocked on unresolved owner decisions** → correct, and
   the wording was the problem: having recorded answers to questions 1 and 5, the
   ROADMAP said "this prerequisite is satisfied" — which reads as *the* prerequisite.
   Questions 2, 3, 4, 7 and 8 remain open and govern the persisted confidence
   representation, model ownership, the explanation endpoint, PR sequencing and atomic
   publication. Following that sentence, implementations of choices the owner has not
   accepted could reach `main`, authorized by the controlling document. It now names
   which prerequisite is satisfied, lists what is still open, and states that the code
   PRs encoding any unresolved choice may not merge until the answer is recorded.
   (Question 9 is answered: the 422 contract plus the owner's stated wish for filtered
   archetypes as a later increment.)
6. **P1 — Analyze the completed table before probing its plans** → correct, and I had
   not thought about statistics at all. Nothing analyzes `system_archetype` after its
   198.5 million rows are inserted, and an `EXPLAIN` on default or stale statistics is
   not evidence about the production plan **in either direction**: it can reject a
   sound build on bad estimates, or — the dangerous case — pass, and then autovacuum
   analyzes after commit and the planner moves off the bounded plan with users already
   being served. The gate would have certified a plan that was about to change. The
   Archetype build now runs and receipts `ANALYZE` on the completed table as its last
   action, and both probes assert `last_analyze` is later than the final insert before
   reading any plan.

### Review round 23 (2026-10-11)

1. **P1 — Require the plan probe before publication commits** → correct, and the
   same design-only mistake for the fourth time on this PR: rounds 21 and 22 built
   the pre-commit probe into the design and left the controlling ROADMAP directing
   the action to publish straight after the image and identity checks. Following the
   higher authority literally, the one-way `published_at` transition commits with
   the production plan never validated — and an archetype whose statistics select a
   sequential scan over 198.5 million rows goes live with no way back.
   ROADMAP step 9′ now carries the whole requirement: the publisher's **own**
   connection, inside the transaction, after both updates and before commit, **all
   eight archetypes at all three floors**, with `ANALYZE` receipted by the build
   step and `last_analyze` asserted to postdate the final insert. I put the reasons
   in alongside, because a bare instruction to run a probe is what gets simplified
   back to "publish after the identity checks".
2. **P2 — Drop the parameterized floor from the count query** → correct, and round
   22's fix reached the page window and not the count window. `<key>_score` is not
   in the partial index, so a parameterized `<key>_score >= $n` forces a heap fetch
   for each of up to **10,001** candidate rows — and it would fail the `Index Only
   Scan` assertion the publication gate now makes, so the gate I have just
   strengthened would have refused the implementation the design specified. The
   count window takes the server-selected literal alone, for exactly the reason the
   page window does.

### Review round 24 (2026-10-11)

1. **P1 — Restore the unresolved atomic-publication decision** → correct, and the
   cause is a numbering collision I walked straight into: the **capacity decision**
   and this design number their owner questions independently. The owner answered
   capacity-decision question 6 (the score-index layout) yes, and I carried that
   "6 is answered" into the ROADMAP's list of design questions — where 6 is **atomic
   publication**, which is open. The result was the worst possible pair of errors:
   the one-transaction publication PR free to merge with no owner answer, while
   question 8 (no purge), an **already accepted** decision, was listed as blocking.
   The ROADMAP now lists 2, 3, 4, 6 and 7 as open, records 1, 5, 8 and 9 as answered,
   and states explicitly that design question 6 is not the capacity decision's
   question 6 — because the collision will otherwise be made again.
2. **P1 — Vacuum the completed table before requiring index-only plans** → correct,
   and round 22's `ANALYZE` was the wrong half of the fix. `ANALYZE` collects
   statistics but does **not** mark heap pages all-visible, and after a bulk insert
   the visibility map is empty. So two things follow, and I had seen neither: the
   planner costs the required `Index Only Scan` as though every row needed a heap
   visit and may plan something else, **rejecting a sound rollout**; and an `Index
   Only Scan` that is chosen anyway still performs a heap fetch per row, which an
   assertion on node type and row count cannot detect — the gate would have
   certified "index-only" over up to 10,001 random heap reads.
   The build step now receipts **`VACUUM (ANALYZE)`**, each probe asserts both
   `last_vacuum` and `last_analyze` postdate the final insert, and the plan
   assertions require **`Heap Fetches: 0`** — which is the only one of these
   assertions that tests what "index-only" actually means.
3. **P1 — Read completeness from the actual rating-vector column** → correct, and I
   took the name from the builder's own vocabulary without checking the schema.
   `system_rating_vector` has `completeness smallint[]`
   (`003_ratings_v4_derived.sql:120`); `evidence_completeness` exists only as a
   `double precision` alias in the unnested `system_economy_rating` view, where it
   is already `completeness[i] / 10000`
   (`003_ratings_v4_derived.sql:223`). So the instruction would either raise an
   undefined-column error — preventing the immutable product from reaching READY —
   or pull in the float the whole integer rule exists to remove. Both normative
   sites and the DDL comment now name `min(system_rating_vector.completeness) × 100`.
4. **P1 — Keep storage-only changes out of the model digest** → correct, and this is
   the fourth iteration of this field's scope, each one narrowing it for a reason the
   previous had missed. Your argument is the sharpest yet because it is
   self-referential: the model file also defines `ARCHETYPE_VERSION`, and **this
   design bumps it to `v3-archetype-4` solely because the persisted storage shape
   changed**. So hashing the whole file would have broken the field on this design's
   own version bump — plus any explanation-only edit or non-semantic refactor, while
   the weighted scores stayed comparable.
   The digest now covers a **named set of members** of the model file rather than the
   file: coefficients, anchors, key order, tier thresholds, the `_weighted_e4`
   integer expression, the confidence rounding rule, and the **source text of the
   named scoring functions** (`fit_all` and what it calls). It excludes
   `ARCHETYPE_VERSION`, the explanation construction and every storage-shape
   constant. That preserves round 19's requirement — a change to how scores are
   computed always moves the digest — while a change to how they are stored,
   versioned or explained never does, which hashing the file could not deliver.

### Review round 25 (2026-10-11)

1. **P1 — Require VACUUM in the controlling publication gate** → correct, and the
   same design-only pattern for the fifth time on this PR: round 24 put
   `VACUUM (ANALYZE)`, `last_vacuum` and `Heap Fetches: 0` into the design and left
   the ROADMAP requiring `ANALYZE`/`last_analyze` alone. Since the ROADMAP outranks
   it, the weaker gate is the one that binds — and the consequence is the specific
   one round 24 identified: after the bulk insert the visibility map is empty, so an
   apparent `Index Only Scan` can still perform up to 10,001 heap fetches per request
   and be **published as bounded**. ROADMAP step 9′ now carries all three
   requirements with the reason for each, including that only the zero-heap-fetch
   assertion tests what index-only means.
2. **P1 — Exclude explanation code from the semantic digest** → correct, and the
   exclusion was **unimplementable as written**. Hashing `fit_all` and everything it
   calls does not exclude explanation construction, because `_fit_anchored` and
   `_fit_flexible` build their explanation dictionaries **inside** the scoring
   functions (`scripts/v3_system_archetype_model.py:120-145`) — which I asserted an
   exclusion for without checking. So an explanation-only edit would still move the
   digest and suppress the F4 comparison with scores provably unchanged, which is the
   precise defect round 24 narrowed this scope to avoid.
   PR1 now **separates explanation construction out of the scoring path**: each
   `_fit_*` returns score, tier and confidence, and a distinct `_explain_*` builds the
   dictionary from the same `SystemVectors`; the digest hashes the `_fit_*` functions
   and excludes the `_explain_*` ones. That is a behaviour-preserving refactor of code
   PR1 already touches, and it is what makes the exclusion true rather than
   aspirational. A test asserts the digest is unchanged by an edit confined to an
   `_explain_*` function and changed by any edit to a `_fit_*` one — which is the
   assertion that would have caught this.
3. **P1 — Probe the local-search window bound before release** → correct. Round 16
   established that JSON Schema cannot express a cross-field bound and that both
   combined bounds therefore need behavioural probes; the ROADMAP then described only
   the `offset`/`limit` pair while claiming to prove both. An image missing **only**
   the local-search `from + size` validator publishes a byte-identical OpenAPI schema
   and passes both stated probes, after which a direct `from=9999&size=2` escapes the
   10,000-row window and drives an excessive `OFFSET`. Both pairs are now required,
   accepted and rejected, with that reasoning recorded so neither is dropped as
   duplicative of the other.

### Review round 26 (2026-10-11)

1. **P1 — Hash the complete scoring call graph** → correct, and it fails in the
   **dangerous** direction, which is what makes it the more serious of the two errors
   this field has had. Round 25 narrowed the digest to the `_fit_*` function bodies
   and left score-affecting code outside it: the fits call `_quality`, `_clamp` and
   `tier_of` (`scripts/v3_system_archetype_model.py:65-84`), and `fit_all` is the
   **dispatcher** deciding which fit applies to each key (`:148`). A changed clamp
   bound, a different quality rule, a reordered tier threshold or a key routed to the
   other fit would all change persisted scores while leaving `archetype_model_sha256`
   identical — and F4 would then compare outputs from **different models as
   equivalent**.
   Round 35 settled that this field must err towards suppressing a comparison rather
   than allowing a wrong one, because a false "not comparable" loses a feature
   visibly while a false "comparable" is a silently wrong comparison shown as fact.
   Every previous correction to this digest narrowed it; this one is the first to
   widen it, and that is the right direction for the risk.
   The digest now covers `fit_all` and **every function reachable from it**, with the
   `_explain_*` functions as the only exclusion, determined by **walking the call
   graph** rather than from a hand-maintained list — a list is one refactor away from
   being incomplete and would fail silently in the dangerous direction, whereas a
   graph walk covers a helper added later automatically. Tests assert one changed
   case per covered function, because "the call graph" is only as real as the
   assertions behind it.

### Review round 27 (2026-10-12)

1. **P1 — Bind completeness derivation into the model digest** → correct. The
   builder's `min(system_rating_vector.completeness) × 100` transformation sits
   outside the `fit_all` graph, while the frozen fixture began with its already-
   derived output. A coordinated builder/validator edit could therefore change every
   persisted weighted key without moving `archetype_model_sha256`. PR1 now owns a
   shared helper used by both paths, hashes that helper as a second semantic root,
   and tests from raw rating-vector completeness arrays through the final key.
2. **P1 — Correct the rollout dependency step references** → correct. The table's
   calibration evidence is produced in step 5 and its deployed release is step 4;
   the Archetype-build and publication rows now cite those steps respectively.
3. **P1 — Supersede the stale fresh-generation instructions** → correct. The
   production-state document retained two executable-sounding paragraphs from the
   superseded route. They are now explicitly marked as historical measurement
   evidence, with the controlling ROADMAP's existing `parallel_v1` attachment and
   combined capacity gate identified as the execution path.
4. **P1 — Carry probe approval into the capacity action** → correct. The rollout
   table required an accepted coefficient decision and probe/manifest identity
   equality, but PR4's executable checklist began at histogram completeness. The
   action contract now refuses a missing or non-accepted decision and either code or
   coefficient identity mismatch before consuming the histogram, with independent
   negative tests while preserving every existing refusal.
5. **P1 — Emit the normalized metrics consumed by the capacity gate** → correct.
   PR4 consumed four normalized per-row fields that PR1's measurement-script contract
   never emitted. PR1 now requires all four, derives them from the measured heap and
   classified indexes (including tier bytes normalized by `sigma_all`), and tests
   their provenance rather than accepting aggregate index bytes.

### Review round 28 (2026-10-12)

1. **P2 — Include the raw-input adapter in the model digest** → correct. After
   round 27, `_read_chunk_vectors` still divided completeness and confidence by
   10,000 and aggregated opportunities with `count`/`avg` in SQL before `fit_all`,
   all outside both hashed roots, and the frozen fixture started after most of it.
   Rather than add a third root, section 5.1 now defines one scoring entry point,
   `score_raw_system`, that starts from database-shaped values (the raw vector row
   and integer `count`/`sum` opportunity groups) and returns every persisted
   model-derived value; the digest walks its whole call graph (`_explain_*`
   excluded) plus the shared opportunity select-list constant. Builder, validator
   and explanation route call only that entry point, the fixture is raw database
   rows exercised through the real chunk read on disposable PostgreSQL 18, and the
   last-bit change from moving the mean out of `avg` is stated with why it is safe.

### Review round 29 (2026-10-12)

1. **P2 — Preserve the existing confidence rounding semantics** → the ambiguity is
   real, the behaviour change is not, provided the helper is fed the right value;
   now stated. The fits already return `round(conf, 6)` and the half-up helper
   converts that six-decimal value to ppm, where no tie can occur (checked for all
   1,000,001 values). Your example — raw `0.9949005` — therefore persists as
   `994900`, matching today; half-up would only differ if applied to the raw
   product, which section 3.1 now forbids, with a test pinning the example and the
   exhaustive conversion.
2. **P1 — Route the calibration probe through the new scoring entry point** →
   correct. The probe calls `fit_all` on `_read_chunk_vectors` output today, so
   once that function is a raw fetch the probe would either break or keep the
   superseded scaling and SQL `avg` path while reporting the builder's
   `code_identity`. PR1 now changes the probe to score the same raw rows through
   `score_raw_system`, forbids a private copy of the old adapter, and tests that the
   probe's per-key tier counts equal the builder's persisted tiers on the same
   fixture chunk; rollout step 5 says the action is unchanged but the Python it runs
   is not.

### Review round 30 (2026-10-12)

1. **P1 — Bind the probe to the canonical model hash** → correct, and the root
   cause was wider than the probe. `code_identity()` hashes
   `scripts/v3_system_archetype_model.py`, which PR1 turns into a re-export of the
   canonical `shared_contracts/` file, so a scoring-only edit to the canonical file
   would have moved no hash in `code_sha256` at all. PR1 now hashes the canonical
   file (with the re-export, the builder and `011`), tested by an edit confined to
   it; and the probe receipt also carries `archetype_model_sha256`, which rollout
   step 5 and PR4's action compare with the manifest's alongside the existing two
   objects, with its own refusal and test.
2. **P1 — Block generation retirement during attached builds** → correct. The
   counterpart rule quantified over the outgoing *published* set, so an unfinished
   product on the outgoing generation was invisible to it and would be stranded
   once its base retired. `publish_derived_generation` now also refuses while any
   outgoing product is `BUILDING` or `VALIDATING`; the operator first brings it to
   `READY` or moves it to `FAILED` (still permitted while its base is PUBLISHED).
   Tests cover both states, the resolved case and the non-blocking terminal states.

### Review round 31 (2026-10-12)

1. **P2 — Keep combined pagination bounds out of the OpenAPI check** → correct.
   PR4's checklist still said `/openapi.json` proves the combined `from`/`offset`
   bound as a maximum, contradicting rollout step 4 and the ROADMAP. It now limits
   the schema check to the floor enum and the four individual maxima and names the
   behavioural accepted/rejected pairs as the only proof of the two combined
   bounds, re-run by the publish action.

### Review round 32 (2026-10-12)

1. **P2 — Canonicalize scoring semantics instead of raw source text** → correct as
   far as it can be. Each covered function is now hashed as its normalized syntax
   tree with the docstring removed, and the select-list constant with whitespace
   collapsed, so comments, docstrings and formatting no longer move the digest
   (new test cases for each). A refactor that changes the tree but not the values
   still moves it: program equivalence is undecidable in general, and that error
   is the suppression direction the asymmetry argument already accepts. The
   manifest records the CPython version the tree was taken under.

### Review round 33 (2026-10-12)

1. **P1 — Define a feasible atomic generation-promotion path** → correct; the rule
   was unsatisfiable as written, because product publication requires the base to
   be current already. `publish_derived_generation` now takes the incoming
   products as an argument and, in one transaction, verifies them, flips the
   pointer, publishes them through the shared routine (whose current-PUBLISHED
   check then passes) and only then evaluates the counterpart and
   unfinished-product rules, rolling everything back on a violation. Tests cover
   the atomic commit and both refusals.
2. **P2 — Bind the rating-vector select contract into the model digest** →
   correct. Its select list is now a second hashed constant shared by both reads,
   and `score_raw_system` takes a named row built from it, so a reorder or cast
   moves the digest; the digest tests cover both constants.
3. **P1 — Assert bounded access for every joined relation** → correct. The probe
   now requires every non-window node reading `system_search` or
   `system_archetype` to be a primary-key index scan with
   `(rows + rows removed) × loops ≤ 10,001`, and fails on any sequential, bitmap
   heap, hash or merge read of either relation, in both the page and count plans.
4. **P2 — Make histogram-backed footprint samples deterministic** → correct, fixed
   in the script: the fractions path assigns bands from a Weyl sequence over the
   row number (realized fractions within about 1/rows of the targets; a Python
   mirror of the SQL is tested), and the bell layouts are seeded with `setseed`
   before each fill. The receipt records the sampling method and seed.

### Review round 34 (2026-10-12)

1. **P1 — Remove the legacy generation-publisher overload** → correct. A new
   argument list makes `CREATE OR REPLACE` an overload, leaving the
   seven-argument publisher callable without either rule. `015` now drops that
   exact signature in the same transaction, with tests that it is gone, that one
   publisher remains, and that an old-style call fails.
2. **P1 — Probe the live default ranking path before publication** → correct. The
   probe covered only picked pairs; it now also plans and bounds the no-pick page
   and its sentinel count — the request the live Explore flow sends by default —
   with the same rules, on the publication connection before commit.

### Review round 35 (2026-10-12)

1. **P2 — Remove the whole-file hash from the model digest** → correct. The
   paragraph heading still said the digest included `model_file_sha256`,
   contradicting the member-level hashing that follows it. It now says the digest
   includes no whole-file hash; `model_file_sha256` stays in the product manifest
   (and so in `archetype_manifest_sha256`) for exact-build identity and the
   explanation route's deployed-file check.
2. **P2 — Keep step 4′ blocked on the remaining owner decisions** → correct, fixed
   in the capacity-decision document's status line: only the questions 5/6
   prerequisite is satisfied, and step 4′ stays blocked on the unresolved F2d
   design questions, as the ROADMAP says.
3. **P1 — Define an ordered window for the default count probe** → correct. The
   no-pick sentinel count has no `ORDER BY`, so requiring a `weighted_potential`
   window would reject a bounded plan. For that count the probe now prescribes
   no node type and bounds work instead: capped by `LIMIT 10001`, with
   `(rows + rows removed) × loops ≤ 10,001` on every node reading either relation.

### Review round 36 (2026-10-12)

1. **Octopus — fractions mode crashes when a key omits a floor** → correct, fixed
   in the script: each key's floors are validated as an object with all three
   numeric entries before use, and malformed input stops with the script's own
   message; tests cover a missing 88, a missing 60, a non-number and a non-object.
2. **P1 — Compare the probe with a manifest available before the gate** →
   correct. The probe now carries the complete expected manifest computed by
   `product_manifest()`; steps 5–6 compare against it, and step 8's registration
   must reproduce it byte for byte or refuse.
3. **P2 — Hash the complete opportunity-input query contract** → correct, for both
   reads: each is one shared SQL constant (select, joins, predicates, grouping,
   ordering; only generation and chunk/system bound) used verbatim by builder,
   validator and explanation route and hashed whole.
4. **P2 — Compare persisted ranking keys in the explanation route** → correct. The
   route now reads and compares `completeness_ppm` and all eight weighted keys,
   with fail-closed tests for a divergent value of each kind.
5. **P2 — Size indexes from a representative tier histogram** → correct. New
   step 5a: seeded random chunk sampling (or a complete read) and a one-sided
   99.9 % upper bound per key and floor feed `Σ_all` and the footprint receipt.
6. **P1 — Include the no-pick tie-break in its ordering index** → correct. The
   index is now `(derived_generation_id, weighted_potential DESC NULLS LAST,
   system_id64)`, matching the `ORDER BY` exactly; about 1.6 GB more, covered by
   PR1's re-measurement.

### Review round 37 (2026-10-12)

1. **P1 — Carry sampled upper bounds into the controlling gate** → correct. The
   ROADMAP's step 7′ now requires the converter's 99.9 % upper bounds whenever the
   probe sampled, and the converter section defines them (per-chunk cumulative
   fractions, bound per key and floor, ordering repaired upward only) with tests
   for complete, sampled and repaired inputs.
2. **P1 — Serialize product publication with application deployment** → correct.
   The publish action runs only in the protected production workflow, under the
   deployment concurrency group and holding the host deployment lock from its
   first image check to after commit, and repeats the digest check as its last
   statement before `COMMIT`.
3. **P1 — Bind the plan probe SQL to the deployed image** → correct. The probe
   SQL is generated inside the running, digest-pinned API container rather than
   from the `trusted-main` checkout, with each statement's SHA-256 recorded.

### Review round 38 (2026-10-12)

1. **P1 — Use a valid simultaneous upper confidence bound** → correct, and the fix
   is to stop sampling for this purpose. The normal-approximation bound is not a
   guarantee for bounded, heterogeneous chunk fractions and gives no simultaneous
   coverage over 24 of them, while a distribution-free simultaneous bound would be
   too wide to ever pass. Step 5a now requires exact counts from a complete,
   detached read-only run; the converter and gate refuse anything else.
2. **P1 — Enforce generation-promotion rules below the function** → correct. `015`
   adds a deferred constraint trigger on `current_derived_generation` that checks
   both rules at commit for any pointer change, with tests for a violating and a
   satisfying direct update.
3. **P2 — Compute the median for even warm-run counts** → correct, fixed in the
   probe-index script with `statistics.median` and tests for even and odd counts.
   The committed probe-index evidence used the default four repeats (three warm
   runs), so its medians were already exact.
4. **P1 — Pin calibration code to the deployed release** → correct. New step 5b:
   the probe and the archetype build refuse unless the checkout's canonical model
   file hashes the same as the file inside the running, digest-pinned API
   container, and publication compares each manifest's `model_file_sha256` with
   that in-container hash before commit.

### Review round 39 (2026-10-12)

1. **P1 — Derive resume capacity from remaining tier counts** → correct. On an
   Archetype resume, heap and one-entry-per-row indexes still scale by rows, but
   the 24 partial indexes are projected from exact remaining entries: the step 5a
   complete-read count minus the count already inserted, read from the partial
   product.
2. **P1 — Limit the model-file check to the Archetype manifest** → correct; only
   the `system_archetype` manifest is compared, and the text says the Search
   manifest has no such field.
3. **P2 — Remove the nonexistent VALIDATING product case** → correct; products are
   `BUILDING | READY | FAILED`, so the unfinished-product rule and its test name
   `BUILDING` only.
4. **P1 — Assign the complete calibration run to an executable action** →
   correct. PR4 now owns the detached complete-read start/status action, its
   workflow allowlist entries, receipt and tests; step 5's row says the capped
   probe is for coefficient review only.

### Review round 40 (2026-10-12)

1. **P2 — Include the no-pick tie-break in the footprint DDL** and
2. **P2 — Measure indexes under production insertion order** → both correct, and
   both are properties of the script's built-in comparison layouts. Those receipts
   now carry `capacity_gate_eligible: false` with the reason; the capacity gate
   requires `true`, which only PR1's final-migration path sets — it applies the
   final `011` DDL (tie-break included) and creates every index before a chunked,
   canonical-order fill, as production does. Test pins the flag.
3. **P1 — Pin the Search builder to the attested release** → correct. The F2d
   release attestation records the expected Search manifest code identity; the
   Search action refuses to register or build from a checkout that does not
   produce it, and publication compares the Search manifest's code identity with
   the attested value before commit.

### Review round 41 (2026-10-12)

1. **Octopus — tests for the script's new behaviour** → the malformed-input and
   determinism tests already landed in rounds 33–36; this round extracts the
   fractions normalization into `normalize_fractions()` and tests that its digest
   and `Σ_all` are canonical (independent of key order and number form), that the
   digest moves with any value, and that unordered or out-of-range fractions are
   refused. The four normalized per-row metrics are PR1's, and section 10 already
   requires their provenance tests there.
2. **P1 — Measure Search instead of hard-coding its capacity** → correct. The gate
   now projects Search from the real pre-`010` bytes per row recorded in the
   committed step 0 receipt plus the `010` delta measured as a pre/post-DDL
   difference on disposable PostgreSQL 18, both provenance-bound, instead of the
   87 GB constant.

### Review round 42 (2026-10-12)

1. **Octopus — validation before the fractions SQL expression** → accepted as
   defence in depth: `_score_expr` now refuses a mapping without numeric, ordered
   60/76/88 floors itself, in addition to `normalize_fractions()` upstream, with a
   parametrized test.
2. **Octopus — synthetic evidence could be mistaken for a gate input** → already
   classified: the committed 200 k evidence carries a `provenance` block with
   `is_capacity_gate_input: false` and the reason, and the gate requires
   `measured-histogram`, a matching digest and `capacity_gate_eligible: true`.
   PR4's refusal tests now also feed that exact file to the gate and require a
   refusal.
3. **P1 — Include distance in the no-pick ordering index** → resolved the other
   way: distance is removed from the no-pick score tie-break as it already was
   from the picked one, so `PROFILE_SPEC.tie_break` is `["system_id64"]` for both
   and the index matches the canonical order exactly.
4. **P1 — Use the measured Search projection in the controlling gate** → correct;
   ROADMAP step 7′ now carries the two-part measured Search projection and its
   refusal rule.

### Review round 43 (2026-10-12)

1. **P1 — Probe the anchored live search path before publication** → correct.
   PR1 rewrites the anchored nearest-first page and count as a GiST KNN index scan
   (bounding box as index condition, `ORDER BY position_ly <-> anchor,
   system_id64`), so they stop after the page or the 10,001st row; the publication
   probe runs it at Sol and at the densest pyramid cell and requires the KNN scan,
   no sort over the candidates, and the same work bound per generation.
2. **P1 — Pin the full Archetype builder identity to the release** → correct. The
   release attestation records the Archetype manifest's complete `code_sha256`,
   and the probe, build and publish actions refuse any other, as already done for
   Search; the model-file check stays as the explanation route's guard.

### Review round 44 (2026-10-12)

1. **P1 — Stop the KNN scan at the radius boundary** → correct; a radius filter
   cannot stop a KNN scan. The rewrite puts the `LIMIT` inside the KNN subquery
   and the radius outside it: the scan stops after `inner_limit` rows, and since
   it runs in distance order the in-radius rows are a prefix of it, so the page
   and the capped count are unchanged in meaning.
2. **P2 — Expose truncation for the anchored sentinel count** → correct; PR1 sets
   `total_is_capped = count > cap` for every count, anchored included, with tests
   at 10,000 and 10,001 anchored matches.
3. **P2 — Preserve the weighted-score tie-break in KNN order** → correct; equal
   distances still order by weighted potential then `system_id64`, via an
   incremental sort per distance group, so the nearest-first contract and its
   hash are unchanged.

### Review round 45 (2026-10-12)

1. **Octopus — operational authority split across documents** → fixed rather than
   accepted (owner's choice). Section 8 now states that the ROADMAP controls and
   that a disagreement is a defect, and a new contract test,
   `tests/test_finder_rollout_doc_invariants.py`, extracts the shared invariants
   from the ROADMAP, this design (excluding its review history), the capacity
   decision and the rollout-state record and fails if any differs: the planned
   migration apply set (every list that includes `015` must equal the ROADMAP's
   step-2 list), every `Σ_all` limit, the attach target generation, and the
   complete-read rule for the capacity input.

### Review round 46 (2026-10-12)

1. **P1 — Bound KNN reads across equal-distance groups** → correct; the bound now
   carries an explicit tie slack `T = 1,000` for the boundary group the incremental
   sort must finish, with the statement timeout as the backstop at unprobed anchors.
2. **P2 — Normalize every documented migration-list spelling** → correct; the
   invariant test now parses every bracketed list containing `015` with any
   spacing, normalizes `011'` to `011-rewritten`, and requires the ROADMAP, this
   design and the capacity decision each to yield at least one planned list.
3. **P1 — Add a generation-scoped KNN access path** → resolved by bounding rather
   than adding an index: the work bound is multiplied by `G`, the generations
   holding Search rows, read at probe time (2 during this rollout, with `opt1`
   retained), and the "after purge P" assumption is removed from this design.
4. **P2 — Bound selective Any-mode scans before calling them capped** → owner
   decision 2026-10-12: galaxy-wide Any requests with any hard filter are refused
   with 422 asking for an anchor or no filter; anchored requests keep every filter
   and are bounded by their window, which the probe exercises with the most
   selective accepted filter.

### Review round 47 (2026-10-12)

1. **Octopus — capacity-decision status could read as gate clearance** → its
   status line now says it records questions 5–6 only and defers every other gate
   to the ROADMAP and this design, and the invariant test checks that the
   ROADMAP and the capacity decision list the same unresolved owner questions.
2. **P1 — Probe both live no-pick searches before commit** → correct; ROADMAP
   step 9′ now requires the galaxy-wide no-pick page and count and the anchored
   nearest-first request alongside the 24 picked pairs, before commit.
3. **P1 — Size Search resumes from the remaining rows** → correct; Search rows are
   variable-width, so a resume subtracts the bytes actually written — the growth of
   the table, its indexes and TOAST since the build's start receipt (insert-only, so
   all of it is this build) — instead of scaling by rows.
4. **P1 — Serialize direct pointer updates with product publication** → correct; a
   `BEFORE UPDATE` trigger on the pointer takes the publication advisory lock, the
   publication audit re-checks the current pointer at commit, and a two-session race
   test covers it.
5. **P2 — Assign publication reporting to the lifecycle status action** → correct;
   PR4 now extends `v3-derived-lifecycle-status` to report each product's
   `published_at` and its publication audit rows, with contract tests.
6. **P2 — Keep local-search contract tests in PR1** → correct; PR1's test list now
   includes `tests/test_local_search_v3.py` for every behaviour PR1 changes.

### Review round 48 (2026-10-12)

1. **P1 — Record question 9 as resolved in the design** → correct; section 11 now
   opens with a status line — answered 1, 5, 8 and 9; open 2, 3, 4, 6 and 7 — that
   matches the ROADMAP, and the invariant test checks the two agree.
2. **P2 — Restrict the Any-mode filter assertion to anchored searches** → correct;
   the tests assert 422 for every galaxy-wide filtered Any request and leave only
   anchored filtered requests unaffected.
3. **P1 — Guard every pointer-table mutation** → correct; `TRUNCATE`, `DELETE` and
   `INSERT` on `current_derived_generation` are rejected unconditionally, with
   tests, so only the locked, rule-checked `UPDATE` can change it.
4. **P2 — Treat the response additions as schema changes** → correct; PR1's
   summary now lists the additive response fields, regenerates clients for them
   and tests their presence.
5. **P1 — Update the ranking-identity fixture in PR2** → correct; PR2 owns the
   `test_ranking_identity_and_no_legacy.py` fixture change.
6. **P2 — Include the capacity decision in the Σ_all drift check** → correct; the
   invariant test now also reads the capacity decision's "stops above Σ_all …"
   phrasing.

### Review round 49 (2026-10-12)

1. **P2 — Hash globals referenced by the scoring call graph** → correct; the walk
   now hashes every module-level assignment a covered function reads (recursively),
   with a test that changes only a referenced global.
2. **P1 — Apply full publication checks to direct pointer updates** → correct; the
   deferred table guard now checks the complete publication contract — READY/
   VERIFIED target on the current canonical generation, a different target, a
   sequence of old plus one, the matching lifecycle transitions and audit row —
   plus both Finder rules, with a rejection test for each omission.
3. **P1 — Preserve a bootstrap path for the pointer singleton** → correct; my round
   48 rejection of every `INSERT` would have made a fresh database unpublishable.
   `INSERT` is now allowed only into an empty table, under the same lock and the
   same contract check, and the revised publisher uses a plain `UPDATE` once the
   singleton exists, because row-level `BEFORE INSERT` triggers fire even for
   `ON CONFLICT DO UPDATE`.

### Review round 50 (2026-10-12)

1. **P2 — Hash non-assignment scoring dependencies** → correct; the round-49 walk
   hashed module-level assignments and classes but not imported names, so a
   scoring function calling an imported repository helper could change behaviour
   without moving the digest. The walk now fails closed: any name that is not a
   model-module definition, a builtin or a `math` member stops the digest, and the
   build cannot register. Test: a scoring function that calls an imported helper
   makes the digest computation fail.
2. **P2 — Size Archetype resumes from actual remaining bytes** → correct; the
   round-47 byte subtraction covered Search only, and the round-39 tier-count
   remainder still scaled the variable-width Archetype heap by rows. Both
   products now subtract the table, index and TOAST growth since the start
   receipt from their full projection, with a test whose written rows are short
   so 90 % of the rows is only 70 % of the bytes.
3. **P1 — Pin the complete calibration probe implementation** → correct; the
   Archetype code identity covers what the probe imports but not the probe or its
   action. The F2d release attestation now records `calibration_code_sha256` over
   the probe script, the complete-read action and the installed `psycopg` wheel;
   the action refuses a checkout that differs, the probe refuses any loaded
   repository module outside the pinned file sets, the receipt carries the value
   and the capacity gate compares it with the attestation.

### Review round 51 (2026-10-12)

1. **P1 — Bound resume cost without subtracting from an estimate** → correct; my
   round-50 subtraction treated the projection as an upper bound, and if early
   chunks overran it the remainder was under-charged. A resume is now charged the
   largest of a fresh projection of the unsealed chunks (with the Archetype tier
   term from their exact per-chunk tier counts, which the complete read now
   records), the build's own observed cost per row times the rows left, and the
   full projection minus the bytes written. Tests cover an early saving, an early
   overrun and a dense tail, each charged by a different term.
2. **P1 — Use the measured Search term in the rollout table** → correct; step 6
   and the section 3.4 stop condition still named the ≈ 87 GB fixture figure. Both
   now use the measured two-part projection and refuse when either input is absent.
3. **P2 — Include rollout state in the Sigma limit check** → partly correct. The
   rollout-state record states no `Σ_all` limit today (its line 456 is disk
   inventory text), but section 8 says the check covers it, so the test now
   parses it too and requires any limit it states to be 4.0, with a self-test that
   a conflicting limit fails.
4. **P1 — Permit the model's dataclass dependencies in the digest** → correct; my
   round-50 rule would have rejected the unchanged model, which declares its
   classes with `dataclass` and `field`. Those two names, resolved through the
   model's own `from dataclasses import …`, join `math` on an explicit allowlist,
   and a test asserts that the unchanged model produces a digest.
5. **P1 — Analyze Search after its final bulk insert** → correct; only Archetype
   was vacuumed and analyzed before the probes, but both no-pick requests read
   Search. The Search build now ends with a receipted `VACUUM (ANALYZE)`, and the
   probes and the publisher refuse unless both tables' timestamps postdate their
   own final inserts.

### Review round 52 (2026-10-12)

1. **P1 — Vacuum the physical Search table instead of its view** → correct;
   `v3_app.system_search` and `v3_app.system_archetype` are views, and
   PostgreSQL rejects `VACUUM` on a view, so the round-51 instruction could not
   run. Both build actions now name the physical tables
   `v3_derived.system_search` and `v3_derived.system_archetype`, and the probes
   read `pg_stat_user_tables` for those tables (design section 8.5).
2. **P1 — Pin the capacity-measurement implementation to the release** →
   correct; the footprint script and the histogram converter produce gate
   inputs and had no attested identity. The attestation now records
   `capacity_code_sha256` over both scripts; the footprint receipt and the
   fractions file record the identity of the code that wrote them and the gate
   refuses on a mismatch (section 8.3).
3. **P1 — Block pointer flips for READY unpublished products** → correct; the
   round-30 rule covered `BUILDING` only, so a flip between the Search build and
   the Archetype registration would have stranded the READY-unpublished Search.
   The flip now also refuses while any outgoing product is READY and
   unpublished, unless the incoming transaction publishes a product with the
   same `product_code` (section 7.4).

### Rewrite (2026-10-12)

After round 52 the design was rewritten from 3,963 lines to about 1,500: each
rule stated once, review-round tags and history-of-reasoning paragraphs
removed, this file split out. The owner chose the rewrite because the review
cycle was converging slowly on a document whose size invited new findings at
each round. A mechanical inventory of every rule-bearing sentence in the old
text (178 items) was checked against the new text by a reviewer who had not seen
the rewrite; seven weakened items were restored, and a separate reviewer checked
every current-code claim against the repository. Corrections made in the rewrite
beyond round 52:

- the stated base is now `b0b2f28` (after PR #807); PR #805 is merged;
- the synthetic `Σ_all` is 1.52 summed over the 24 recorded fractions (1.54 came
  from rounded percentages), and the footprint table now separates the measured
  layout (382 B/row) from the designed layout (≈ 394 B/row with the trailing
  `system_id64` and `completeness_ppm`);
- the "persisted-explanation field policy is removed" sentence was dropped: the
  current `field_policy` has no explanation entry;
- measurements that are not in the committed evidence (the ≥ 60 read count, the
  `double precision`/ppm heap widths, the generic-plan observation) are labelled
  as such, and the 500,000-triple rounding check became a PR1 test;
- the anchored path's radius is not fixed at 500 ly — the route caps
  `max_distance_ly` at `MAX_SEARCH_RADIUS` (10,000 ly by default) — so a
  **filtered** anchored request, whose only bound is the bounding box's candidate
  count, is now capped at the 500 ly the publication probe measures and answers
  422 above it; unfiltered anchored requests stay bounded by the inner `LIMIT` at
  any accepted radius.

### Review round 53 (2026-10-13, on the rewrite)

1. **P1 — Remove the first-launch exception for unfinished products** → wording
   fixed; the rule was right but the test case said "every registered product
   READY but unpublished" without saying on which generation. It now says the
   incoming generation's products (the fixture bootstrap) and that an outgoing
   READY-unpublished product the incoming transaction does not replace refuses
   the flip (section 7.5 item 8).
2. **P1 — Reject unbounded score-sorted anchored searches** → correct; the route
   maps the default `sort_by='development'` to score order even with an anchor
   (`local_search.py:665-671,886-910`), and no index orders by score and
   distance together, so at a 10,000-ly radius that request could scan and sort
   most of the galaxy. Score-sorted anchored requests are now treated like
   filtered anchored requests: radius capped at the probed 500 ly, 422 above it,
   probed at the densest window with the bounding-box bound (sections 6 and 8.7).

### Review round 54 (2026-10-13)

1. **P1 — Exempt the sentinel count from the index-scan-only rule** → correct;
   the rewrite dropped the word "exception" that made the two rules
   consistent. Section 8.7 now names the no-pick sentinel count as the one
   exception to the node-type rule.
2. **P1 — Pin the capacity-gate implementation itself** and 3. **P1 — Pin the
   publication and plan-assertion code** → correct, and the same class as
   rounds 40, 50 and 52. Closed structurally rather than one identity at a
   time: every F2d operator action compares the `SOURCE_SHA` the workflow hands
   it with the attestation's `source_sha` and refuses to run from any other
   checkout (section 8.3). The per-artifact identities stay for receipts
   produced at other times.
4. **P2 — Exclude the KNN radius from hard-filter classification** → correct;
   `_v3_hard_filters` records `max_distance_ly` for every anchored request, so
   a literal reading would have made every nearest-first request "filtered".
   The radius is now defined as the KNN path's intrinsic predicate for this
   classification; `min_distance_ly` and the rest remain hard filters.
5. **Octopus — brittle heading anchor in the invariant test** → fixed; the test
   asserts the section 11 heading exists before slicing.

### Review round 55 (2026-10-13)

1. **P1 — Bound resume cost from the remaining source data** → correct; the
   largest of three row-scaled estimates is still not an upper bound when the
   unsealed tail is wider than the head. The remainder is now derived from the
   unsealed source: fixed widths × rows left, Search's variable text read from
   the canonical source by one aggregate (counted twice for the `lower(name)`
   index), Archetype's two text columns at their CHECKed maximum of 63 bytes,
   and the exact tier entries of the unsealed chunks; the subtraction term
   remains as a floor (section 8.4).
2. **P1 — Reconcile the histogram commit with source-SHA pinning** → correct;
   round 54's commit-SHA pin would have refused every action once step 5
   committed the histogram. The actions are now pinned to the content of an
   explicit operator-code manifest (`f2d_operator_code_sha256`), which a
   documentation or evidence commit does not move; it replaces the per-script
   `calibration_code_sha256` and `capacity_code_sha256` and the `source_sha`
   row (section 8.3).

### Review round 56 (2026-10-13)

1. **P1 — Coalesce nullable Search text lengths** → correct; `region_name` and
   `main_star_class` are nullable (`004:31-32`) and a NULL inside `SUM`'s
   expression drops the whole row. The aggregate now `COALESCE`s each nullable
   length to 0.
2. **P2 — Check the complete-read rule in every named document** → correct; the
   capacity decision said "the step 6 probe is unchanged" and "run the
   calibration probe" while the ROADMAP requires every chunk. Both documents
   now state the complete read and the invariant test requires the phrase in
   all four.
3. **P1 — Assign production of the eligible footprint receipt** → correct; no
   step produced the gate's real input. PR4 adds a dispatchable GitHub Actions
   workflow on a disposable PostgreSQL 18 service container that converts the
   committed complete-read receipt, runs the Archetype and Search
   measurements from the attested operator code and uploads sealed receipts
   for a reviewed evidence commit (step 5, section 8.2).
4. **P1 — Insert rows after migration 010 when measuring its delta** →
   correct; `010` adds 18 `NOT NULL DEFAULT 0` columns as fast defaults, so a
   populated table sized before and after `ALTER` shows no delta. The delta is
   now the difference between the two DDLs each filled from empty with the same
   rows (section 8.4).
5. **P1 — Provide the fixed-cost inputs used by resume arithmetic** → correct;
   the receipt now records `search_fixed_bytes_per_row` (one-character text
   fill) and `archetype_fixed_bytes_per_row` (shortest archetype name), the
   gate refuses a receipt missing either, and the resume formula names them.
6. **Octopus — Weyl key offset precision** → false positive with evidence: the
   offset is formatted with `:.20f`, not two decimals, and the eight per-key
   offsets differ by ≈ 0.41 each; a `Decimal` form is a harmless nicety for the
   code PR, not a design matter.

