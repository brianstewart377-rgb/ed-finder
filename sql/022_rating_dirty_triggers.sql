-- =============================================================================
-- 022: Rating dirty trigger audit/fix
--
-- Stage 17N.2c-R tightens the deferred rating rebuild contract:
--   * system main-star and data-freshness changes mark rating_dirty
--   * body insert/update/delete marks the affected system rating_dirty
--   * no-op body updates do not mark ratings dirty
--   * coordinate/region/population changes continue to mark cluster_dirty
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_mark_system_dirty()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    rating_changed BOOLEAN;
    cluster_changed BOOLEAN;
BEGIN
    rating_changed := (
        OLD.primary_economy        IS DISTINCT FROM NEW.primary_economy OR
        OLD.secondary_economy      IS DISTINCT FROM NEW.secondary_economy OR
        OLD.population             IS DISTINCT FROM NEW.population OR
        OLD.is_colonised           IS DISTINCT FROM NEW.is_colonised OR
        OLD.is_being_colonised     IS DISTINCT FROM NEW.is_being_colonised OR
        OLD.main_star_type         IS DISTINCT FROM NEW.main_star_type OR
        OLD.main_star_subtype      IS DISTINCT FROM NEW.main_star_subtype OR
        OLD.main_star_is_scoopable IS DISTINCT FROM NEW.main_star_is_scoopable OR
        OLD.has_body_data          IS DISTINCT FROM NEW.has_body_data OR
        OLD.body_count             IS DISTINCT FROM NEW.body_count OR
        OLD.data_quality           IS DISTINCT FROM NEW.data_quality OR
        OLD.updated_at             IS DISTINCT FROM NEW.updated_at
    );

    cluster_changed := (
        OLD.x                     IS DISTINCT FROM NEW.x OR
        OLD.y                     IS DISTINCT FROM NEW.y OR
        OLD.z                     IS DISTINCT FROM NEW.z OR
        OLD.population            IS DISTINCT FROM NEW.population OR
        OLD.is_colonised          IS DISTINCT FROM NEW.is_colonised OR
        OLD.is_being_colonised    IS DISTINCT FROM NEW.is_being_colonised OR
        OLD.galaxy_region_id      IS DISTINCT FROM NEW.galaxy_region_id
    );

    IF rating_changed THEN
        NEW.rating_dirty := TRUE;
    END IF;

    IF cluster_changed THEN
        NEW.cluster_dirty := TRUE;
    END IF;

    IF rating_changed OR cluster_changed THEN
        NEW.updated_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_mark_body_system_dirty()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    old_system_id64 BIGINT;
    new_system_id64 BIGINT;
BEGIN
    old_system_id64 := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.system_id64 ELSE NULL END;
    new_system_id64 := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.system_id64 ELSE NULL END;

    UPDATE systems
       SET rating_dirty  = TRUE,
           cluster_dirty = TRUE,
           has_body_data = CASE WHEN TG_OP = 'DELETE' THEN has_body_data ELSE TRUE END,
           updated_at    = NOW()
     WHERE id64 IN (
        SELECT DISTINCT id64
        FROM (VALUES (old_system_id64), (new_system_id64)) AS affected(id64)
        WHERE id64 IS NOT NULL
     );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_system_dirty ON systems;
CREATE TRIGGER trg_system_dirty
    BEFORE UPDATE OF x, y, z,
                     primary_economy, secondary_economy, population,
                     is_colonised, is_being_colonised,
                     main_star_type, main_star_subtype, main_star_is_scoopable,
                     has_body_data, body_count, data_quality,
                     galaxy_region_id, updated_at
    ON systems
    FOR EACH ROW
    EXECUTE FUNCTION fn_mark_system_dirty();

DROP TRIGGER IF EXISTS trg_body_dirty ON bodies;
DROP TRIGGER IF EXISTS trg_body_dirty_insert ON bodies;
DROP TRIGGER IF EXISTS trg_body_dirty_update ON bodies;
DROP TRIGGER IF EXISTS trg_body_dirty_delete ON bodies;

CREATE TRIGGER trg_body_dirty_insert
    AFTER INSERT ON bodies
    FOR EACH ROW
    EXECUTE FUNCTION fn_mark_body_system_dirty();

CREATE TRIGGER trg_body_dirty_update
    AFTER UPDATE OF system_id64, body_type, subtype, is_main_star,
                    distance_from_star, is_tidal_lock,
                    is_terraformable, is_landable,
                    is_water_world, is_earth_like, is_ammonia_world,
                    bio_signal_count, geo_signal_count,
                    spectral_class, is_scoopable
    ON bodies
    FOR EACH ROW
    WHEN (
        OLD.system_id64         IS DISTINCT FROM NEW.system_id64 OR
        OLD.body_type           IS DISTINCT FROM NEW.body_type OR
        OLD.subtype             IS DISTINCT FROM NEW.subtype OR
        OLD.is_main_star        IS DISTINCT FROM NEW.is_main_star OR
        OLD.distance_from_star  IS DISTINCT FROM NEW.distance_from_star OR
        OLD.is_tidal_lock       IS DISTINCT FROM NEW.is_tidal_lock OR
        OLD.is_terraformable    IS DISTINCT FROM NEW.is_terraformable OR
        OLD.is_landable         IS DISTINCT FROM NEW.is_landable OR
        OLD.is_water_world      IS DISTINCT FROM NEW.is_water_world OR
        OLD.is_earth_like       IS DISTINCT FROM NEW.is_earth_like OR
        OLD.is_ammonia_world    IS DISTINCT FROM NEW.is_ammonia_world OR
        OLD.bio_signal_count    IS DISTINCT FROM NEW.bio_signal_count OR
        OLD.geo_signal_count    IS DISTINCT FROM NEW.geo_signal_count OR
        OLD.spectral_class      IS DISTINCT FROM NEW.spectral_class OR
        OLD.is_scoopable        IS DISTINCT FROM NEW.is_scoopable
    )
    EXECUTE FUNCTION fn_mark_body_system_dirty();

CREATE TRIGGER trg_body_dirty_delete
    AFTER DELETE ON bodies
    FOR EACH ROW
    EXECUTE FUNCTION fn_mark_body_system_dirty();
