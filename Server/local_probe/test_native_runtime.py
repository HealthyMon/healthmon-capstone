"""Existing account, model lineage and restart safety for the desktop launcher."""
import json
from pathlib import Path
import time

import pytest

from Server.local_probe import native_runtime as runtime


def test_start_reuses_the_original_server_without_creating_a_new_process(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, 'ensure_postgres', lambda p: calls.append('original database'))
    monkeypatch.setattr(runtime, 'ensure_ai', lambda p: calls.append('original AI'))
    monkeypatch.setattr(runtime, 'same_server', lambda p: True)
    monkeypatch.setattr(runtime, 'write_guide', lambda p, opened: calls.append(('guide', opened)))
    monkeypatch.setattr(runtime, 'spawn', lambda *args: pytest.fail('A second API was launched'))
    runtime.start({}, False)
    assert calls == ['original database', ('guide', False), 'original AI']


def test_another_server_on_the_selected_port_is_never_adopted(monkeypatch):
    monkeypatch.setattr(runtime, 'request', lambda *args: {'server_instance_id': 'different'})
    with pytest.raises(RuntimeError, match='different server'):
        runtime.same_server({'base_url': 'http://127.0.0.1:18092', 'environment': {'SERVER_INSTANCE_ID': 'original'}})


def test_missing_original_pet_does_not_silently_select_a_different_pet(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    session = tmp_path / 'session.json'
    session.write_text(json.dumps({'bearer_token': 'test-only-token'}))
    monkeypatch.setattr(runtime, 'request', lambda base, path, token: {'owner_id': 'owner'} if path == '/identity' else {'pets': [{'pet_id': 'another'}]})
    with pytest.raises(RuntimeError, match='original selected pet'):
        runtime.write_guide({'session': session, 'base_url': 'http://127.0.0.1:18092', 'pet_id': 'original'}, False)
    assert not (tmp_path / 'native-runtime-ready.json').exists()


def test_original_account_connection_guide_contains_the_same_pet(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    session = tmp_path / 'session.json'
    session.write_text(json.dumps({'bearer_token': 'test-only-token'}))
    monkeypatch.setattr(runtime, 'request', lambda base, path, token: {'owner_id': 'owner'} if path == '/identity' else {'pets': [{'pet_id': 'original'}]})
    runtime.write_guide({'session': session, 'base_url': 'http://127.0.0.1:18092', 'pet_id': 'original', 'environment': {'SERVER_INSTANCE_ID': 'same-instance'}}, False)
    result = json.loads((tmp_path / 'native-runtime-ready.json').read_text())
    assert result == {'base_url': 'http://127.0.0.1:18092', 'owner_id': 'owner', 'pet_id': 'original', 'server_instance_id': 'same-instance', 'ready': True}
    assert 'test-only-token' in (tmp_path / 'local-server-connection.html').read_text(encoding='utf-8')
    assert 'test-only-token' not in capsys.readouterr().out


def test_existing_evolution_journal_is_restored_without_rewriting_api_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    llm = tmp_path / 'llm.json'
    llm.write_text(json.dumps({'server_token': 'test-only-service-token'}))
    current = tmp_path / 'services.json'
    current.write_text(json.dumps({'python': 'existing-python', 'llm_config': str(llm), 'evolution_config': str(tmp_path / 'new-journal.json')}))
    original = tmp_path / 'original-journal.json'
    original.write_text('{}')
    status = tmp_path / 'local-services-status.json'
    status.write_text(json.dumps({'phase': 'stopped', 'updated_at': time.time()}))
    launches = []
    class Process:
        def poll(self): return None
    def spawn(command, name):
        launches.append(command)
        status.write_text(json.dumps({'phase': 'ready', 'updated_at': time.time()}))
        return Process()
    monkeypatch.setattr(runtime, 'spawn', spawn)
    environment = {'AI_MODE': 'remote', 'AI_SERVER_TOKEN': 'test-only-service-token', 'DATABASE_URL': 'original-db', 'SERVER_INSTANCE_ID': 'original-instance'}
    runtime.ensure_ai({'ai_config': current, 'evolution_config': original, 'environment': environment})
    assert json.loads(current.read_text())['evolution_config'] == str(original)
    assert len(launches) == 1
    assert environment['DATABASE_URL'] == 'original-db' and environment['SERVER_INSTANCE_ID'] == 'original-instance'
    assert len(list(tmp_path.glob('before-native-runtime-*.json'))) == 1


def test_backend_start_and_stop_never_touch_ai(tmp_path, monkeypatch):
    from Server.local_probe import local_services
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    monkeypatch.setattr(runtime, 'ensure_ai', lambda _: pytest.fail('Backend launched AI'))
    monkeypatch.setattr(runtime, 'ensure_postgres', lambda _: None)
    monkeypatch.setattr(runtime, 'same_server', lambda _: True)
    monkeypatch.setattr(runtime, 'write_guide', lambda *_: None)
    runtime.start({}, False, 'backend')
    commands = []
    monkeypatch.setattr(local_services, 'stop_matching', lambda c: commands.append(c))
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: type('Result', (), {'returncode': 3})())
    runtime.stop({'python': 'python', 'path': tmp_path / 'profile.json', 'pg_ctl': 'pg_ctl', 'pg_data': tmp_path}, 'backend')
    assert len(commands) == 1 and 'Server.local_probe.native_runtime' in commands[0]
    assert not (tmp_path / 'local-services.stop').exists()


def test_ai_start_and_stop_do_not_require_or_stop_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    called = []
    monkeypatch.setattr(runtime, 'ensure_ai', lambda _: called.append('ai'))
    monkeypatch.setattr(runtime, 'ensure_postgres', lambda _: pytest.fail('AI launched database'))
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: pytest.fail('AI stopped database/API'))
    runtime.start({}, False, 'ai')
    runtime.stop({}, 'ai')
    assert called == ['ai'] and (tmp_path / 'local-services.stop').exists()


def test_backend_profile_does_not_require_ai_files(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path)
    environment = tmp_path / 'env.json'
    environment.write_text('{"APP_ENV":"test"}')
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps({**{k: str(environment) for k in ('python', 'pg_ctl', 'pg_data', 'api_env', 'session')},
                                   'ai_config': 'missing.json', 'evolution_config': 'missing.json'}))
    assert runtime.load_profile(profile, 'backend')['environment']['APP_ENV'] == 'test'
    with pytest.raises(ValueError, match='ai_config'):
        runtime.load_profile(profile, 'ai')


@pytest.mark.parametrize('migration_fails', [False, True])
def test_native_api_applies_schema_before_serving_and_refuses_failed_migration(monkeypatch, migration_fails):
    import sys
    import uvicorn
    from Server.healthmon.config import Settings
    from Server.healthmon.db import Database
    calls = []
    monkeypatch.setattr(sys, 'argv', ['native_runtime', 'api'])
    monkeypatch.setenv('WORKER_ENABLED', 'false')
    monkeypatch.setattr(runtime, 'load_profile', lambda *_: {'environment': {}, 'api_port': 18092})
    monkeypatch.setattr(Settings, 'from_env', lambda: None)
    def migrate(self):
        calls.append('migration')
        if migration_fails:
            raise RuntimeError('migration not ready')
    monkeypatch.setattr(Database, 'migrate', migrate)
    monkeypatch.setattr(uvicorn, 'run', lambda *a, **k: calls.append('api'))
    if migration_fails:
        with pytest.raises(RuntimeError, match='migration not ready'):
            runtime.main()
        assert calls == ['migration']
    else:
        runtime.main()
        assert calls == ['migration', 'api']
