ALTER TABLE requests ADD COLUMN IF NOT EXISTS dependency_source_ids jsonb NOT NULL DEFAULT '[]';
ALTER TABLE requests ADD COLUMN IF NOT EXISTS dependency_memory_ids jsonb NOT NULL DEFAULT '[]';
ALTER TABLE food_analyses ADD COLUMN IF NOT EXISTS erased_at timestamptz;
CREATE TABLE IF NOT EXISTS game_retained_scores (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 period text NOT NULL CHECK(period IN ('daily','weekly')),period_start date NOT NULL,
 adjustment jsonb NOT NULL,rule_version text NOT NULL,
 PRIMARY KEY(pet_id,period,period_start)
);
