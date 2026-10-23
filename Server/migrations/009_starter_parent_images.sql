ALTER TABLE starter_models ADD COLUMN IF NOT EXISTS image_data bytea;
ALTER TABLE starter_models ADD CONSTRAINT starter_parent_image_limit CHECK(image_data IS NULL OR octet_length(image_data) BETWEEN 8 AND 1048576);
