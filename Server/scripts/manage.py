"""Cross-platform development operations. Never reads another project's .env."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]


def compose(*args, **kwargs):
    return subprocess.run(['docker', 'compose', *args], cwd=ROOT, check=True, **kwargs)


def initialize(test=False, port=8020):
    path = ROOT / '.env'
    owner_a, owner_b = 'dev-test-a', 'dev-test-b'
    token_a, token_b = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
    project = re.sub('[^a-z0-9_-]', '-', ROOT.name.lower())
    lines = {'COMPOSE_PROJECT_NAME': project, 'API_BIND': '127.0.0.1', 'API_PORT': str(port),
             'PUBLIC_BASE_URL': f'http://localhost:{port}', 'POSTGRES_PASSWORD': secrets.token_urlsafe(36), 'POSTGRES_DB': 'healthmon',
             'APP_ENV': 'test' if test else 'development', 'AI_MODE': 'disabled', 'AI_BASE_URL': '', 'AI_SERVER_TOKEN': '',
             'AI_TIMEOUT_SECONDS': '30', 'AI_CONTRACT_VERSION': 'healthmon.ai.v1', 'ALLOW_HTTP_AI': 'false',
             'DEV_TOKENS': json.dumps({token_a: owner_a, token_b: owner_b}, separators=(',', ':')),
             'AUTH_TOKEN_HASHES': '{}', 'TEST_OWNERS': json.dumps([owner_a, owner_b], separators=(',', ':')),
             'SERVER_INSTANCE_ID': str(uuid.uuid4()), 'EMBEDDING_MODEL_ID': 'BAAI/bge-m3', 'EMBEDDING_MODEL_VERSION': '1', 'WORKER_ENABLED': 'true'}
    try:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            for key, value in lines.items():
                stream.write(f'{key}={value}\n')
        if os.name != 'nt':
            path.chmod(0o600)
    except FileExistsError:
        print('Existing .env preserved; no credentials were changed.')
        return
    print('Created isolated local .env. Credentials are stored only in that file.')
    print('Next: docker compose up -d --build')


def seed():
    # Run inside the common image, where only CPU dependencies are installed.
    sys.path.insert(0, str(ROOT))
    from Server.healthmon.config import Settings
    from Server.healthmon.db import Database
    from Server.healthmon import service
    settings = Settings.from_env()
    if settings.environment == 'production':
        raise SystemExit('Development seed is disabled in production')
    db = Database(settings)
    db.ready()
    for owner in sorted(set(settings.token_hashes.values())):
        with db.connect() as c:
            old = c.execute('SELECT id FROM pets WHERE owner_id=%s LIMIT 1', (owner,)).fetchone()
            if old:
                print(json.dumps({'owner': owner, 'pet_id': old['id'], 'existing': True}))
                continue
            ident = uuid.uuid4().hex
            from psycopg.types.json import Jsonb
            from Server.healthmon.contracts import PetSettings
            timestamp = service.utcnow()
            c.execute('INSERT INTO pets(id,owner_id,settings,created_at) VALUES(%s,%s,%s,%s)', (ident, owner, Jsonb(PetSettings().model_dump()), timestamp))
            service.seed_goals(c, ident, timestamp)
            service.refresh(c, service.owned(c, owner, ident, True), timestamp, settings.ai_mode != 'disabled')
            from Server.healthmon import starters
            starters.bind_default(c,service.owned(c,owner,ident,True),timestamp,settings.ai_mode!='disabled')
        print(json.dumps({'owner': owner, 'pet_id': ident, 'existing': False}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init', 'start', 'stop', 'down', 'logs', 'test', 'seed', 'seed-in-container', 'backup', 'restore'])
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--port', type=int, default=8020)
    parser.add_argument('--file', type=Path)
    parser.add_argument('--database')
    args = parser.parse_args()
    if args.command == 'init':
        initialize(args.test, args.port)
    elif args.command == 'seed-in-container':
        seed()
    elif args.command == 'seed':
        compose('exec', '-T', 'api', 'python', 'Server/scripts/manage.py', 'seed-in-container')
    elif args.command == 'start':
        compose('up', '-d', '--build')
    elif args.command in ('stop', 'down'):
        compose(args.command)  # Never down -v: database volume remains intact.
    elif args.command == 'logs':
        compose('logs', '--tail', '100', 'api', 'migrate')
    elif args.command == 'test':
        compose('--profile', 'test', 'build', 'checks')
        compose('--profile', 'test', 'run', '--rm', 'checks')
    elif args.command == 'backup':
        selected = 'healthmon'
        for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
            if line.startswith('POSTGRES_DB='):
                selected = line.partition('=')[2].strip()
        if not re.fullmatch('[a-zA-Z0-9_]{1,63}', selected):
            raise SystemExit('POSTGRES_DB must be a plain PostgreSQL database identifier')
        target = args.file or ROOT / 'backups' / ('healthmon-' + uuid.uuid4().hex + '.dump')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            compose('exec', '-T', 'db', 'pg_dump', '-U', 'healthmon', '-d', selected, '-Fc', stdout=stream)
        print('Backup written to the explicitly selected local file.')
    elif args.command == 'restore':
        if args.file is None or not args.file.is_file():
            raise SystemExit('--file must select an existing backup')
        name = args.database or ('healthmon_restore_' + uuid.uuid4().hex[:12])
        if not re.fullmatch('healthmon_restore_[a-z0-9_]{1,40}', name):
            raise SystemExit('Restore target must be a new healthmon_restore_* database')
        # createdb fails if the name exists; never overwrite an existing database.
        compose('exec', '-T', 'db', 'createdb', '-U', 'healthmon', name)
        with args.file.open('rb') as stream:
            compose('exec', '-T', 'db', 'pg_restore', '--exit-on-error', '-U', 'healthmon', '-d', name, stdin=stream)
        print('Restored into new database: ' + name)


if __name__ == '__main__':
    main()
