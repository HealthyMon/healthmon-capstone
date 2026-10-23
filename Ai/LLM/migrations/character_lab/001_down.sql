-- Explicit rollback tool is restricted to a disposable verification DB.
DROP TABLE IF EXISTS character_lab_reviews;
DROP TABLE IF EXISTS character_lab_events;
DROP TABLE IF EXISTS character_lab_sessions;
DROP TABLE IF EXISTS character_lab_schema_version;
