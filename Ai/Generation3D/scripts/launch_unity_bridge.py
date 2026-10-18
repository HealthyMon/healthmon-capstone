"""Run the evolution bridge from this checkout; keep existing heavyweight runtime data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import ssl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path('E:/qwen-llm/healthmon-generation3d/Ai/Generation3D'))
    parser.add_argument('--gpu-lock', type=Path, default=Path(__file__).resolve().parents[2] / 'LLM/runtime/gpu.lock', help='Shared host GPU lock for this repository')
    args = parser.parse_args()
    runtime = args.runtime_root.resolve()
    source = Path(__file__).resolve().parents[1] / 'runtime/unity/service.py'
    logs = runtime / 'outputs/unity_service'
    tls = logs / 'tls'
    if not (tls / 'localhost.crt').is_file() or not (tls / 'localhost.key').is_file():
        parser.error('Existing local TLS certificate is missing; run the documented TLS setup.')
    context = ssl.create_default_context(cafile=str(tls / 'localhost.crt'))
    try:
        with urllib.request.urlopen('https://127.0.0.1:8010/health', context=context, timeout=3) as response:
            status = json.load(response)
        if status.get('worker_alive'):
            print('Evolution bridge already running on https://127.0.0.1:8010')
            return
    except (OSError, ValueError):
        pass
    command = [sys.executable, '-u', str(source), '--runtime-root', str(runtime),
        '--ssl-certfile', str(tls / 'localhost.crt'), '--ssl-keyfile', str(tls / 'localhost.key'),
        '--delivery-quality', 'original']
    env = os.environ.copy()
    if args.gpu_lock is not None:
        env['HEALTHMON_GPU_LOCK'] = str(args.gpu_lock.resolve())
    with (logs / 'service.stdout.log').open('a', encoding='utf-8') as out, (logs / 'service.stderr.log').open('a', encoding='utf-8') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (logs / 'service-process.json').write_text(json.dumps({'pid': process.pid, 'source': str(source)}))
    print('Evolution bridge started from the ai/3d checkout, PID=' + str(process.pid))


if __name__ == '__main__':
    main()
