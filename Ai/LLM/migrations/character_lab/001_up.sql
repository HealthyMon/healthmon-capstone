-- Applied only to Persona Lab's separate SQLite test store, never PostgreSQL.
CREATE TABLE IF NOT EXISTS character_lab_sessions (
    id TEXT PRIMARY KEY CHECK(id LIKE 'clab-%'),
    namespace TEXT NOT NULL CHECK(namespace='character-lab-test'),
    state TEXT NOT NULL,
    initiative REAL NOT NULL DEFAULT 50 CHECK(initiative BETWEEN 0 AND 100),
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS character_lab_events (
    session_id TEXT NOT NULL REFERENCES character_lab_sessions(id),
    event_id TEXT NOT NULL, log TEXT NOT NULL, rule_version TEXT NOT NULL,
    PRIMARY KEY(session_id,event_id)
);
CREATE TABLE IF NOT EXISTS character_lab_reviews (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL CHECK(namespace='character-lab-test'),
    kind TEXT NOT NULL CHECK(kind IN ('analyzer','response')),
    status TEXT NOT NULL CHECK(status IN ('pending','approved','corrected','excluded')),
    draft TEXT NOT NULL, correction TEXT,
    reviewer_note TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_at TEXT,
    model_identifier TEXT NOT NULL, prompt_version TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS character_lab_schema_version (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO character_lab_schema_version(version) VALUES(1);
