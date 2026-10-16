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
 'a7076522-54cd-52f3-a291-4e5406bea230',4,'disposable-rehearsal','synthetic seed');
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
