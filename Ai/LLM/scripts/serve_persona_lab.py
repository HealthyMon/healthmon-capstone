"""Windows/local-only Persona Lab. No legacy DB startup or migrations."""
import argparse
import json
import os
import socket
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class LocalHealthOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def already_running(port):
    """Check the local listener before importing or loading a GPU model."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass
    except ConnectionRefusedError:
        return False
    except OSError:
        # Windows can time out instead of refusing an unused loopback port.
        # Confirm it is free with an exclusive bind, without starting a listener.
        with socket.socket() as probe:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                pass
            else:
                return False

    url = f'http://127.0.0.1:{port}'
    try:
        # Local health checks must not pass through an environment HTTP proxy.
        with build_opener(ProxyHandler({}), LocalHealthOnly()).open(url + '/api/health', timeout=3) as response:
            health = json.loads(response.read(65536))
        is_lab = (isinstance(health, dict) and health.get('status') == 'ok'
                  and health.get('development_only') is True
                  and isinstance(health.get('baseline'), str)
                  and str(health.get('storage', '')).startswith('separate synthetic test store'))
    except (OSError, URLError, HTTPException, ValueError):
        is_lab = False
    if not is_lab:
        raise SystemExit(f'포트 {port}가 이미 사용 중입니다. 기존 프로그램은 그대로 두고 시작을 중단했습니다.')
    print(f'Persona Lab이 이미 실행 중입니다. 새 서버를 시작하지 않습니다.\n'
          f'브라우저에서 접속하세요: {url}/\n'
          f'종료 명령: .\\.venv\\Scripts\\python.exe scripts\\stop_persona_lab.py', flush=True)
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--warmup', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if any(os.getenv(key, '').lower() in ('production', 'prod') for key in ('APP_ENV', 'ENVIRONMENT', 'NODE_ENV')):
        raise SystemExit('Persona Lab cannot run in production')
    if already_running(args.port):
        return
    os.environ['APP_ENV'] = 'development'
    os.environ['PERSONA_LAB_ENABLED'] = '1'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from src.persona_lab import app
    if args.warmup:
        try:
            app.state.runtime._load()
        except RuntimeError as error:
            if str(error) != 'Another Healthmon process is using the GPU':
                raise
            raise SystemExit('다른 Healthmon 프로세스가 GPU를 사용 중입니다.\n'
                             '이미 실행한 서버를 이용하거나, 해당 서버를 종료한 뒤 다시 실행하세요.\n'
                             '이 프로젝트의 Persona Lab 종료 명령: '
                             '.\\.venv\\Scripts\\python.exe scripts\\stop_persona_lab.py') from None
    folder = ROOT / 'runs/persona-lab'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'server.pid').write_text(str(os.getpid()))
    print(f'Persona Lab http://127.0.0.1:{args.port} — local synthetic test state only', flush=True)
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
