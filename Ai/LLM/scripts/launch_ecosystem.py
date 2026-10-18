"""Start the shared local API, wait for readiness, then open the team Unity scene."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path(r'E:\qwen-llm'))
    parser.add_argument('--pet', default='')
    parser.add_argument('--api-only', action='store_true')
    args = parser.parse_args()
    scripts = Path(__file__).resolve().parent
    runtime = args.runtime_root.resolve()
    if not args.api_only:
        bridge = scripts.parents[2] / 'Ai/Generation3D/scripts/launch_unity_bridge.py'
        subprocess.run([sys.executable, str(bridge), '--runtime-root', str(runtime / 'healthmon-generation3d/Ai/Generation3D')], check=True)
    tokens = json.loads(dotenv_values(runtime / '.env').get('DEV_TOKENS', '{}'))
    if not tokens:
        parser.error('No local user account is configured in runtime .env.')
    token = next(iter(tokens))
    def health():
        with urlopen('http://127.0.0.1:8000/health', timeout=3) as response:
            result = json.load(response)
        request = Request('http://127.0.0.1:8000/ecosystem/health', headers={'Authorization': 'Bearer ' + token})
        with urlopen(request, timeout=3) as response:
            ecosystem = json.load(response)
        expected_adapter = runtime / json.loads((scripts.parent / 'config/serving.json').read_text(encoding='utf-8'))['adapter_path']
        if (not result.get('ready') or result.get('model_lifecycle') != 'conversation_session'
                or Path(result.get('adapter') or '').resolve() != expected_adapter.resolve()
                or ecosystem.get('food_api') != 'healthmon.food.v1' or not ecosystem['vision']['configured']):
            raise ValueError('The API is not ready for this ecosystem.')
    try:
        health()
    except (URLError, ValueError):
        logs = runtime / 'runs/ecosystem'
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / 'api.stdout.log').open('a', encoding='utf-8') as out, (logs / 'api.stderr.log').open('a', encoding='utf-8') as err:
            process = subprocess.Popen([sys.executable, '-u', str(scripts / 'start_desktop.py'), '--runtime-root', str(runtime)],
                                       stdout=out, stderr=err, env={**os.environ, 'PYTHONUTF8': '1'},
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        print('Preparing Qwen, database and Vision API. Logs: ' + str(logs), flush=True)
        deadline = time.monotonic() + 240
        while True:
            if process.poll() is not None:
                parser.error('API launcher stopped. Inspect ' + str(logs / 'api.stderr.log'))
            try:
                health()
                break
            except (URLError, ValueError):
                if time.monotonic() > deadline:
                    parser.error('API readiness timed out. Inspect the logs before restarting.')
                time.sleep(1)
    if args.api_only:
        print('Shared API ready on http://127.0.0.1:8000')
        return
    command = [sys.executable, str(scripts / 'open_unity_desktop.py'), '--runtime-root', str(runtime)]
    if args.pet:
        command.extend(['--pet', args.pet])
    subprocess.run(command, check=True)
    print('Press Play. Food analysis, confirmed meals and dialogue share the same pet and API.')


if __name__ == '__main__':
    main()
