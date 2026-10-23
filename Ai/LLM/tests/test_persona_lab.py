"""API/isolation tests with a declared dummy runtime; these are not model evaluations."""
import copy
import hashlib
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.persona_lab import create_app, simulate, Simulation
from src.persona_runtime import PersonaRuntime
from src.persona_store import LabStore

ORIGIN = 'http://127.0.0.1:8001'
HEADERS = {'Origin': ORIGIN, 'X-Persona-Lab': '1'}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('PERSONA_LAB_ENABLED', '1')
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('NODE_ENV', raising=False)
    store = LabStore(tmp_path / 'isolated.sqlite3')
    runtime = PersonaRuntime()
    monkeypatch.setattr(runtime, '_load', lambda: pytest.fail('Unit tests must never claim actual model execution'))
    # Any accidental legacy DB connection is an immediate failure.
    import src.db
    monkeypatch.setattr(src.db, 'connect', lambda: pytest.fail('Legacy DB must not be connected'))
    application = create_app(runtime, store)
    with TestClient(application, base_url=ORIGIN, client=('127.0.0.1', 30000)) as client:
        yield client, store


def post(client, path, body):
    result = client.post(path, json=body, headers=HEADERS)
    assert result.status_code == 200, result.text
    return result.json()


def test_preview_ab_same_input_seed_parameters_and_no_store(lab):
    client, store = lab
    result = post(client, '/api/preview', {'mode': 'dummy', 'text': '오늘 무슨 이야기를 해볼까?', 'repetitions': 5,
        'a': {'personality': dict.fromkeys(('curiosity','affection','activity','confidence'), 20)},
        'b': {'personality': dict.fromkeys(('curiosity','affection','activity','confidence'), 80)}})
    assert not store.path.exists()
    assert len(result['results']) == 5
    assert [row['seed'] for row in result['results']] == list(range(20261001, 20261006))
    assert result['contexts']['a']['memories'] == result['contexts']['b']['memories']
    assert result['contexts']['a']['style_profile'] != result['contexts']['b']['style_profile']
    assert all(not row['a']['is_real_model'] and not row['b']['is_real_model'] for row in result['results'])
    a_input = json.loads(result['prompts']['a'][1]['content'])['user_text']
    b_input = json.loads(result['prompts']['b'][1]['content'])['user_text']
    assert a_input == b_input == result['user_text']


def test_character_voice_changes_prompt_without_growth_or_quest_changes(lab):
    client, store = lab
    result = post(client, '/api/preview', {'mode':'dummy', 'text':'소파랑 한몸이 됐어. 한마디 해 줘.',
                                         'a':{}, 'b':{'character_voice':'sassy'}})
    a, b = result['contexts']['a'], result['contexts']['b']
    for key in ('personality', 'short_term', 'stages', 'candidates', 'memories'):
        assert a[key] == b[key]
    assert result['prompts']['a'][0]['content'] != result['prompts']['b'][0]['content']
    assert b['character_voice'] == 'sassy'
    assert not store.path.exists()
    default_sim = post(client, '/api/simulate', {'days':7, 'scenario':'steady_exercise_success'})
    sassy_sim = post(client, '/api/simulate', {'days':7, 'scenario':'steady_exercise_success',
                                            'initial':{'character_voice':'sassy'}})
    assert default_sim == sassy_sim


def test_dry_run_no_store_and_reproducibility(lab):
    client, store = lab
    body = {'scenario': 'steady_exercise_success', 'days': 30}
    first = post(client, '/api/simulate', body)
    second = post(client, '/api/simulate', body)
    assert first == second and first['dry_run'] and not store.path.exists()
    assert len(first['timeline']) == 31 and first['ledger']
    for row in first['ledger_summary']:
        assert row['before'] + row['total_delta'] == pytest.approx(row['after'])
        assert sum(reason['final_delta'] for reason in row['reasons']) == pytest.approx(row['total_delta'])


def test_preview_dryrun_preserve_existing_test_database(lab):
    client, store = lab
    post(client, '/api/characters', {})
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    post(client, '/api/preview', {'mode': 'dummy'})
    post(client, '/api/simulate', {'days': 7})
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('env,value', [('APP_ENV','production'),('APP_ENV','staging'),('ENVIRONMENT','production'),('NODE_ENV','production'),('PERSONA_LAB_ENABLED','0')])
def test_production_disabled_all_routes(lab, monkeypatch, env, value):
    client, _ = lab
    monkeypatch.setenv(env, value)
    for path in ('/', '/lab/app.js', '/api/health', '/api/config'):
        assert client.get(path).status_code == 404
    assert client.post('/api/preview', json={'mode':'dummy'}, headers=HEADERS).status_code == 404


def test_origin_and_host(lab):
    client, _ = lab
    assert client.post('/api/preview', json={'mode':'dummy'}).status_code == 403
    assert client.post('/api/preview', json={}, headers={**HEADERS,'Origin':'http://attacker.invalid'}).status_code == 403
    assert client.get('/', headers={'Host':'attacker.invalid'}).status_code == 403
    assert client.get('/').status_code == 200


def test_commit_only_separate_test_id_and_idempotence(lab):
    client, store = lab
    invalid = client.post('/api/simulate', json={'days':1,'commit':True,'character_id':'real-user-pet'}, headers=HEADERS)
    assert invalid.status_code == 422 and not store.path.exists()
    character = post(client, '/api/characters', {})['character_id']
    body = {'scenario':'steady_exercise_success','days':1,'commit':True,'character_id':character}
    first = post(client,'/api/simulate',body)
    second = post(client,'/api/simulate',body)
    assert first['commit_result']['inserted'] > 0 and second['commit_result']['inserted'] == 0
    assert first['commit_result']['state'] == second['commit_result']['state']
    assert first['commit_result']['state']['personality'] == first['timeline'][-1]['state']['personality']
    assert first['commit_result']['state']['as_of'] == first['timeline'][-1]['state']['as_of']
    assert all(x['character_id'] == character for x in store.read(character)['events'])


def test_commit_conflict_atomic_and_source_spoof_rejected(lab):
    client, store = lab
    character = post(client, '/api/characters', {})['character_id']
    body={'scenario':'steady_exercise_success','days':1,'commit':True,'character_id':character}
    result=post(client,'/api/simulate',body)
    event=copy.deepcopy(result['events'][0])
    event['payload']['forged']=True
    response=client.post(f'/api/characters/{character}/events',json={'events':[event],'now':result['timeline'][-1]['date']},headers=HEADERS)
    assert response.status_code==422
    event['source']='backend'
    response=client.post('/api/preview',json={'events':[event],'mode':'dummy'},headers=HEADERS)
    assert response.status_code==422


def test_invalid_range_and_timezone(lab):
    client,_=lab
    for body in ({'mode':'dummy','a':{'personality':{'activity':101}}}, {'mode':'dummy','now':'2026-10-01T00:00:00'}, {'mode':'dummy','repetitions':99}):
        assert client.post('/api/preview',json=body,headers=HEADERS).status_code==422


def test_simulation_rejects_events_outside_window(lab):
    client,store=lab
    event={'event_id':'too-old','idempotency_key':'too-old','user_id':'persona-lab','character_id':'lab-preview',
           'event_type':'exercise_recorded','occurred_at':'2026-09-30T23:59:00+09:00','source':'simulation',
           'verification_status':'verified','confidence':1,'payload':{'exercise_type':'walk','steps':200}}
    response=client.post('/api/simulate',json={'days':1,'events':[event]},headers=HEADERS)
    assert response.status_code==422 and not store.path.exists()


def test_simulated_day_shortterm_all_accepted_by_preview(lab):
    client,_=lab
    result=post(client,'/api/simulate',{'scenario':'steady_food_low_exercise','days':7})
    state=result['timeline'][-1]['state']
    subset={key:state[key] for key in ('personality','short_term','stages')}
    post(client,'/api/preview',{'mode':'dummy','a':subset,'events_a':result['events'],'now':result['timeline'][-1]['date']})
