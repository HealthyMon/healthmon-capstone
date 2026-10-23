"""Actual HTTP/Compose persistence and restore acceptance test on test-only data."""
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
from dotenv import dotenv_values


def compose(*args, **kwargs):
    return subprocess.run(['docker', 'compose', *args], cwd=ROOT, check=True, **kwargs)


def main():
    env = dotenv_values(ROOT / '.env')
    database_name = env.get('POSTGRES_DB', 'healthmon')
    if env.get('APP_ENV') != 'test':
        raise SystemExit('Smoke acceptance requires an explicitly isolated APP_ENV=test database')
    owners = json.loads(env['TEST_OWNERS'])
    token = next((token for token, owner in json.loads(env['DEV_TOKENS']).items() if owner in owners), None)
    if not token:
        raise SystemExit('No test owner provisioned')
    origin = 'http://127.0.0.1:' + str(int(env['API_PORT']))
    def call(path, payload=None):
        request = urllib.request.Request(origin + path, data=json.dumps(payload).encode() if payload is not None else None,
                                         headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    def wait_ready():
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if call('/health/ready')['ready']:
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.5)
        raise RuntimeError('API failed to become ready')
    wait_ready()
    info = call('/server-info')
    pet = call('/pets', {'name': '합성 Compose 검증'})['pet_id']
    assert call('/pets/' + pet + '/state')['lower_body'] == 50
    call('/pets/' + pet + '/goals', {'exercise_type': 'running', 'target': 30, 'unit': 'minutes', 'body_part': 'lower'})
    instant = datetime.datetime.now(datetime.timezone.utc).isoformat()
    event = {'event_id': 'compose-synthetic-' + uuid.uuid4().hex, 'revision': 1, 'occurred_at': instant, 'started_at': instant,
             'workout_type': 'running', 'actual': 30, 'unit': 'minutes', 'target': 30, 'source': 'user', 'synthetic': True}
    # The quantity is an explicit synthetic fixture; no real 30-minute workout is claimed.
    applied = call('/pets/' + pet + '/workouts', event)
    assert applied['state']['lower_body'] == 52
    replayed = call('/pets/' + pet + '/workouts', event)
    assert replayed['duplicate'] and replayed['state']['lower_body'] == 52
    assert applied['state']['total_exp'] == replayed['state']['total_exp']
    compose('restart', 'api', 'db')
    wait_ready()
    assert call('/server-info')['server_instance_id'] == info['server_instance_id']
    assert call('/pets/' + pet + '/state')['lower_body'] == 52
    assert any(row['event_id'] == event['event_id'] for row in call('/pets/' + pet + '/workouts')['records'])
    compose('exec', '-T', 'api', 'python', '-c', "import importlib.util; assert all(importlib.util.find_spec(m) is None for m in ['torch','transformers','diffusers','bpy']); print('CPU dependency boundary PASS')")
    backup = ROOT / '.runtime' / ('compose-smoke-' + uuid.uuid4().hex + '.dump')
    backup.parent.mkdir(exist_ok=True)
    with backup.open('xb') as stream:
        compose('exec', '-T', 'db', 'pg_dump', '-U', 'healthmon', '-d', database_name, '-Fc', stdout=stream)
    restored = 'healthmon_restore_' + uuid.uuid4().hex[:12]
    compose('exec', '-T', 'db', 'createdb', '-U', 'healthmon', restored)
    with backup.open('rb') as stream:
        compose('exec', '-T', 'db', 'pg_restore', '--exit-on-error', '-U', 'healthmon', '-d', restored, stdin=stream)
    if len(pet) != 32 or any(c not in 'abcdef0123456789' for c in pet):
        raise RuntimeError('Unexpected pet identifier')
    result = compose('exec', '-T', 'db', 'psql', '-U', 'healthmon', '-d', restored, '-At', '-c',
                     "SELECT state->>'lower_body' FROM game_states WHERE pet_id='" + pet + "'", capture_output=True, text=True)
    assert result.stdout.strip() == '52'
    report = {'result': 'PASS', 'compose_startup': True, 'cpu_no_model_libraries': True, 'postgres_persistence': True,
              'lower_body': [50, 52, 52, 52], 'duplicate_reward_unchanged': True, 'server_instance_preserved': True,
              'new_database_backup_restore': True, 'synthetic_fixture': True, 'real_watch': False, 'gpu_inference': False}
    output = ROOT / 'Docs/verification/compose-smoke.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
