-- Shared immutable CPU-hosted starter assets, separate from generated evolution jobs.
CREATE TABLE IF NOT EXISTS starter_models (
 id text PRIMARY KEY, species text NOT NULL, sha256 text NOT NULL CHECK(length(sha256)=64),
 size_bytes bigint NOT NULL CHECK(size_bytes BETWEEN 20 AND 67108864),
 image_sha256 text NOT NULL CHECK(length(image_sha256)=64),
 manifest_sha256 text NOT NULL CHECK(length(manifest_sha256)=64),
 provenance jsonb NOT NULL, data bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(octet_length(data)=size_bytes)
);
CREATE TABLE IF NOT EXISTS starter_model_default (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 starter_id text NOT NULL REFERENCES starter_models(id)
);
CREATE TABLE IF NOT EXISTS pet_starter_models (
 pet_id text PRIMARY KEY REFERENCES pets(id) ON DELETE CASCADE,
 starter_id text NOT NULL REFERENCES starter_models(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
