ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_input jsonb;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS lease_token text;
