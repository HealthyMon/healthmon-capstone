import json
from pathlib import Path

import pytest

from Server.local_probe import local_services as services


def test_interpreter_path_preserves_virtualenv_symlink(tmp_path, monkeypatch):
    import os
    import sys
    if os.name == 'nt':
        pytest.skip('POSIX virtualenv symlinks are verified in the portable Linux image')
    launcher = tmp_path / 'venv/bin/python'
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(sys.executable)
    monkeypatch.setattr(services, 'ROOT', tmp_path)
    assert services.interpreter_path('venv/bin/python') == launcher
    assert launcher.resolve() != launcher
    commands = services.service_commands(dict(python=launcher, llm_python=launcher,
        llm_config='llm.json', vision_config='vision.json', path='services.json', pose_python=launcher))
    assert all(command[0] == str(launcher) for _, command in commands.values())


@pytest.mark.parametrize('body,expected', [
    ({'service': 'healthmon-pose', 'status': 'idle'}, True),
    ({'service': 'healthmon-pose', 'status': 'ready'}, True),
    ({'service': 'healthmon-pose', 'status': 'failed'}, False),
    ({'service': 'other', 'status': 'idle'}, False),
    ({'ready': False, 'status': 'ok'}, False),
])
def test_health_accepts_only_pose_lazy_loading_contract(monkeypatch, body, expected):
    import httpx
    client_type = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    monkeypatch.setattr(services.httpx, 'Client', lambda **kwargs: client_type(transport=transport, **kwargs))
    assert services.health(18095) is expected


@pytest.mark.parametrize('busy_attempts', [2, 5])
def test_status_reader_lock_cannot_kill_heartbeat(tmp_path, monkeypatch, busy_attempts):
    status = tmp_path / 'status.json'
    status.write_text('{"phase":"ready"}')
    monkeypatch.setattr(services, 'STATUS', status)
    monkeypatch.setattr(services.time, 'sleep', lambda seconds: None)
    original = Path.replace
    attempts = []
    def replace(path, target):
        attempts.append(1)
        if len(attempts) <= busy_attempts:
            raise PermissionError('Windows reader has no delete sharing')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    assert services.write_status('generating_3d') is (busy_attempts < 5)
    if busy_attempts == 5:
        assert json.loads(status.read_text())['phase'] == 'ready'
        assert services.write_status('generating_3d') is True
    assert json.loads(status.read_text())['phase'] == 'generating_3d'


@pytest.mark.parametrize('fails', [False, True])
def test_generation_releases_dialogue_gpu_and_restores_it_even_on_failure(fails):
    events = []
    def generate():
        events.append('generate')
        if fails:
            raise RuntimeError('controlled generation failure')
        return 'published'
    call = lambda: services.generate_queued(generate, lambda: events.append('restore'), lambda: events.append('release'))
    if fails:
        with pytest.raises(RuntimeError):
            call()
    else:
        assert call() == 'published'
    assert events == ['release', 'generate', 'restore']


def test_local_ai_configuration_preserves_accounts_database_and_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(services, 'ROOT', tmp_path)
    runtime = tmp_path / '.runtime'
    runtime.mkdir()
    monkeypatch.setattr(services, 'RUNTIME', runtime)
    original = 'APP_ENV=test\nAI_MODE=disabled\nDEV_TOKENS={"existing-token":"owner-a"}\nPOSTGRES_PASSWORD=existing-db\nSERVER_INSTANCE_ID=existing-instance\n'
    path = tmp_path / '.env'
    path.write_text(original, encoding='utf-8')
    services.configure_environment({'token': 'server-only-token'})
    first = path.read_text()
    for line in original.splitlines():
        if not line.startswith('AI_MODE='):
            assert line in first
    assert 'AI_MODE=remote' in first
    assert 'AI_BASE_URL=http://host.docker.internal:18090' in first
    assert 'AI_SERVER_TOKEN=server-only-token' in first
    services.configure_environment({'token': 'server-only-token'})
    assert path.read_text() == first
    assert len(list(runtime.glob('before-local-services-*.env'))) == 1


def test_existing_relative_configuration_process_is_owned_but_other_checkout_is_not(monkeypatch, tmp_path):
    class Process:
        def __init__(self, name, directory):
            self.info = {'pid': name, 'cmdline': ['python.exe', '-B', '-m', 'Server.local_probe.gpu_gateway', '--config', '.runtime/private.json']}
            self.directory = directory
        def cwd(self):
            return str(self.directory)
    expected = tmp_path / 'selected'
    ours, other = Process(1, expected), Process(2, tmp_path / 'other')
    monkeypatch.setattr(services.psutil, 'process_iter', lambda *_: [ours, other])
    command = ['python.exe', '-B', '-m', 'Server.local_probe.gpu_gateway', '--config', str((expected / '.runtime/private.json').resolve())]
    assert services.matching_processes(command) == [ours]


def test_stopping_during_generation_finishes_it_without_reloading_gpu():
    events = []
    result = services.generate_queued(lambda: events.append('published') or 'same-job',
                                     lambda: pytest.fail('Reloaded GPU while stopping'),
                                     lambda: events.append('release'), lambda: True)
    assert result == 'same-job' and events == ['release', 'published']


def test_connection_setup_does_not_require_model_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(services, 'ROOT', tmp_path)
    monkeypatch.setattr(services, 'RUNTIME', tmp_path)
    for name in ('llm', 'vision'):
        (tmp_path / (name + '.json')).write_text('{"environment":"test","server_token":"fixture"}')
    path = tmp_path / 'services.json'
    path.write_text('{"llm_config":"llm.json","vision_config":"vision.json","python":"missing-python"}')
    assert services.connection_configuration(path)['token'] == 'fixture'
    with pytest.raises(ValueError, match='python'):
        services.configuration(path)


def test_ai_toggle_rejects_unprepared_connection_without_rewriting_env(tmp_path, monkeypatch):
    monkeypatch.setattr(services, 'ROOT', tmp_path)
    path = tmp_path / '.env'
    original = 'APP_ENV=test\nAI_MODE=disabled\nDEV_TOKENS={"fixture":"owner"}\n'
    path.write_text(original)
    with pytest.raises(ValueError, match=r'Start-HealthMon\.cmd -Target Backend'):
        services.check_backend_connection({'token': 'private-fixture'})
    assert path.read_text() == original


def test_duplicate_supervisor_cannot_clear_stop_or_spawn_jobs(tmp_path, monkeypatch):
    from filelock import FileLock
    monkeypatch.setattr(services, 'RUNTIME', tmp_path)
    monkeypatch.setattr(services, 'STOP', tmp_path / 'stop')
    services.STOP.touch()
    monkeypatch.setattr(services, 'service_commands', lambda _: {})
    monkeypatch.setattr(services.subprocess, 'Popen', lambda *a, **k: pytest.fail('Duplicate process'))
    with FileLock(str(tmp_path / 'local-services.lock')):
        services.supervise({})
    assert services.STOP.exists()
