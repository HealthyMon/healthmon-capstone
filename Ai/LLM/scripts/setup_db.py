import json, secrets, subprocess, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PG=ROOT/'runtime/pgsql/bin'
env_path=ROOT/'.env'
if not env_path.exists():
    password=secrets.token_hex(24)
    tokens={secrets.token_urlsafe(32):'local-user-a',secrets.token_urlsafe(32):'local-user-b'}
    env_path.write_text(f'DATABASE_URL=postgresql://healthmon:{password}@127.0.0.1:55432/healthmon\n'
        f'DEV_TOKENS={json.dumps(tokens)}\nPRODUCER_TOKEN={secrets.token_urlsafe(32)}\n'
        'MODEL_BACKEND=qwen\nMODEL_PATH=models/qwen3.5-9b\nEMBEDDING_PATH=models/bge-m3\n',encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(env_path)
from urllib.parse import urlparse
dsn=os.environ['DATABASE_URL']; parts=urlparse(dsn)
data=ROOT/'runtime/pgdata'
if not (data/'PG_VERSION').exists():
    pwfile=ROOT/'runtime/.pg-init-password'
    pwfile.write_text(parts.password)
    try:
        subprocess.run([str(PG/'initdb.exe'),'-D',str(data),'-U','healthmon','--pwfile',str(pwfile),
                        '--auth=scram-sha-256','--encoding=UTF8','--locale=C'],check=True)
    finally: pwfile.unlink(missing_ok=True)
status=subprocess.run([str(PG/'pg_ctl.exe'),'-D',str(data),'status'],capture_output=True)
if status.returncode:
    subprocess.run([str(PG/'pg_ctl.exe'),'-D',str(data),'-l',str(ROOT/'runs/postgres.log'),
                    '-o','-h 127.0.0.1 -p 55432','-w','start'],check=True)
import psycopg
admin_dsn=dsn.rsplit('/',1)[0]+'/postgres'
with psycopg.connect(admin_dsn,autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='healthmon'").fetchone():
        c.execute('CREATE DATABASE healthmon')
with psycopg.connect(dsn) as c:
    for migration in sorted((ROOT/'migrations').glob('*.sql')):c.execute(migration.read_text())
    print(c.execute("SELECT version(), (SELECT extversion FROM pg_extension WHERE extname='vector')").fetchone())
print('DB ready: 127.0.0.1:55432/healthmon; credentials only in .env')
