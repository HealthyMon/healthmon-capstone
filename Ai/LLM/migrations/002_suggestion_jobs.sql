CREATE TABLE IF NOT EXISTS suggestion_jobs (
  pet_id text NOT NULL REFERENCES pets(id), source_id text NOT NULL, revision integer NOT NULL,
  status text NOT NULL DEFAULT 'pending', result jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(pet_id,source_id,revision), FOREIGN KEY(pet_id,source_id) REFERENCES sources(pet_id,id)
);
INSERT INTO schema_migrations(version) VALUES('002') ON CONFLICT DO NOTHING;
