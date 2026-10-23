import json
from pathlib import Path

import pytest

from Server.local_probe import local_services as services


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
