import os,time
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')

@contextmanager
def connect():
    c=None
    for attempt in range(3):
        try:
            c=psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,connect_timeout=5)
            break
        except psycopg.OperationalError:
            if attempt==2:raise
            time.sleep(0.1*(attempt+1))
    # Retry establishment only. Never replay a partially committed transaction blindly.
    with c:
        c.execute("SET statement_timeout='10s'")
        yield c

def owned(c,user,pet,lock=False):
    row=c.execute('SELECT * FROM pets WHERE id=%s AND owner_id=%s'+(' FOR UPDATE' if lock else ''),(pet,user)).fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404,'Pet not found')
    return row

def sources(c,pet):
    return c.execute('SELECT * FROM sources WHERE pet_id=%s AND valid ORDER BY occurred_at,id',(pet,)).fetchall()

def bump(c,pet):
    return c.execute('UPDATE pets SET version=version+1 WHERE id=%s RETURNING version',(pet,)).fetchone()['version']

def snapshot(c,pet,state,version):
    c.execute('INSERT INTO state_snapshots(pet_id,version,state) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(pet,version,Jsonb(state)))
