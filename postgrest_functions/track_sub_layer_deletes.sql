CREATE OR REPLACE FUNCTION track_sub_layer_deletes() 
RETURNS TRIGGER AS $$ 
BEGIN 
    IF OLD.parent_id IS NOT NULL AND EXISTS (SELECT 1 FROM layers l WHERE l.id = OLD.layer_id) THEN
        INSERT INTO sub_layer_deletes (sub_layer_id, parent_feature_id)
        VALUES (OLD.layer_id, OLD.parent_id);
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Create the trigger
DROP TRIGGER IF EXISTS track_sub_layer_deletes_trigger ON points;
CREATE TRIGGER track_sub_layer_deletes_trigger BEFORE DELETE ON points FOR EACH ROW EXECUTE FUNCTION track_sub_layer_deletes();
