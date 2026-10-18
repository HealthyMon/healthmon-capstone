"""Extends LabStore's isolated SQLite DB. Reads/dry-runs never run migrations."""
import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .character_lab_schema import ROOT, Session, canonical_json
from .character_lab_engine import execute, fresh


class Conflict(ValueError):
    pass


class CharacterLabStore:
    def __init__(self, path):
        self.path = Path(path)

    def _connect(self, write=False):
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(self.path, timeout=10)
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript((ROOT/'migrations/character_lab/001_up.sql').read_text(encoding='utf-8'))
        else:
            if not self.path.exists():
                raise ValueError('Unknown test session/store')
            c = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def create(self, state=None):
        lab = fresh(state)
        ident = 'clab-' + uuid.uuid4().hex
        with self._connect(True) as c:
            c.execute('INSERT INTO character_lab_sessions(id,namespace,state,initiative) VALUES(?,?,?,?)',
                      (ident, 'character-lab-test', json.dumps(lab), lab['state']['initiative']))
        return {'session_id': ident, 'revision': 0, 'session': lab, 'namespace': 'character-lab-test'}

    def read(self, ident):
        if not ident.startswith('clab-'):
            raise ValueError('Only Character Lab test sessions are accepted; production character IDs are forbidden')
        try:
            with self._connect() as c:
                row = c.execute('SELECT * FROM character_lab_sessions WHERE id=?', (ident,)).fetchone()
                if not row:
                    raise ValueError('Unknown test session')
                return {'session_id': ident, 'revision': row['revision'], 'session': json.loads(row['state']),
                        'namespace': row['namespace']}
        except sqlite3.OperationalError as error:
            raise ValueError('No saved Character Lab sessions yet') from error

    def run(self, ident, commands, revision):
        self.read(ident)  # fail closed before opening writable connection
        if revision is None:
            raise ValueError('expected_revision required for explicit test-session writes')
        with self._connect(True) as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM character_lab_sessions WHERE id=?', (ident,)).fetchone()
            if row['revision'] != revision:
                raise Conflict('Saved session changed; reload before committing')
            result = execute(json.loads(row['state']), commands, dry_run=False)
            new = [x for x in result['results'] if not x.get('duplicate')]
            for log in new:
                c.execute('INSERT INTO character_lab_events VALUES(?,?,?,?)',
                          (ident, log['event_id'], json.dumps(log, ensure_ascii=False), log['rule_version']))
            updated = revision + bool(new)
            c.execute('UPDATE character_lab_sessions SET state=?, initiative=?, revision=? WHERE id=?',
                      (json.dumps(result['session'], ensure_ascii=False), result['after']['initiative'], updated, ident))
            result.update(session_id=ident, revision=updated, target=ident, namespace='character-lab-test')
            return result

    def save_review(self, draft, status, correction, note, revision=None):
        ident = draft['id']
        timestamp = datetime.now(timezone.utc).isoformat()
        encoded = canonical_json(draft)
        with self._connect(True) as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM character_lab_reviews WHERE id=?', (ident,)).fetchone()
            if old and (canonical_json(json.loads(old['draft'])) != encoded or revision != old['revision']):
                raise Conflict('Review changed or raw draft modified; reload before reviewing')
            new_revision = old['revision']+1 if old else 0
            c.execute('''INSERT INTO character_lab_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(id) DO UPDATE SET status=excluded.status, correction=excluded.correction,
                         reviewer_note=excluded.reviewer_note, reviewed_at=excluded.reviewed_at, revision=excluded.revision''',
                      (ident, 'character-lab-test', draft['kind'], status, encoded,
                       json.dumps(correction, ensure_ascii=False) if correction is not None else None,
                       note, draft['created_at'], timestamp if status != 'pending' else None,
                       draft['model_identifier'], draft['prompt_version'], new_revision))
        return {'id': ident, 'status': status, 'revision': new_revision, 'namespace': 'character-lab-test'}

    def reviews(self):
        if not self.path.exists():
            return []
        try:
            with self._connect() as c:
                return [{**dict(row), 'draft': json.loads(row['draft']),
                         'correction': json.loads(row['correction']) if row['correction'] else None}
                        for row in c.execute('SELECT * FROM character_lab_reviews ORDER BY created_at,id')]
        except sqlite3.OperationalError:
            return []

    def export(self, kind):
        rows = []
        for r in self.reviews():
            d = r['draft']
            # Dummies, invalid analysis and server fallback speech cannot become training targets.
            if (r['kind'] != kind or r['status'] not in ('approved', 'corrected') or d['output_origin'] == 'dummy'
                    or r['status'] == 'approved' and d['output_origin'] in ('fallback', 'invalid')):
                continue
            target = r['correction'] if r['status'] == 'corrected' else d['prediction']
            common = {'sample_id': r['id'], 'reviewer_status': r['status'], 'model_identifier': d['model_identifier'],
                      'prompt_version': d['prompt_version'], 'rule_version': d['rule_version'], 'synthetic': True,
                      'reviewer_note': r['reviewer_note'], 'created_at': r['created_at'], 'reviewed_at': r['reviewed_at']}
            if kind == 'analyzer':
                rows.append({'text': d['text'], 'label': target, 'prompt': d['prompt'], **common})
            else:
                s = d['state']
                contract = d.get('response_contract')
                if contract is None:
                    from .contracts import ModelOutput
                    for attempt in reversed(d['raw_model_output']):
                        try:
                            contract = ModelOutput.model_validate_json(attempt['raw']).model_dump()
                            break
                        except (ValueError, KeyError):
                            continue
                    if contract is None:
                        contract = ModelOutput(speech=target, emotion='neutral', animation='idle',
                                               action={'type': 'none', 'target_id': None}, memory_ids=[]).model_dump()
                contract = dict(contract, speech=target)
                rows.append({'user': d['text'], 'state': {**s, 'affinity': s['affection']}, 'memory': d['memory'],
                             'quest_context': d['quest_context'], 'response': target,
                             'response_contract': contract, 'prompt': d['prompt'], **common})
        return ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows)
