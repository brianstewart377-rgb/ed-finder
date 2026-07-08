-- Keep station_body_links aligned with canonical station/body rows.
--
-- Goals:
--   - preserve station->system ownership on every write
--   - keep denormalized body_name synced to the referenced body row
--   - reject impossible confirmed rows at write time
--   - downgrade linked rows cleanly before a canonical body row is deleted

CREATE OR REPLACE FUNCTION fn_station_body_link_contract_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    station_system_id BIGINT;
    linked_body_system_id BIGINT;
    linked_body_name TEXT;
BEGIN
    SELECT st.system_id64
      INTO station_system_id
      FROM stations st
     WHERE st.id = NEW.station_id;

    IF station_system_id IS NOT NULL THEN
        NEW.system_id64 := station_system_id;
    END IF;

    IF NEW.body_id IS NOT NULL THEN
        SELECT b.system_id64, b.name
          INTO linked_body_system_id, linked_body_name
          FROM bodies b
         WHERE b.id = NEW.body_id;

        IF linked_body_system_id IS NULL THEN
            RAISE EXCEPTION
                'station_body_links body_id % does not resolve to a canonical body row',
                NEW.body_id;
        END IF;

        IF NEW.system_id64 IS DISTINCT FROM linked_body_system_id THEN
            RAISE EXCEPTION
                'station_body_links system/body mismatch: link system %, body system %',
                NEW.system_id64, linked_body_system_id;
        END IF;

        NEW.body_name := linked_body_name;
    END IF;

    IF NEW.association_status = 'confirmed' THEN
        IF NEW.body_id IS NULL THEN
            RAISE EXCEPTION
                'station_body_links confirmed rows require body_id';
        END IF;
        IF NEW.lane NOT IN ('orbital', 'surface') THEN
            RAISE EXCEPTION
                'station_body_links confirmed rows require orbital/surface lane, got %',
                NEW.lane;
        END IF;
        NEW.association_confidence := 'exact';
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_downgrade_station_body_links_for_deleted_body()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE station_body_links
       SET body_id                = NULL,
           body_name              = COALESCE(OLD.name, body_name),
           association_status     = 'unresolved',
           association_confidence = 'unresolved',
           association_source     = 'unknown',
           resolver_notes         = CASE
               WHEN resolver_notes IS NULL OR resolver_notes = '' THEN
                   'Canonical body row deleted; station/body link downgraded automatically.'
               WHEN resolver_notes LIKE '%Canonical body row deleted; station/body link downgraded automatically.%' THEN
                   resolver_notes
               ELSE
                   resolver_notes || ' | Canonical body row deleted; station/body link downgraded automatically.'
           END,
           updated_at             = NOW()
     WHERE body_id = OLD.id;

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_station_body_link_contract_guard ON station_body_links;
CREATE TRIGGER trg_station_body_link_contract_guard
BEFORE INSERT OR UPDATE OF system_id64, body_id, body_name, lane, association_status, association_confidence
ON station_body_links
FOR EACH ROW
EXECUTE FUNCTION fn_station_body_link_contract_guard();

DROP TRIGGER IF EXISTS trg_station_body_link_body_delete_guard ON bodies;
CREATE TRIGGER trg_station_body_link_body_delete_guard
BEFORE DELETE ON bodies
FOR EACH ROW
EXECUTE FUNCTION fn_downgrade_station_body_links_for_deleted_body();
