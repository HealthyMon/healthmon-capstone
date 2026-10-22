ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS rejected_at timestamptz;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS completion_verified boolean NOT NULL DEFAULT false;
ALTER TABLE quest_offers ADD COLUMN IF NOT EXISTS completion_event_id text;
CREATE TABLE IF NOT EXISTS game_proposal_controls (
 pet_id text PRIMARY KEY REFERENCES pets(id) ON DELETE CASCADE,
 rest_until timestamptz,stopped_until timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS game_rest_days (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 day date NOT NULL,reason text NOT NULL DEFAULT 'user_requested',
 PRIMARY KEY(pet_id,day)
);
CREATE INDEX IF NOT EXISTS game_visible_proposals
 ON quest_offers(pet_id,shown_at) WHERE is_proposal AND shown_at IS NOT NULL;
