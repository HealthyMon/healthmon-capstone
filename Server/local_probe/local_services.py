"""One-click local AI lifecycle; model files and machine configuration stay private."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime'
STATUS = RUNTIME / 'local-services-status.json'
STOP = RUNTIME / 'local-services.stop'


def resolve(value):
    path = Path(value)
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def configuration(path):
    path = resolve(path)
    if not path.is_relative_to(RUNTIME):
        raise ValueError('Local service configuration must stay in this project .runtime')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    for name in ('python', 'llm_python', 'llm_config', 'vision_config', 'evolution_config'):
        config[name] = resolve(config[name])
        if not config[name].is_file():
            raise ValueError('Missing local AI prerequisite: ' + name)
    llm = json.loads(config['llm_config'].read_text(encoding='utf-8-sig'))
    vision = json.loads(config['vision_config'].read_text(encoding='utf-8-sig'))
    if llm.get('environment') != 'test' or vision.get('environment') != 'test':
        raise ValueError('Local AI requires the test environment')
    if not llm.get('server_token') or llm['server_token'] != vision.get('server_token'):
        raise ValueError('LLM and Vision must use the same private server token')
    for name in ('model_path', 'embedding_path'):
        if not Path(llm[name]).is_dir():
            raise ValueError('Missing existing local model: ' + name)
    if not Path(vision['vision_python']).is_file() or not Path(vision['vision_assets']).is_dir():
        raise ValueError('The Vision environment and trained weights must be prepared first')
    evolution = json.loads(config['evolution_config'].read_text(encoding='utf-8-sig'))
    for name in ('work_root', 'model_root', 'vendor_root'):
        evolution[name] = resolve(evolution[name])
        if name != 'work_root' and not evolution[name].is_dir():
            raise ValueError('Missing existing 3D prerequisite: ' + name)
    config.update(token=llm['server_token'], evolution=evolution)
    return config


def configure_environment(config):
    from dotenv import dotenv_values
    path = ROOT / '.env'
    current = dotenv_values(path)
    if current.get('APP_ENV') != 'test':
        raise ValueError('The local AI launcher requires APP_ENV=test')
    updates = {'AI_MODE': 'remote', 'AI_BASE_URL': 'http://host.docker.internal:18090',
               'AI_SERVER_TOKEN': config['token'], 'ALLOW_HTTP_AI': 'true', 'AI_TIMEOUT_SECONDS': '180'}
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    changed = []
    for line in lines:
        key = line.partition('=')[0]
        changed.append(key + '=' + updates.pop(key) if key in updates else line)
    changed.extend(key + '=' + value for key, value in updates.items())
    content = '\n'.join(changed) + '\n'
    if path.read_text(encoding='utf-8-sig') != content:
        backup = RUNTIME / ('before-local-services-' + str(time.time_ns()) + '.env')
        backup.write_bytes(path.read_bytes())
        path.write_text(content, encoding='utf-8')


def health(port):
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            response = client.get(f'http://127.0.0.1:{port}/health')
            response.raise_for_status()
            body = response.json()
            return body.get('ready', body.get('status') == 'ok') is True
    except (httpx.HTTPError, ValueError):
        return False


def write_status(phase, **extra):
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps({'pid': os.getpid(), 'phase': phase, 'updated_at': time.time(), **extra}), encoding='utf-8')
    temporary.replace(STATUS)


def matching_processes(command):
    """Identify only this checkout's exact module and private configuration."""
    expected = command[1:]
    matches = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            actual = list((process.info['cmdline'] or [])[1:])
            if len(actual) != len(expected) or actual[:4] != expected[:4]:
                continue
            for flag in ('--config', '--key-config'):
                if flag in actual:
                    index = actual.index(flag) + 1
                    candidate = Path(actual[index])
                    actual[index] = str((Path(process.cwd()) / candidate).resolve() if not candidate.is_absolute() else candidate.resolve())
            if actual == expected:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def stop_matching(command):
    processes = matching_processes(command)
    # Windows virtualenv launchers can have a child with the same arguments.
    for process in reversed(processes):
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=10)
    for process in alive:
        process.kill()


def service_commands(config):
    cpu, gpu = str(config['python']), str(config['llm_python'])
    llm, vision = str(config['llm_config']), str(config['vision_config'])
    return {
        'router': (18090, [cpu, '-B', '-m', 'Server.local_probe.router', '--key-config', llm]),
        'vision': (18094, [cpu, '-B', '-m', 'Server.local_probe.vision_gateway', '--config', vision]),
        'llm': (18091, [gpu, '-B', '-m', 'Server.local_probe.gpu_gateway', '--config', llm]),
        'evolution': (18093, [cpu, '-B', '-m', 'Server.local_probe.local_services',
                               'evolution', '--config', str(config['path'])]),
    }


def generate_queued(generate, start_llm, stop_llm):
    """One GPU: release the dialogue model before 3D and always restore it."""
    stop_llm()
    try:
        return generate()
    finally:
        start_llm()


def supervise(config):
    from filelock import FileLock, Timeout
    commands = service_commands(config)
    lock = FileLock(str(RUNTIME / 'local-services.lock'), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        return
    STOP.unlink(missing_ok=True)
    owned = set()
    with ExitStack() as files:
        files.callback(lock.release)
        def start(name):
            port, command = commands[name]
            existing = matching_processes(command)
            available = health(port)
            if available and not existing:
                raise RuntimeError('The ' + name + ' port belongs to another service; it was left untouched')
            owned.add(name)
            if not available:
                if existing:
                    return  # Still warming up; never start a second GPU model.
                output = files.enter_context((RUNTIME / ('local-' + name + '.stdout.log')).open('a', encoding='utf-8'))
                errors = files.enter_context((RUNTIME / ('local-' + name + '.stderr.log')).open('a', encoding='utf-8'))
                subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=errors,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

        def stop(name):
            # A healthy existing gateway is adopted only when its exact private
            # config belongs to this checkout; unrelated listeners are untouched.
            stop_matching(commands[name][1])

        try:
            write_status('starting')
            for name in commands:
                start(name)
            deadline = time.monotonic() + 300
            while not STOP.exists():
                ready = {name: health(port) for name, (port, _) in commands.items()}
                write_status('ready' if all(ready.values()) else 'starting', services=ready)
                if all(ready.values()):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('AI startup timed out; inspect .runtime/local-*.stderr.log')
                time.sleep(2)
            if STOP.exists():
                return
            from Ai.Generation3D.runtime.common_gateway.service import Settings
            from Ai.Generation3D.runtime.common_gateway.store import Store
            from Ai.Generation3D.runtime.common_gateway.worker import run_once
            evolution = config['evolution']
            settings = Settings(evolution['work_root'], config['token'])
            store = Store(settings.work_root)
            while not STOP.exists():
                with store.connect() as connection:
                    pending = connection.execute("SELECT id FROM jobs WHERE status='queued' OR (status='running' AND lease_until<?) LIMIT 1", (time.time(),)).fetchone()
                if pending:
                    write_status('generating_3d', services={'router': True, 'vision': True, 'llm': False, 'evolution': True})
                    finished = threading.Event()
                    def heartbeat():
                        while not finished.wait(2):
                            write_status('generating_3d', services={'router': True, 'vision': True, 'llm': False, 'evolution': True})
                    pulse = threading.Thread(target=heartbeat, daemon=True)
                    pulse.start()
                    try:
                        generate_queued(
                            lambda: run_once(settings, store, evolution['model_root'], evolution['vendor_root'], allow_gpu=True),
                            lambda: start('llm'), lambda: stop('llm'))
                    finally:
                        finished.set()
                        pulse.join(timeout=3)
                else:
                    ready = {name: health(port) for name, (port, _) in commands.items()}
                    for name, available in ready.items():
                        if not available:
                            start(name)
                    write_status('ready' if all(ready.values()) else 'starting', services=ready)
                time.sleep(2)
        except Exception as error:
            write_status('failed', error=type(error).__name__, message=str(error)[:180])
            raise
        finally:
            for name in reversed(tuple(commands)):
                if name in owned:
                    stop(name)
            if STOP.exists():
                write_status('stopped')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['configure', 'run', 'evolution', 'stop'])
    parser.add_argument('--config', default='.runtime/local-services.json')
    args = parser.parse_args()
    if args.action == 'stop':
        STOP.touch()
        print('Local AI stop requested. An active 3D generation finishes before shutdown.')
        return
    config = configuration(args.config)
    config['path'] = resolve(args.config)
    if args.action == 'configure':
        subprocess.run(['docker', 'image', 'inspect', 'healthmon-3d:3090'], stdout=subprocess.DEVNULL, check=True)
        configure_environment(config)
        print('Local dialogue, Vision and 3D settings verified.')
    elif args.action == 'evolution':
        import uvicorn
        from Ai.Generation3D.runtime.common_gateway.service import Settings, create_app
        uvicorn.run(create_app(Settings(config['evolution']['work_root'], config['token'])),
                    host='127.0.0.1', port=18093, access_log=False)
    else:
        supervise(config)


if __name__ == '__main__':
    main()
