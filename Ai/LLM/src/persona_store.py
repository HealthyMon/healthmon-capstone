"""Separate, append-only SQLite store for synthetic Lab characters only."""
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / 'runs/persona-lab/test-characters.sqlite3'


class LabStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS lab_characters (
                id TEXT PRIMARY KEY CHECK(id LIKE 'lab-%'), owner TEXT NOT NULL CHECK(owner='persona-lab'),
                initial TEXT NOT NULL, short_term TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS lab_events (
                character_id TEXT NOT NULL REFERENCES lab_characters(id), event_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, fingerprint TEXT NOT NULL, event TEXT NOT NULL,
                PRIMARY KEY(character_id,event_id), UNIQUE(character_id,idempotency_key));
            CREATE TABLE IF NOT EXISTS lab_snapshots (
                character_id TEXT NOT NULL REFERENCES lab_characters(id), fingerprint TEXT NOT NULL,
                state TEXT NOT NULL, PRIMARY KEY(character_id,fingerprint));
        ''')
        return connection

    def create(self, initial, short_term):
        ident = 'lab-' + uuid.uuid4().hex
        with self._connect() as c:
            c.execute('INSERT INTO lab_characters(id,owner,initial,short_term) VALUES(?,?,?,?)',
                      (ident, 'persona-lab', json.dumps(initial), json.dumps(short_term)))
        return ident

    def read(self, ident):
        if not ident.startswith('lab-') or not self.path.exists():
            raise ValueError('Only an existing separate Lab test character is allowed')
        with self._connect() as c:
            row = c.execute('SELECT * FROM lab_characters WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise ValueError('Unknown Lab character; production IDs are never accepted')
            events = [json.loads(x['event']) for x in c.execute('SELECT event FROM lab_events WHERE character_id=? ORDER BY event_id', (ident,))]
            return {'id': ident, 'initial': json.loads(row['initial']), 'short_term': json.loads(row['short_term']), 'events': events}

    def append(self, ident, events, now):
        from .persona_engine import replay_events
        # Validate a full proposed replay before any write. Transaction rechecks concurrency.
        if not ident.startswith('lab-') or not self.path.exists():
            raise ValueError('Only an existing Lab test character can receive events')
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM lab_characters WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise ValueError('Unknown Lab character')
            old = [json.loads(x['event']) for x in c.execute('SELECT event FROM lab_events WHERE character_id=?', (ident,))]
            inserted = 0
            for supplied in events:
                event = dict(supplied, user_id='persona-lab', character_id=ident)
                if event['source'] != 'simulation':
                    raise ValueError('Lab commits contain synthetic simulation events only')
                encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
                match = c.execute('SELECT fingerprint FROM lab_events WHERE character_id=? AND (event_id=? OR idempotency_key=?)',
                                  (ident, event['event_id'], event['idempotency_key'])).fetchall()
                if match:
                    if any(x['fingerprint'] != fingerprint for x in match):
                        raise ValueError('Conflicting event ID or idempotency key; nothing committed')
                    continue
                c.execute('INSERT INTO lab_events VALUES(?,?,?,?,?)',
                          (ident, event['event_id'], event['idempotency_key'], fingerprint, encoded))
                old.append(event)
                inserted += 1
            state = replay_events(old, now=now, initial=json.loads(row['initial']), short_term=json.loads(row['short_term']))
            encoded_state = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
            digest = hashlib.sha256(encoded_state.encode()).hexdigest()
            c.execute('INSERT OR IGNORE INTO lab_snapshots VALUES(?,?,?)', (ident, digest, encoded_state))
            return {'character_id': ident, 'inserted': inserted, 'state': state,
                    'storage': 'separate_synthetic_test_store', 'production_write': False}
