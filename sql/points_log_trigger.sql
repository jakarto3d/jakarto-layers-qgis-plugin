-- Create the trigger function
CREATE OR REPLACE FUNCTION log_points_changes()
RETURNS trigger AS $$
BEGIN
    CASE TG_OP
        WHEN 'INSERT' THEN
            INSERT INTO points_log (operation, point_id, geom, attributes)
            VALUES ('INSERT', NEW.id, NEW.geom, NEW.attributes);

        WHEN 'UPDATE' THEN
            INSERT INTO points_log (operation, point_id, geom, attributes)
            SELECT
                'UPDATE',
                NEW.id,
                NEW.geom,
                CASE
                    WHEN NEW.attributes IS DISTINCT FROM OLD.attributes THEN NEW.attributes
                    ELSE NULL
                END;
        WHEN 'DELETE' THEN
            INSERT INTO points_log (operation, point_id)
            VALUES ('DELETE', OLD.id);
    END CASE;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Create the trigger
CREATE OR REPLACE TRIGGER points_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON points
FOR EACH ROW EXECUTE FUNCTION log_points_changes();
