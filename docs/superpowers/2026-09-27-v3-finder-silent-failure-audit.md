# V3 Finder silent-failure audit — dc218fb7

Report only. Audited commit **dc218fb7** on **feat/v3-finder-f2c-ranking-profile**, including merged F2b code and the F2c/F3 code. No code was changed by this audit.

All line references below refer to that commit. Separate working-tree edits appeared during the audit, including ranking-identity work; they are excluded. A frozen source snapshot was used for follow-up probes. Links point into the shared checkout, whose line numbers may move as that separate work continues.

**Result:** 30 findings, including confirmed false verification of malformed data, success exit codes on failure, incorrect search results, and tests that still pass after breaking ranking behavior. No P0 finding established.

**Evidence:** all 70 tests in the ten requested non-integration test files passed against the repository's disposable PostgreSQL 18 service. The first run without the database configured produced 48 passes/22 skips; the DB-enabled run produced **70 passes, no skips**. That pytest run used installed CPython 3.14.4; separate ranking mutation probes used CPython 3.14.7. The existing integration test file was read in full, but its shared PG/Redis/destructive-reset harness was not run. Instead, targeted HTTP probes used the real FastAPI router, request models and search builder with captured database calls. Corruption probes used real PostgreSQL 18.6, random fixture databases and normal schema guards; no production data or service was accessed.

## Ranked findings

1. **P1 — Eight archetype rows can be the wrong eight keys, with stale row versions, and still become VERIFIED/READY.**  
   **Location:** [scripts/v3_system_archetype.py:485](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:485), coverage decision at :523; schema [011_v3_system_archetype.sql](C:/Users/brian/ed-finder/sql/v3/migrations/011_v3_system_archetype.sql).  
   **Trigger:** before insertion, replace a nonwinning required archetype key with a syntactically valid invented key, preserving eight rows per system; independently, stamp data rows with a stale archetype_version while keeping chunk receipts current.  
   **Wrong outcome / silence:** coverage counts rows, not exact key sets or per-row versions. Real PG18 probes independently returned VERIFIED, promoted the product to READY and reported every_system_has_all_archetypes=true in both cases. Receipt-version checking does not check data-row versions.  
   **Minimal fix:** require each system's exact ARCHETYPE_KEYS set and each row's PRODUCT_VERSION; classify a fully receipted violation as FAILED. Add both negative tests to [test_v3_system_archetype_validate.py:91](C:/Users/brian/ed-finder/tests/test_v3_system_archetype_validate.py:91).

2. **P1 — “Seals verified” never verifies the stored archetype content seal.**  
   **Location:** [scripts/v3_system_archetype.py:596](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:596), digest construction :752; resume handling :357; content hashing :272.  
   **Trigger:** write valid rows and source seals but use arbitrary all-FF content_sha256 values in archetype chunk receipts.  
   **Wrong outcome / silence:** the validator checks source identity, version and system counts, then merely incorporates the supplied content hash into a new validation hash. The PG18 probe returned VERIFIED/READY with seals_verified=true. Resume also accepts a matching source receipt without checking its content against rows. Additionally, _chunk_content_sha omits explanation and archetype_version, so simply adding a hash comparison would not protect those fields.  
   **Minimal fix:** recompute and compare each content seal during validation, use it on resume where integrity is asserted, and include all governed output fields or give omitted fields explicit independent checks. Add a corrupted-content-seal fixture.

3. **P1 — Fabricated secondary archetypes and classification confidence pass validation.**  
   **Location:** [scripts/v3_system_archetype.py:563](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:563), especially :583; expected formula [v3_system_archetype_model.py:136](C:/Users/brian/ed-finder/scripts/v3_system_archetype_model.py:136).  
   **Trigger:** preserve the correct winner/score/tier, but write an incorrect secondary_archetype and false archetype_confidence. For example, scores 90/89 require about 0.022222 separation confidence, not 1.  
   **Wrong outcome / silence:** the summary gate validates only the winner, score and tier. A real PG18 probe with fabricated secondary/confidence passed VERIFIED/READY. This directly changes no-pick ranking, which multiplies by that confidence.  
   **Minimal fix:** validate the first two ranked fits and the exact summary confidence formula, including tie and zero-score rules. Tests must assert secondary and confidence values, not only maximum score.

4. **P1 — Validation does not protect its checks and READY transition with one transaction/lock.**  
   **Location:** [scripts/v3_system_archetype.py:673](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:673) through :767; transaction begins only at :769.  
   **Trigger:** while the product is still BUILDING, insert a validly shaped extra low-score archetype after coverage has been checked but before promotion.  
   **Wrong outcome / silence:** the PG18 interleaving probe inserted late_extra through normal guards. Validation returned VERIFIED and claimed 96 rows; immediately rerunning coverage found 97 rows and failed. The product had already become READY. The final guarded UPDATE protects lifecycle state, not the data snapshot used to justify it.  
   **Minimal fix:** take the base/product locks in the established order before validation, exclude product writes, and perform all checks plus promotion inside that protected transaction. Test the interleaving explicitly.

5. **P1 — --follow declares BUILT while the base is still being built, and does not handle terminal base state.**  
   **Location:** [scripts/v3_system_archetype.py:804](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:804), :825–843.  
   **Trigger:** start follow mode against a BUILDING base with one committed Ratings chunk; catch up with that chunk before the next arrives. Alternatively, the base fails after its currently visible chunks are consumed.  
   **Wrong outcome / silence:** matching receipt counts immediately return BUILT even though more chunks may arrive. The loop never refreshes generation lifecycle state; a failed base can look complete when counts match, or leave an empty/incomplete follower polling indefinitely. A direct run probe confirmed BUILDING → BUILT.  
   **Minimal fix:** refresh lifecycle each iteration, wait for sealed terminal success and complete coverage, and fail explicitly on terminal failure. Preserve explicitly bounded partial-run semantics. [test_v3_system_archetype_cli.py:124](C:/Users/brian/ed-finder/tests/test_v3_system_archetype_cli.py:124) tests only max_chunks stopping, which avoids the real follow lifecycle.

6. **P1 — CLI validation failure exits successfully.**  
   **Location:** [scripts/v3_system_archetype.py:865](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:865), unconditional return 0 at :882.  
   **Trigger:** --validate returns a FAILED or INCOMPLETE receipt rather than raising.  
   **Wrong outcome / silence:** JSON reports failure/incompleteness but the process exits 0, so shell pipelines and jobs report success. A direct main() probe with a FAILED receipt returned 0.  
   **Minimal fix:** map terminal receipt statuses to explicit exit codes; validation succeeds only for VERIFIED. Define a separate documented result for intentionally bounded partial builds. The CLI tests at :88 cover successful verification and missing DSN, not failed/incomplete receipts.

7. **P1 — Most declared body filters, including every upper bound, are silently dropped.**  
   **Location:** [apps/api/src/local_search.py:600](C:/Users/brian/ed-finder/apps/api/src/local_search.py:600); declared fields [models.py:95](C:/Users/brian/ed-finder/apps/api/src/models.py:95).  
   **Trigger:** body_filters={"elw_count":{"max":0}}, {"ammonia_count":{"min":5}}, or any nonzero minimum for the fifteen unsupported declared count fields listed in the matrix below.  
   **Wrong outcome / silence:** the mapper uses only minima for elw_count, ww_count, terraformable_count and landable_count. Every max and every other declared field vanishes. HTTP probes returned 200 with SQL containing no corresponding predicate. Recognized historical short/camelCase aliases are also accepted but not mapped to the four exact keys the V3 mapper reads.  
   **Minimal fix:** enforce every supported range using a complete mapping; explicitly 422 fields/bounds without projection support; reject unknown keys. Add per-field positive/negative fixtures and both range bounds.

8. **P1 — Selecting an economy silently ranks by overall colony potential.**  
   **Location:** [apps/api/src/ranking/ranking_sql.py:170](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:170); caller [local_search.py:740](C:/Users/brian/ed-finder/apps/api/src/local_search.py:740).  
   **Trigger:** select Extraction, Agriculture or another valid economy.  
   **Wrong outcome / silence:** picked_economy is never used. SQL and parameters are identical to no-pick ranking, while display_economy still advertises the requested economy. A code comment calls this a gap, but callers receive no warning or error. The intended V4 potential already exists in the rating vector.  
   **Minimal fix:** join/read the selected economy's potential from the pinned rating vector, or reject that mode until implemented. Test two economies whose expected orders oppose each other. [test_ranking_sql.py:76](C:/Users/brian/ed-finder/tests/test_ranking_sql.py:76) explicitly blesses the fallback.

9. **P1 — Cache hits bypass the V3 generation requirement and can serve legacy results after cutover.**  
   **Location:** [apps/api/src/routers/search.py:39](C:/Users/brian/ed-finder/apps/api/src/routers/search.py:39), :186–191; TTL [config.py:38](C:/Users/brian/ed-finder/apps/api/src/config.py:38).  
   **Trigger:** retain a pre-F3 search:v4 cache entry for the same body, or publish another generation/change ranking while an entry is cached. The namespace and body shape were retained from the pre-F3 implementation.  
   **Wrong outcome / silence:** cache returns immediately without calling V3 search or checking publication, for the default one-hour TTL. A targeted HTTP probe returned 200/source=local_db with local_db_search_v3 never called. Generation/hash changes are absent from the key; even the intended no-publication 404 can be bypassed.  
   **Minimal fix:** bump cutover namespace and key responses by resolved generation/publication plus ranking identity. Resolve authoritative availability before serving a ranked cache entry. Test warm legacy cache, republish, and absent publication.

10. **P1 — Results and count are not pinned to the generation that was checked.**  
    **Location:** [apps/api/src/local_search.py:767](C:/Users/brian/ed-finder/apps/api/src/local_search.py:767); [routers/archetypes.py:368](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:368).  
    **Trigger:** G2 publishes between _current_derived_generation(), the page SELECT and the COUNT under ordinary READ COMMITTED isolation.  
    **Wrong outcome / silence:** both endpoints discard the returned generation ID. The views resolve the publication pointer per statement, permitting a G1 page with a G2 total. readonly=True does not give these statements a shared snapshot. Each individual query is consistent; the response across queries is not.  
    **Minimal fix:** use the resolved generation in every derived-table query, following [ratings_v4.py:207](C:/Users/brian/ed-finder/apps/api/src/routers/ratings_v4.py:207), or establish repeatable-read and return its identity. Add a two-publication interleaving test.

11. **P1, scale-dependent — Radius queries bypass the available spatial index; page and count repeat work over the generation.**  
    **Location:** [apps/api/src/ranking/ranking_sql.py:123](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:123), :205, :255; GiST index [004_v3_search_spatial_clusters.sql:52](C:/Users/brian/ed-finder/sql/v3/migrations/004_v3_search_spatial_clusters.sql:52).  
    **Trigger:** a cache-miss 1-LY search without another selective filter against the full galaxy. An unfiltered galaxy-wide request additionally scores/orders joined rows before LIMIT and requests an exact full count.  
    **Wrong outcome / silence:** the radius is solely sqrt(x/y/z arithmetic); there is no position_ly index predicate. PostgreSQL cannot use the spatial GiST to prune this radius computation. This is a structural whole-generation scan issue, hidden by twelve-row tests. Timeouts feed the error-masking path. **No production latency or timeout was measured.**  
    **Minimal fix:** use indexed cube/bounds pruning followed by exact distance, as required by [the architecture decision:77](C:/Users/brian/ed-finder/docs/development/v3-search-spatial-derived-data-decision.md:77). Establish an indexed/materialized ranking and affordable count strategy for galaxy-wide access. Verify plans on representative disposable data.

12. **P2 — Malformed, fully receipted builds are labelled INCOMPLETE instead of FAILED.**  
    **Location:** [scripts/v3_system_archetype.py:682](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:682), :686–709.  
    **Trigger:** all expected archetype chunk receipts exist and the base is ready, but rows are missing from a supposedly completed chunk.  
    **Wrong outcome / silence:** coverage_ok=false enters the general INCOMPLETE branch before invariant checking. A PG18 probe with all three receipts and 93 rather than 96 rows returned INCOMPLETE. Resume skips receipted chunks, so this state is not ordinary pending work.  
    **Minimal fix:** distinguish absent/unbuilt chunks from malformed completed chunks; the latter must return FAILED with diagnostic reasons. Existing tests cover missing chunk receipts, not corruption inside fully receipted chunks.

13. **P2 — Fully observed systems can receive zero “uncertainty” because their top archetypes tie.**  
    **Location:** [ranking/ranking_sql.py:174](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:174); [v3_system_archetype_model.py:142](C:/Users/brian/ed-finder/scripts/v3_system_archetype_model.py:142).  
    **Trigger:** no-pick ranking of a system with complete evidence and multiple equally strong fits. The real model with all potential/quality=100, confidence/completeness=1 and ample opportunities produces best score 100 but summary archetype_confidence=0.  
    **Wrong outcome / silence:** no-pick SQL uses classification separation confidence as evidence confidence, so effective ranking score becomes zero. A weaker but separated classification can outrank it. Meanwhile local_search returns s.confidence, which can be 1, so the badge does not explain the penalty.  
    **Minimal fix:** use the intended system evidence confidence for general uncertainty and retain classification confidence as a separate field, or explicitly revise/version the product contract if separation is intended as a ranking penalty. The F2c design describes observation confidence/completeness, not ambiguity between good archetype fits.

14. **P2 — A distance lower bound is accepted and ignored.**  
    **Location:** [local_search.py:237](C:/Users/brian/ed-finder/apps/api/src/local_search.py:237), :634; explicit TODO at :577.  
    **Trigger:** reference at Sol and filters.distance={"min":100,"max":500}.  
    **Wrong outcome / silence:** systems inside 100 LY are eligible; SQL has only <=500. A real HTTP/captured-query probe confirmed this.  
    **Minimal fix:** add a lower-bound predicate shared by page/count, or reject nonzero lower bounds. Test an inner excluded system and an annulus match.

15. **P2 — sort_by is accepted but never used in V3 ordering.**  
    **Location:** [local_search.py:227](C:/Users/brian/ed-finder/apps/api/src/local_search.py:227), :748; caller [ExploreWorkspace.svelte:133](C:/Users/brian/ed-finder/apps/web/src/lib/features/explore/ExploreWorkspace.svelte:133).  
    **Trigger:** sort_by="distance", which the current Explore UI actually sends.  
    **Wrong outcome / silence:** ranking remains weighted score first; distance is only a tie-break. Arbitrary unsupported sort strings are also accepted. HTTP/captured SQL confirmed the distance request retains score-first ordering.  
    **Minimal fix:** route supported sort modes through the versioned ranking policy, or reject unsupported values and update the calling UI contract. Test different-score near/far systems.

16. **P2 — The declared population range bypasses the unsupported-population rejection.**  
    **Location:** [models.py:73](C:/Users/brian/ed-finder/apps/api/src/models.py:73), :490; [local_search.py:243](C:/Users/brian/ed-finder/apps/api/src/local_search.py:243), :729.  
    **Trigger:** filters.population={"min":100} or {"max":0}.  
    **Wrong outcome / silence:** the public schema declares min/max, but the parser only looks for the extra field value. Thus range requests return 200 with no population predicate; only a successfully parsed legacy value shape triggers 422. Invalid extra value strings are swallowed to None and also bypass rejection.  
    **Minimal fix:** reject any explicitly requested population constraint while no projection exists; align the schema and parser. The existing rejection test uses only {"value":0,"comparison":"equal"}, avoiding the documented shape.

17. **P2 — Valid one-sided distance ranges crash before the database and become 503s.**  
    **Location:** [routers/search.py:165](C:/Users/brian/ed-finder/apps/api/src/routers/search.py:165); [local_search.py:238](C:/Users/brian/ed-finder/apps/api/src/local_search.py:238).  
    **Trigger:** filters.distance={"max":500}, {"min":10}, or an empty range, with complete reference coordinates. RangeFilter explicitly allows omitted bounds.  
    **Wrong outcome / silence:** model_dump includes missing bounds as None; float(None) raises TypeError. Both one-sided HTTP probes returned 503 before any database query, implying temporary backend failure for a valid request.  
    **Minimal fix:** normalize optional bounds explicitly rather than relying on dict.get defaults, validate range ordering/finite values, and return 422 for genuinely invalid inputs. Exercise the full request-model → router → parser path.

18. **P2 — Ranking hash/spec does not identify the executed algorithm.**  
    **Location:** [ranking/ranking_sql.py:219](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:219), :281; [ranking/profile.py:144](C:/Users/brian/ed-finder/apps/api/src/ranking/profile.py:144).  
    **Trigger:** change uncertainty/tie-break/filter policy in the supplied spec, or change the SQL formula without changing profile.py.  
    **Wrong outcome / silence:** neither builder reads spec. A changed spec hash can produce identical SQL, and changed SQL can retain an identical hash. The “recorded” hash is calculated from the same live definition at import, so its equality test cannot require a reviewed version/digest update.  
    **Minimal fix:** derive implemented semantics from a canonical immutable definition, or incorporate effective implementation identity, and pin a reviewed expected digest per version. In-memory formula mutations demonstrated unchanged identity and passing tests.

19. **P2 — Missing ranking products masquerade as no matches or null-scored results.**  
    **Location:** [ranking/ranking_sql.py:156](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:156), :161; [routers/archetypes.py:339](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:339); [local_search.py:768](C:/Users/brian/ed-finder/apps/api/src/local_search.py:768).  
    **Trigger:** a Ratings generation is published but required search/archetype products were not registered/built. This is distinct from there being no published generation.  
    **Wrong outcome / silence:** existence-only publication checking passes. Empty search data becomes an ordinary empty result; missing archetypes give local null scores, or rankings total=0 because selected score >= minimum excludes NULL. No unavailable-product signal distinguishes missing data from a genuine search result.  
    **Minimal fix:** check required product readiness for the pinned generation before ranked reads, and return an explicit unavailable response. Current fixtures always build both products.

20. **P2 — Result shaping loses or invents available archetype facts.**  
    **Location:** [ranking/ranking_sql.py:268](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:268); [local_search.py:679](C:/Users/brian/ed-finder/apps/api/src/local_search.py:679); [routers/archetypes.py:445](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:445).  
    **Trigger:** rank a system under an archetype other than its actual primary.  
    **Wrong outcome / silence:** SQL joins the summary but does not select its fields. Local results omit primary/secondary/best-potential fields; rankings invent primary_archetype=requested key and secondary=None. Retained fixture system 158872029 is flexible/stronghold with best potential 75, but querying mining_hub labels it primarily mining_hub.  
    **Minimal fix:** select the actual summary fields, preserve their meanings, and expose selected_archetype separately. Assert shaped values against the stored summary with a nonprimary selection.

21. **P2 — Dividing uncertainty by completeness loses confidence at zero and conflates two confidence measures.**  
    **Location:** [routers/archetypes.py:429](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:429), :447, :453.  
    **Trigger:** valid completeness=0, with stored selected-fit confidence either zero or nonzero.  
    **Wrong outcome / silence:** response confidence becomes null because the product cannot be inverted at zero. At positive completeness, the recovered fit evidence confidence is also emitted as archetype_confidence, whose summary meaning is classification separation. The real row-shaper probe confirmed null at zero.  
    **Minimal fix:** select a.confidence and summary.archetype_confidence directly; never reconstruct either by division. Test zero completeness and different values for the two confidence meanings.

22. **P2 — Ranked responses lack the required generation/hash identity.**  
    **Location:** [local_search.py:782](C:/Users/brian/ed-finder/apps/api/src/local_search.py:782); [routers/archetypes.py:388](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:388); [models.py:357](C:/Users/brian/ed-finder/apps/api/src/models.py:357).  
    **Trigger:** any successful ranked response at dc218fb7, including empty results.  
    **Wrong outcome / silence:** source contains the version string only; ranking_sha256, derived_generation_id and publication_sequence are absent. Different data/formulas cannot be distinguished from the response. The envelope schemas also need extending.  
    **Minimal fix:** add the specified ranking identity block, populated from the actual pinned read; verify both HTTP envelopes. This is the planned Task 5 gap; separate concurrent identity work was not reviewed here.

23. **P2 — has_elw=false is rejected despite sufficient projected data.**  
    **Location:** [routers/archetypes.py:329](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:329).  
    **Trigger:** GET rankings with has_elw=false.  
    **Wrong outcome / silence:** 422 claims the filter is unsupported, although elw_count supplies the exact-zero predicate. This is explicit rejection rather than silence, but is the legitimate-false failure class requested in the audit.  
    **Minimal fix:** implement count=0/count-max or a boolean ELW predicate with defined unknown semantics. [test_archetype_rankings_v3.py:310](C:/Users/brian/ed-finder/tests/test_archetype_rankings_v3.py:310) currently locks in rejection.

24. **P2 — SQL and identity tests accept materially broken ranking implementations.**  
    **Location:** [test_ranking_sql.py:50](C:/Users/brian/ed-finder/tests/test_ranking_sql.py:50), :191, :205, :273; [test_ranking_profile_identity.py:37](C:/Users/brian/ed-finder/tests/test_ranking_profile_identity.py:37), :60.  
    **Trigger / untested real paths:** in-memory mutations changed confidence*completeness to addition, reversed distance ASC to DESC, and substituted a y placeholder for x while still adding all parameters. Each mutant passed all 17 SQL test functions. The third created repeated placeholders with missing indices despite passing the occurrence-count assertion.  
    **Why silent:** tests mostly assert token presence. The strict count-query binding test has reference coordinates but no max-distance filter, so it never exercises the count distance expression. The identity test compares values generated by the same function.  
    **Minimal fix:** execute discriminating orders, assert actual formula/direction, and require the placeholder-index set to equal 1..len(params) across both builders and radius/reference combinations. The existing real-DB local-reference regression would catch the placeholder mutant when run; this is specifically a unit-suite blind spot.

25. **P2 — “Extraction” and ranking-order integration tests can pass without proving the behavior in their names.**  
    **Location:** [integration/test_phase2_search_no_fallback.py:21](C:/Users/brian/ed-finder/tests/integration/test_phase2_search_no_fallback.py:21), :45–72; [test_archetype_rankings_v3.py:169](C:/Users/brian/ed-finder/tests/test_archetype_rankings_v3.py:169).  
    **Trigger / untested real paths:** return an empty list, omit both score fields from every result, or use overall ordering for Extraction. The integration tests still accept the envelope/empty sorted list, and explicitly tolerate the economy fallback. In the archetype order fixture, min_score is the maximum flexible score: eleven surviving rows all have raw score 100. Dropping the raw-score multiplier does not change that expected order.  
    **Why silent:** no mandatory nonempty scored comparison for Extraction; nondiscriminating equal-score fixtures for archetype score weighting.  
    **Minimal fix:** require matching/nonmatching rows and opposing economy ranks. Test unequal passing raw scores, including 90×0.8 versus 50×0.9, plus a case where uncertainty legitimately reverses raw-score order. The current archetype test still usefully tests uncertainty order and filtering.

26. **P2 — Builder tests substitute checksum consistency and partial joins for determinism and complete summary correctness.**  
    **Location:** [test_v3_system_archetype_build.py:100](C:/Users/brian/ed-finder/tests/test_v3_system_archetype_build.py:100), :122; [test_v3_system_archetype_model.py:53](C:/Users/brian/ed-finder/tests/test_v3_system_archetype_model.py:53).  
    **Trigger / untested real paths:** a model uses randomness during fit generation; a build omits all rows; or summarise picks an incorrect secondary.  
    **Why silent:** the “deterministic” test builds once and hashes the same stored rows again, so randomness at build time is invisible. The standalone summary test's inner join and grouping over existing rows pass on empty tables, and do not establish that the named primary is the maximum. The model test named “primary and secondary” never asserts secondary. Other row-count tests catch a globally empty builder, but not the claimed properties of these individual tests.  
    **Minimal fix:** independently build identical inputs twice; compare full governed outputs; drive coverage from expected input IDs; assert exact top-two/tie/zero cases.

27. **P2 — The SQL helper silently broadens unsupported or incomplete filter requests.**  
    **Location:** [ranking/ranking_sql.py:179](C:/Users/brian/ed-finder/apps/api/src/ranking/ranking_sql.py:179), :206; tests :124 and :154.  
    **Trigger:** direct helper input {"elw_count_max":0}, a typo, or {"max_distance_ly":50} with reference_coords=None.  
    **Wrong outcome / silence:** both builders return unrestricted SQL for those constraints. Tests explicitly require ignoring them.  
    **Minimal fix:** reject unknown filter keys and missing required context; let callers deliberately omit truly inapplicable fields. **Reachability:** current public callers construct known keys and avoid radius-without-reference; this is an exposed function-contract defect, not a claim those exact helper calls are reachable through today's routes.

28. **P2 — Client validation gaps become database failures instead of 422s.**  
    **Location:** [models.py:506](C:/Users/brian/ed-finder/apps/api/src/models.py:506), :507; [routers/archetypes.py:478](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:478), :484.  
    **Trigger:** local size=-1; from/offset=9223372036854775808; rankings galaxy_region=2147483648.  
    **Wrong outcome / silence:** negative size passes Pydantic (confirmed), then PostgreSQL rejects negative LIMIT. Unbounded Python integers pass request parsing but overflow asyncpg integer/bigint encoding. The routes classify the resulting internal/database errors as availability failures. Region domain is also not constrained.  
    **Minimal fix:** enforce positive size and actual domain/storage bounds, alongside finite/nonnegative/order checks for ranges. Add HTTP-boundary tests rather than helper-only calls. Oversized-integer failure is established from declared binding types, not a production request replay.

29. **P2 — The generic 503 wrapper still classifies arbitrary internal bugs as backend outages.**  
    **Location:** [routers/search.py:199](C:/Users/brian/ed-finder/apps/api/src/routers/search.py:199), error shaping :68; [integration/test_phase2_search_no_fallback.py:78](C:/Users/brian/ed-finder/tests/integration/test_phase2_search_no_fallback.py:78).  
    **Trigger:** TypeError in parsing/serialization preparation, ValueError from implementation code, or an asyncpg argument-binding/programming error. The valid one-sided-distance request in finding 17 is a concrete instance.  
    **Wrong outcome / silence:** every non-HTTPException becomes “temporarily unavailable,” with reduce-radius/retry guidance. Default expose_error_detail=false hides the cause from clients. The local route does log the original exception, so this is status/category masking rather than complete loss of server diagnostics. The integration test deliberately raises generic RuntimeError and insists on 503, thereby preserving the conflation.  
    **Minimal fix:** map genuine transient availability exceptions to 503; use 422 for input errors and the ordinary 500/error-monitoring path for implementation failures. Test these categories independently.

30. **P3 — Several failure paths discard diagnostic causes.**  
    **Location:** [local_search.py:773](C:/Users/brian/ed-finder/apps/api/src/local_search.py:773); [routers/archetypes.py:374](C:/Users/brian/ed-finder/apps/api/src/routers/archetypes.py:374); [scripts/v3_system_archetype.py:878](C:/Users/brian/ed-finder/scripts/v3_system_archetype.py:878).  
    **Trigger:** a missing/renamed V3 table or schema; a CLI ValueError for an invalid generation, source seal or lifecycle.  
    **Wrong outcome / silence:** missing-relation exceptions become handled generic HTTPExceptions without logging at either inner handler; the outer local route rethrows them before its logger. CLI prints only the exception class, so unrelated integrity failures become indistinguishable {"status":"FAILED","error":"ValueError"}. Exception chaining alone does not log a FastAPI-handled HTTPException.  
    **Minimal fix:** record safe structured diagnostic codes/context and the underlying cause server-side; retain credential redaction. Test a missing relation and two distinct integrity failures.

## Complete request-input disposition

The base reference request for examples is {"reference_coords":{"x":0,"y":0,"z":0},"filters":{"distance":{"min":0,"max":500}}}. Add galaxy_wide=true when no reference is needed.

### LocalSearchRequest

| Field / nested input | Actual handling at dc218fb7 |
|---|---|
| reference_coords | Required complete x/y/z unless galaxy_wide=true; then used for distance and tie-break. Partial galaxy-wide coordinates become no reference. Finite values are not enforced. |
| galaxy_wide | Enforced: removes the default radius constraint. Distance bounds are intentionally N/A to galaxy-wide candidate scope; a supplied reference still affects tie-break/display. |
| filters.distance.min | Parsed but ignored; one-sided requests crash when another bound is None. Finding 14/17. |
| filters.distance.max | Enforced outside galaxy-wide mode, capped at MAX_SEARCH_RADIUS with a warning. Optional-bound/null handling broken. |
| filters.population.min / max | Silently ignored. Finding 16. |
| filters.population.value / comparison (allowed extras) | A parsable non-None value gets 422. Invalid value is swallowed to None and ignored. |
| filters.economy | Normalized/validated, echoed; every concrete economy silently uses no-pick ordering. Finding 8. “any” is legitimately no pick. |
| sort_by | Normalized (rating → development), otherwise arbitrary strings accepted; ignored by V3 ordering. Finding 15. |
| size | Enforced as LIMIT; HTTP upper bound 500, but no lower bound. Finding 28. |
| from / from_ | Enforced as OFFSET; nonnegative, but no bigint upper bound. |
| require_bio | true → has_biologicals=true; false/null → no requirement, consistent with “require” semantics. |
| require_geo | true → has_geologicals=true; false/null → no requirement. |
| require_terra | true → terraformable_count minimum at least 1; combines correctly with larger explicit minimum. false/null → no additional requirement. |
| star_types | Nonempty list → main_star_class IN (...); empty/null → no filter. Strings are not vocabulary-validated. |
| min_development_score | Positive values filter the selected/no-pick raw score in both queries. Zero/negative act as no floor; negatives are not rejected. Large values have no meaningful score-domain validation. |
| body_filters | Four lower bounds only; complete breakdown below. Unknown keys allowed by the nested model and ignored downstream. |
| Undeclared top-level extras | Default Pydantic extra-ignore drops them. For example galaxy_region_id, secondary_economy or archetype submitted to this endpoint receive no validation error or effect; they are not declared LocalSearchRequest features. |
| Direct local_db_search_v3 body: galaxy_region_id | Mapped and enforced when truthy; zero treated as absent. The HTTP router never passes it. |
| Direct local_db_search_v3 body: secondary_economy | Parsed into context and never used by the V3 path. |

### Every declared BodyFilters key

| Key | min | max |
|---|---|---|
| elw_count | Enforced when nonzero | Ignored |
| ww_count | Enforced when nonzero | Ignored |
| terraformable_count | Enforced when nonzero; combined with require_terra | Ignored |
| landable_count | Enforced when nonzero | Ignored |
| ammonia_count | Ignored | Ignored |
| gas_giant_count | Ignored | Ignored |
| bio_signal_total | Ignored | Ignored |
| geo_signal_total | Ignored | Ignored |
| neutron_count | Ignored | Ignored |
| black_hole_count | Ignored | Ignored |
| white_dwarf_count | Ignored | Ignored |
| hmc_count | Ignored | Ignored |
| metal_rich_count | Ignored | Ignored |
| rocky_count | Ignored | Ignored |
| rocky_ice_count | Ignored | Ignored |
| icy_count | Ignored | Ignored |
| other_star_count | Ignored | Ignored |
| ring_count | Ignored | Ignored |
| walkable_count | Ignored | Ignored |

Zero minimum is a legitimate no-op for nonnegative counts. Negative minima are accepted and effectively match all nonnegative values. Alias normalization only converts certain camelCase names to short names; the V3 mapper still expects the four exact *_count names. For example elw and gasGiant remain ineffective.

### Every GET /api/archetypes/rankings query parameter

| Parameter | Actual handling |
|---|---|
| archetype | Required; eight V3 keys only, unknown keys 422; selects the joined fit. |
| min_score | HTTP integer 0–100, default 40; enforced against selected raw score. |
| galaxy_region | Equality enforced when supplied; no storage/domain bounds. |
| max_distance_ly | Enforced from Sol, lower bound zero; same predicate in page/count. |
| has_elw | true → elw_count>=1; omitted → no requirement; false → erroneous 422. |
| min_slots | Every supplied value including zero → explicit 422; no projection. |
| max_contamination | Every supplied value including zero → explicit 422; no projection. |
| limit | HTTP 1–500, default 50; enforced in page. |
| offset | HTTP nonnegative, default 0; enforced in page; overflow unchecked. |

### Ranking builder function arguments

Both builders ignore spec and picked_economy. picked_archetype selects the joined fit; current route validates its key. The hard_filters keys elw_count_min, ww_count_min, terraformable_count_min, landable_count_min, has_rings, has_biologicals, has_geologicals, main_star_class_in, min_development_score, max_distance_ly and galaxy_region all have implementations. Genuine Python False values work for the three has_* keys. Unknown keys are ignored, and max_distance_ly is ignored without reference coordinates. reference_coords controls radius calculation and page tie-break; limit/offset apply only to the page.

Direct helper-only hazards: main_star_class_in=[] generates IN (); string "false" is truthy under bool(value). Current public callers guard/construct these values, so neither is presented above as an exposed endpoint defect.

## Coverage and qualifications across the eleven requested classes

| Class | Audit result |
|---|---|
| 1. Masked exceptions | Findings 17, 28–30. Local generic errors are logged but incorrectly classified; missing-relation handlers and CLI lose diagnostics. Legacy-only handlers outside the requested paths were not re-audited. |
| 2. Ignored inputs | Findings 7–8, 14–18, 23, 27–28 and complete matrices. require_* false is legitimately “no requirement”; has_elw=false is an actual defect. |
| 3. Success on failure | Findings 5–6, 12, 19. COUNT(*) returning None is not a demonstrated live path; its fallback to len(results) was not promoted into a speculative finding. |
| 4. Silent fallback | Economy fallback and warm legacy cache, findings 8–9. The old inline SQL fallback is absent. Source comments do not notify API callers. The explicit no-silent-fallback contract is in routers/search.py:59–62. |
| 5. Count/results and bindings | Current shared _build_common preserves predicates. A 104-case matrix found contiguous placeholder sets, matching parameters and identical WHERE clauses. Earlier coordinate-count crash is fixed. Publication race remains; unit test blind spots remain. |
| 6. Generation pinning | Findings 9–10, 19, 22. Uncached “no published generation” is correctly 404. F2b source reads intentionally use the explicitly selected build generation; they should not be forced onto the published generation. |
| 7. Validation gates | Findings 1–4, 12; real PG18 fault injection with guards enabled. |
| 8. Identity/reproducibility | Findings 2, 18, 21–22, 26. F2b manifest code_identity includes builder, model and migration bytes, so edits there do change manifest identity; no blanket claim that its source hash misses formula edits. |
| 9. Numeric behavior | Anchored economy ordinals correctly use ordinal-1; completeness/confidence correctly divide by 10000 once; null anchored quality uses the midpoint; score clamps precede rounding; displayed tier thresholds agree. Confidence issues are findings 13/21. |
| 10. Async/resources | Async reads are awaited and pools/transactions use context managers; test pools close in finally. No unawaited coroutine or cursor leak established. Validator transaction/locking issue is finding 4. |
| 11. Test quality | Findings 24–26 plus each behavior-specific test gap. Existing local DB tests now exercise reference coordinates/count, require_bio and discriminating terraformable filtering; these repaired cases were not falsely reported as still absent. |

**Numeric/specification issues not overstated as proven defects:** SystemVectors.completeness is read/scaled but not directly consumed by the fit model. The earlier F2 design says to combine completeness and confidence; the later F2b implementation plan and current manifest explicitly specify the implemented confidence formula, and V4 source confidence already incorporates completeness. This is a specification conflict to resolve, not evidence by itself of a new arithmetic failure. Flexible-fit handling of unknown quality is also less explicit than anchored-fit handling and deserves an explicit product rule. Python round uses ties-to-even (e.g. 44.5 → 44); the manifest says round and does not specify half-up. Boundary tests should freeze the intended rule, but no unsupported rounding defect is asserted.

**Test mutation evidence is qualified:** memory-only mutants demonstrate that the named unit tests fail to protect their claimed behavior. They do not claim every full DB/API test would also pass every mutant. Corruption probes alter prospective derived output before insertion; they do not assume that append-only protections permit modifying already-published data.

No fixes, commits, pushes or production operations were performed.

