CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS pets (
  id text PRIMARY KEY, owner_id text NOT NULL, version bigint NOT NULL DEFAULT 0,
  settings jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sources (
  pet_id text NOT NULL REFERENCES pets(id), id text NOT NULL, kind text NOT NULL CHECK(kind IN ('message','activity')),
  revision integer NOT NULL CHECK(revision>0), occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(), session_id text, payload jsonb NOT NULL,
  valid boolean NOT NULL DEFAULT true, PRIMARY KEY(pet_id,id)
);
CREATE TABLE IF NOT EXISTS memories (
  pet_id text NOT NULL, id text NOT NULL, source_id text NOT NULL, source_revision integer NOT NULL,
  slot text NOT NULL, content text NOT NULL, embedding vector(1024), embedding_revision text,
  valid boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(pet_id,id), FOREIGN KEY(pet_id,source_id) REFERENCES sources(pet_id,id)
);
CREATE INDEX IF NOT EXISTS memories_hnsw ON memories USING hnsw(embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS requests (
  pet_id text NOT NULL REFERENCES pets(id), id text NOT NULL, fingerprint text NOT NULL,
  status text NOT NULL, result jsonb, started_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(pet_id,id)
);
CREATE TABLE IF NOT EXISTS exchanges (
  pet_id text NOT NULL, request_id text NOT NULL, source_id text NOT NULL, speech text NOT NULL,
  memory_ids jsonb NOT NULL, state_used jsonb NOT NULL, state_after jsonb NOT NULL,
  valid boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(pet_id,request_id), FOREIGN KEY(pet_id,source_id) REFERENCES sources(pet_id,id)
);
CREATE TABLE IF NOT EXISTS quest_offers (
  pet_id text NOT NULL REFERENCES pets(id), id text NOT NULL, template jsonb NOT NULL,
  status text NOT NULL, state_version bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL, accepted_at timestamptz, progress double precision NOT NULL DEFAULT 0,
  PRIMARY KEY(pet_id,id)
);
CREATE UNIQUE INDEX IF NOT EXISTS quest_one_active ON quest_offers(pet_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS reward_ledger (
  pet_id text NOT NULL, offer_id text NOT NULL, state_version bigint NOT NULL, amount integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(pet_id,offer_id,state_version),
  FOREIGN KEY(pet_id,offer_id) REFERENCES quest_offers(pet_id,id)
);
CREATE TABLE IF NOT EXISTS state_snapshots (
  pet_id text NOT NULL REFERENCES pets(id), version bigint NOT NULL, state jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(pet_id,version)
);
CREATE TABLE IF NOT EXISTS outbox (
  pet_id text NOT NULL REFERENCES pets(id), source_id text NOT NULL, revision integer NOT NULL,
  status text NOT NULL DEFAULT 'pending', PRIMARY KEY(pet_id,source_id,revision)
);
INSERT INTO schema_migrations(version) VALUES('001') ON CONFLICT DO NOTHING;
