CREATE TABLE IF NOT EXISTS food_analyses (
  id text PRIMARY KEY,
  pet_id text NOT NULL REFERENCES pets(id),
  result jsonb NOT NULL,
  confirmation jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS food_analyses_pet_created ON food_analyses(pet_id,created_at);
INSERT INTO schema_migrations(version) VALUES('003') ON CONFLICT DO NOTHING;
