"""Isolated AI job journal; never connects to a game/user database."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager
import uuid

TERMINAL={'succeeded','failed','unsupported'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'jobs.sqlite3'
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,pet_id TEXT NOT NULL,stage INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,input TEXT NOT NULL,parent TEXT,status TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'queued',result TEXT,error TEXT,lease_until REAL,lease_token TEXT,
                created_at REAL NOT NULL,updated_at REAL NOT NULL,UNIQUE(pet_id,stage))''')
            c.execute('CREATE TABLE IF NOT EXISTS parents(pet_id TEXT PRIMARY KEY,manifest TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally: c.close()

    @staticmethod
    def decode(row):
        if row is None: raise KeyError('Job not found')
        value=dict(row)
        for key in ('input','parent','result'):
            if value[key] is not None: value[key]=json.loads(value[key])
        return value

    def get(self,job_id):
        with self.connect() as c:
            return self.decode(c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())

    def bind_parent(self,pet,manifest):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT manifest FROM parents WHERE pet_id=?',(pet,)).fetchone()
            if old and old['manifest']!=canonical(manifest):
                raise Conflict('Existing parent binding is immutable; use an isolated test pet')
            c.execute('INSERT OR IGNORE INTO parents VALUES(?,?)',(pet,canonical(manifest)))

    def parent(self,pet):
        with self.connect() as c:
            row=c.execute('SELECT manifest FROM parents WHERE pet_id=?',(pet,)).fetchone()
        return json.loads(row['manifest']) if row else None

    def submit(self,job_id,body,supported_stages):
        now=time.time();stage=body['input']['stage'];pet=body['pet_id']
        digest=fingerprint(body)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if old:
                if old['fingerprint']!=digest: raise Conflict('Stable job ID content conflict')
                return self.decode(old)
            other=c.execute('SELECT id FROM jobs WHERE pet_id=? AND stage=?',(pet,stage)).fetchone()
            if other: raise Conflict('This pet/stage already has another stable job')
            parent_row=c.execute('SELECT manifest FROM parents WHERE pet_id=?',(pet,)).fetchone()
            parent=json.loads(parent_row['manifest']) if parent_row else None
            incoming=body['input'].get('parent_asset')
            if incoming is not None:
                from .contracts import validate_parent_asset
                image=validate_parent_asset(incoming)
                if stage!=1 or body['input']['state']['published_model_stage']!=0:raise ValueError('Starter binding requires stage0 to1')
                if parent is None:
                    relative=f"parents/{pet}/{incoming['image_sha256']}.png"
                    path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists():
                        if hashlib.sha256(path.read_bytes()).hexdigest()!=incoming['image_sha256']:raise Conflict('Starter image collision')
                    else:
                        with path.open('xb') as stream:stream.write(image)
                    parent={k:incoming[k] for k in ('stage','revision','species','species_contract','image_sha256','model_sha256','source_kind')}
                    parent['image_relative']=relative
                    c.execute('INSERT INTO parents(pet_id,manifest) VALUES(?,?)',(pet,canonical(parent)))
                elif any(parent[k]!=incoming[k] for k in ('stage','species','image_sha256','model_sha256')):
                    raise Conflict('Server starter differs from the immutable bound parent')
            reason=None
            if parent is None: reason='parent_not_provisioned'
            elif stage not in supported_stages: reason='stage_not_validated_by_this_adapter'
            elif parent['stage'] != body['input']['state']['published_model_stage']: reason='parent_stage_mismatch'
            elif parent['stage'] != stage-1: reason='stage_skip_not_supported'
            status='unsupported' if reason else 'queued'
            c.execute('INSERT INTO jobs(id,pet_id,stage,fingerprint,input,parent,status,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (job_id,pet,stage,digest,canonical(body),canonical(parent) if parent else None,status,reason,now,now))
            return self.decode(c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())

    def claim(self):
        now=time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM jobs WHERE status IN ('queued','running') AND (lease_until IS NULL OR lease_until<?) ORDER BY created_at,id LIMIT 1",(now,)).fetchone()
            if row is None: return None
            token=uuid.uuid4().hex
            c.execute("UPDATE jobs SET status='running',lease_until=?,lease_token=?,updated_at=? WHERE id=?",(now+90,token,now,row['id']))
            result=self.decode(row);result.update(status='running',lease_token=token)
            return result

    def update(self,job_id,*,expected_lease=None,**values):
        allowed={'status','phase','result','error','lease_until'}
        if not set(values)<=allowed: raise ValueError('Unknown job fields')
        values=dict(values,updated_at=time.time())
        if 'result' in values: values['result']=canonical(values['result'])
        with self.connect() as c:
            where=' WHERE id=?'+(' AND lease_token=?' if expected_lease else '')
            parameters=(*values.values(),job_id,*((expected_lease,) if expected_lease else ()))
            result=c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+where,parameters)
            if result.rowcount != 1: raise Conflict('Worker lease was superseded')
        return self.get(job_id)

    def publish(self,job_id,result,new_parent,*,expected_lease=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            job=self.decode(c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())
            if job['status']=='succeeded': return job
            if expected_lease and job['lease_token']!=expected_lease: raise Conflict('Worker lease was superseded')
            current=c.execute('SELECT manifest FROM parents WHERE pet_id=?',(job['pet_id'],)).fetchone()
            if not current or canonical(json.loads(current['manifest']))!=canonical(job['parent']):
                raise Conflict('Stale parent cannot replace a newer model')
            c.execute("UPDATE jobs SET status='succeeded',phase='complete',result=?,error=NULL,lease_until=NULL,updated_at=? WHERE id=?",(canonical(result),time.time(),job_id))
            c.execute('UPDATE parents SET manifest=? WHERE pet_id=?',(canonical(new_parent),job['pet_id']))
        return self.get(job_id)
