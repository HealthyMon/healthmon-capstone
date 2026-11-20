"""Start the existing desktop installation without replacing its database or account."""
import argparse
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime'


def resolve(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load_profile(path):
    path = resolve(path)
    if not path.is_relative_to(RUNTIME):
        raise ValueError('The native runtime profile must be inside this project .runtime')
    profile = json.loads(path.read_text(encoding='utf-8-sig'))
    for key in ('python', 'pg_ctl', 'pg_data', 'api_env', 'session', 'ai_config', 'evolution_config'):
        profile[key] = resolve(profile[key])
        if not profile[key].exists():
            raise ValueError('Missing existing installation prerequisite: ' + key)
    environment = json.loads(profile['api_env'].read_text(encoding='utf-8-sig'))
    if environment.get('APP_ENV') != 'test':
        raise ValueError('This desktop launcher requires the existing test installation')
    profile.update(path=path, environment=environment)
    return profile


def request(base, path, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers), timeout=5) as response:
        return json.load(response)


def same_server(profile):
    try:
        info = request(profile['base_url'], '/server-info')
    except OSError:
        return False
    if info['server_instance_id'] != profile['environment']['SERVER_INSTANCE_ID']:
        raise RuntimeError('This API port belongs to a different server; it was left unchanged')
    return True


def spawn(command, name):
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / (name + '.stdout.log')).open('a', encoding='utf-8') as out, (RUNTIME / (name + '.stderr.log')).open('a', encoding='utf-8') as err:
        return subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=err,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def ensure_postgres(profile):
    command = [str(profile['pg_ctl']), '-D', str(profile['pg_data'])]
    # pg_ctl validates the existing cluster's PID. Never run initdb or remove files.
    if subprocess.run(command + ['status'], capture_output=True).returncode == 0:
        return
    print('Starting the original PostgreSQL database...', flush=True)
    subprocess.run(command + ['-l', str(RUNTIME / 'native-postgres.log'), '-o',
                             '-h 127.0.0.1 -p ' + str(profile['pg_port']), '-w', '-t', '30', 'start'], check=True)


def ensure_ai(profile):
    config_path = profile['ai_config']
    values = json.loads(config_path.read_text(encoding='utf-8-sig'))
    changed = resolve(values['evolution_config']) != profile['evolution_config']
    status_path = RUNTIME / 'local-services-status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    if changed:
        if status.get('phase') == 'generating_3d' and time.time() - status.get('updated_at', 0) < 15:
            raise RuntimeError('An existing generation is active; finish it before switching its journal')
        if time.time() - status.get('updated_at', 0) < 15 and status.get('phase') not in ('stopped', 'failed'):
            (RUNTIME / 'local-services.stop').touch()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                current = json.loads(status_path.read_text())
                if current.get('phase') in ('stopped', 'failed'):
                    break
                time.sleep(1)
            else:
                raise RuntimeError('The existing AI services have not finished stopping')
        backup = config_path.with_name('before-native-runtime-' + str(time.time_ns()) + '.json')
        backup.write_bytes(config_path.read_bytes())
        values['evolution_config'] = str(profile['evolution_config'])
        config_path.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')
    llm = json.loads(resolve(values['llm_config']).read_text(encoding='utf-8-sig'))
    if llm.get('server_token') != profile['environment'].get('AI_SERVER_TOKEN'):
        raise RuntimeError('Existing API and AI credentials differ; neither was changed')
    command = [str(resolve(values['python'])), '-B', '-m', 'Server.local_probe.local_services', 'run', '--config', str(config_path)]
    active = time.time() - status.get('updated_at', 0) < 15 and status.get('phase') not in ('stopped', 'failed')
    launched_at = 0
    process = None
    if not active or changed:
        launched_at = time.time()
        process = spawn(command, 'native-ai-services')
    print('Waiting for the original dialogue, Vision and evolution services...', flush=True)
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None and process.returncode != 0:
            raise RuntimeError('AI process failed; inspect .runtime/native-ai-services.stderr.log')
        if status_path.exists():
            current = json.loads(status_path.read_text())
            fresh = time.time() - current.get('updated_at', 0) < 15 and current.get('updated_at', 0) >= launched_at
            if fresh and current.get('phase') in ('ready', 'generating_3d'):
                return
            if fresh and current.get('phase') == 'failed':
                raise RuntimeError('Existing AI startup failed; inspect .runtime/local-*.stderr.log')
        time.sleep(2)
    raise RuntimeError('Existing AI services did not become ready')


def write_guide(profile, open_browser):
    session = json.loads(profile['session'].read_text(encoding='utf-8-sig'))
    token = session['bearer_token']
    base = profile['base_url']
    identity = request(base, '/identity', token)
    pets = request(base, '/pets', token)['pets']
    selected = profile.get('pet_id')
    if selected and not any(pet['pet_id'] == selected for pet in pets):
        raise RuntimeError('The original selected pet is missing; no replacement was created')
    selected = selected or (pets[-1]['pet_id'] if pets else '')
    def field(label, value):
        return '<label>' + label + '<input readonly onclick="this.select()" value="' + html.escape(value, quote=True) + '"></label>'
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>기존 HealthMon 서버</title>
<style>body{max-width:780px;margin:40px auto;font:18px/1.7 system-ui;padding:20px;background:#edf5fa;color:#193147}input{display:block;width:100%;padding:12px;box-sizing:border-box;font:16px monospace;margin-bottom:20px}h1{color:#087851}</style>
<h1>기존 18092 서버 준비 완료</h1><p>기존 계정·펫·진화 모델·기록을 그대로 사용합니다. Unity 설정에서 아래 값을 사용하세요. 입력칸을 누르면 전체 선택됩니다.</p>'''
    document += field('API 주소', base) + field('사용자 토큰', token) + field('기존 펫 ID', selected)
    document += '<p>이 페이지에는 인증 정보가 있습니다. 파일을 공유하지 마세요.</p><p>다음에도 Start-HealthMon.cmd 하나로 시작합니다.</p></html>'
    path = RUNTIME / 'local-server-connection.html'
    path.write_text(document, encoding='utf-8')
    # A local-only handoff for editor verification; no credential is printed.
    (RUNTIME / 'native-runtime-ready.json').write_text(json.dumps({
        'base_url': base, 'owner_id': identity['owner_id'], 'pet_id': selected,
        'server_instance_id': profile['environment']['SERVER_INSTANCE_ID'], 'ready': True}), encoding='utf-8')
    print('Ready: ' + base + ' (original account, database and models)', flush=True)
    print('Unity connection guide: ' + str(path), flush=True)
    if open_browser:
        webbrowser.open(path.as_uri())


def start(profile, open_browser):
    ensure_postgres(profile)
    ensure_ai(profile)
    if not same_server(profile):
        spawn([str(profile['python']), '-B', '-m', 'Server.local_probe.native_runtime', 'api', '--profile', str(profile['path'])], 'native-api')
        deadline = time.monotonic() + 40
        while not same_server(profile):
            if time.monotonic() > deadline:
                raise RuntimeError('The original API did not become ready; inspect .runtime/native-api.stderr.log')
            time.sleep(1)
    write_guide(profile, open_browser)


def stop(profile):
    status_path = RUNTIME / 'local-services-status.json'
    if status_path.exists():
        status = json.loads(status_path.read_text())
        if status.get('phase') == 'generating_3d' and time.time() - status.get('updated_at', 0) < 15:
            raise RuntimeError('A generation is active. Finish it before stopping the existing server')
    (RUNTIME / 'local-services.stop').touch()
    # Match the exact absolute profile in our own module command. Never kill
    # arbitrary Python processes or another checkout's API.
    environment = dict(os.environ, HEALTHMON_NATIVE_PROFILE_PATH=str(profile['path']))
    command = "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*-m Server.local_probe.native_runtime api *' -and $_.CommandLine.Contains($env:HEALTHMON_NATIVE_PROFILE_PATH) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], env=environment, check=True)
    subprocess.run([str(profile['pg_ctl']), '-D', str(profile['pg_data']), '-m', 'fast', '-w', '-t', '30', 'stop'], check=True)
    print('Original server stopped. Database, account, pets and models are preserved.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'api'])
    parser.add_argument('--profile', default='.runtime/native-server.json')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    profile = load_profile(args.profile)
    if args.action == 'api':
        os.environ.update(profile['environment'])
        # Previously the operator manually pumped this queue. The same server
        # now handles only requests actually enqueued by its authenticated clients.
        os.environ['WORKER_ENABLED'] = 'true' if profile.get('enable_worker', False) else profile['environment'].get('WORKER_ENABLED', 'false')
        import uvicorn
        uvicorn.run('Server.healthmon.app:create_app', factory=True, host='127.0.0.1', port=int(profile['api_port']), access_log=False)
    elif args.action == 'start':
        start(profile, not args.no_open)
    else:
        stop(profile)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Configuration paths and credentials stay in local logs/files.
        print('Existing server startup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
