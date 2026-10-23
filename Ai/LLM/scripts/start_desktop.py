"""Serve existing desktop resources without copying credentials or model weights."""
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path(r'E:\qwen-llm'))
    args = parser.parse_args()
    runtime = args.runtime_root.resolve()
    llm = Path(__file__).resolve().parents[1]
    vision_python = llm.parent / 'Vision/.venv/Scripts/python.exe'
    if not vision_python.is_file():
        parser.error('Vision environment missing. Run Ai/LLM/scripts/setup_vision.py first.')
    adapter = runtime / json.loads((llm / 'config/serving.json').read_text(encoding='utf-8'))['adapter_path']
    try:
        with urlopen('http://127.0.0.1:8000/health', timeout=3) as response:
            health = json.load(response)
    except (URLError, TimeoutError):
        health = None
    if health is not None:
        if (not health.get('ready') or health.get('model_lifecycle') != 'conversation_session' or health.get('backend') != 'qwen3.5-9b-bf16-lora'
                or Path(health.get('adapter', '')).resolve() != adapter.resolve()):
            parser.error('Port 8000 has a different server. Inspect it before starting another GPU process.')
        from dotenv import dotenv_values
        from urllib.request import Request
        tokens = json.loads(dotenv_values(runtime / '.env').get('DEV_TOKENS', '{}'))
        try:
            request = Request('http://127.0.0.1:8000/ecosystem/health', headers={'Authorization': 'Bearer ' + next(iter(tokens))})
            with urlopen(request, timeout=3) as response:
                ecosystem = json.load(response)
            if ecosystem.get('food_api') != 'healthmon.food.v1':
                raise ValueError('Unexpected ecosystem API')
        except (URLError, ValueError, StopIteration):
            parser.error('The running API lacks this Vision integration. Stop that API and restart this launcher.')
        print('The Unity + Vision + Qwen ecosystem is already running at http://127.0.0.1:8000.')
        return
    python = runtime / '.venv/Scripts/python.exe'
    env_file = runtime / '.env'
    model = runtime / 'models/qwen3.5-9b'
    embedding = runtime / 'models/bge-m3'
    pgctl = runtime / 'runtime/pgsql/bin/pg_ctl.exe'
    pgdata = runtime / 'runtime/pgdata'
    for path in (python, env_file, model / 'config.json', embedding / 'config.json',
                 adapter / 'adapter_config.json', pgctl, pgdata / 'PG_VERSION'):
        if not path.is_file():
            parser.error(f'Required existing resource missing: {path}')
    (runtime / 'runs').mkdir(exist_ok=True)
    if subprocess.run([str(pgctl), '-D', str(pgdata), 'status'], capture_output=True).returncode:
        subprocess.run([str(pgctl), '-D', str(pgdata), '-l', str(runtime / 'runs/postgres.log'),
                        '-o', '-h 127.0.0.1 -p 55432', '-w', 'start'], check=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    result = subprocess.run([str(python), '-u', 'scripts/serve.py', '--env-file', str(env_file),
                             '--model-path', str(model), '--embedding-path', str(embedding),
                             '--adapter', str(adapter)], cwd=llm, env=env)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
