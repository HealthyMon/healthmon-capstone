"""Run unchanged legacy tests against a new isolated PostgreSQL database."""
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
import psycopg
from psycopg import sql
load_dotenv(ROOT/'.env')


def fingerprint(dsn):
    result={}
    with psycopg.connect(dsn) as c:
        c.execute('SET TRANSACTION READ ONLY')
        for table in ('schema_migrations','pets','sources','memories','requests','exchanges','quest_offers',
                      'reward_ledger','state_snapshots','outbox','suggestion_jobs'):
            if c.execute('SELECT to_regclass(%s)',(table,)).fetchone()[0] is None:continue
            rows=c.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} AS t ORDER BY row_to_json(t)::text').format(sql.Identifier(table))).fetchall()
            result[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    return result


def main():
    from filelock import FileLock, Timeout
    try:
        with FileLock(str(ROOT/'runtime/gpu.lock'),timeout=0):
            pass
    except Timeout:
        raise RuntimeError('Stop the Persona Lab/model server before running the unchanged GPU lock regression test') from None
    out=ROOT/'runs/character-lab'
    original=os.environ['DATABASE_URL'];name='character_lab_test_'+uuid.uuid4().hex[:12]
    before=fingerprint(original)
    admin=original.rsplit('/',1)[0]+'/postgres'
    with psycopg.connect(admin,autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    isolated=original.rsplit('/',1)[0]+'/'+name
    with psycopg.connect(isolated) as c:
        for migration in sorted((ROOT/'migrations').glob('*.sql')):
            c.execute(migration.read_text(encoding='utf-8'))
    environment=dict(os.environ,DATABASE_URL=isolated,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUTF8='1')
    with (out/'tests-full.log').open('w',encoding='utf-8') as log:
        r=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
    after=fingerprint(original)
    result={'exit_code':r.returncode,'isolated_database':name,'original_database_before':before,
            'original_database_after':after,'original_user_data_unchanged':before==after,
            'test_database_preserved':True,'model_inference':'controlled model fixtures; existing BGE is actual CPU inference'}
    (out/'regression-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    raise SystemExit(r.returncode)


if __name__=='__main__':main()
