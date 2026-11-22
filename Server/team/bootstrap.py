"""CPU team setup: food and pose only. No Hub, dialogue or generation imports."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.runtime/team'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(value, encoding='utf-8')
    os.replace(temporary, path)


def assets(*, clients_only=False):
    from Server.portable.downloads import lfs_assets
    lfs_assets(ROOT, 'client')
    if clients_only:
        return
    lfs_assets(ROOT, 'food')
    subprocess.run([sys.executable, '-B', str(ROOT / 'Ai/Pose/mac-exercise-counter/scripts/download_models.py')], check=True)
    verify_models()
    write(STATE / 'assets-ready.json', json.dumps({'capabilities': ['food', 'pose'], 'integrity': 'PASS'}))


def available_models():
    from Server.portable.downloads import sha256
    ready, skipped = [], {}
    for capability, directory, manifest_name in (
        ('food', ROOT / 'Ai/Vision', 'weights-manifest.json'),
        ('pose', ROOT / 'Ai/Pose/mac-exercise-counter/models', 'manifest.json')):
        try:
            for name, spec in json.loads((directory / manifest_name).read_text()).items():
                path = directory / spec.get('file', name)
                if not path.is_file() or (spec.get('size_bytes') and path.stat().st_size != spec['size_bytes']) or sha256(path) != spec['sha256']:
                    raise ValueError('missing or incomplete model: ' + path.name)
            ready.append(capability)
        except (OSError, ValueError, KeyError) as error:
            skipped[capability] = str(error)
    return dict(ready=ready, skipped=skipped)


def verify_models():
    status = available_models()
    if status['skipped']:
        raise ValueError('Model verification failed; run menu 5: ' + ', '.join(status['skipped']))


def connection(*, native=False):
    from dotenv import dotenv_values
    from Server.scripts import manage
    token_path = STATE / 'server-token'
    if native:
        # PowerShell copied ONLY the token from the existing host API config.
        if not token_path.is_file() or not token_path.read_text().strip():
            raise ValueError('Existing backend token was not prepared')
        return
    manage.initialize(test=True, port=18092)
    path = ROOT / '.env'
    current = dotenv_values(path)
    if current.get('APP_ENV') != 'test':
        raise ValueError('Team setup requires a local test backend; existing settings preserved')
    token = current.get('AI_SERVER_TOKEN') or (token_path.read_text().strip() if token_path.exists() else secrets.token_urlsafe(36))
    original = path.read_text(encoding='utf-8-sig')
    updates = dict(AI_MODE='remote', AI_BASE_URL='http://host.docker.internal:18090',
                   AI_SERVER_TOKEN=token, AI_TIMEOUT_SECONDS='300', ALLOW_HTTP_AI='true')
    lines = []
    for line in original.splitlines():
        key = line.partition('=')[0]
        lines.append(key + '=' + updates.pop(key) if key in updates else line)
    lines.extend(key + '=' + value for key, value in updates.items())
    updated = '\n'.join(lines) + '\n'
    if updated != original:
        write(STATE / ('before-setup-' + str(time.time_ns()) + '.env'), original)
        write(path, updated)
    write(token_path, token)
    if os.name != 'nt':
        token_path.chmod(0o600)
    print('Local connection prepared. No address or token entry needed.')


def food_app(config_path=None, *, runner=None):
    from Server.local_probe.vision_gateway import create_app
    from fastapi import HTTPException, Header
    import hmac
    if config_path is None:
        config_path = STATE / 'vision/private.json'
        write(config_path, json.dumps(dict(environment='test', vision_enabled=True,
              server_token=(STATE / 'server-token').read_text().strip(),
              vision_python='/opt/vision/bin/python', vision_assets=str(ROOT / 'Ai/Vision'), timeout_seconds=300)))
    app = create_app(config_path, runner=runner)
    @app.get('/health/services')
    def services(authorization: str = Header(default='')):
        token = json.loads(Path(config_path).read_text(encoding='utf-8'))['server_token']
        if not hmac.compare_digest(authorization, 'Bearer ' + token):
            raise HTTPException(401, 'Server authentication required')
        return {'status': 'ready', 'services': {
            'chat': {'available': False, 'status': 'not_installed'},
            'vision': {'available': True, 'status': 'ready'},
            'evolution': {'available': False, 'status': 'not_installed'}}}
    @app.api_route('/v1/{capability:path}', methods=['GET', 'POST', 'PUT'])
    def unavailable(capability: str):
        # Fail immediately, without loading models, queuing generation or fake results.
        raise HTTPException(501, {'code': 'capability_not_installed', 'enabled': ['food', 'pose']})
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['assets', 'client-assets', 'verify', 'available', 'connection', 'food'])
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    if args.action in ('assets', 'client-assets'):
        assets(clients_only=args.action == 'client-assets')
    elif args.action == 'verify':
        verify_models()
    elif args.action == 'available':
        print(json.dumps(available_models()))
    elif args.action == 'connection':
        connection(native=args.native)
    else:
        import uvicorn
        uvicorn.run(food_app(), host='0.0.0.0', port=18090, access_log=False)

if __name__ == '__main__':
    main()
