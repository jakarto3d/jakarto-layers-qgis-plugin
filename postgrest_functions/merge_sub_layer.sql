CREATE OR REPLACE FUNCTION merge_sub_layer(sub_layer_id uuid) RETURNS void AS $$
DECLARE parent_layer_id uuid;
BEGIN 
    -- Get the parent layer id and verify it exists
    SELECT l.parent_id INTO parent_layer_id
    FROM layers l
    WHERE l.id = sub_layer_id;

    IF parent_layer_id IS NULL THEN
        RAISE EXCEPTION 'Layer % is not a sub-layer', sub_layer_id;
    END IF;

    -- Update existing features to replace their parent features
    UPDATE points p
    SET 
        geom = sub.geom,
        attributes = sub.attributes
    FROM (
        SELECT p2.parent_id, p2.geom, p2.attributes
        FROM points p2
        WHERE p2.layer_id = sub_layer_id
            AND p2.parent_id IS NOT NULL
    ) AS sub
    WHERE p.id = sub.parent_id;

    -- Insert new features (without parent_id) into the parent layer
    INSERT INTO points (layer_id, created_at, geom, attributes)
    SELECT
        parent_layer_id,
        created_at,
        geom,
        attributes
    FROM points
    WHERE
        layer_id = sub_layer_id
        AND parent_id IS NULL;

    -- Delete features from parent layer that are referenced in sub_layer_deletes
    DELETE FROM points p
    WHERE p.layer_id = parent_layer_id
        AND p.id IN (
            SELECT sld.parent_feature_id
            FROM sub_layer_deletes sld
            WHERE sld.sub_layer_id = merge_sub_layer.sub_layer_id
        );

    -- Delete the points in the sub-layer
    DELETE FROM points
    WHERE layer_id = sub_layer_id;


    -- Delete the sub-layer
    -- Note: This will cascade delete points(sub-layer features) and sub_layer_deletes
    DELETE FROM layers
    WHERE id = sub_layer_id;

END;
$$ LANGUAGE plpgsql;
