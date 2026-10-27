"""Synthetic rows, preserving the committed lifecycle receipt's proportions.

Only the disposable harness calls these statements. No immutability trigger,
constraint, or referential check is disabled for loading.
"""

METADATA = """
INSERT INTO v3_source.source(source_id,source_code,display_name,authority_class)
VALUES (1,'purge_rehearsal','Disposable synthetic rehearsal','OPERATOR_ADJUDICATION');
INSERT INTO v3_source.source_rights_policy(rights_policy_id,source_id,policy_version,
 rights_class,retention_class,effective_at)
VALUES(1,1,'synthetic','INTERNAL_USE','disposable',now());
INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,
 acquisition_kind,trust_zone,run_state,idempotency_key,started_at,completed_at,
 importer_version,importer_code_sha256,importer_config_sha256,normalizer_version,normalizer_sha256)
VALUES('00000000-0000-0000-0000-000000000001',1,1,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',
 'purge-rehearsal',now(),now(),'synthetic',decode(repeat('00',32),'hex'),
 decode(repeat('00',32),'hex'),'synthetic',decode(repeat('00',32),'hex'));
INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,
 lifecycle_state,manifest_sha256,build_source_run_id,validation_completed_at)
VALUES('a7076522-54cd-52f3-a291-4e5406bea230','phase4c_full_20260827_r5',
 'v3_gen_phase4c_full_20260827_r5','PUBLISHED',decode(repeat('00',32),'hex'),
 '00000000-0000-0000-0000-000000000001',now());
INSERT INTO v3_meta.current_canonical_generation VALUES
 (true,'a7076522-54cd-52f3-a291-4e5406bea230',4,now());
INSERT INTO v3_spatial.spatial_generation(spatial_generation_id,canonical_generation_id,
 pyramid_version,expected_systems)
VALUES('00000000-0000-0000-0000-000000000002',
 'a7076522-54cd-52f3-a291-4e5406bea230','synthetic_purge_rehearsal',1);
UPDATE v3_spatial.spatial_generation SET lifecycle_state='READY',validated_at=now(),
 validation_receipt='{"status":"VERIFIED","synthetic":true}',
 validation_sha256=decode(repeat('00',32),'hex')
WHERE spatial_generation_id='00000000-0000-0000-0000-000000000002';
SELECT v3_spatial.publish_spatial_pyramid('00000000-0000-0000-0000-000000000002',NULL,0,
 'a7076522-54cd-52f3-a291-4e5406bea230','disposable-rehearsal','synthetic seed');
"""

GENERATION = """
INSERT INTO v3_meta.derived_generation(derived_generation_id,canonical_generation_id,
 canonical_publication_sequence,generation_key,mechanics_version,scorer_version,adapter_version,
 manifest,manifest_sha256,expected_systems,expected_bodies)
VALUES(%(generation)s::uuid,'a7076522-54cd-52f3-a291-4e5406bea230',4,%(key)s,
 'v4-mechanics-2026-09','4.0.0','v4-canonical-stream-1','{}',decode(repeat('00',32),'hex'),
 %(systems)s::bigint,%(bodies)s::bigint);
INSERT INTO v3_derived.build_chunk(derived_generation_id,chunk_ordinal,source_projection_sha256,
 canonical_input_sha256,content_sha256,systems,canonical_bodies,physical_bodies,eligible_opportunities)
SELECT %(generation)s::uuid,n,decode(repeat('00',32),'hex'),decode(repeat('00',32),'hex'),
 decode(repeat('00',32),'hex'),least(1000,%(systems)s::int-n*1000),0,0,0
FROM generate_series(0,(%(systems)s::int-1)/1000) n;
"""

VECTOR = """
INSERT INTO v3_derived.system_rating_vector
SELECT %(generation)s::uuid,n,(n-1)/1000,3,3,decode(md5(n::text)||md5(n::text),'hex'),
 ARRAY[50,50,50,50,50,50,50]::smallint[],ARRAY[50,50,50,50,50,50,50]::smallint[],
 ARRAY[50,50,50,50,50,50,50]::smallint[],ARRAY[50,50,50,50,50,50,50]::smallint[],
 ARRAY[9000,9000,9000,9000,9000,9000,9000]::smallint[],
 ARRAY[9000,9000,9000,9000,9000,9000,9000]::smallint[]
FROM generate_series(%(first)s::bigint,%(last)s::bigint) n;
"""

BODY = """
INSERT INTO v3_derived.body_mechanics(derived_generation_id,system_id64,body_pk,
 source_body_id64,body_class,spectral_class,luminosity_class,rings,biologicals,
 geologicals,volcanism,terraformable,tidally_locked,is_main_star,reserve_level,
 usable_ground_opportunity,subtype_present,subtype_observed_at)
SELECT %(generation)s::uuid,(n-1)%%%(systems)s::bigint+1,n,n,
 (ARRAY['Rocky body','High metal content body','M (Red dwarf) Star'])[1+n%%3],
 CASE WHEN n%%3=0 THEN 'M' END,CASE WHEN n%%3=0 THEN 'V' END,
 n%%11=0,n%%7=0,n%%5=0,n%%13=0,n%%17=0,n%%2=0,n%%3=0,
 'common',true,true,'2026-10-10T00:00:00Z'
FROM generate_series(%(first)s::bigint,%(last)s::bigint) n;
"""

ECONOMY = """
INSERT INTO v3_derived.economy_opportunity
SELECT %(generation)s::uuid,((n-1)%%%(bodies)s::bigint)%%%(systems)s::bigint+1,
 (n-1)%%%(bodies)s::bigint+1,((n-1)/%(bodies)s::bigint+1)::smallint,
 true,false,50,50,50,50,0.9,0.9
FROM generate_series(%(first)s::bigint,%(last)s::bigint) n;
"""

SEARCH = """
INSERT INTO v3_derived.system_search(derived_generation_id,system_id64,name,x_ly,y_ly,z_ly,
 position_ly,galaxy_region_id,region_name,main_star_class,body_count,landable_count,
 station_count,has_rings,has_biologicals,has_geologicals,has_terraformable,
 source_observed_at,completeness,confidence)
SELECT %(generation)s::uuid,n,'Rehearsal system '||n,n%%1000,n%%700,n%%300,
 cube(ARRAY[(n%%1000)::float8,(n%%700)::float8,(n%%300)::float8]),n%%42,
 'Synthetic region','M',3,1,0,n%%11=0,n%%7=0,n%%5=0,n%%17=0,
 '2026-10-10T00:00:00Z',0.9,0.9
FROM generate_series(%(first)s::bigint,%(last)s::bigint) n;
"""

# 019's verify recounts the copied rows per Ratings chunk against the build
# receipts, as production's builder recorded them: vector rows (systems), body
# rows (physical_bodies) and opportunity rows (eligible_opportunities) per
# vector chunk. Receipts are written while the generation is still BUILDING.
CHUNK_RECEIPTS = """
UPDATE v3_derived.build_chunk b SET canonical_bodies=x.bodies,physical_bodies=x.bodies,
 eligible_opportunities=x.opportunities
FROM (SELECT k.chunk_ordinal,COALESCE(m.n,0)::int AS bodies,COALESCE(o.n,0)::int AS opportunities
  FROM v3_derived.build_chunk k
  LEFT JOIN (SELECT v.chunk_ordinal,count(*) n FROM v3_derived.body_mechanics t
    JOIN v3_derived.system_rating_vector v ON v.derived_generation_id=t.derived_generation_id AND v.system_id64=t.system_id64
    WHERE t.derived_generation_id=%(generation)s::uuid GROUP BY 1) m USING (chunk_ordinal)
  LEFT JOIN (SELECT v.chunk_ordinal,count(*) n FROM v3_derived.economy_opportunity t
    JOIN v3_derived.system_rating_vector v ON v.derived_generation_id=t.derived_generation_id AND v.system_id64=t.system_id64
    WHERE t.derived_generation_id=%(generation)s::uuid GROUP BY 1) o USING (chunk_ordinal)
  WHERE k.derived_generation_id=%(generation)s::uuid) x
WHERE b.derived_generation_id=%(generation)s::uuid AND b.chunk_ordinal=x.chunk_ordinal;
"""

# The published survivor Search product's per-chunk receipts (search_build_chunk,
# one row per Ratings chunk holding Search rows), inserted while the product is
# BUILDING exactly as the production Search build recorded them.
SEARCH_CHUNK_RECEIPTS = """
INSERT INTO v3_derived.search_build_chunk(derived_generation_id,chunk_ordinal,product_code,
 projection_version,source_projection_sha256,content_sha256,systems)
SELECT %(generation)s::uuid,v.chunk_ordinal,'system_search',%(version)s,decode(repeat('00',32),'hex'),
 decode(repeat('00',32),'hex'),count(*)::int
FROM v3_derived.system_search s JOIN v3_derived.system_rating_vector v
  ON v.derived_generation_id=s.derived_generation_id AND v.system_id64=s.system_id64
WHERE s.derived_generation_id=%(generation)s::uuid GROUP BY v.chunk_ordinal;
"""

# The owner-applied production planner statistics (2026-10-19,
# docs/operations/v3-postgres-server-settings.md), so the copy carries them and
# the opportunity swap recalibrates and restores them as production will.
PLANNER_STATISTICS = """
ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET STATISTICS 1000;
ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = -0.13);
"""

FINALIZE = """
UPDATE v3_meta.derived_generation SET lifecycle_state='VALIDATING',
 source_receipt='{"status":"SEALED","synthetic":true}',
 content_sha256=decode(repeat('00',32),'hex') WHERE derived_generation_id=%(generation)s::uuid;
"""

PUBLISH = """
UPDATE v3_meta.derived_generation SET lifecycle_state='READY',validated_at=now(),
 validation_receipt='{"status":"VERIFIED","synthetic":true}'
WHERE derived_generation_id=%(generation)s::uuid;
SELECT v3_meta.publish_derived_generation(%(generation)s::uuid,NULL,0,
 'a7076522-54cd-52f3-a291-4e5406bea230',4,'disposable-rehearsal','synthetic seed',ARRAY[]::text[]);
"""

SEARCH_PRODUCT = """
INSERT INTO v3_meta.derived_product(derived_generation_id,product_code,product_version,
 manifest,manifest_sha256,expected_rows)
VALUES(%(generation)s::uuid,'system_search','v3-system-search-1','{}',
 decode(repeat('00',32),'hex'),%(systems)s::bigint);
"""

SEARCH_PRODUCT_READY = """
UPDATE v3_meta.derived_product SET lifecycle_state='READY',validated_at=now(),
 validation_receipt='{"status":"VERIFIED","synthetic":true}',
 validation_sha256=decode(repeat('00',32),'hex')
WHERE derived_generation_id=%(generation)s::uuid AND product_code='system_search';
"""

# Post-go-live survivors. Production built both Finder products on the already
# PUBLISHED parallel_v1 generation, validated them READY/VERIFIED and published
# them through 015's publish_derived_product (publish run 39933842811). The
# seed follows the same lifecycle with the production product versions; the
# rows are synthetic, every guard and constraint stays enabled.
SURVIVOR_PRODUCTS = (('system_search', 'v3-system-search-2'), ('system_archetype', 'v3-archetype-4'))

SURVIVOR_PRODUCT = """
INSERT INTO v3_meta.derived_product(derived_generation_id,product_code,product_version,
 manifest,manifest_sha256,expected_rows)
VALUES(%(generation)s::uuid,%(product)s,%(version)s,'{"synthetic":true}',
 decode(repeat('00',32),'hex'),%(rows)s::bigint);
"""

PRODUCT_READY = """
UPDATE v3_meta.derived_product SET lifecycle_state='READY',validated_at=now(),
 validation_receipt='{"status":"VERIFIED","synthetic":true}',
 validation_sha256=decode(repeat('00',32),'hex')
WHERE derived_generation_id=%(generation)s::uuid AND product_code=%(product)s;
"""

# One transaction, one publication time, one audit row per product, as the
# production publication run committed both products together.
PUBLISH_PRODUCTS = """
BEGIN;
SELECT v3_meta.publish_derived_product(%(generation)s::uuid,'system_search','disposable-rehearsal');
SELECT v3_meta.publish_derived_product(%(generation)s::uuid,'system_archetype','disposable-rehearsal');
COMMIT;
"""

_ARCHETYPES = ('paradise', 'mining_hub', 'manufacturing_hub', 'megacomplex',
               'research_hub', 'stronghold', 'population_capital', 'flexible')


def _tier(score):
    return (f"CASE WHEN {score}>=88 THEN 'S' WHEN {score}>=76 THEN 'A' WHEN {score}>=60 THEN 'B' "
            f"WHEN {score}>=40 THEN 'C' ELSE 'D' END")


# One wide row per survivor system (011). Scores vary per archetype so every
# B/A/S partial ranking index holds a share of rows, as built rows do.
ARCHETYPE = ("""
INSERT INTO v3_derived.system_archetype(derived_generation_id,system_id64,archetype_version,"""
    + ','.join(f'{name}_score,{name}_tier,{name}_confidence_ppm,{name}_weighted_e4' for name in _ARCHETYPES)
    + """,
 primary_archetype,secondary_archetype,best_colony_potential,best_tier,archetype_confidence_ppm,
 weighted_potential,completeness_ppm)
SELECT %(generation)s::uuid,n,'v3-archetype-4',"""
    + ','.join(f's[{index}],{_tier(f"s[{index}]")},500000+(n*{index})%%500000,s[{index}]*(9000+n%%1000)'
               for index in range(1, 9))
    + """,
 (ARRAY['paradise','mining_hub','manufacturing_hub','megacomplex','research_hub','stronghold',
  'population_capital','flexible'])[1+n%%8],
 (ARRAY['paradise','mining_hub','manufacturing_hub','megacomplex','research_hub','stronghold',
  'population_capital','flexible'])[1+(n+1)%%8],
 best,""" + _tier('best') + """,500000+n%%500000,best::float8,1000000
FROM generate_series(%(first)s::bigint,%(last)s::bigint) n,
 LATERAL (SELECT ARRAY[(n*7)%%101,(n*11)%%101,(n*13)%%101,(n*17)%%101,(n*19)%%101,
  (n*23)%%101,(n*29)%%101,(n*31)%%101]::smallint[] AS s) scores,
 LATERAL (SELECT (SELECT max(v) FROM unnest(s) v) AS best) peak;
""")

SURVIVOR_PUBLICATION = """
SELECT jsonb_build_object(
 'archetype_rows',(SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%(generation)s::uuid),
 'search_rows',(SELECT count(*) FROM v3_derived.system_search WHERE derived_generation_id=%(generation)s::uuid),
 'products',(SELECT jsonb_object_agg(product_code,jsonb_build_object('version',product_version,
   'state',lifecycle_state,'status',validation_receipt->>'status','expected_rows',expected_rows,
   'published',published_at IS NOT NULL))
   FROM v3_meta.derived_product WHERE derived_generation_id=%(generation)s::uuid),
 'audit_rows',(SELECT count(*) FROM v3_meta.derived_product_publication_audit a
   JOIN v3_meta.derived_product p USING (derived_generation_id,product_code,product_version,manifest_sha256,published_at)
   WHERE a.derived_generation_id=%(generation)s::uuid),
 'app_search_rows',(SELECT count(*) FROM v3_app.system_search),
 'app_archetype_rows',(SELECT count(*) FROM v3_app.system_archetype));
"""
