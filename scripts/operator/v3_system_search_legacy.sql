-- Frozen pre-optimization SELECT from PR #700; comparison only, never a writer.
WITH target AS MATERIALIZED (
    SELECT v.system_id64,v.loaded_body_count,v.completeness,v.confidence
      FROM v3_derived.system_rating_vector v
     WHERE v.derived_generation_id=%(generation_id)s AND v.chunk_ordinal=%(chunk_ordinal)s
),
body_summary AS (
    SELECT b.system_id64,
           (count(*) FILTER (
               WHERE b.lifecycle_state='ACTIVE' AND b.is_landable IS TRUE
           ))::integer AS landable_count,
           bool_or(
               b.lifecycle_state='ACTIVE'
               AND ts.public_code IN ('terraformable','terraformed','terraforming')
           ) AS has_terraformable
      FROM {schema}.bodies b
      JOIN target t ON t.system_id64=b.system_id64
 LEFT JOIN v3_vocab.terraforming_state ts
        ON ts.terraforming_state_id=b.terraforming_state_id
  GROUP BY b.system_id64
),
ring_summary AS (
    SELECT r.system_id64,true AS has_rings
      FROM {schema}.rings r
      JOIN target t ON t.system_id64=r.system_id64
     WHERE r.lifecycle_state='ACTIVE' AND r.kind='RING'
  GROUP BY r.system_id64
),
signal_summary AS (
    SELECT b.system_id64,
           bool_or(st.public_code='saa_signaltype_biological'
                   AND bs.signal_count>0) AS has_biologicals,
           bool_or(st.public_code='saa_signaltype_geological'
                   AND bs.signal_count>0) AS has_geologicals
      FROM {schema}.body_signal_current bs
      JOIN {schema}.bodies b ON b.body_pk=bs.body_pk
      JOIN target t ON t.system_id64=b.system_id64
      JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
     WHERE b.lifecycle_state='ACTIVE'
  GROUP BY b.system_id64
),
station_summary AS (
    SELECT st.system_id64,
           (count(*) FILTER (WHERE st.lifecycle_state='ACTIVE'))::integer
               AS station_count
      FROM {schema}.stations st
      JOIN target t ON t.system_id64=st.system_id64
  GROUP BY st.system_id64
),
main_star AS (
    SELECT DISTINCT ON (bm.system_id64)
           bm.system_id64,bm.body_class AS main_star_class
      FROM v3_derived.body_mechanics bm
      JOIN target t ON t.system_id64=bm.system_id64
     WHERE bm.derived_generation_id=%(generation_id)s AND bm.is_main_star IS TRUE
  ORDER BY bm.system_id64,bm.body_pk
)
SELECT %(generation_id)s,t.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
       cube(ARRAY[s.x_ly,s.y_ly,s.z_ly]),
       s.galaxy_region_id,gr.display_name,ms.main_star_class,
       t.loaded_body_count,COALESCE(bs.landable_count,0),
       COALESCE(ss.station_count,0),COALESCE(rs.has_rings,false),
       COALESCE(sig.has_biologicals,false),
       COALESCE(sig.has_geologicals,false),
       COALESCE(bs.has_terraformable,false),
       s.source_updated_at,
       (SELECT min(value)::double precision/10000
          FROM unnest(t.completeness) AS value),
       (SELECT min(value)::double precision/10000
          FROM unnest(t.confidence) AS value)
  FROM target t
  JOIN {schema}.systems s ON s.id64=t.system_id64
         LEFT JOIN v3_vocab.galaxy_region gr
    ON gr.galaxy_region_id=s.galaxy_region_id
         LEFT JOIN body_summary bs USING(system_id64)
         LEFT JOIN ring_summary rs USING(system_id64)
         LEFT JOIN signal_summary sig USING(system_id64)
         LEFT JOIN station_summary ss USING(system_id64)
         LEFT JOIN main_star ms USING(system_id64)
ORDER BY t.system_id64
