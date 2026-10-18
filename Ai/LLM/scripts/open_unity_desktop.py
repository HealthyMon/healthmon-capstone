"""Launch the existing team Unity scene with credentials kept in process memory."""
import argparse
import hashlib
import ssl
import json
import os
import subprocess
import re
from urllib.request import Request, urlopen
from pathlib import Path

from dotenv import dotenv_values


def resolve_pet(runtime, token, preferred=''):
    """Select one owned pet with a published model for all three clients."""
    request = Request('http://127.0.0.1:8000/pets',
                      headers={'Authorization': 'Bearer ' + token})
    with urlopen(request, timeout=10) as response:
        pets = json.load(response).get('pets', [])
    candidates = [item['pet_id'] for item in pets if isinstance(item.get('pet_id'), str)]
    if preferred:
        if preferred not in candidates:
            raise ValueError('The selected pet does not belong to the configured local account.')
        candidates = [preferred]
    model_root = runtime / 'healthmon-generation3d/Ai/Generation3D/outputs/unity_service/pets'
    for pet_id in candidates:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', pet_id):
            continue
        current = model_root / pet_id / 'current.json'
        if current.is_file() and json.loads(current.read_text(encoding='utf-8')).get('pet_id') == pet_id:
            return pet_id
    raise ValueError('No owned pet has an initialized 3D starter. Publish its stage-0 model before opening Unity.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path(r'E:\qwen-llm'))
    parser.add_argument('--editor', type=Path)
    parser.add_argument('--pet', default='')
    args = parser.parse_args()
    editor = args.editor or args.runtime_root / 'runtime/Unity6000.4.6f1/Editor/Unity.exe'
    project = Path(__file__).resolve().parents[3] / 'Client/HealthMonUnity'
    if not editor.is_file():
        parser.error(f'Unity Editor missing: {editor}')
    credentials = dotenv_values(args.runtime_root / '.env')
    tokens = json.loads(credentials.get('DEV_TOKENS', '{}'))
    if not tokens:
        parser.error('No local user tokens found in the existing runtime .env')
    token = next(iter(tokens))
    try:
        pet_id = resolve_pet(args.runtime_root, token, args.pet)
    except (OSError, ValueError) as error:
        parser.error('Cannot select a shared pet: ' + str(error))
    env = os.environ.copy()
    (project / 'Logs').mkdir(exist_ok=True)
    env['HEALTHMON_SERVER_URL'] = 'http://127.0.0.1:8000'
    env['HEALTHMON_USER_TOKEN'] = token
    env['HEALTHMON_PET_ID'] = pet_id
    env['HEALTHMON_EVOLUTION_PET'] = pet_id
    # Keep the development certificate pin out of the shared Unity asset.
    certificate = args.runtime_root / 'healthmon-generation3d/Ai/Generation3D/outputs/unity_service/tls/localhost.crt'
    if certificate.is_file():
        der = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding='ascii'))
        env['HEALTHMON_EVOLUTION_CERT_SHA256'] = hashlib.sha256(der).hexdigest()
    evolution_token = credentials.get('HEALTHMON_EVOLUTION_TOKEN')
    if evolution_token:
        env['HEALTHMON_EVOLUTION_TOKEN'] = evolution_token

    process = subprocess.Popen([str(editor), '-projectPath', str(project),
                                '-executeMethod', 'OpenDesktopScene.Open',
                                '-logFile', str(project / 'Logs/desktop-llm-editor.log')], env=env)
    print(f'Unity started, PID={process.pid}. Token passed in memory only. Shared pet={pet_id}. Press Play.')


if __name__ == '__main__':
    main()
