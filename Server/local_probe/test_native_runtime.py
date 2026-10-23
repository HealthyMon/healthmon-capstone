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
    assert calls == ['original database', 'original AI', ('guide', False)]


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
    environment = {'AI_SERVER_TOKEN': 'test-only-service-token', 'DATABASE_URL': 'original-db', 'SERVER_INSTANCE_ID': 'original-instance'}
    runtime.ensure_ai({'ai_config': current, 'evolution_config': original, 'environment': environment})
    assert json.loads(current.read_text())['evolution_config'] == str(original)
    assert len(launches) == 1
    assert environment['DATABASE_URL'] == 'original-db' and environment['SERVER_INSTANCE_ID'] == 'original-instance'
    assert len(list(tmp_path.glob('before-native-runtime-*.json'))) == 1
