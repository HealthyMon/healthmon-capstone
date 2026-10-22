ALTER TABLE sources ADD COLUMN IF NOT EXISTS fingerprint text;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS evaluation_status text;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_model text;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS slot text;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS period_start date;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS shown_at timestamptz;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS excluded boolean NOT NULL DEFAULT false;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS replacement_count integer NOT NULL DEFAULT 0;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS is_proposal boolean NOT NULL DEFAULT false;
DROP INDEX IF EXISTS quest_one_active;
CREATE UNIQUE INDEX IF NOT EXISTS game_quest_slot ON quest_offers(pet_id,slot,period_start) WHERE slot IS NOT NULL;
CREATE TABLE IF NOT EXISTS common_server_metadata (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),instance_id text NOT NULL UNIQUE,environment text NOT NULL
);
CREATE TABLE IF NOT EXISTS game_states (
 pet_id text PRIMARY KEY REFERENCES pets(id) ON DELETE CASCADE,state jsonb NOT NULL,
 rule_version text NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),projection_hash text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS source_revisions (
 pet_id text NOT NULL,source_id text NOT NULL,revision int NOT NULL,raw_payload jsonb NOT NULL,
 changed_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(pet_id,source_id,revision),
 FOREIGN KEY(pet_id,source_id) REFERENCES sources(pet_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workout_goals (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,id text NOT NULL,
 exercise_type text NOT NULL,target double precision NOT NULL CHECK(target>0),unit text NOT NULL,
 body_part text NOT NULL,effective_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(pet_id,id)
);
CREATE INDEX IF NOT EXISTS workout_goals_at ON workout_goals(pet_id,exercise_type,effective_at DESC);
CREATE TABLE IF NOT EXISTS game_ledger (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,reward_key text NOT NULL,
 exp int NOT NULL CHECK(exp>=0),coin int NOT NULL CHECK(coin>=0),reason text NOT NULL,
 source_id text,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(pet_id,reward_key)
);
CREATE TABLE IF NOT EXISTS game_daily (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,day date NOT NULL,summary jsonb NOT NULL,
 rule_version text NOT NULL,PRIMARY KEY(pet_id,day)
);
CREATE TABLE IF NOT EXISTS game_weekly (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,week_start date NOT NULL,summary jsonb NOT NULL,
 rule_version text NOT NULL,PRIMARY KEY(pet_id,week_start)
);
CREATE TABLE IF NOT EXISTS ai_jobs (
 id text PRIMARY KEY,pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 kind text NOT NULL,request_id text NOT NULL,fingerprint text NOT NULL,input jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued',result jsonb,error text,attempts int NOT NULL DEFAULT 0,
 lease_until timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(pet_id,kind,request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS evolution_one_stage ON ai_jobs(pet_id,(input->>'stage')) WHERE kind='evolution';
CREATE TABLE IF NOT EXISTS model_assets (
 job_id text PRIMARY KEY REFERENCES ai_jobs(id) ON DELETE CASCADE,pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 stage int NOT NULL CHECK(stage BETWEEN 0 AND 3),sha256 text NOT NULL,data bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS common_chat_sessions (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,session_id text NOT NULL,
 expires_at timestamptz NOT NULL,active boolean NOT NULL,PRIMARY KEY(pet_id,session_id)
);
