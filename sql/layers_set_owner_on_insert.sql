CREATE OR REPLACE FUNCTION layers_set_owner_on_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO layer_permissions (user_id, layer_id, role)
  VALUES ((select auth.uid()), NEW.id, 'owner');

  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER layers_set_owner_on_insert_trigger
AFTER INSERT ON layers
FOR EACH ROW
EXECUTE PROCEDURE layers_set_owner_on_insert();
